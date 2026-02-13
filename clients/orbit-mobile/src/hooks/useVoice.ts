import { useState, useCallback, useRef, useEffect } from 'react';

// expo-speech-recognition requires a native dev build — it won't work in Expo Go.
// We dynamically require the module and catch the error if the native module isn't available.
let SpeechRecognitionModule: any = null;
let WebSpeechRecognition: any = null;
let nativeModuleAvailable = false;

try {
  const mod = require('expo-speech-recognition');
  SpeechRecognitionModule = mod.ExpoSpeechRecognitionModule;
  WebSpeechRecognition = mod.ExpoWebSpeechRecognition;
  nativeModuleAvailable = true;
} catch {
  // Native module not available (e.g., running in Expo Go)
}

interface UseVoiceReturn {
  isListening: boolean;
  isSupported: boolean;
  startListening: () => void;
  stopListening: () => void;
  error: string | null;
}

export function useVoice(
  onTranscript: (text: string) => void,
  language: string = 'en-US'
): UseVoiceReturn {
  const [isListening, setIsListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<any>(null);
  const onTranscriptRef = useRef(onTranscript);
  onTranscriptRef.current = onTranscript;

  // Accumulate finalized text across the entire listening session.
  // Only delivered to the caller once, when recognition ends.
  const accumulatedRef = useRef('');
  const deliveredRef = useRef(false);

  const deliverTranscript = useCallback(() => {
    if (!deliveredRef.current && accumulatedRef.current) {
      deliveredRef.current = true;
      onTranscriptRef.current(accumulatedRef.current);
    }
  }, []);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch { /* ignore */ }
      recognitionRef.current = null;
    }
    // Deliver happens in onend to avoid double-delivery
    setIsListening(false);
  }, []);

  const startListening = useCallback(async () => {
    if (!nativeModuleAvailable) return;

    setError(null);
    accumulatedRef.current = '';
    deliveredRef.current = false;

    try {
      const result = await SpeechRecognitionModule.requestPermissionsAsync();
      if (!result.granted) {
        setError('Microphone permission denied');
        return;
      }

      const recognition = new WebSpeechRecognition();
      recognition.lang = language;
      recognition.continuous = false; // Single utterance per tap
      recognition.interimResults = false; // Only final results

      recognition.onresult = (event: any) => {
        const results = event.results;
        if (results && results.length > 0) {
          const lastResult = results[results.length - 1];
          const transcript = lastResult?.[0]?.transcript || '';
          if (transcript) {
            // Accumulate — don't deliver yet
            accumulatedRef.current = accumulatedRef.current
              ? accumulatedRef.current + ' ' + transcript
              : transcript;
          }
        }
      };

      recognition.onerror = (event: any) => {
        const code = event.error;
        const messages: Record<string, string> = {
          'no-speech': 'No speech detected',
          'audio-capture': 'Microphone access denied',
          'not-allowed': 'Microphone access not allowed',
          network: 'Network error occurred',
        };
        setError(messages[code] || `Speech recognition error: ${code}`);
        setIsListening(false);
      };

      // Single delivery point — recognition has fully stopped
      recognition.onend = () => {
        deliverTranscript();
        accumulatedRef.current = '';
        recognitionRef.current = null;
        setIsListening(false);
      };

      recognitionRef.current = recognition;
      recognition.start();
      setIsListening(true);
    } catch (err: any) {
      setError(err?.message || 'Failed to start speech recognition');
    }
  }, [language, deliverTranscript]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        try { recognitionRef.current.stop(); } catch { /* ignore */ }
        recognitionRef.current = null;
      }
    };
  }, []);

  return {
    isListening,
    isSupported: nativeModuleAvailable,
    startListening,
    stopListening,
    error,
  };
}
