import React, { useState, useRef, useEffect } from 'react';
import { Send, Mic, MicOff } from 'lucide-react';
import { useChatStore } from '../store';

interface ChatInputProps {
  onSendMessage: (message: string) => void;
  disabled?: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSendMessage, disabled }) => {
  const [input, setInput] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const isLoading = useChatStore(state => state.isLoading);
  const language = useChatStore(state => state.language);

  useEffect(() => {
    if (!isLoading && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isLoading]);

  useEffect(() => {
    // Initialize speech recognition
    if ('webkitSpeechRecognition' in window) {
      const SpeechRecognition = window.webkitSpeechRecognition;
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = `${language}-${language.toUpperCase()}`;

      recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        let processedText = transcript;
        
        // Add question mark if it's likely a question but doesn't end with one
        const questionWords = ['what', 'when', 'where', 'who', 'why', 'how', 'can', 'could', 'would', 'should', 'do', 'does', 'is', 'are'];
        const startsWithQuestionWord = questionWords.some(word => 
          transcript.toLowerCase().trim().startsWith(word)
        );
        
        if (startsWithQuestionWord && !transcript.trim().endsWith('?')) {
          processedText = transcript.trim() + '?';
        }

        setInput(processedText);
        // Automatically send message after recording
        if (processedText.trim()) {
          onSendMessage(processedText.trim());
          setInput('');
        }
        setIsRecording(false);
      };

      recognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        setIsRecording(false);
      };

      recognition.onend = () => {
        setIsRecording(false);
      };

      recognitionRef.current = recognition;
    }

    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.abort();
      }
    };
  }, [onSendMessage, language]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim()) {
      onSendMessage(input.trim());
      setInput('');
    }
  };

  const toggleRecording = () => {
    if (!recognitionRef.current) {
      alert('Speech recognition is not supported in your browser.');
      return;
    }

    if (isRecording) {
      recognitionRef.current.stop();
    } else {
      setInput('');
      recognitionRef.current.start();
    }
    setIsRecording(!isRecording);
  };

  return (
    <form onSubmit={handleSubmit} className="flex gap-2 p-4 border-t">
      <input
        ref={inputRef}
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder={
          language === 'fr' ? 'Poser une question sur les services municipaux...' :
          language === 'es' ? 'Haga una pregunta sobre servicios municipales...' :
          'Ask a question about municipal services...'
        }
        className="flex-1 p-3 text-lg border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        disabled={disabled || isRecording}
      />
      <button
        type="button"
        onClick={toggleRecording}
        disabled={disabled}
        className={`px-6 py-3 rounded-lg transition-colors ${
          isRecording 
            ? 'bg-red-500 hover:bg-red-600 text-white' 
            : 'bg-gray-100 hover:bg-gray-200 text-gray-700'
        }`}
        title={isRecording ? 'Stop recording' : 'Start recording'}
      >
        {isRecording ? <MicOff size={24} /> : <Mic size={24} />}
      </button>
      <button
        type="submit"
        disabled={disabled || !input.trim() || isRecording}
        className="px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <Send size={24} />
      </button>
    </form>
  );
};