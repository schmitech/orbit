import { useState, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { debugLog, debugError } from '../utils/debug';

interface UseVoiceReturn {
  isListening: boolean;
  isSupported: boolean;
  startListening: () => void;
  stopListening: () => void;
  error: string | null;
}

interface UseVoiceOptions {
  silenceTimeoutMs?: number;
  language?: string;
}

// Speech Recognition API types
interface SpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  onstart: ((this: SpeechRecognition, ev: Event) => void) | null;
  onend: ((this: SpeechRecognition, ev: Event) => void) | null;
  onerror: ((this: SpeechRecognition, ev: SpeechRecognitionErrorEvent) => void) | null;
  onresult: ((this: SpeechRecognition, ev: SpeechRecognitionEvent) => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

interface SpeechRecognitionEvent extends Event {
  resultIndex: number;
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionErrorEvent extends Event {
  error: string;
  message: string;
}

interface SpeechRecognitionResultList {
  readonly length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionResult {
  readonly length: number;
  item(index: number): SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
  isFinal: boolean;
}

interface SpeechRecognitionAlternative {
  transcript: string;
  confidence: number;
}

const DEFAULT_SILENCE_TIMEOUT_MS = 4000;

declare global {
  interface Window {
    SpeechRecognition: {
      new (): SpeechRecognition;
      prototype: SpeechRecognition;
    };
    webkitSpeechRecognition: {
      new (): SpeechRecognition;
      prototype: SpeechRecognition;
    };
  }
}

export function useVoice(
  onResult: (text: string) => void,
  onComplete?: () => void,
  options: UseVoiceOptions = {}
): UseVoiceReturn {
  const { t } = useTranslation();
  const [isListening, setIsListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const pendingTranscriptRef = useRef<string>('');
  const lastEmittedTranscriptRef = useRef<string>('');
  const completionNotifiedRef = useRef(false);
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const browserLanguage = typeof navigator !== 'undefined' ? navigator.language : 'en-US';
  const silenceTimeoutMs = Number.isFinite(options.silenceTimeoutMs)
    ? Math.max(Math.floor(options.silenceTimeoutMs as number), 1000)
    : DEFAULT_SILENCE_TIMEOUT_MS;
  const recognitionLanguage = options.language?.trim() || browserLanguage || 'en-US';

  const normalizeTranscript = useCallback((text: string) => {
    return text.replace(/\s+/g, ' ').trim();
  }, []);

  const emitTranscript = useCallback((text: string) => {
    const normalized = normalizeTranscript(text);
    if (!normalized) {
      return;
    }
    if (normalized === lastEmittedTranscriptRef.current) {
      return;
    }
    lastEmittedTranscriptRef.current = normalized;
    onResult(normalized);
  }, [normalizeTranscript, onResult]);

  const flushPendingTranscript = useCallback(() => {
    if (!pendingTranscriptRef.current) {
      return;
    }
    const pending = pendingTranscriptRef.current;
    pendingTranscriptRef.current = '';
    emitTranscript(pending);
  }, [emitTranscript]);

  const isSupported = typeof window !== 'undefined' && 
    ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window);

  const notifyCompletion = useCallback(() => {
    if (!onComplete || completionNotifiedRef.current) {
      return;
    }
    completionNotifiedRef.current = true;
    onComplete();
  }, [onComplete]);

  const clearSilenceTimer = useCallback(() => {
    if (silenceTimerRef.current !== null) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
  }, []);

  const scheduleSilenceTimer = useCallback(() => {
    clearSilenceTimer();
    silenceTimerRef.current = setTimeout(() => {
      debugLog('Speech recognition silence threshold reached, stopping recording');
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      } else {
        notifyCompletion();
      }
    }, silenceTimeoutMs);
  }, [clearSilenceTimer, notifyCompletion, silenceTimeoutMs]);

  const startListening = useCallback(() => {
    if (!isSupported) {
      setError(t('voice.browserNotSupported'));
      return;
    }

    // Guard with ref to prevent double-start from rapid clicks (stale isListening closure)
    if (recognitionRef.current) {
      return;
    }

    try {
      completionNotifiedRef.current = false;
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      const recognition = new SpeechRecognition();

      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = recognitionLanguage;
      recognition.maxAlternatives = 1;

      recognition.onstart = () => {
        setIsListening(true);
        setError(null);
        pendingTranscriptRef.current = '';
        lastEmittedTranscriptRef.current = '';
        debugLog('Speech recognition started');
        scheduleSilenceTimer();
      };

      recognition.onresult = (event: SpeechRecognitionEvent) => {
        let finalTranscript = '';
        let interimTranscript = '';
        
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcript = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            finalTranscript += transcript;
          } else {
            interimTranscript += transcript;
          }
        }
        
        if (interimTranscript) {
          pendingTranscriptRef.current = normalizeTranscript(interimTranscript);
        }
        
        if (finalTranscript) {
          pendingTranscriptRef.current = '';
          emitTranscript(finalTranscript);
        }
        scheduleSilenceTimer();
      };

      recognition.onend = () => {
        clearSilenceTimer();
        flushPendingTranscript();
        setIsListening(false);
        recognitionRef.current = null;
        debugLog('Speech recognition ended');
        notifyCompletion();
      };

      recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
        clearSilenceTimer();
        debugError('Speech recognition error:', event.error);
        setIsListening(false);
        recognitionRef.current = null;
        pendingTranscriptRef.current = '';
        notifyCompletion();
        
        switch (event.error) {
          case 'no-speech':
            setError(t('voice.error.noSpeech'));
            break;
          case 'audio-capture':
            setError(t('voice.error.audioCapture'));
            break;
          case 'not-allowed':
            setError(t('voice.error.notAllowed'));
            break;
          case 'network':
            setError(t('voice.error.network'));
            break;
          default:
            setError(t('voice.error.generic', { error: event.error }));
        }
      };

      recognition.start();
      recognitionRef.current = recognition;
    } catch (err) {
      debugError('Failed to start speech recognition:', err);
      setError(t('voice.error.startFailed'));
      setIsListening(false);
    }
  }, [isSupported, flushPendingTranscript, notifyCompletion, scheduleSilenceTimer, clearSilenceTimer, recognitionLanguage, normalizeTranscript, emitTranscript, t]);

  const stopListening = useCallback(() => {
    debugLog('Stopping speech recognition...');
    if (recognitionRef.current) {
      const recognition = recognitionRef.current;
      recognition.onstart = null;
      recognition.onerror = null;
      
      try {
        recognition.stop();
      } catch (err) {
        // Recognition might already be stopped, ignore errors
        debugLog('Recognition already stopped or error stopping:', err);
        clearSilenceTimer();
        flushPendingTranscript();
        recognition.onend = null;
        recognition.onresult = null;
        recognitionRef.current = null;
        setIsListening(false);
        notifyCompletion();
      }
    }
    clearSilenceTimer();
    setIsListening(false);
    setError(null);
    debugLog('Speech recognition stopped, isListening set to false');
  }, [clearSilenceTimer, flushPendingTranscript, notifyCompletion]);

  return {
    isListening,
    isSupported,
    startListening,
    stopListening,
    error
  };
}
