import React from 'react';
import { Copy, Check } from 'lucide-react';
import clsx from 'clsx';
import { Message as MessageType } from '../store/chatStore';
import { MarkdownRenderer } from '../shared/MarkdownComponents';
import { TypingEffect } from './TypingEffect';

export interface MessageProps {
  message: MessageType;
  index: number;
  isLatestAssistantMessage: boolean;
  showTypingAnimation: boolean;
  theme: any; // TODO: Type this properly
  copiedMessageId: string | null;
  onCopyToClipboard: (text: string, messageId: string) => void;
  onMarkMessageAnimated: (id: string, messagesLength: number, scrollToBottom: () => void) => void;
  messagesLength: number;
  scrollToBottom: () => void;
  inputRef: React.RefObject<HTMLTextAreaElement>;
  hasBeenAnimated: (id: string) => boolean;
  typingProgressRef: React.MutableRefObject<Map<string, number>>;
  isTypingRef: React.MutableRefObject<boolean>;
  setIsAnimating: (value: boolean) => void;
  formatTime: (date: Date) => string;
  lastMessageRef: React.RefObject<HTMLDivElement>;
}

/**
 * Message component handles individual message rendering
 * Supports both user and assistant messages with different styling
 */
export const Message: React.FC<MessageProps> = ({
  message,
  index,
  isLatestAssistantMessage,
  showTypingAnimation,
  theme,
  copiedMessageId,
  onCopyToClipboard,
  onMarkMessageAnimated,
  messagesLength,
  scrollToBottom,
  inputRef,
  hasBeenAnimated,
  typingProgressRef,
  isTypingRef,
  setIsAnimating,
  formatTime,
  lastMessageRef,
}) => {
  // Generate timestamp (using relative offset since messages lack explicit timestamps)
  const timestamp = new Date();
  timestamp.setMinutes(timestamp.getMinutes() - (messagesLength - index));

  return (
    <div 
      className={clsx(
        "flex",
        message.role === 'user' ? "justify-end" : "justify-start"
      )}
      ref={index === messagesLength - 1 ? lastMessageRef : null}
    >
      <div 
        className={clsx(
          "max-w-[85%] rounded-xl p-4 shadow-sm"
        )}
        style={{
          background: message.role === 'user' ? theme.message.user : theme.message.assistant,
          color: message.role === 'user' ? theme.message.userText : theme.text.primary,
          border: message.role === 'assistant' ? `1px solid ${theme.input.border}` : 'none',
          width: '100%',
          maxWidth: '85%',
          wordWrap: 'break-word',
          overflowWrap: 'anywhere',
          borderRadius: message.role === 'assistant' ? '0.75rem' : undefined
        }}
      >
        {/* Message Content */}
        {message.role === 'assistant' ? (
          !message.content ? (
            <div className="text-gray-500">
              <span className="font-medium">Thinking</span>
              <span className="animate-dots ml-1">
                <span className="dot">.</span>
                <span className="dot">.</span>
                <span className="dot">.</span>
              </span>
            </div>
          ) : !hasBeenAnimated(message.id) && isLatestAssistantMessage ? (
            <TypingEffect
              content={message.content}
              onComplete={() => onMarkMessageAnimated(message.id, messagesLength, scrollToBottom)}
              messageId={message.id}
              inputRef={inputRef}
              hasBeenAnimated={hasBeenAnimated}
              typingProgressRef={typingProgressRef}
              isTypingRef={isTypingRef}
              setIsAnimating={setIsAnimating}
              scrollToBottom={scrollToBottom}
              isStreaming={showTypingAnimation}
            />
          ) : (
            <MarkdownRenderer content={message.content} />
          )
        ) : (
          <p className="text-base" style={{ 
            overflowWrap: 'anywhere', 
            wordBreak: 'break-word',
            whiteSpace: 'pre-wrap',
            width: '100%'
          }}>
            {message.content}
          </p>
        )}
        
        {/* Message Footer with Timestamp and Copy Button */}
        <div className={clsx(
          "flex text-xs mt-2",
          message.role === 'user' ? "justify-start text-white/70" : "justify-between text-gray-400"
        )}>
          <span>{formatTime(timestamp)}</span>
          
          {message.role === 'assistant' && !showTypingAnimation && (
            <div className="relative">
              <button 
                onClick={() => onCopyToClipboard(message.content, message.id)}
                className="ml-2 p-1 rounded-full"
                style={{
                  color: theme.text.secondary,
                  transition: 'color 0.2s ease',
                  background: 'transparent',
                  border: 'none',
                  outline: 'none'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.setProperty('color', theme.text.primary, 'important');
                  e.currentTarget.style.setProperty('background', 'transparent', 'important');
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.setProperty('color', theme.text.secondary, 'important');
                  e.currentTarget.style.setProperty('background', 'transparent', 'important');
                }}
                onMouseDown={(e) => {
                  e.currentTarget.style.setProperty('color', theme.text.primary, 'important');
                  e.currentTarget.style.setProperty('background', 'transparent', 'important');
                  e.currentTarget.style.setProperty('transform', 'none', 'important');
                }}
                onMouseUp={(e) => {
                  e.currentTarget.style.setProperty('color', theme.text.primary, 'important');
                  e.currentTarget.style.setProperty('background', 'transparent', 'important');
                }}
                aria-label="Copy to clipboard"
              >
                {copiedMessageId === message.id ? <Check size={16} /> : <Copy size={16} />}
              </button>
              {copiedMessageId === message.id && (
                <div
                  className="absolute bottom-full right-0 mb-1 px-2 py-1 text-xs rounded-md shadow-sm animate-fade-in-out whitespace-nowrap"
                  style={{
                    backgroundColor: theme.secondary,
                    color: theme.text.inverse
                  }}
                >
                  Copied!
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
