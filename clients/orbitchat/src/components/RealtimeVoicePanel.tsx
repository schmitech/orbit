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

/** Cheap RMS-ish level in [0, 1] from an analyser's time-domain buffer. */
function getLevel(analyser: AnalyserNode | null): number {
  if (!analyser) return 0;
  const data = new Uint8Array(analyser.fftSize);
  analyser.getByteTimeDomainData(data);
  let sumSquares = 0;
  for (let i = 0; i < data.length; i++) {
    const centered = (data[i]! - 128) / 128;
    sumSquares += centered * centered;
  }
  return Math.min(1, Math.sqrt(sumSquares / data.length) * 3.2);
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
  const orbRef = useRef<HTMLDivElement | null>(null);
  const nextPlaybackRef = useRef(0);
  const playbackSourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set());
  const isMutedRef = useRef(false);
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

  // Live "call orb" — scales with mic level while listening, with assistant
  // output level while it's replying. Skips the per-frame transform when the
  // user asked for reduced motion; color/label alone still carry the state.
  useEffect(() => {
    let frame = 0;
    const reducedMotion = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const tick = () => {
      const orb = orbRef.current;
      if (orb) {
        if (status === 'connected' && !reducedMotion) {
          const analyser = isAssistantSpeaking ? outputAnalyserRef.current : micAnalyserRef.current;
          const level = getLevel(analyser);
          orb.style.transform = `scale(${1 + level * 0.35})`;
        } else {
          orb.style.transform = 'scale(1)';
        }
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [status, isAssistantSpeaking]);

  // Call duration, ticking once per second for the lifetime of a connected call.
  // elapsedSeconds itself is reset by the user-initiated start()/stop() actions below.
  useEffect(() => {
    if (status !== 'connected') return;
    const startedAt = Date.now();
    const id = window.setInterval(() => setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => window.clearInterval(id);
  }, [status]);

  const start = useCallback(async () => {
    try {
      setStatus('connecting'); setElapsedSeconds(0); setVoice({ status: 'connecting', error: undefined, transcript: '' });
      const api = await getApi();
      const url = api.getRealtimeVoiceWebSocketUrl(adapterName, { sessionId });
      const socket = new WebSocket(url); socketRef.current = socket;
      socket.onmessage = event => {
        const message = JSON.parse(event.data) as Record<string, unknown>;
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
        else if (message.type === 'done') { setIsAssistantSpeaking(false); finishTurn(conversationId); }
        else if (message.type === 'interrupted') { clearPlayback(); finishTurn(conversationId); }
        else if (message.type === 'error') {
          setStatus('error'); setIsAssistantSpeaking(false);
          setVoice({ status: 'error', error: String(message.message || t('realtimeVoice.errors.connectionFailed')) });
        }
      };
      socket.onerror = () => { setStatus('error'); setVoice({ status: 'error', error: t('realtimeVoice.errors.connectionFailed') }); };
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
  const orbClass =
    status === 'connecting' ? 'bg-blue-400 animate-pulse'
    : status === 'error' ? 'bg-red-400'
    : connected ? 'bg-blue-500'
    : 'bg-gray-300 dark:bg-[#3c3f4a]';

  return (
    <section className="mx-auto flex w-full max-w-xl shrink-0 flex-col py-3 sm:py-4" aria-label={t('realtimeVoice.sectionAriaLabel')}>
      <div className="overflow-hidden rounded-[1.75rem] border border-gray-200 bg-white shadow-sm dark:border-[#2f303d] dark:bg-[#161720]">
        <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3 dark:border-[#2f303d]">
          <div className="flex items-center gap-2">
            <span className={`h-2 w-2 shrink-0 rounded-full ${statusDotClass}`} aria-hidden="true" />
            <span aria-live="polite" className="text-sm font-medium text-[#353740] dark:text-[#ececf1]">
              {statusLabel}{voice.model ? ` · ${voice.model}` : ''}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {connected && <span className="font-mono text-xs tabular-nums text-gray-500 dark:text-[#8a8fa3]">{formatDuration(elapsedSeconds)}</span>}
            {adapterNotes && (
              <button
                type="button"
                onClick={() => setShowAgentInfo(visible => !visible)}
                aria-expanded={showAgentInfo}
                aria-label={t('messageInput.agentInfo.ariaLabel')}
                title={t('messageInput.agentInfo.title')}
                className="inline-flex h-8 w-8 items-center justify-center rounded-full text-gray-500 transition-all active:scale-95 hover:bg-gray-100 hover:text-[#353740] dark:text-[#bfc2cd] dark:hover:bg-[#2f313a]"
              >
                <CircleHelp className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>

        <div className="flex flex-col items-center gap-3 px-5 py-6 sm:py-8">
          <div
            ref={orbRef}
            aria-hidden="true"
            className={`flex h-16 w-16 items-center justify-center rounded-full transition-colors duration-300 sm:h-20 sm:w-20 ${orbClass}`}
          >
            {connected ? <Volume2 className="h-6 w-6 text-white" /> : <Mic className="h-6 w-6 text-white" />}
          </div>
          {!connected && status !== 'error' && status !== 'connecting' && (
            <p className="max-w-xs text-center text-sm text-gray-500 dark:text-[#8a8fa3]">{t('realtimeVoice.idleHint')}</p>
          )}
        </div>

        {voice.error && (
          <div role="alert" className="mx-5 mb-4 flex items-start justify-between gap-3 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-600/40 dark:bg-red-900/30 dark:text-red-200">
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
          <div className="mx-5 mb-4 rounded-xl border border-gray-200 bg-transparent px-4 py-3 dark:border-[#2f303d]">
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

        <div className="flex items-center justify-center gap-3 border-t border-gray-100 px-5 py-4 dark:border-[#2f303d]">
          {status === 'connecting' ? (
            <span className="inline-flex items-center gap-2 rounded-full bg-gray-100 px-5 py-2.5 text-sm font-medium text-gray-500 dark:bg-[#2f313a] dark:text-[#8a8fa3]">
              <Loader2 className="h-4 w-4 animate-spin" /> {t('realtimeVoice.status.connecting')}
            </span>
          ) : !connected ? (
            <button
              type="button"
              onClick={start}
              className="inline-flex items-center gap-2 rounded-full bg-blue-600 px-5 py-2.5 text-sm font-medium text-white transition-all active:scale-95 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-400"
            >
              <Mic className="h-4 w-4" /> {t('realtimeVoice.startCall')}
            </button>
          ) : (
            <>
              <button
                type="button"
                onClick={toggleMute}
                aria-pressed={isMuted}
                title={isMuted ? t('realtimeVoice.unmuteMic') : t('realtimeVoice.muteMic')}
                aria-label={isMuted ? t('realtimeVoice.unmuteMic') : t('realtimeVoice.muteMic')}
                className={`inline-flex h-10 w-10 items-center justify-center rounded-full transition-all active:scale-95 ${
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
                className="inline-flex items-center gap-2 rounded-full bg-red-500 px-5 py-2.5 text-sm font-medium text-white transition-all active:scale-95 hover:bg-red-600 dark:bg-red-600 dark:hover:bg-red-700"
              >
                <PhoneOff className="h-4 w-4" /> {t('realtimeVoice.endCall')}
              </button>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
