/**
 * ORBIT Realtime Voice Bridge — test client
 *
 * Speaks the same ORBIT WebSocket protocol regardless of which real-time
 * speech-to-speech provider is behind the adapter (OpenAI Realtime, Gemini
 * Live, ...). Wire format is PCM16 mono 24 kHz (base64) both ways; the server
 * resamples to whatever the active provider actually needs.
 *
 * Protocol (ORBIT JSON):
 * - Client sends: {"type": "audio_chunk", "data": "<base64_pcm16_le>", "format": "pcm"}
 * - Server sends: {"type": "audio_chunk", "data": "<base64_pcm16_le>", "format": "pcm", ...}
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
  mode?: string;
  audio_format: string;
  sample_rate?: number;
  realtime_model?: string;
}

interface AudioChunkMessage extends OrbitMessage {
  type: 'audio_chunk';
  data: string;  // base64 pcm16
  format: string;
  sample_rate?: number;
  chunk_index?: number;
}

// No hardcoded provider default — set VITE_ADAPTER_NAME, or type an adapter
// name in the UI (VITE_DISPLAY_SETTINGS=true), for whichever STS provider
// (OpenAI Realtime, Gemini Live, ...) the server has configured.
const DEFAULT_ADAPTER = '';

/** Friendly labels for known realtime STS providers, keyed by the server's `connected.mode`. */
const PROVIDER_LABELS: Record<string, string> = {
  openai_realtime: 'OpenAI Realtime',
  openai_realtime_translation: 'OpenAI Realtime (Translate)',
  gemini_live: 'Gemini Live',
};

function providerLabelFor(mode?: string): string {
  if (!mode) return '—';
  if (PROVIDER_LABELS[mode]) return PROVIDER_LABELS[mode];
  return mode.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

// ============================================================================
// Configuration
// ============================================================================

const STREAM_SAMPLE_RATE = 24000;  // ORBIT realtime STS wire format: pcm16 @ 24 kHz
const CAPTURE_SAMPLE_RATE = 48000;

const DEFAULT_SERVER_URL = (import.meta.env.VITE_ORBIT_SERVER_URL || 'ws://localhost:3000').trim();
const API_BASE_OVERRIDE = (import.meta.env.VITE_ORBIT_API_URL || '').trim();
const DEFAULT_ADAPTER_NAME = (import.meta.env.VITE_ADAPTER_NAME || DEFAULT_ADAPTER).trim();
const DEFAULT_API_KEY = (import.meta.env.VITE_API_KEY || '').trim();
const DEFAULT_APP_TITLE = (import.meta.env.VITE_APP_TITLE || 'ORBIT Realtime Voice Bridge').trim();

const ENV_CONFIG = {
  serverUrl: DEFAULT_SERVER_URL || 'ws://localhost:3000',
  apiBaseUrlOverride: API_BASE_OVERRIDE.length > 0 ? API_BASE_OVERRIDE : null,
  adapterName: DEFAULT_ADAPTER_NAME,
  apiKey: DEFAULT_API_KEY,
  appTitle: DEFAULT_APP_TITLE,
  displaySettings: String(import.meta.env.VITE_DISPLAY_SETTINGS).toLowerCase() === 'true'
};

function stripTrailingSlash(url: string): string {
  return url.replace(/\/+$/, '');
}

function convertWebsocketToHttpUrl(url: string): string {
  if (!url) {
    return '';
  }

  let candidate = url.trim();
  if (/^ws:\/\//i.test(candidate)) {
    candidate = candidate.replace(/^ws:\/\//i, 'http://');
  } else if (/^wss:\/\//i.test(candidate)) {
    candidate = candidate.replace(/^wss:\/\//i, 'https://');
  }

  if (!/^[a-zA-Z][a-zA-Z0-9+\-.]*:\/\//.test(candidate)) {
    candidate = `https://${candidate}`;
  }

  try {
    const parsed = new URL(candidate);
    parsed.search = '';
    parsed.hash = '';
    const normalizedPath = parsed.pathname === '/' ? '' : parsed.pathname.replace(/\/+$/, '');
    return `${parsed.protocol}//${parsed.host}${normalizedPath}`;
  } catch {
    return stripTrailingSlash(candidate);
  }
}

function getApiBaseUrl(serverUrl: string): string {
  if (ENV_CONFIG.apiBaseUrlOverride) {
    return stripTrailingSlash(ENV_CONFIG.apiBaseUrlOverride);
  }
  return convertWebsocketToHttpUrl(serverUrl);
}

interface ApiKeyStatusResponse {
  exists?: boolean;
  active?: boolean;
  adapter_name?: string | null;
  client_name?: string | null;
  message?: string;
}

interface AdapterInfoResponse {
  client_name?: string;
  adapter_name?: string;
}

/** Same endpoints as @schmitech/chatbot-api (no npm dependency for this demo app). */
async function validateOrbitApiKey(
  apiBase: string,
  apiKey: string
): Promise<ApiKeyStatusResponse> {
  const url = `${apiBase}/admin/api-keys/${apiKey}/status`;
  const res = await fetch(url, {
    method: 'GET',
    headers: { 'X-API-Key': apiKey }
  });
  const text = await res.text();
  if (!res.ok) {
    let detail = text || `HTTP ${res.status}`;
    try {
      const j = JSON.parse(text) as { detail?: string; message?: string };
      detail = j.detail || j.message || detail;
    } catch {
      /* use text */
    }
    throw new Error(detail);
  }
  return JSON.parse(text) as ApiKeyStatusResponse;
}

async function fetchAdapterInfo(apiBase: string, apiKey: string): Promise<AdapterInfoResponse> {
  const res = await fetch(`${apiBase}/admin/adapters/info`, {
    method: 'GET',
    headers: { 'X-API-Key': apiKey }
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(text || `HTTP ${res.status}`);
  }
  return JSON.parse(text) as AdapterInfoResponse;
}

// ============================================================================
// PCM16 <-> base64 (OpenAI Realtime wire format)
// ============================================================================

function float32ToPcm16Base64(samples: Float32Array): string {
  const out = new Uint8Array(samples.length * 2);
  const view = new DataView(out.buffer);
  for (let i = 0; i < samples.length; i++) {
    let s = samples[i] ?? 0;
    if (s > 1) s = 1;
    if (s < -1) s = -1;
    const v = s < 0 ? s * 0x8000 : s * 0x7fff;
    view.setInt16(i * 2, Math.round(v), true);
  }
  let binary = '';
  for (let i = 0; i < out.length; i++) {
    binary += String.fromCharCode(out[i]!);
  }
  return btoa(binary);
}

/** Decode base64 PCM16 LE mono to float32 [-1, 1] for Web Audio playback */
/**
 * Merge streaming base64 PCM16 chunks so odd byte counts do not misalign int16 frames.
 */
let pcmByteRemainder = new Uint8Array(0);

function resetPcmReceiveState() {
  pcmByteRemainder = new Uint8Array(0);
}

/** Decode merged PCM16 LE bytes to float32 in [-1, 1]. */
function pcm16LeBytesToFloat32(bytes: Uint8Array): Float32Array {
  const sampleCount = Math.floor(bytes.length / 2);
  const out = new Float32Array(sampleCount);
  const view = new DataView(bytes.buffer, bytes.byteOffset, sampleCount * 2);
  for (let i = 0; i < sampleCount; i++) {
    out[i] = view.getInt16(i * 2, true) / 32768.0;
  }
  return out;
}

/**
 * Turn the next base64 chunk into float32 samples (24 kHz semantics from the API).
 * Carries a byte across chunk boundaries when needed.
 */
function feedPcm16Base64ToFloat32Stream(base64: string): Float32Array {
  const binary = atob(base64);
  const incoming = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    incoming[i] = binary.charCodeAt(i);
  }
  const merged = new Uint8Array(pcmByteRemainder.length + incoming.length);
  merged.set(pcmByteRemainder, 0);
  merged.set(incoming, pcmByteRemainder.length);
  const alignedBytes = Math.floor(merged.length / 2) * 2;
  pcmByteRemainder = merged.subarray(alignedBytes);
  if (alignedBytes === 0) {
    return new Float32Array(0);
  }
  return pcm16LeBytesToFloat32(merged.subarray(0, alignedBytes));
}

// ============================================================================
// State
// ============================================================================

let audioContext: AudioContext | null = null;
let mediaStream: MediaStream | null = null;
let audioWorkletNode: AudioWorkletNode | null = null;
let captureSource: MediaStreamAudioSourceNode | null = null;
let playbackWorkletNode: AudioWorkletNode | null = null;
let socket: WebSocket | null = null;
let isConnected = false;
let responseAnalyser: AnalyserNode | null = null;
let captureAnalyser: AnalyserNode | null = null;
let playbackSuppressed = false;

// ============================================================================
// DOM Elements
// ============================================================================

const serverUrlInput = document.getElementById('serverUrl') as HTMLInputElement | null;
const apiKeyInput = document.getElementById('apiKey') as HTMLInputElement | null;
const adapterInput = document.getElementById('adapterName') as HTMLInputElement | null;
const settingsPanel = document.getElementById('settingsPanel') as HTMLDivElement | null;
const titleText = document.getElementById('appTitleText') as HTMLSpanElement | null;
const serverUrlCounter = document.querySelector('[data-counter="serverUrl"]') as HTMLDivElement | null;
const apiKeyCounter = document.querySelector('[data-counter="apiKey"]') as HTMLDivElement | null;
const adapterCounter = document.querySelector('[data-counter="adapterName"]') as HTMLDivElement | null;
const connectBtn = document.getElementById('connectBtn') as HTMLButtonElement;
const statusDot = document.getElementById('statusDot') as HTMLDivElement;
const statusText = document.getElementById('statusText') as HTMLSpanElement;
const signalCanvas = document.getElementById('signalCanvas') as HTMLCanvasElement;
const providerLabelEl = document.getElementById('providerLabel') as HTMLSpanElement | null;
const modelLabelEl = document.getElementById('modelLabel') as HTMLSpanElement | null;
const transcriptEl = document.getElementById('transcript') as HTMLPreElement | null;
const targetLanguageInput = document.getElementById('targetLanguage') as HTMLSelectElement | null;

const INPUT_LIMITS = {
  serverUrl: 120,
  apiKey: 120,
  adapterName: 120
} as const;

const OUTBOUND_TARGET_SAMPLES = Math.floor(STREAM_SAMPLE_RATE * 0.05);
const OUTBOUND_FLUSH_INTERVAL_MS = 40;

let outboundChunks: Float32Array[] = [];
let outboundSampleCount = 0;
let outboundFlushTimer: number | null = null;

/** AudioContext.outputSampleRate — playback worklet input must match this (step=1). */
let playbackNativeSampleRate = STREAM_SAMPLE_RATE;

// ============================================================================
// UI Updates
// ============================================================================

function setStatus(status: 'disconnected' | 'connecting' | 'initializing' | 'connected' | 'error', text: string) {
  const cssClass = status === 'initializing' ? 'connecting' : status;
  statusDot.className = 'status-dot ' + cssClass;
  statusText.textContent = text;

  if (status === 'connected') {
    playbackSuppressed = false;
    connectBtn.textContent = 'Disconnect';
    connectBtn.classList.add('connected');
    connectBtn.disabled = false;
  } else if (status === 'connecting' || status === 'initializing') {
    connectBtn.textContent = status === 'initializing' ? 'Initializing...' : 'Connecting...';
    connectBtn.classList.remove('connected');
    connectBtn.disabled = true;
  } else {
    connectBtn.textContent = 'Connect';
    connectBtn.classList.remove('connected');
    connectBtn.disabled = false;
  }
}

function appendTranscriptLine(prefix: string, text: string) {
  if (!transcriptEl) return;
  const line = `[${prefix}] ${text}\n`;
  transcriptEl.textContent += line;
  transcriptEl.scrollTop = transcriptEl.scrollHeight;
}

function clearTranscript() {
  if (transcriptEl) transcriptEl.textContent = '';
}

function setMeta(el: HTMLSpanElement | null, value: string) {
  if (!el) return;
  el.textContent = value;
  el.classList.toggle('is-empty', value === '—');
}

function updateCharCounter(field: keyof typeof INPUT_LIMITS) {
  const input =
    field === 'serverUrl' ? serverUrlInput : field === 'apiKey' ? apiKeyInput : adapterInput;
  const counter =
    field === 'serverUrl' ? serverUrlCounter : field === 'apiKey' ? apiKeyCounter : adapterCounter;
  if (!input || !counter) return;
  const max = INPUT_LIMITS[field];
  const remaining = Math.max(0, max - input.value.length);
  counter.textContent = `${remaining} characters left`;
}

function bindCharCounter(field: keyof typeof INPUT_LIMITS) {
  const input =
    field === 'serverUrl' ? serverUrlInput : field === 'apiKey' ? apiKeyInput : adapterInput;
  if (!input) return;
  input.maxLength = INPUT_LIMITS[field];
  input.addEventListener('input', () => updateCharCounter(field));
  updateCharCounter(field);
}

function resetOutboundQueue() {
  outboundChunks = [];
  outboundSampleCount = 0;
  if (outboundFlushTimer !== null) {
    clearTimeout(outboundFlushTimer);
    outboundFlushTimer = null;
  }
}

function scheduleOutboundFlush() {
  if (outboundFlushTimer !== null) return;
  outboundFlushTimer = window.setTimeout(() => {
    outboundFlushTimer = null;
    flushOutboundQueue(true);
  }, OUTBOUND_FLUSH_INTERVAL_MS);
}

function flushOutboundQueue(force = false) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  if (outboundSampleCount === 0) return;
  if (!force && outboundSampleCount < OUTBOUND_TARGET_SAMPLES) {
    scheduleOutboundFlush();
    return;
  }

  const merged = new Float32Array(outboundSampleCount);
  let offset = 0;
  for (const chunk of outboundChunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }

  resetOutboundQueue();

  const base64 = float32ToPcm16Base64(merged);
  socket.send(JSON.stringify({
    type: 'audio_chunk',
    data: base64,
    format: 'pcm'
  }));
}

function queueOutboundChunk(chunk: Float32Array) {
  if (chunk.length === 0) return;
  outboundChunks.push(chunk);
  outboundSampleCount += chunk.length;

  if (outboundSampleCount >= OUTBOUND_TARGET_SAMPLES) {
    flushOutboundQueue();
  } else {
    scheduleOutboundFlush();
  }
}

// ============================================================================
// Audio Visualization — duplex signal strip (IN = mic, OUT = model reply)
// ============================================================================

const STRIP_HISTORY_LENGTH = 140;
const inLevels = new Float32Array(STRIP_HISTORY_LENGTH);
const outLevels = new Float32Array(STRIP_HISTORY_LENGTH);
let idleWavePhase = 0;

/** Cheap RMS-ish level in [0, 1] from an analyser's time-domain buffer. */
function getLevel(analyser: AnalyserNode | null): number {
  if (!analyser) return 0;
  const length = analyser.fftSize;
  if (!length) return 0;
  const buffer = new Uint8Array(length);
  analyser.getByteTimeDomainData(buffer);
  let sumSquares = 0;
  for (let i = 0; i < buffer.length; i++) {
    const centered = (buffer[i]! - 128) / 128;
    sumSquares += centered * centered;
  }
  return Math.min(1, Math.sqrt(sumSquares / buffer.length) * 3.2);
}

function pushLevel(history: Float32Array, value: number) {
  history.copyWithin(0, 1);
  history[history.length - 1] = value;
}

/** Draws two scrolling amplitude lanes (IN above, OUT below) sharing one timeline. */
function drawSignalStrip() {
  if (!signalCanvas) return;
  const ctx = signalCanvas.getContext('2d');
  if (!ctx) return;

  const dpr = window.devicePixelRatio || 1;
  const width = Math.floor(signalCanvas.clientWidth * dpr) || signalCanvas.width;
  const height = Math.floor(signalCanvas.clientHeight * dpr) || signalCanvas.height;
  if (width === 0 || height === 0) return;

  if (signalCanvas.width !== width || signalCanvas.height !== height) {
    signalCanvas.width = width;
    signalCanvas.height = height;
  }

  if (isConnected) {
    pushLevel(inLevels, getLevel(captureAnalyser));
    pushLevel(outLevels, getLevel(responseAnalyser));
  } else {
    // Idle standby pulse — a faint synthetic heartbeat instead of a dead panel.
    idleWavePhase += 0.02;
    const idle = 0.05 + Math.max(0, Math.sin(idleWavePhase)) * 0.03;
    pushLevel(inLevels, idle);
    pushLevel(outLevels, idle);
  }

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = '#0e1210';
  ctx.fillRect(0, 0, width, height);

  const laneHeight = height / 2;
  const barWidth = width / STRIP_HISTORY_LENGTH;

  drawLane(ctx, inLevels, 0, laneHeight, 'top', isConnected ? '#8fa398' : '#3c4841');
  drawLane(ctx, outLevels, laneHeight, laneHeight, 'bottom', isConnected ? '#4ce0a0' : '#2c6e56');

  ctx.strokeStyle = '#2a332e';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, laneHeight);
  ctx.lineTo(width, laneHeight);
  ctx.stroke();

  function drawLane(
    context: CanvasRenderingContext2D,
    history: Float32Array,
    top: number,
    laneH: number,
    align: 'top' | 'bottom',
    color: string
  ) {
    const baseline = align === 'top' ? top : top + laneH;
    context.fillStyle = color;
    for (let i = 0; i < history.length; i++) {
      const barHeight = Math.max(1, history[i]! * (laneH - 8));
      const x = i * barWidth;
      const y = align === 'top' ? baseline : baseline - barHeight;
      context.fillRect(x, y, Math.max(1, barWidth - 1), barHeight);
    }
  }
}

let waveAnimationId: number | null = null;

function startWaveAnimation() {
  if (waveAnimationId !== null) return;

  const render = () => {
    drawSignalStrip();
    waveAnimationId = requestAnimationFrame(render);
  };

  waveAnimationId = requestAnimationFrame(render);
}

// ============================================================================
// Audio Capture & Playback
// ============================================================================

async function startAudio() {
  try {
    audioContext = new AudioContext({
      sampleRate: CAPTURE_SAMPLE_RATE,
      latencyHint: 'balanced'
    });
    playbackNativeSampleRate = audioContext.sampleRate;

    await audioContext.audioWorklet.addModule('/audio-processor.js');
    await audioContext.audioWorklet.addModule('/playback-processor.js');

    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: CAPTURE_SAMPLE_RATE,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      }
    });

    captureSource = audioContext.createMediaStreamSource(mediaStream);

    audioWorkletNode = new AudioWorkletNode(audioContext, 'audio-capture-processor');

    audioWorkletNode.port.onmessage = (event) => {
      if (!isConnected || !socket || socket.readyState !== WebSocket.OPEN) return;

      if (event.data.type === 'audio') {
        const inputData = event.data.data as Float32Array;
        const processedData = resampleBuffer(
          inputData,
          CAPTURE_SAMPLE_RATE,
          STREAM_SAMPLE_RATE
        );

        queueOutboundChunk(processedData);
      }
    };

    captureSource.connect(audioWorkletNode);

    captureAnalyser = audioContext.createAnalyser();
    captureAnalyser.fftSize = 512;
    captureAnalyser.smoothingTimeConstant = 0.8;
    captureSource.connect(captureAnalyser);

    responseAnalyser = audioContext.createAnalyser();
    responseAnalyser.fftSize = 512;
    responseAnalyser.smoothingTimeConstant = 0.8;

    playbackWorkletNode = new AudioWorkletNode(audioContext, 'playback-processor');
    playbackWorkletNode.port.postMessage({
      type: 'config',
      // Feed samples already resampled to the context rate so the worklet runs at 1:1 (no fractional stepping).
      inputSampleRate: playbackNativeSampleRate,
      bufferThresholdMs: 300,
      targetBufferMs: 520,
      maxBufferThresholdMs: 1200
    });

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

  if (captureSource) {
    captureSource.disconnect();
    captureSource = null;
  }

  if (captureAnalyser) {
    captureAnalyser.disconnect();
    captureAnalyser = null;
  }

  if (mediaStream) {
    mediaStream.getTracks().forEach(track => track.stop());
    mediaStream = null;
  }

  responseAnalyser = null;
}

function queueAudioForPlayback(pcmData: Float32Array) {
  if (playbackWorkletNode && pcmData.length > 0) {
    playbackWorkletNode.port.postMessage({
      type: 'audio',
      data: pcmData
    });
  }
}

function stopAllAudio() {
  if (playbackWorkletNode) {
    playbackWorkletNode.port.postMessage({ type: 'reset' });
  }
}

function resampleBuffer(buffer: Float32Array, inputRate: number, targetRate: number): Float32Array {
  if (inputRate === targetRate) {
    return buffer;
  }

  const ratio = inputRate / targetRate;

  if (ratio > 1) {
    const newLength = Math.floor(buffer.length / ratio);
    const result = new Float32Array(newLength);
    for (let i = 0; i < newLength; i++) {
      const start = Math.floor(i * ratio);
      const end = Math.min(Math.floor((i + 1) * ratio), buffer.length);
      let sum = 0;
      let count = 0;
      for (let j = start; j < end; j++) {
        sum += buffer[j] ?? 0;
        count++;
      }
      result[i] = count > 0 ? sum / count : 0;
    }
    return result;
  } else {
    const newLength = Math.floor(buffer.length / ratio);
    const result = new Float32Array(newLength);
    for (let i = 0; i < newLength; i++) {
      const position = i * ratio;
      const index = Math.floor(position);
      const frac = position - index;
      const s0 = buffer[index] ?? 0;
      const s1 = buffer[index + 1] ?? s0;
      result[i] = s0 + (s1 - s0) * frac;
    }
    return result;
  }
}

// ============================================================================
// WebSocket
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

function getAdapterNameField() {
  if (ENV_CONFIG.displaySettings && adapterInput) {
    const v = adapterInput.value.trim();
    return v || DEFAULT_ADAPTER;
  }
  return ENV_CONFIG.adapterName.trim() || DEFAULT_ADAPTER;
}

async function connect() {
  const baseUrl = getServerUrl();
  const apiKey = getApiKey();

  if (!baseUrl) {
    setStatus('error', 'Please enter server URL');
    return;
  }

  const apiBaseUrl = getApiBaseUrl(baseUrl);
  if (!apiBaseUrl) {
    setStatus('error', 'Unable to determine API base URL');
    return;
  }

  let adapterName = getAdapterNameField();
  let statusMessage = 'Connecting...';

  if (apiKey) {
    setStatus('connecting', 'Validating API key...');
    try {
      const validation = await validateOrbitApiKey(apiBaseUrl, apiKey);

      if (validation.adapter_name && validation.adapter_name.trim().length > 0) {
        adapterName = validation.adapter_name.trim();
      }

      const friendlyTarget = validation.client_name || validation.adapter_name || adapterName;
      if (friendlyTarget) {
        statusMessage = `Connecting to ${friendlyTarget}...`;
      }

      try {
        const adapterInfo = await fetchAdapterInfo(apiBaseUrl, apiKey);
        const label = adapterInfo.client_name || adapterInfo.adapter_name || adapterName;
        statusMessage = `Connecting to ${label}...`;
      } catch (infoError) {
        console.warn('Failed to fetch adapter info', infoError);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to validate API key';
      setStatus('error', message);
      return;
    }
  } else {
    setStatus('connecting', `Connecting to ${adapterName}...`);
  }

  const params = new URLSearchParams();
  if (apiKey) {
    params.set('api_key', apiKey);
  }
  const targetLanguage = targetLanguageInput?.value.trim();
  if (targetLanguage) {
    params.set('target_language', targetLanguage);
  }
  const qs = params.toString() ? `?${params.toString()}` : '';
  let wsUrl = `${stripTrailingSlash(baseUrl)}/ws/voice${qs}`;
  if (!apiKey) {
    const normalizedAdapterName = adapterName.trim();
    if (!normalizedAdapterName) {
      setStatus('error', 'Adapter name is empty');
      return;
    }
    wsUrl = `${stripTrailingSlash(baseUrl)}/ws/voice/${encodeURIComponent(normalizedAdapterName)}${qs}`;
  }

  setStatus('connecting', statusMessage);
  clearTranscript();

  socket = new WebSocket(wsUrl);

  socket.onopen = async () => {
    resetPcmReceiveState();
    const audioStarted = await startAudio();
    if (!audioStarted) {
      disconnect();
      return;
    }

    resetOutboundQueue();
    idleWavePhase = 0;
    startWaveAnimation();
  };

  socket.onmessage = (event) => {
    try {
      const message: OrbitMessage = JSON.parse(event.data);
      handleMessage(message);
    } catch {
      /* ignore */
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
    if (socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'interrupt' }));
    }
    socket.close();
    socket = null;
  }

  handleDisconnect();
}

function handleDisconnect() {
  isConnected = false;
  playbackSuppressed = false;
  resetOutboundQueue();
  resetPcmReceiveState();
  stopAudio();

  if (audioContext) {
    void audioContext.close();
    audioContext = null;
  }

  setStatus('disconnected', 'Idle');
  setMeta(providerLabelEl, '—');
  setMeta(modelLabelEl, '—');
}

function handleMessage(message: OrbitMessage) {
  switch (message.type) {
    case 'connected': {
      const connMsg = message as ConnectedMessage;
      isConnected = true;
      playbackSuppressed = false;
      setStatus('connected', 'Connected');
      setMeta(providerLabelEl, providerLabelFor(connMsg.mode));
      setMeta(modelLabelEl, connMsg.realtime_model || '—');
      appendTranscriptLine('system', connMsg.adapter ? `Connected — ${connMsg.adapter}` : 'Connected');
      break;
    }

    case 'audio_chunk': {
      const audioMsg = message as AudioChunkMessage;
      if (!playbackSuppressed) {
        const apiRate =
          typeof audioMsg.sample_rate === 'number' && audioMsg.sample_rate > 0
            ? audioMsg.sample_rate
            : STREAM_SAMPLE_RATE;
        const atApiRate = feedPcm16Base64ToFloat32Stream(audioMsg.data);
        if (atApiRate.length === 0) break;
        const atDeviceRate = resampleBuffer(atApiRate, apiRate, playbackNativeSampleRate);
        queueAudioForPlayback(atDeviceRate);
      }
      break;
    }

    case 'transcription': {
      const t = typeof message.text === 'string' ? message.text : '';
      if (t) appendTranscriptLine('you', t);
      break;
    }

    case 'assistant_transcript_delta': {
      const d = typeof message.delta === 'string' ? message.delta : '';
      if (d && transcriptEl) {
        transcriptEl.textContent += d;
        transcriptEl.scrollTop = transcriptEl.scrollHeight;
      }
      break;
    }

    case 'interrupted': {
      playbackSuppressed = false;
      stopAllAudio();
      appendTranscriptLine('system', 'Interrupted');
      break;
    }

    case 'done': {
      appendTranscriptLine('system', 'Turn complete');
      if (transcriptEl) transcriptEl.textContent += '\n';
      break;
    }

    case 'target_language_updated': {
      const lang = typeof message.target_language === 'string' ? message.target_language : '';
      appendTranscriptLine('system', `Target language → ${lang}`);
      break;
    }

    case 'pong': {
      break;
    }

    case 'error': {
      isConnected = false;
      const msg = typeof message.message === 'string' ? message.message : 'Error';
      setStatus('error', `Error: ${msg}`);
      appendTranscriptLine('error', msg);
      break;
    }

    default:
      break;
  }
}

// ============================================================================
// Events
// ============================================================================

connectBtn.addEventListener('click', () => {
  if (isConnected) {
    disconnect();
  } else {
    void connect().catch((error) => {
      console.error('Failed to establish connection', error);
      setStatus('error', error instanceof Error ? error.message : 'Failed to connect');
    });
  }
});

targetLanguageInput?.addEventListener('change', () => {
  const language = targetLanguageInput.value.trim();
  if (!language) return;
  // If connected, switch live; otherwise it applies on the next connect.
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: 'set_target_language', language }));
  }
});

setInterval(() => {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: 'ping' }));
  }
}, 5000);

if (ENV_CONFIG.displaySettings) {
  if (serverUrlInput) {
    serverUrlInput.value = ENV_CONFIG.serverUrl;
    bindCharCounter('serverUrl');
  }
  if (apiKeyInput) {
    apiKeyInput.value = ENV_CONFIG.apiKey;
    bindCharCounter('apiKey');
  }
  if (adapterInput) {
    adapterInput.value = ENV_CONFIG.adapterName;
    bindCharCounter('adapterName');
  }
} else if (settingsPanel) {
  settingsPanel.remove();
}
document.title = ENV_CONFIG.appTitle;
if (titleText) {
  titleText.textContent = ENV_CONFIG.appTitle;
}

drawSignalStrip();
startWaveAnimation();
