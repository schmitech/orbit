import React, { useEffect, useRef, useState } from 'react';
import { Message } from './Message';
import { Message as MessageType } from '../types';
import orbitLogo from '../assets/orbit.png';

interface MessageListProps {
  messages: MessageType[];
  onRegenerate?: (messageId: string) => void;
  isLoading?: boolean;
}

export function MessageList({ messages, onRegenerate, isLoading }: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const prevMessageCountRef = useRef(messages.length);
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);

  // Check if user has scrolled up manually
  const handleScroll = () => {
    if (!containerRef.current) return;
    
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;
    setShouldAutoScroll(isNearBottom);
  };

  // Keep messages anchored to the latest content while the user stays near the bottom
  useEffect(() => {
    const messageCount = messages.length;
    const hadMessages = prevMessageCountRef.current;
    const hasNewMessage = messageCount > hadMessages;
    const lastMessage = messages[messages.length - 1];

    if ((hasNewMessage || lastMessage?.isStreaming) && shouldAutoScroll) {
      messagesEndRef.current?.scrollIntoView({ behavior: hasNewMessage ? 'smooth' : 'auto' });
    }

    prevMessageCountRef.current = messageCount;
  }, [messages, shouldAutoScroll]);

  // Scroll to bottom when loading starts (new assistant message)
  useEffect(() => {
    if (isLoading && shouldAutoScroll) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [isLoading, shouldAutoScroll]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-start justify-center pt-8 pb-4 px-12">
        <div className="max-w-md text-center space-y-4">
          <img
            src={orbitLogo}
            alt="ORBIT"
            className="w-48 h-48 mx-auto drop-shadow-[0_10px_30px_rgba(37,99,235,0.25)]"
          />
          <div className="space-y-2">
            <h2 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">
              Welcome to ORBIT
            </h2>
            <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
              Ask thoughtful questions, explore ideas, or iterate on your work. I'll respond instantly and evolve with your conversation.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto px-6 sm:px-10 relative"
      onScroll={handleScroll}
    >
      {/* Top gradient fade */}
      <div className="pointer-events-none sticky top-0 left-0 right-0 h-8 bg-gradient-to-b from-white/20 to-transparent dark:from-slate-950/20 dark:to-transparent z-10" />

      <div className="max-w-3xl mx-auto pt-1 pb-2 space-y-4">
        {messages.map((message) => (
          <Message
            key={message.id}
            message={message}
            onRegenerate={onRegenerate}
          />
        ))}

        <div ref={messagesEndRef} className="h-8" />
      </div>
      {/* Bottom gradient fade */}
      <div className="pointer-events-none sticky bottom-0 left-0 right-0 h-16 bg-gradient-to-t from-white/40 to-transparent dark:from-slate-950/30 dark:to-transparent" />
    </div>
  );
}
