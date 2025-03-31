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
  const [isThinking, setIsThinking] = useState(isAssistant);
  const [isTyping, setIsTyping] = useState(isAssistant);
  const [typingDots, setTypingDots] = useState('.');
  const contentRef = useRef(message.content);
  const charIndexRef = useRef(0);

  // Handle typing animation for assistant messages
  useEffect(() => {
    if (!isAssistant) {
      setDisplayedContent(message.content);
      return;
    }

    // Update the content reference when message content changes
    if (contentRef.current !== message.content) {
      contentRef.current = message.content;
      charIndexRef.current = 0;
      setDisplayedContent('');
      setIsTyping(true);
      setIsThinking(true);
    }

    if (isTyping && charIndexRef.current < contentRef.current.length) {
      const typingTimer = setTimeout(() => {
        charIndexRef.current += 1;
        const newContent = contentRef.current.substring(0, charIndexRef.current);
        setDisplayedContent(newContent);
        
        // Hide thinking indicator as soon as we have content
        if (newContent.length > 0 && isThinking) {
          setIsThinking(false);
        }
        
        if (charIndexRef.current >= contentRef.current.length) {
          setIsTyping(false);
        }
      }, 20); // 20ms delay per character, same as in the CLI
      
      return () => clearTimeout(typingTimer);
    }
  }, [isAssistant, isTyping, message.content, displayedContent, isThinking]);

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
        <div 
          className="text-gray-800 whitespace-pre-wrap"
          dangerouslySetInnerHTML={{ __html: renderMarkdown(displayedContent) }}
        />
        {isThinking && (
          <span className="inline-block text-gray-500 ml-1">
            <span className="font-medium">thinking</span>
            <span className="font-mono">{typingDots}</span>
          </span>
        )}
      </div>
    </div>
  );
};