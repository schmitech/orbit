/// <reference types="vite/client" />

interface Window {
    webkitSpeechRecognition: new () => SpeechRecognition;
  }
  
  interface SpeechRecognition extends EventTarget {
    continuous: boolean;
    interimResults: boolean;
    lang: string;
    start: () => void;
    stop: () => void;
    abort: () => void;
    onerror: (event: { error: string }) => void;
    onend: () => void;
    onresult: (event: {
      results: {
        [index: number]: {
          [index: number]: {
            transcript: string;
            confidence: number;
          };
        };
      };
    }) => void;
  }