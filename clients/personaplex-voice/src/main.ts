/**
 * ORBIT PersonaPlex Voice Client
 *
 * A simple full-duplex voice client for the ORBIT PersonaPlex adapter.
 * Uses Web Audio API for microphone capture and audio playback,
 * and WebSocket for real-time bidirectional audio streaming.
 *
 * Protocol (ORBIT PersonaPlex JSON):
 * - Client sends: {"type": "audio_chunk", "data": "<base64_pcm>", "format": "pcm"}
 * - Server sends: {"type": "audio_chunk", "data": "<base64_pcm>", "format": "pcm", ...}
 * - Server sends: {"type": "transcription", "text": "...", "partial": true}
 */

// ============================================================================
// Types
// ============================================================================

interface OrbitMessage {
  type: string;
  [key: string]: unknown;
}

interface ConnectedMessage extends OrbitMessage {
  type: 'connected';
  adapter: string;
  session_id: string;
  mode: string;
  audio_format: string;
  sample_rate: number;
  capabilities: {
    full_duplex: boolean;
    interruption: boolean;
    backchannels: boolean;
  };
}

interface AudioChunkMessage extends OrbitMessage {
  type: 'audio_chunk';
  data: string;  // base64
  format: string;
  sample_rate: number;
  chunk_index: number;
}

interface TranscriptionMessage extends OrbitMessage {
  type: 'transcription';
  text: string;
  partial: boolean;
}

// ============================================================================
// Configuration
// ============================================================================

const SAMPLE_RATE = 24000;  // ORBIT PersonaPlex uses 24kHz
const CHUNK_DURATION_MS = 80;  // 80ms chunks
// ScriptProcessor requires power-of-2 buffer size, use 2048 (~85ms at 24kHz)
const CHUNK_SIZE = 2048;

// Environment variables (loaded from .env.local via Vite)
const ENV_CONFIG = {
  serverUrl: import.meta.env.VITE_ORBIT_SERVER_URL || 'ws://localhost:3000',
  adapterName: import.meta.env.VITE_ADAPTER_NAME || 'personaplex-assistant',
  apiKey: import.meta.env.VITE_API_KEY || 'personaplex',
  appTitle: import.meta.env.VITE_APP_TITLE || 'ORBIT PersonaPlex Voice'
};

// ============================================================================
// State
// ============================================================================

let audioContext: AudioContext | null = null;
let mediaStream: MediaStream | null = null;
let audioWorkletNode: AudioWorkletNode | null = null;
let socket: WebSocket | null = null;
let isConnected = false;
let userAnalyser: AnalyserNode | null = null;
let serverAnalyser: AnalyserNode | null = null;

// Audio playback buffer with scheduled playback for gapless audio
const audioQueue: Float32Array[] = [];
let isPlaying = false;
let nextPlayTime = 0;  // When to schedule the next chunk
let activeAudioSources: AudioBufferSourceNode[] = [];  // Track playing sources for interrupt

// Statistics
let framesSent = 0;
let framesReceived = 0;
let bytesReceived = 0;

// ============================================================================
// DOM Elements
// ============================================================================

const serverUrlInput = document.getElementById('serverUrl') as HTMLInputElement;
const adapterNameInput = document.getElementById('adapterName') as HTMLInputElement;
const apiKeyInput = document.getElementById('apiKey') as HTMLInputElement;
const connectBtn = document.getElementById('connectBtn') as HTMLButtonElement;
const interruptBtn = document.getElementById('interruptBtn') as HTMLButtonElement;
const statusDot = document.getElementById('statusDot') as HTMLDivElement;
const statusText = document.getElementById('statusText') as HTMLSpanElement;
const transcriptDiv = document.getElementById('transcript') as HTMLDivElement;
const statsDiv = document.getElementById('stats') as HTMLDivElement;
const userCanvas = document.getElementById('userCanvas') as HTMLCanvasElement;
const serverCanvas = document.getElementById('serverCanvas') as HTMLCanvasElement;

// ============================================================================
// UI Updates
// ============================================================================

function setStatus(status: 'disconnected' | 'connecting' | 'connected' | 'error', text: string) {
  statusDot.className = 'status-dot ' + status;
  statusText.textContent = text;

  if (status === 'connected') {
    connectBtn.textContent = 'Disconnect';
    connectBtn.classList.add('connected');
    interruptBtn.disabled = false;
  } else {
    connectBtn.textContent = 'Connect';
    connectBtn.classList.remove('connected');
    interruptBtn.disabled = true;
  }
}

function appendTranscript(text: string) {
  transcriptDiv.textContent += text;
  transcriptDiv.scrollTop = transcriptDiv.scrollHeight;
}

function clearTranscript() {
  transcriptDiv.textContent = '';
}

function updateStats() {
  statsDiv.textContent = `Sent: ${framesSent} frames | Received: ${framesReceived} frames | ${(bytesReceived / 1024).toFixed(1)} KB`;
}

// ============================================================================
// Audio Visualization
// ============================================================================

function drawVisualizer(canvas: HTMLCanvasElement, analyser: AnalyserNode | null, color: string) {
  const ctx = canvas.getContext('2d')!;
  const width = canvas.width;
  const height = canvas.height;
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(width, height) / 2 - 10;

  // Clear canvas
  ctx.clearRect(0, 0, width, height);

  let amplitude = 0;
  if (analyser) {
    const dataArray = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteTimeDomainData(dataArray);

    // Calculate RMS amplitude
    let sum = 0;
    for (let i = 0; i < dataArray.length; i++) {
      const val = (dataArray[i] - 128) / 128;
      sum += val * val;
    }
    amplitude = Math.sqrt(sum / dataArray.length);
  }

  // Draw circle with amplitude-based radius
  const dynamicRadius = radius * (0.3 + amplitude * 2);

  ctx.beginPath();
  ctx.arc(centerX, centerY, Math.min(dynamicRadius, radius), 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.globalAlpha = 0.3 + amplitude * 0.7;
  ctx.fill();
  ctx.globalAlpha = 1;

  // Draw outer ring
  ctx.beginPath();
  ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.stroke();
}

function animateVisualizers() {
  drawVisualizer(userCanvas, userAnalyser, '#76b900');
  drawVisualizer(serverCanvas, serverAnalyser, '#00d4ff');

  if (isConnected) {
    requestAnimationFrame(animateVisualizers);
  }
}

// ============================================================================
// Audio Capture (Microphone)
// ============================================================================

async function startAudioCapture() {
  try {
    // Create audio context
    audioContext = new AudioContext({ sampleRate: SAMPLE_RATE });

    // Load AudioWorklet module
    await audioContext.audioWorklet.addModule('/audio-processor.js');

    // Request microphone access
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: SAMPLE_RATE,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      }
    });

    // Create audio source from microphone
    const source = audioContext.createMediaStreamSource(mediaStream);

    // Create analyser for visualization
    userAnalyser = audioContext.createAnalyser();
    userAnalyser.fftSize = 256;
    source.connect(userAnalyser);

    // Create analyser for server audio visualization
    serverAnalyser = audioContext.createAnalyser();
    serverAnalyser.fftSize = 256;

    // Create AudioWorkletNode for capturing audio data
    // Runs in a separate audio thread for better performance
    audioWorkletNode = new AudioWorkletNode(audioContext, 'audio-capture-processor');

    // Handle audio data from the worklet
    audioWorkletNode.port.onmessage = (event) => {
      if (!isConnected || !socket || socket.readyState !== WebSocket.OPEN) return;

      if (event.data.type === 'audio') {
        const inputData = event.data.data as Float32Array;

        // Convert Float32 to base64
        const base64 = float32ToBase64(inputData);

        // Send audio chunk
        const message = {
          type: 'audio_chunk',
          data: base64,
          format: 'pcm'
        };

        socket.send(JSON.stringify(message));
        framesSent++;
        updateStats();
      }
    };

    source.connect(audioWorkletNode);
    // AudioWorklet doesn't need to connect to destination for capture-only

    return true;
  } catch (error) {
    setStatus('error', 'Microphone access denied');
    return false;
  }
}

function stopAudioCapture() {
  if (audioWorkletNode) {
    audioWorkletNode.disconnect();
    audioWorkletNode.port.close();
    audioWorkletNode = null;
  }

  if (mediaStream) {
    mediaStream.getTracks().forEach(track => track.stop());
    mediaStream = null;
  }

  userAnalyser = null;
  serverAnalyser = null;
}

// ============================================================================
// Audio Playback
// ============================================================================

// Minimum chunks to buffer before starting playback (reduces jitter)
const MIN_BUFFER_CHUNKS = 3;

function queueAudioForPlayback(pcmData: Float32Array) {
  // Skip empty audio chunks
  if (!pcmData || pcmData.length === 0) {
    return;
  }

  audioQueue.push(pcmData);

  // Start playback once we have enough buffered chunks
  if (!isPlaying && audioQueue.length >= MIN_BUFFER_CHUNKS) {
    playNextChunk();
  }
}

function stopAllAudio() {
  // Stop all active audio sources
  for (const source of activeAudioSources) {
    try {
      source.stop();
      source.disconnect();
    } catch (e) {
      // Source may have already ended
    }
  }
  activeAudioSources = [];
  audioQueue.length = 0;
  isPlaying = false;
  nextPlayTime = 0;
}

function playNextChunk() {
  if (audioQueue.length === 0 || !audioContext) {
    isPlaying = false;
    return;
  }

  isPlaying = true;
  const pcmData = audioQueue.shift()!;

  // Create buffer and source
  const buffer = audioContext.createBuffer(1, pcmData.length, SAMPLE_RATE);
  buffer.getChannelData(0).set(pcmData);

  const source = audioContext.createBufferSource();
  source.buffer = buffer;

  // Track this source for interrupt
  activeAudioSources.push(source);

  // Connect to server analyser for visualization
  if (serverAnalyser) {
    source.connect(serverAnalyser);
    serverAnalyser.connect(audioContext.destination);
  } else {
    source.connect(audioContext.destination);
  }

  // Schedule playback for gapless audio
  const currentTime = audioContext.currentTime;
  const startTime = Math.max(currentTime, nextPlayTime);

  // Calculate duration of this chunk
  const duration = pcmData.length / SAMPLE_RATE;
  nextPlayTime = startTime + duration;

  source.onended = () => {
    // Remove from active sources
    const index = activeAudioSources.indexOf(source);
    if (index > -1) {
      activeAudioSources.splice(index, 1);
    }

    // Continue playing if more chunks available
    if (audioQueue.length > 0) {
      playNextChunk();
    } else {
      isPlaying = false;
    }
  };

  source.start(startTime);
}

// ============================================================================
// WebSocket Connection
// ============================================================================

function connect() {
  const baseUrl = serverUrlInput.value.trim();
  const adapterName = adapterNameInput.value.trim();
  const apiKey = apiKeyInput.value.trim();

  if (!baseUrl || !adapterName) {
    setStatus('error', 'Please enter server URL and adapter name');
    return;
  }

  // Build WebSocket URL
  const wsUrl = `${baseUrl}/ws/voice/${adapterName}${apiKey ? `?api_key=${apiKey}` : ''}`;

  setStatus('connecting', 'Connecting...');

  socket = new WebSocket(wsUrl);

  socket.onopen = async () => {

    // Start audio capture after connection
    const captureStarted = await startAudioCapture();
    if (!captureStarted) {
      disconnect();
      return;
    }

    isConnected = true;
    clearTranscript();
    framesSent = 0;
    framesReceived = 0;
    bytesReceived = 0;
    nextPlayTime = 0;  // Reset scheduled playback timing
    updateStats();

    // Start visualizers
    requestAnimationFrame(animateVisualizers);
  };

  socket.onmessage = (event) => {
    try {
      const message: OrbitMessage = JSON.parse(event.data);
      handleMessage(message);
    } catch (error) {
      // Silently ignore parse errors
    }
  };

  socket.onclose = () => {
    handleDisconnect();
  };

  socket.onerror = () => {
    setStatus('error', 'Connection error');
  };
}

function disconnect() {
  if (socket) {
    // Send end message
    if (socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'end' }));
    }
    socket.close();
    socket = null;
  }

  handleDisconnect();
}

function handleDisconnect() {
  isConnected = false;
  stopAudioCapture();
  audioQueue.length = 0;
  isPlaying = false;

  if (audioContext) {
    audioContext.close();
    audioContext = null;
  }

  setStatus('disconnected', 'Disconnected');
}

function handleMessage(message: OrbitMessage) {
  switch (message.type) {
    case 'connected': {
      const connMsg = message as ConnectedMessage;
      setStatus('connected', `Connected (${connMsg.mode})`);
      break;
    }

    case 'audio_chunk': {
      const audioMsg = message as AudioChunkMessage;
      framesReceived++;
      bytesReceived += audioMsg.data.length * 0.75;  // Base64 overhead
      updateStats();

      // Decode base64 and queue for playback
      const pcmData = base64ToFloat32(audioMsg.data);
      queueAudioForPlayback(pcmData);
      break;
    }

    case 'transcription': {
      const txMsg = message as TranscriptionMessage;
      if (txMsg.text) {
        appendTranscript(txMsg.text);
      }
      break;
    }

    case 'interrupted': {
      stopAllAudio();
      appendTranscript('\n[interrupted]\n');
      break;
    }

    case 'pong': {
      // Heartbeat response
      break;
    }

    case 'error': {
      setStatus('error', `Error: ${message.message}`);
      break;
    }
  }
}

function sendInterrupt() {
  // Immediately stop local audio for responsive feel
  stopAllAudio();

  // Also notify server to stop PersonaPlex
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: 'interrupt' }));
  }
}

// ============================================================================
// Utility Functions
// ============================================================================

function float32ToBase64(float32Array: Float32Array): string {
  const bytes = new Uint8Array(float32Array.buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function base64ToFloat32(base64: string): Float32Array {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new Float32Array(bytes.buffer);
}

// ============================================================================
// Event Listeners
// ============================================================================

connectBtn.addEventListener('click', () => {
  if (isConnected) {
    disconnect();
  } else {
    connect();
  }
});

interruptBtn.addEventListener('click', () => {
  sendInterrupt();
});

// Keep connection alive with ping
setInterval(() => {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: 'ping' }));
  }
}, 5000);

// Initialize from environment variables
serverUrlInput.value = ENV_CONFIG.serverUrl;
adapterNameInput.value = ENV_CONFIG.adapterName;
apiKeyInput.value = ENV_CONFIG.apiKey;
document.title = ENV_CONFIG.appTitle;

// Update the h1 title if present
const titleElement = document.querySelector('h1');
if (titleElement) {
  titleElement.textContent = ENV_CONFIG.appTitle;
}

// Initialize visualizers with empty state
drawVisualizer(userCanvas, null, '#76b900');
drawVisualizer(serverCanvas, null, '#00d4ff');
