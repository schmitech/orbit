import { useEffect, useMemo, useRef, useCallback } from 'react';
import { Message } from './Message';
import { Message as MessageType } from '../types';
import { useSettings } from '../contexts/SettingsContext';
import { playSoundEffect } from '../utils/soundEffects';
import './MessageList.css';


interface MessageListProps {
  messages: MessageType[];
  onRegenerate?: (messageId: string) => void;
  onStartThread?: (messageId: string, sessionId: string) => void;
  onSendThreadMessage?: (threadId: string, parentMessageId: string, content: string) => Promise<void> | void;
  sessionId?: string;
  isLoading?: boolean;
}

export function MessageList({
  messages,
  onRegenerate,
  onStartThread,
  onSendThreadMessage,
  sessionId,
  isLoading
}: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const prevMessageCountRef = useRef(messages.length);
  const prevLastMessageContentRef = useRef<string>('');
  const prevIsLoadingRef = useRef(isLoading);
  const shouldAutoScrollRef = useRef(true);
  const { settings } = useSettings();

  const { topLevelMessages, threadLookup } = useMemo(() => {
    const lookup = new Map<string, MessageType[]>();
    const roots: MessageType[] = [];

    messages.forEach(msg => {
      if (msg.isThreadMessage && msg.parentMessageId) {
        // Add all thread messages (both user and assistant) to the lookup
        // They will be displayed in chronological order in the thread replies
        const existing = lookup.get(msg.parentMessageId) || [];
        lookup.set(msg.parentMessageId, [...existing, msg]);
        // Filter out all thread messages (both user and assistant) from top-level
        return;
      }
      
      roots.push(msg);
    });

    return { topLevelMessages: roots, threadLookup: lookup };
  }, [messages]);

  // Check if user has scrolled up manually
  const handleScroll = () => {
    if (!containerRef.current) return;
    
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    // Only disable auto-scroll if user has scrolled significantly up (more than 200px)
    const isNearBottom = distanceFromBottom < 200;
    shouldAutoScrollRef.current = isNearBottom;
  };

  // Scroll to bottom helper function - uses direct scrollTop for stability during streaming
  const scrollToBottom = useCallback(() => {
    // Use requestAnimationFrame for smooth visual update
    // Direct scrollTop is instantaneous (no animation) so won't cause bounce
    requestAnimationFrame(() => {
      if (containerRef.current) {
        containerRef.current.scrollTop = containerRef.current.scrollHeight;
      }
    });
  }, []);

  // Auto-scroll when messages change (new message added or content updated)
  useEffect(() => {
    const messageCount = messages.length;
    const hadMessages = prevMessageCountRef.current;
    const hasNewMessage = messageCount > hadMessages;
    const lastMessage = messages[messages.length - 1];
    const lastMessageContent = lastMessage?.content || '';
    const contentChanged = lastMessageContent !== prevLastMessageContentRef.current;
    const isCurrentlyStreaming = lastMessage?.isStreaming ?? false;

    // Always scroll when:
    // 1. A new message is added (user sends message or assistant response starts)
    // 2. The last message is streaming (response is being received)
    // 3. The content of the last message changed (streaming update)
    if (hasNewMessage) {
      // Immediate scroll for new messages
      scrollToBottom();
      shouldAutoScrollRef.current = true;
    } else if (isCurrentlyStreaming && contentChanged) {
      // Always scroll during streaming to follow the text
      scrollToBottom();
      // Keep auto-scroll enabled during streaming
      shouldAutoScrollRef.current = true;
    } else if (shouldAutoScrollRef.current && contentChanged) {
      // Scroll when user is near bottom and content changed (non-streaming)
      scrollToBottom();
    }

    prevMessageCountRef.current = messageCount;
    prevLastMessageContentRef.current = lastMessageContent;
  }, [messages, scrollToBottom]);

  // Scroll to bottom when loading starts (new assistant message being prepared)
  useEffect(() => {
    if (isLoading) {
      // Always scroll when loading starts, regardless of scroll position
      // This ensures we scroll when user sends a message and response is being prepared
      scrollToBottom();
      shouldAutoScrollRef.current = true;
    }
  }, [isLoading, scrollToBottom]);

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

  if (topLevelMessages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center px-4 sm:px-6">
        <div className="text-center text-lg text-gray-500 dark:text-[#bfc2cd]">
          <p className="text-xl">Your messages will appear here.</p>
          <p className="mt-1 text-lg">Start the conversation by sending a prompt below.</p>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="message-list flex-1 overflow-y-auto pb-6 pt-4 sm:pt-6"
      onScroll={handleScroll}
    >
      <div className="space-y-6 px-2 sm:px-4 md:px-0">
        {topLevelMessages.map((message) => (
          <div
            key={message.id}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            style={{ contentVisibility: 'auto', containIntrinsicSize: '420px' }}
          >
            <Message
              message={message}
              onRegenerate={onRegenerate}
              onStartThread={onStartThread}
              onSendThreadMessage={onSendThreadMessage}
              threadMessages={threadLookup.get(message.id)}
              sessionId={sessionId}
              isThreadSendDisabled={isLoading}
            />
          </div>
        ))}

        <div ref={messagesEndRef} className="h-8" />
      </div>
    </div>
  );
}
