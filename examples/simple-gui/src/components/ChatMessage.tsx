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
  const [displayedContent, setDisplayedContent] = useState(isAssistant ? '' : message.content);
  const [isThinking, setIsThinking] = useState(isAssistant && message.content === '');
  const [isTyping, setIsTyping] = useState(false);
  const [typingDots, setTypingDots] = useState('.');
  const contentRef = useRef(message.content);
  const charIndexRef = useRef(0);

  // Handle content changes and state transitions
  useEffect(() => {
    if (!isAssistant) {
      setDisplayedContent(message.content);
      return;
    }

    // Update the content reference when message content changes
    if (contentRef.current !== message.content) {
      contentRef.current = message.content;
      
      // If we have content to type, prepare for typing animation
      if (message.content.length > 0) {
        // Only reset character index if we're starting fresh
        // This prevents restarting the animation on re-renders
        if (isThinking || displayedContent === '') {
          charIndexRef.current = 0;
          setDisplayedContent('');
          setIsThinking(false);
          setIsTyping(true);
        }
      } else {
        // If no content yet, show thinking animation
        setIsTyping(false);
        setIsThinking(true);
      }
    }
  }, [isAssistant, isThinking, message.content, displayedContent]);

  // Handle typing animation separately
  useEffect(() => {
    if (!isTyping) return;
    
    if (charIndexRef.current < contentRef.current.length) {
      const typingTimer = setTimeout(() => {
        charIndexRef.current += 1;
        const newContent = contentRef.current.substring(0, charIndexRef.current);
        setDisplayedContent(newContent);
                
        if (charIndexRef.current >= contentRef.current.length) {
          setIsTyping(false);
        }
      }, 20); // 20ms delay per character
      
      return () => clearTimeout(typingTimer);
    }
  }, [isTyping, displayedContent]);

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
            dangerouslySetInnerHTML={{ __html: renderMarkdown(displayedContent) }}
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