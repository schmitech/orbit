import { useState, useCallback, useRef } from 'react';
import { debugLog, debugError } from '../utils/debug';

interface UseVoiceReturn {
  isListening: boolean;
  isSupported: boolean;
  startListening: () => void;
  stopListening: () => void;
  error: string | null;
}

declare global {
  interface Window {
    SpeechRecognition: typeof SpeechRecognition;
    webkitSpeechRecognition: typeof SpeechRecognition;
  }
}

export function useVoice(onResult: (text: string) => void): UseVoiceReturn {
  const [isListening, setIsListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const pendingTranscriptRef = useRef<string>('');

  const isSupported = typeof window !== 'undefined' && 
    ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window);

  const startListening = useCallback(() => {
    if (!isSupported) {
      setError('Speech recognition is not supported in this browser. Please try Chrome, Edge, or Safari.');
      return;
    }

    if (isListening) {
      return;
    }

    try {
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
      };

      recognition.onresult = (event) => {
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
      };

      recognition.onend = () => {
        if (pendingTranscriptRef.current) {
          onResult(' ' + pendingTranscriptRef.current);
          pendingTranscriptRef.current = '';
        }
        setIsListening(false);
        recognitionRef.current = null;
        debugLog('Speech recognition ended');
      };

      recognition.onerror = (event) => {
        debugError('Speech recognition error:', event.error);
        setIsListening(false);
        recognitionRef.current = null;
        pendingTranscriptRef.current = '';
        
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
  }, [isSupported, onResult, isListening]);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
    pendingTranscriptRef.current = '';
    setIsListening(false);
    setError(null);
  }, []);

  return {
    isListening,
    isSupported,
    startListening,
    stopListening,
    error
  };
}
