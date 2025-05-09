import React, { useState, useEffect, useRef } from 'react';
import { Bot, User } from 'lucide-react';
import { Message } from '../types';
import { marked } from 'marked';

interface ChatMessageProps {
  message: Message;
}

const renderMarkdown = (text: string) => {
  return marked(text);
};

export const ChatMessage: React.FC<ChatMessageProps> = ({ message }) => {
  const isAssistant = message.role === 'assistant';
  const [isThinking, setIsThinking] = useState(isAssistant && message.content === '');
  const [typingDots, setTypingDots] = useState('.');

  // Handle content changes
  useEffect(() => {
    if (isAssistant) {
      setIsThinking(message.content === '');
    }
  }, [isAssistant, message.content]);

  // Animate the typing indicator dots
  useEffect(() => {
    if (!isThinking) return;
    
    const dotsTimer = setInterval(() => {
      setTypingDots(prev => {
        if (prev === '.') return '..';
        if (prev === '..') return '...';
        return '.';
      });
    }, 400);
    
    return () => clearInterval(dotsTimer);
  }, [isThinking]);

  return (
    <div className={`flex gap-4 ${isAssistant ? 'bg-gray-50' : 'bg-white'} p-6`}>
      <div className={`w-10 h-10 flex items-center justify-center rounded-full ${isAssistant ? 'bg-green-100' : 'bg-blue-500'}`}>
        {isAssistant ? (
          <Bot size={24} className="text-green-600" />
        ) : (
          <User size={24} className="text-white" />
        )}
      </div>
      <div className="flex-1">
        <div className={`font-medium mb-2 text-sm uppercase ${isAssistant ? 'text-green-600' : 'text-blue-500'}`}>
          {isAssistant ? 'AI Assistant' : 'You'}
        </div>
        {!isThinking && (
          <div 
            className="text-gray-800 whitespace-pre-wrap"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(message.content) }}
          />
        )}
        {isThinking && (
          <span className="inline-block text-gray-500">
            <span className="font-medium">thinking</span>
            <span className="font-mono">{typingDots}</span>
          </span>
        )}
      </div>
    </div>
  );
};