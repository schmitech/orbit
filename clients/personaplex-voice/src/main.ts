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

// ============================================================================
// Configuration
// ============================================================================

const SAMPLE_RATE = 24000;  // ORBIT PersonaPlex uses 24kHz

// Environment variables (loaded from .env.local via Vite)
const ENV_CONFIG = {
  serverUrl: import.meta.env.VITE_ORBIT_SERVER_URL || 'ws://localhost:3000',
  adapterName: import.meta.env.VITE_ADAPTER_NAME || 'personaplex-assistant',
  apiKey: import.meta.env.VITE_API_KEY || 'personaplex',
  appTitle: import.meta.env.VITE_APP_TITLE || 'ORBIT PersonaPlex Voice',
  displaySettings: String(import.meta.env.VITE_DISPLAY_SETTINGS).toLowerCase() === 'true'
};

// ============================================================================
// State
// ============================================================================

let audioContext: AudioContext | null = null;
let mediaStream: MediaStream | null = null;
let audioWorkletNode: AudioWorkletNode | null = null;
let playbackWorkletNode: AudioWorkletNode | null = null;
let socket: WebSocket | null = null;
let isConnected = false;
let responseAnalyser: AnalyserNode | null = null;
let waveAnimationId: number | null = null;
let idleWavePhase = 0;

// ============================================================================
// DOM Elements
// ============================================================================

const serverUrlInput = document.getElementById('serverUrl') as HTMLInputElement | null;
const apiKeyInput = document.getElementById('apiKey') as HTMLInputElement | null;
const settingsPanel = document.getElementById('settingsPanel') as HTMLDivElement | null;
const titleText = document.getElementById('appTitleText') as HTMLSpanElement | null;
const serverUrlCounter = document.querySelector('[data-counter=\"serverUrl\"]') as HTMLDivElement | null;
const apiKeyCounter = document.querySelector('[data-counter=\"apiKey\"]') as HTMLDivElement | null;
const connectBtn = document.getElementById('connectBtn') as HTMLButtonElement;
const statusDot = document.getElementById('statusDot') as HTMLDivElement;
const statusText = document.getElementById('statusText') as HTMLSpanElement;
const responseCanvas = document.getElementById('responseCanvas') as HTMLCanvasElement;

const INPUT_LIMITS = {
  serverUrl: 120,
  apiKey: 120
} as const;

// ============================================================================
// UI Updates
// ============================================================================

function setStatus(status: 'disconnected' | 'connecting' | 'connected' | 'error', text: string) {
  statusDot.className = 'status-dot ' + status;
  statusText.textContent = text;

  if (status === 'connected') {
    connectBtn.textContent = 'Disconnect';
    connectBtn.classList.add('connected');
    connectBtn.disabled = false;
  } else if (status === 'connecting') {
    connectBtn.textContent = 'Connecting...';
    connectBtn.classList.remove('connected');
    connectBtn.disabled = true;
  } else {
    connectBtn.textContent = 'Connect';
    connectBtn.classList.remove('connected');
    connectBtn.disabled = false;
  }
}

function updateCharCounter(field: keyof typeof INPUT_LIMITS) {
  const input = field === 'serverUrl' ? serverUrlInput : apiKeyInput;
  const counter = field === 'serverUrl' ? serverUrlCounter : apiKeyCounter;
  if (!input || !counter) return;
  const max = INPUT_LIMITS[field];
  const remaining = Math.max(0, max - input.value.length);
  counter.textContent = `${remaining} characters left`;
}

function bindCharCounter(field: keyof typeof INPUT_LIMITS) {
  const input = field === 'serverUrl' ? serverUrlInput : apiKeyInput;
  if (!input) return;
  input.maxLength = INPUT_LIMITS[field];
  input.addEventListener('input', () => updateCharCounter(field));
  updateCharCounter(field);
}

// ============================================================================
// Audio Visualization
// ============================================================================

function drawResponseWave() {
  if (!responseCanvas) return;
  const ctx = responseCanvas.getContext('2d');
  if (!ctx) return;

  const dpr = window.devicePixelRatio || 1;
  const width = Math.floor(responseCanvas.clientWidth * dpr) || responseCanvas.width;
  const height = Math.floor(responseCanvas.clientHeight * dpr) || responseCanvas.height;

  if (width === 0 || height === 0) return;

  if (responseCanvas.width !== width || responseCanvas.height !== height) {
    responseCanvas.width = width;
    responseCanvas.height = height;
  }

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = 'rgba(2, 6, 23, 0.4)';
  ctx.fillRect(0, 0, width, height);

  const gradient = ctx.createLinearGradient(0, 0, width, height);
  gradient.addColorStop(0, 'rgba(52, 211, 153, 0.85)');
  gradient.addColorStop(1, 'rgba(56, 189, 248, 0.85)');

  const sampleCount = responseAnalyser && isConnected ? responseAnalyser.fftSize : 256;
  const dataPoints: Array<{ x: number; y: number }> = [];
  let waveform: Uint8Array<ArrayBuffer> | null = null;

  if (responseAnalyser && isConnected) {
    waveform = new Uint8Array(responseAnalyser.fftSize) as Uint8Array<ArrayBuffer>;
    responseAnalyser.getByteTimeDomainData(waveform);
  }

  for (let i = 0; i < sampleCount; i++) {
    const x = (i / (sampleCount - 1)) * width;
    const value = waveform
      ? (waveform[i] - 128) / 128
      : Math.sin((i / sampleCount) * 4 * Math.PI + idleWavePhase) * 0.25;
    const y = height / 2 + value * (height / 2 - 24);
    dataPoints.push({ x, y });
  }

  if (dataPoints.length === 0) return;

  ctx.beginPath();
  ctx.moveTo(dataPoints[0].x, dataPoints[0].y);
  for (let i = 1; i < dataPoints.length; i++) {
    ctx.lineTo(dataPoints[i].x, dataPoints[i].y);
  }

  ctx.lineWidth = 4;
  ctx.strokeStyle = gradient;
  ctx.shadowColor = 'rgba(56, 189, 248, 0.35)';
  ctx.shadowBlur = 20;
  ctx.stroke();
  ctx.shadowBlur = 0;

  ctx.lineTo(width, height);
  ctx.lineTo(0, height);
  ctx.closePath();
  ctx.fillStyle = 'rgba(56, 189, 248, 0.12)';
  ctx.fill();

  ctx.beginPath();
  ctx.strokeStyle = 'rgba(148, 163, 184, 0.12)';
  ctx.lineWidth = 1;
  ctx.moveTo(0, height / 2);
  ctx.lineTo(width, height / 2);
  ctx.stroke();
}

function startWaveAnimation() {
  if (waveAnimationId !== null) return;

  const render = () => {
    drawResponseWave();
    idleWavePhase += isConnected ? 0.2 : 0.05;
    waveAnimationId = requestAnimationFrame(render);
  };

  waveAnimationId = requestAnimationFrame(render);
}

// ============================================================================
// Audio Capture (Microphone) & Playback Setup
// ============================================================================

async function startAudio() {
  try {
    // Create audio context
    audioContext = new AudioContext({ sampleRate: SAMPLE_RATE });

    // Load AudioWorklet modules
    await audioContext.audioWorklet.addModule('/audio-processor.js');
    await audioContext.audioWorklet.addModule('/playback-processor.js');

    // --- Setup Microphone Capture ---
    
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

    // Create AudioWorkletNode for capturing audio data
    audioWorkletNode = new AudioWorkletNode(audioContext, 'audio-capture-processor');

    // Handle audio data from the capture worklet
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
      }
    };

    source.connect(audioWorkletNode);
    // AudioWorklet doesn't need to connect to destination for capture-only

    // --- Setup Audio Playback ---

    // Create analyser for visualization (AI response)
    responseAnalyser = audioContext.createAnalyser();
    responseAnalyser.fftSize = 512;
    responseAnalyser.smoothingTimeConstant = 0.8;

    // Create Playback Worklet
    playbackWorkletNode = new AudioWorkletNode(audioContext, 'playback-processor');
    playbackWorkletNode.port.postMessage({ 
      type: 'config', 
      inputSampleRate: SAMPLE_RATE 
    });
    
    // Connect Playback -> Analyser -> Destination
    playbackWorkletNode.connect(responseAnalyser);
    responseAnalyser.connect(audioContext.destination);

    return true;
  } catch (error) {
    console.error(error);
    setStatus('error', 'Audio access denied or error');
    return false;
  }
}

function stopAudio() {
  if (audioWorkletNode) {
    audioWorkletNode.disconnect();
    audioWorkletNode.port.close();
    audioWorkletNode = null;
  }
  
  if (playbackWorkletNode) {
    playbackWorkletNode.disconnect();
    playbackWorkletNode.port.close();
    playbackWorkletNode = null;
  }

  if (mediaStream) {
    mediaStream.getTracks().forEach(track => track.stop());
    mediaStream = null;
  }

  responseAnalyser = null;
}

// ============================================================================
// Audio Playback
// ============================================================================

function queueAudioForPlayback(pcmData: Float32Array) {
  // Send data to the playback worklet
  if (playbackWorkletNode && pcmData.length > 0) {
    playbackWorkletNode.port.postMessage({
      type: 'audio',
      data: pcmData
    });
  }
}

function stopAllAudio() {
  // Reset the playback worklet buffer
  if (playbackWorkletNode) {
    playbackWorkletNode.port.postMessage({ type: 'reset' });
  }
}

// ============================================================================
// WebSocket Connection
// ============================================================================

function getServerUrl() {
  if (ENV_CONFIG.displaySettings && serverUrlInput) {
    return serverUrlInput.value.trim();
  }
  return ENV_CONFIG.serverUrl.trim();
}

function getApiKey() {
  if (ENV_CONFIG.displaySettings && apiKeyInput) {
    return apiKeyInput.value.trim();
  }
  return ENV_CONFIG.apiKey.trim();
}

function connect() {
  const baseUrl = getServerUrl();
  const adapterName = ENV_CONFIG.adapterName.trim();
  const apiKey = getApiKey();

  if (!baseUrl) {
    setStatus('error', 'Please enter server URL');
    return;
  }

  if (!adapterName) {
    setStatus('error', 'Missing adapter name in configuration');
    return;
  }

  // Build WebSocket URL
  const wsUrl = `${baseUrl}/ws/voice/${adapterName}${apiKey ? `?api_key=${apiKey}` : ''}`;

  setStatus('connecting', 'Connecting...');

  socket = new WebSocket(wsUrl);

  socket.onopen = async () => {

    // Start audio capture after connection
    const audioStarted = await startAudio();
    if (!audioStarted) {
      disconnect();
      return;
    }

    isConnected = true;
    idleWavePhase = 0;
    startWaveAnimation();
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
  stopAudio();
  
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
      // Decode base64 and queue for playback
      const pcmData = base64ToFloat32(audioMsg.data);
      queueAudioForPlayback(pcmData);
      break;
    }

    case 'transcription': {
      // Transcriptions are intentionally hidden in the simplified UI
      break;
    }

    case 'interrupted': {
      stopAllAudio();
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

// Keep connection alive with ping
setInterval(() => {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: 'ping' }));
  }
}, 5000);

// Initialize from environment variables
if (ENV_CONFIG.displaySettings) {
  if (serverUrlInput) {
    serverUrlInput.value = ENV_CONFIG.serverUrl;
    bindCharCounter('serverUrl');
  }
  if (apiKeyInput) {
    apiKeyInput.value = ENV_CONFIG.apiKey;
    bindCharCounter('apiKey');
  }
} else if (settingsPanel) {
  settingsPanel.remove();
}
document.title = ENV_CONFIG.appTitle;
if (titleText) {
  titleText.textContent = ENV_CONFIG.appTitle;
}

// Initialize the wave visualizer
drawResponseWave();
startWaveAnimation();
