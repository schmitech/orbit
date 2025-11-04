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
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center text-base text-gray-500 dark:text-[#bfc2cd] px-6">
          <p>Your messages will appear here.</p>
          <p className="mt-2">Start the conversation by sending a prompt below.</p>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto py-6"
      onScroll={handleScroll}
    >
      <div className="space-y-6 px-4">
        {messages.map((message) => (
          <Message
            key={message.id}
            message={message}
            onRegenerate={onRegenerate}
          />
        ))}

        <div ref={messagesEndRef} className="h-8" />
      </div>
    </div>
  );
}
