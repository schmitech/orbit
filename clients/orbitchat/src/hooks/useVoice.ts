import { useState, useCallback, useRef } from 'react';
import { debugLog, debugError } from '../utils/debug';

interface UseVoiceReturn {
  isListening: boolean;
  isSupported: boolean;
  startListening: () => void;
  stopListening: () => void;
  error: string | null;
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

const SILENCE_TIMEOUT_MS = 2000;

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
  onComplete?: () => void
): UseVoiceReturn {
  const [isListening, setIsListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const pendingTranscriptRef = useRef<string>('');
  const completionNotifiedRef = useRef(false);
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flushPendingTranscript = useCallback(() => {
    if (!pendingTranscriptRef.current) {
      return;
    }
    const pending = pendingTranscriptRef.current;
    pendingTranscriptRef.current = '';
    onResult(' ' + pending);
  }, [onResult]);

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
    }, SILENCE_TIMEOUT_MS);
  }, [clearSilenceTimer, notifyCompletion]);

  const startListening = useCallback(() => {
    if (!isSupported) {
      setError('Speech recognition is not supported in this browser. Please try Chrome, Edge, or Safari.');
      return;
    }

    if (isListening) {
      return;
    }

    try {
      completionNotifiedRef.current = false;
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      const recognition = new SpeechRecognition();

      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = navigator.language || 'en-US';
      recognition.maxAlternatives = 1;

      recognition.onstart = () => {
        setIsListening(true);
        setError(null);
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
          pendingTranscriptRef.current = interimTranscript;
        }
        
        if (finalTranscript) {
          pendingTranscriptRef.current = '';
          onResult(' ' + finalTranscript);
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
            setError('No speech detected. Please try again.');
            break;
          case 'audio-capture':
            setError('Microphone access denied. Please allow microphone access and try again.');
            break;
          case 'not-allowed':
            setError('Microphone access not allowed. Please enable microphone permissions.');
            break;
          case 'network':
            setError('Network error occurred. Please check your connection.');
            break;
          default:
            setError(`Speech recognition error: ${event.error}`);
        }
      };

      recognition.start();
      recognitionRef.current = recognition;
    } catch (err) {
      debugError('Failed to start speech recognition:', err);
      setError('Failed to start speech recognition. Please try again.');
      setIsListening(false);
    }
  }, [isSupported, onResult, isListening, flushPendingTranscript, notifyCompletion, scheduleSilenceTimer, clearSilenceTimer]);

  const stopListening = useCallback(() => {
    debugLog('Stopping speech recognition...');
    if (recognitionRef.current) {
      // Remove event handlers before stopping to prevent race conditions
      const recognition = recognitionRef.current;
      recognition.onend = null;
      recognition.onerror = null;
      recognition.onresult = null;
      recognition.onstart = null;
      
      try {
        recognition.stop();
      } catch (err) {
        // Recognition might already be stopped, ignore errors
        debugLog('Recognition already stopped or error stopping:', err);
      }
      
      recognitionRef.current = null;
    }
    clearSilenceTimer();
    flushPendingTranscript();
    setIsListening(false);
    setError(null);
    notifyCompletion();
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
