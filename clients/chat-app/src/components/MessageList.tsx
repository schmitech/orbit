import React, { useEffect, useRef, useState } from 'react';
import { Message } from './Message';
import { Message as MessageType } from '../types';
import { useSettings } from '../contexts/SettingsContext';
import { playSoundEffect } from '../utils/soundEffects';

interface MessageListProps {
  messages: MessageType[];
  onRegenerate?: (messageId: string) => void;
  isLoading?: boolean;
}

export function MessageList({ messages, onRegenerate, isLoading }: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const prevMessageCountRef = useRef(messages.length);
  const prevLastMessageContentRef = useRef<string>('');
  const prevIsLoadingRef = useRef(isLoading);
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);
  const { settings } = useSettings();

  // Check if user has scrolled up manually
  const handleScroll = () => {
    if (!containerRef.current) return;
    
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    // Only disable auto-scroll if user has scrolled significantly up (more than 200px)
    const isNearBottom = distanceFromBottom < 200;
    setShouldAutoScroll(isNearBottom);
  };

  // Scroll to bottom helper function
  const scrollToBottom = (behavior: ScrollBehavior = 'smooth') => {
    // Use double requestAnimationFrame to ensure DOM has fully updated
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (messagesEndRef.current) {
          messagesEndRef.current.scrollIntoView({ behavior });
        } else if (containerRef.current) {
          // Fallback: scroll container directly
          containerRef.current.scrollTop = containerRef.current.scrollHeight;
        }
      });
    });
  };

  // Auto-scroll when messages change (new message added or content updated)
  useEffect(() => {
    const messageCount = messages.length;
    const hadMessages = prevMessageCountRef.current;
    const hasNewMessage = messageCount > hadMessages;
    const lastMessage = messages[messages.length - 1];
    const lastMessageContent = lastMessage?.content || '';
    const contentChanged = lastMessageContent !== prevLastMessageContentRef.current;

    // Always scroll when:
    // 1. A new message is added (user sends message or assistant response starts)
    // 2. The last message is streaming (response is being received)
    // 3. The content of the last message changed (streaming update)
    if (hasNewMessage || lastMessage?.isStreaming || (contentChanged && lastMessage?.role === 'assistant')) {
      // Force scroll for new messages or when streaming, regardless of shouldAutoScroll
      // This ensures we always scroll when user sends a message or receives a response
      // Use 'auto' for immediate scroll on new messages, 'smooth' for streaming updates
      scrollToBottom(hasNewMessage ? 'auto' : 'smooth');
      // Reset shouldAutoScroll to true when new content arrives
      setShouldAutoScroll(true);
    } else if (shouldAutoScroll && contentChanged) {
      // If user is near bottom and content changed, scroll smoothly
      scrollToBottom('smooth');
    }

    prevMessageCountRef.current = messageCount;
    prevLastMessageContentRef.current = lastMessageContent;
  }, [messages, shouldAutoScroll]);

  // Scroll to bottom when loading starts (new assistant message being prepared)
  useEffect(() => {
    if (isLoading) {
      // Always scroll when loading starts, regardless of scroll position
      // This ensures we scroll when user sends a message and response is being prepared
      scrollToBottom('auto');
      setShouldAutoScroll(true);
    }
  }, [isLoading]);

  // Play sound when assistant message is received (loading completes)
  useEffect(() => {
    // When loading transitions from true to false, assistant message is complete
    if (prevIsLoadingRef.current && !isLoading) {
      const lastMessage = messages[messages.length - 1];
      // Only play sound if the last message is from assistant and has content
      if (lastMessage?.role === 'assistant' && lastMessage.content) {
        playSoundEffect('messageReceived', settings.soundEnabled);
      }
    }
    prevIsLoadingRef.current = isLoading;
  }, [isLoading, messages, settings.soundEnabled]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center text-lg text-gray-500 dark:text-[#bfc2cd] px-6">
          <p className="text-xl">Your messages will appear here.</p>
          <p className="mt-1 text-lg">Start the conversation by sending a prompt below.</p>
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
