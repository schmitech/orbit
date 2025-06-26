import React, { useState, useRef, useEffect } from 'react';
import { Send, Mic, MicOff, Paperclip, Square } from 'lucide-react';
import { useVoice } from '../hooks/useVoice';

interface MessageInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function MessageInput({ 
  onSend, 
  disabled = false, 
  placeholder = "Ask me anything..." 
}: MessageInputProps) {
  const [message, setMessage] = useState('');
  const [isComposing, setIsComposing] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const {
    isListening,
    isSupported: voiceSupported,
    startListening,
    stopListening,
    error: voiceError
  } = useVoice((text) => {
    setMessage(prev => (prev + text).slice(0, 1000));
  });

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [message]);

  // Auto-focus when not disabled (when AI response is complete)
  useEffect(() => {
    if (!disabled && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [disabled]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (message.trim() && !disabled && !isComposing) {
      onSend(message.trim());
      setMessage('');
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleVoiceToggle = () => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  };

  return (
    <div className="h-24 pt-6 pb-4 px-4 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 flex items-center justify-center">
      {voiceError && (
        <div className="mb-2 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 p-2 rounded">
          {voiceError}
        </div>
      )}
      
      <form onSubmit={handleSubmit} className="relative w-full">
        <div className={`relative flex items-center gap-3 rounded-2xl p-3 transition-all duration-300 border ${
          isFocused 
            ? 'border-blue-300 dark:border-blue-600 bg-white dark:bg-gray-800 shadow-lg ring-4 ring-blue-100 dark:ring-blue-900/30' 
            : 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 hover:border-gray-300 dark:hover:border-gray-600'
        }`}>
          {/* Attachment button */}
          <button
            type="button"
            className="flex-shrink-0 p-2 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 transition-colors rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
            title="Attach file"
          >
            <Paperclip className="w-5 h-5" />
          </button>

          {/* Text input */}
          <textarea
            ref={textareaRef}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            onCompositionStart={() => setIsComposing(true)}
            onCompositionEnd={() => setIsComposing(false)}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder={placeholder}
            disabled={disabled}
            rows={1}
            maxLength={1000}
            className="flex-1 bg-transparent border-0 outline-none resize-none text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 max-h-32 leading-relaxed"
            style={{ minHeight: '24px' }}
          />

          {/* Character count */}
          {message.length > 0 && (
            <div className="flex-shrink-0 text-xs text-gray-400 dark:text-gray-500">
              <span className={message.length >= 1000 ? 'text-red-500 font-bold' : ''}>
                {message.length}/1000
              </span>
            </div>
          )}

          {/* Voice input button */}
          {voiceSupported && (
            <button
              type="button"
              onClick={handleVoiceToggle}
              className={`flex-shrink-0 p-2 transition-all duration-200 rounded-lg ${
                isListening
                  ? 'text-red-500 bg-red-50 dark:text-red-400 dark:bg-red-900/20 shadow-sm'
                  : 'text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
              }`}
              title={isListening ? 'Stop recording' : 'Start voice input'}
            >
              {isListening ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
            </button>
          )}

          {/* Send button */}
          <button
            type="submit"
            disabled={!message.trim() || disabled || isComposing}
            className={`flex-shrink-0 p-2.5 rounded-xl transition-all duration-200 ${
              message.trim() && !disabled && !isComposing
                ? 'bg-blue-600 hover:bg-blue-700 text-white shadow-md hover:shadow-lg transform hover:scale-105 active:scale-95'
                : 'bg-gray-200 dark:bg-gray-600 text-gray-400 dark:text-gray-500 cursor-not-allowed'
            }`}
            title="Send message"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>

        {/* Hints */}
        <div className="h-4 mt-1 px-1">
          {isListening && (
            <span className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
              <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></span>
              <span className="font-medium">Listening...</span>
            </span>
          )}
        </div>
      </form>
    </div>
  );
}