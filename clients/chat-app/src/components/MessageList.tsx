import React, { useEffect, useRef, useState } from 'react';
import { Message } from './Message';
import { Message as MessageType } from '../types';

interface MessageListProps {
  messages: MessageType[];
  onRegenerate?: (messageId: string) => void;
  isLoading?: boolean;
}

export function MessageList({ messages, onRegenerate, isLoading }: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [lastMessageCount, setLastMessageCount] = useState(0);
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);

  // Check if user has scrolled up manually
  const handleScroll = () => {
    if (!containerRef.current) return;
    
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;
    setShouldAutoScroll(isNearBottom);
  };

  // Only auto-scroll when new messages are added (not when content updates)
  useEffect(() => {
    const messageCount = messages.length;
    
    // Only scroll if:
    // 1. New message was added (count increased)
    // 2. User hasn't manually scrolled up
    if (messageCount > lastMessageCount && shouldAutoScroll) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
    
    setLastMessageCount(messageCount);
  }, [messages.length, shouldAutoScroll, lastMessageCount]);

  // Scroll to bottom when loading starts (new assistant message)
  useEffect(() => {
    if (isLoading && shouldAutoScroll) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [isLoading, shouldAutoScroll]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="text-center max-w-lg">
          <div className="w-20 h-20 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center mx-auto mb-6 shadow-lg">
            <span className="text-white text-3xl font-bold">ORBIT</span>
          </div>
          <h3 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-3">
            Welcome to ORBIT Chat
          </h3>
          <p className="text-base text-gray-600 dark:text-gray-400 leading-relaxed">
            Start a conversation by typing a message below. I'm here to help with questions, creative tasks, analysis, and more.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div 
      ref={containerRef}
      className="flex-1 overflow-y-auto"
      onScroll={handleScroll}
    >
      <div className="max-w-4xl mx-auto">
        {messages.map((message) => (
          <Message
            key={message.id}
            message={message}
            onRegenerate={onRegenerate}
          />
        ))}
        
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}