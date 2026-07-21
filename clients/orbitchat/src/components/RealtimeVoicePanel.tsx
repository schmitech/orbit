import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CircleHelp, Loader2, Mic, MicOff, PhoneOff, Volume2, X } from 'lucide-react';
import { getApi } from '../apiClient';
import { useChatStore } from '../stores/chatStore';
import { MarkdownRenderer } from './markdown';

const WIRE_RATE = 24000;

function toBase64(samples: Float32Array): string {
  const bytes = new Uint8Array(samples.length * 2);
  const view = new DataView(bytes.buffer);
  samples.forEach((sample, index) => view.setInt16(index * 2, Math.round(Math.max(-1, Math.min(1, sample)) * (sample < 0 ? 0x8000 : 0x7fff)), true));
  let binary = '';
  bytes.forEach(byte => { binary += String.fromCharCode(byte); });
  return btoa(binary);
}

function fromBase64(value: string): Float32Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index++) bytes[index] = binary.charCodeAt(index);
  const samples = new Float32Array(Math.floor(bytes.length / 2));
  const view = new DataView(bytes.buffer);
  for (let index = 0; index < samples.length; index++) samples[index] = view.getInt16(index * 2, true) / 32768;
  return samples;
}

function resample(samples: Float32Array, sourceRate: number, targetRate: number): Float32Array {
  if (sourceRate === targetRate) return samples;
  const output = new Float32Array(Math.floor(samples.length * targetRate / sourceRate));
  const ratio = sourceRate / targetRate;
  for (let index = 0; index < output.length; index++) {
    const position = index * ratio;
    const lower = Math.floor(position);
    const upper = Math.min(lower + 1, samples.length - 1);
    output[index] = (samples[lower] || 0) + ((samples[upper] || 0) - (samples[lower] || 0)) * (position - lower);
  }
  return output;
}

function formatDuration(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

export function RealtimeVoicePanel({
  conversationId,
  adapterName,
  sessionId,
  adapterNotes,
}: {
  conversationId: string;
  adapterName: string;
  sessionId: string;
  adapterNotes?: string | null;
}) {
  const { t } = useTranslation();
  const socketRef = useRef<WebSocket | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<AudioWorkletNode | null>(null);
  const micAnalyserRef = useRef<AnalyserNode | null>(null);
  const outputAnalyserRef = useRef<AnalyserNode | null>(null);
  const activityOrbRef = useRef<HTMLSpanElement | null>(null);
  const activityGlowRef = useRef<HTMLSpanElement | null>(null);
  const nextPlaybackRef = useRef(0);
  const playbackSourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set());
  const isMutedRef = useRef(false);
  const isStoppingRef = useRef(false);
  const [status, setStatus] = useState<'idle' | 'connecting' | 'connected' | 'error'>('idle');
  const [isMuted, setIsMuted] = useState(false);
  const [isAssistantSpeaking, setIsAssistantSpeaking] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [showAgentInfo, setShowAgentInfo] = useState(false);
  const voice = useChatStore(state => state.realtimeVoice);
  const setVoice = useChatStore(state => state.setRealtimeVoiceState);
  const beginTurn = useChatStore(state => state.beginRealtimeVoiceTurn);
  const appendDelta = useChatStore(state => state.appendRealtimeVoiceAssistantDelta);
  const finishTurn = useChatStore(state => state.finishRealtimeVoiceTurn);

  useEffect(() => { isMutedRef.current = isMuted; }, [isMuted]);

  const stop = useCallback(() => {
    isStoppingRef.current = true;
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'interrupt' }));
    socket?.close(); socketRef.current = null;
    processorRef.current?.disconnect(); processorRef.current?.port.close(); processorRef.current = null;
    streamRef.current?.getTracks().forEach(track => track.stop()); streamRef.current = null;
    playbackSourcesRef.current.forEach(source => {
      try { source.stop(); } catch { /* source already ended */ }
    });
    playbackSourcesRef.current.clear();
    void contextRef.current?.close(); contextRef.current = null;
    micAnalyserRef.current = null; outputAnalyserRef.current = null;
    setIsMuted(false); setIsAssistantSpeaking(false); setElapsedSeconds(0);
    setStatus('idle'); setVoice({ status: 'idle' });
  }, [setVoice]);

  const clearPlayback = useCallback(() => {
    playbackSourcesRef.current.forEach(source => {
      try { source.stop(); } catch { /* source already ended */ }
    });
    playbackSourcesRef.current.clear();
    nextPlaybackRef.current = contextRef.current?.currentTime || 0;
    setIsAssistantSpeaking(false);
  }, []);

  useEffect(() => () => stop(), [stop]);

  // Call duration, ticking once per second for the lifetime of a connected call.
  // elapsedSeconds itself is reset by the user-initiated start()/stop() actions below.
  useEffect(() => {
    if (status !== 'connected') return;
    const startedAt = Date.now();
    const id = window.setInterval(() => setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => window.clearInterval(id);
  }, [status]);

  // A compact version of the original call orb. It responds to the mic while
  // listening and to playback while the assistant is speaking, without adding
  // a wide waveform that competes with the composer text.
  useEffect(() => {
    let frame = 0;
    const animate = () => {
      const analyser = isAssistantSpeaking ? outputAnalyserRef.current : micAnalyserRef.current;
      const data = analyser && !isMuted ? new Uint8Array(analyser.fftSize) : null;
      if (data) analyser.getByteTimeDomainData(data);
      let level = 0;
      if (data) {
        for (const sample of data) {
          const normalized = (sample - 128) / 128;
          level += normalized * normalized;
        }
        level = Math.min(1, Math.sqrt(level / data.length) * 8);
      }
      activityOrbRef.current?.style.setProperty('transform', `scale(${1 + level * 0.16})`);
      if (activityGlowRef.current) {
        activityGlowRef.current.style.setProperty('transform', `scale(${1.05 + level * 0.45})`);
        activityGlowRef.current.style.setProperty('opacity', `${0.08 + level * 0.35}`);
      }
      frame = window.requestAnimationFrame(animate);
    };
    animate();
    return () => window.cancelAnimationFrame(frame);
  }, [isAssistantSpeaking, isMuted, status]);

  const start = useCallback(async () => {
    try {
      isStoppingRef.current = false;
      setStatus('connecting'); setElapsedSeconds(0); setVoice({ status: 'connecting', error: undefined, transcript: '' });
      const api = await getApi();
      const url = api.getRealtimeVoiceWebSocketUrl(adapterName, { sessionId });
      const socket = new WebSocket(url); socketRef.current = socket;
      socket.onmessage = event => {
        let message: Record<string, unknown>;
        try {
          message = JSON.parse(event.data) as Record<string, unknown>;
        } catch {
          return;
        }
        if (message.type === 'connected') {
          setStatus('connected'); setIsAssistantSpeaking(false);
          setVoice({ status: 'connected', provider: String(message.mode || ''), model: String(message.realtime_model || '') });
        } else if (message.type === 'audio_chunk' && typeof message.data === 'string' && contextRef.current && outputAnalyserRef.current) {
          const context = contextRef.current; const input = fromBase64(message.data);
          const rate = typeof message.sample_rate === 'number' ? message.sample_rate : WIRE_RATE;
          const buffer = context.createBuffer(1, Math.max(1, Math.floor(input.length * context.sampleRate / rate)), context.sampleRate);
          buffer.copyToChannel(resample(input, rate, context.sampleRate), 0);
          const source = context.createBufferSource(); source.buffer = buffer; source.connect(outputAnalyserRef.current);
          playbackSourcesRef.current.add(source);
          source.onended = () => playbackSourcesRef.current.delete(source);
          nextPlaybackRef.current = Math.max(nextPlaybackRef.current, context.currentTime + 0.06);
          source.start(nextPlaybackRef.current); nextPlaybackRef.current += buffer.duration;
          setIsAssistantSpeaking(true);
        } else if (message.type === 'transcription' && typeof message.text === 'string') beginTurn(conversationId, message.text);
        else if (message.type === 'assistant_transcript_delta' && typeof message.delta === 'string') appendDelta(conversationId, message.delta);
        else if (message.type === 'done') {
          setIsAssistantSpeaking(false);
          finishTurn(conversationId, {
            userMessageId: typeof message.user_message_id === 'string' ? message.user_message_id : undefined,
            assistantMessageId: typeof message.assistant_message_id === 'string' ? message.assistant_message_id : undefined,
          });
        }
        else if (message.type === 'interrupted') { clearPlayback(); finishTurn(conversationId); }
        else if (message.type === 'error') {
          setStatus('error'); setIsAssistantSpeaking(false);
          finishTurn(conversationId);
          setVoice({ status: 'error', error: String(message.message || t('realtimeVoice.errors.connectionFailed')) });
        }
      };
      socket.onerror = () => {
        if (isStoppingRef.current) return;
        setIsAssistantSpeaking(false); finishTurn(conversationId);
        setStatus('error'); setVoice({ status: 'error', error: t('realtimeVoice.errors.connectionFailed') });
      };
      socket.onclose = () => {
        if (isStoppingRef.current) return;
        setIsAssistantSpeaking(false); finishTurn(conversationId);
        setStatus('error'); setVoice({ status: 'error', error: t('realtimeVoice.errors.connectionFailed') });
      };
      socket.onopen = async () => {
        const context = new AudioContext(); contextRef.current = context; nextPlaybackRef.current = context.currentTime;
        const outputAnalyser = context.createAnalyser(); outputAnalyser.fftSize = 256; outputAnalyser.smoothingTimeConstant = 0.8;
        outputAnalyser.connect(context.destination); outputAnalyserRef.current = outputAnalyser;
        await context.audioWorklet.addModule('/audio-capture-processor.js');
        const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } }); streamRef.current = stream;
        const source = context.createMediaStreamSource(stream); const micAnalyser = context.createAnalyser(); micAnalyser.fftSize = 256; micAnalyser.smoothingTimeConstant = 0.8; micAnalyserRef.current = micAnalyser; source.connect(micAnalyser);
        const processor = new AudioWorkletNode(context, 'audio-capture-processor'); processorRef.current = processor;
        processor.port.onmessage = event => {
          if (socket.readyState !== WebSocket.OPEN) return;
          if (event.data?.type !== 'audio' || !(event.data.data instanceof Float32Array)) return;
          if (isMutedRef.current) return;
          socket.send(JSON.stringify({ type: 'audio_chunk', data: toBase64(resample(event.data.data, context.sampleRate, WIRE_RATE)), format: 'pcm' }));
        };
        source.connect(processor); processor.connect(context.destination);
      };
    } catch (error) {
      const microphoneDenied = error instanceof DOMException && (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError');
      setStatus('error');
      setVoice({
        status: 'error',
        error: microphoneDenied
          ? t('realtimeVoice.errors.microphoneDenied')
          : error instanceof Error ? error.message : t('realtimeVoice.errors.connectionFailed'),
      });
    }
  }, [adapterName, appendDelta, beginTurn, clearPlayback, conversationId, finishTurn, sessionId, setVoice, t]);

  const toggleMute = useCallback(() => setIsMuted(muted => !muted), []);

  const connected = status === 'connected';
  const statusLabel =
    status === 'connecting' ? t('realtimeVoice.status.connecting')
    : status === 'error' ? t('realtimeVoice.status.error')
    : connected ? (isAssistantSpeaking ? t('realtimeVoice.status.speaking') : t('realtimeVoice.status.listening'))
    : t('realtimeVoice.status.ready');
  const statusDotClass =
    status === 'connecting' ? 'bg-amber-400 animate-pulse'
    : status === 'error' ? 'bg-red-500'
    : connected ? 'bg-blue-500'
    : 'bg-gray-300 dark:bg-[#4a4b54]';
  return (
    <section className="mx-auto flex w-full max-w-[64rem] shrink-0 flex-col" aria-label={t('realtimeVoice.sectionAriaLabel')}>
      <div className="relative w-full">
        {voice.error && (
          <div role="alert" className="mb-2 flex items-start justify-between gap-3 rounded-lg bg-red-50 px-3.5 py-2.5 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-200">
            <p>{voice.error}</p>
            <button
              type="button"
              onClick={start}
              className="shrink-0 whitespace-nowrap font-medium underline underline-offset-2 hover:text-red-900 dark:hover:text-red-100"
            >
              {t('realtimeVoice.retry')}
            </button>
          </div>
        )}

        {showAgentInfo && adapterNotes && (
          <div className="mb-2 rounded-lg border border-gray-200 bg-transparent px-4 py-3 dark:border-[#2f303d]">
            <div className="mb-2 flex items-center justify-between gap-3">
              <p className="text-sm font-medium text-[#353740] dark:text-[#ececf1]">{t('messageInput.agentInfoModal.title')}</p>
              <button
                type="button"
                onClick={() => setShowAgentInfo(false)}
                aria-label={t('messageInput.agentInfoModal.closeAriaLabel')}
                title={t('messageInput.agentInfoModal.closeAriaLabel')}
                className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-gray-500 transition-all active:scale-95 hover:bg-gray-100 hover:text-[#353740] dark:text-[#bfc2cd] dark:hover:bg-[#2f313a]"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <MarkdownRenderer
              content={adapterNotes}
              className="message-markdown prose prose-slate max-w-none text-sm leading-relaxed text-[#434654] dark:prose-invert dark:text-[#d7dae3] [&>:first-child]:mt-0 [&>:last-child]:mb-0"
            />
          </div>
        )}

        <div className="flex items-center gap-2 rounded-xl border border-gray-300 bg-gray-50 px-2.5 py-2 shadow-sm transition-all dark:border-[#242424] dark:bg-[#111111] md:rounded-lg md:px-4 md:py-3">
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <span className={`h-2 w-2 shrink-0 rounded-full ${statusDotClass}`} aria-hidden="true" />
            <span aria-live="polite" className="min-w-0 break-words text-sm text-[#353740] dark:text-[#ececf1]">
              {statusLabel}{voice.model ? ` · ${voice.model}` : ''}
            </span>
          </div>
          <div className="flex shrink-0 items-center gap-1 md:gap-2">
            {connected && <span className="hidden font-mono text-xs tabular-nums text-gray-500 dark:text-[#8a8fa3] sm:inline">{formatDuration(elapsedSeconds)}</span>}
            <span className="relative flex h-7 w-7 shrink-0 items-center justify-center" aria-hidden="true">
              <span
                ref={activityGlowRef}
                className={`absolute inset-0 rounded-full transition-[background-color] duration-200 ${
                  status === 'error' ? 'bg-red-500' : connected ? 'bg-blue-500' : 'bg-gray-400 dark:bg-[#565869]'
                }`}
              />
              <span
                ref={activityOrbRef}
                className={`relative flex h-6 w-6 items-center justify-center rounded-full transition-[background-color,transform] duration-150 ${
                  status === 'error' ? 'bg-red-500 text-white' : connected ? 'bg-blue-600 text-white dark:bg-blue-500' : 'bg-gray-200 text-gray-500 dark:bg-[#2f313a] dark:text-[#bfc2cd]'
                }`}
              >
                {isAssistantSpeaking ? <Volume2 className="h-3.5 w-3.5" /> : <Mic className="h-3.5 w-3.5" />}
              </span>
            </span>
            {adapterNotes && (
              <button
                type="button"
                onClick={() => setShowAgentInfo(visible => !visible)}
                aria-expanded={showAgentInfo}
                aria-label={t('messageInput.agentInfo.ariaLabel')}
                title={t('messageInput.agentInfo.title')}
                className="inline-flex h-8 w-8 items-center justify-center rounded-full text-gray-500 transition-all active:scale-95 hover:bg-gray-200 hover:text-[#353740] dark:text-[#bfc2cd] dark:hover:bg-[#565869]"
              >
                <CircleHelp className="h-4 w-4" />
              </button>
            )}
            {status === 'connecting' ? (
              <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-gray-300 text-gray-500 dark:bg-[#565869] dark:text-[#bfc2cd]">
                <Loader2 className="h-4 w-4 animate-spin" />
              </span>
            ) : !connected ? (
              <button
                type="button"
                onClick={start}
                title={t('realtimeVoice.startCall')}
                aria-label={t('realtimeVoice.startCall')}
                className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-black text-white transition-all active:scale-95 hover:bg-gray-800 dark:bg-white dark:text-black dark:hover:bg-gray-200"
              >
                <Mic className="h-4 w-4" />
              </button>
            ) : (
              <>
              <button
                type="button"
                onClick={toggleMute}
                aria-pressed={isMuted}
                title={isMuted ? t('realtimeVoice.unmuteMic') : t('realtimeVoice.muteMic')}
                aria-label={isMuted ? t('realtimeVoice.unmuteMic') : t('realtimeVoice.muteMic')}
                className={`inline-flex h-9 w-9 items-center justify-center rounded-full transition-all active:scale-95 ${
                  isMuted
                    ? 'bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-300'
                    : 'text-gray-500 hover:bg-gray-200 hover:text-[#353740] dark:text-[#bfc2cd] dark:hover:bg-[#565869]'
                }`}
              >
                {isMuted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              </button>
              <button
                type="button"
                onClick={stop}
                title={t('realtimeVoice.endCall')}
                aria-label={t('realtimeVoice.endCall')}
                className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-red-500 text-white transition-all active:scale-95 hover:bg-red-600 dark:bg-red-600 dark:hover:bg-red-700"
              >
                <PhoneOff className="h-4 w-4" />
              </button>
            </>
          )}
          </div>
        </div>
      </div>
    </section>
  );
}
