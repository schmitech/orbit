import React, { useEffect, useRef, useMemo } from 'react';
import { Copy, Check } from 'lucide-react';
import clsx from 'clsx';
import { Message as MessageType } from '../store/chatStore';
import { MarkdownRenderer } from '@schmitech/markdown-renderer';
import { sanitizeMessageContent, truncateLongContent } from '../utils/contentFiltering';

type ThemeMode = 'light' | 'dark';

const parseHexColor = (color?: string): [number, number, number] | null => {
  if (!color) return null;
  let hex = color.trim();
  if (!hex.startsWith('#')) {
    return null;
  }
  hex = hex.replace('#', '');
  if (hex.length === 3) {
    hex = hex.split('').map(char => char + char).join('');
  }
  if (hex.length !== 6) {
    return null;
  }
  const int = parseInt(hex, 16);
  return [(int >> 16) & 255, (int >> 8) & 255, int & 255];
};

const isColorDark = (color?: string): boolean => {
  const rgb = parseHexColor(color);
  if (!rgb) {
    return false;
  }
  const [r, g, b] = rgb.map(value => value / 255);
  const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return luminance < 0.5;
};

const resolveThemeMode = (theme: any): ThemeMode => {
  const declaredMode = theme?.mode;
  if (declaredMode === 'dark' || declaredMode === 'light') {
    return declaredMode;
  }
  if (declaredMode === 'system' && typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return isColorDark(theme?.background) ? 'dark' : 'light';
};

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
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  hasBeenAnimated: (id: string) => boolean;
  typingProgressRef: React.MutableRefObject<Map<string, number>>;
  isTypingRef: React.MutableRefObject<boolean>;
  setIsAnimating: (value: boolean) => void;
  formatTime: (date: Date) => string;
  lastMessageRef: React.RefObject<HTMLDivElement | null>;
}

/**
 * Message component handles individual message rendering
 * Supports both user and assistant messages with different styling
 */
const MessageComponent: React.FC<MessageProps> = ({
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
  const themeMode = useMemo<ThemeMode>(() => resolveThemeMode(theme), [theme]);
  const syntaxTheme: 'dark' | 'light' = themeMode === 'dark' ? 'dark' : 'light';
  const markdownRendererClassName = useMemo(
    () => clsx('w-full min-w-0', themeMode),
    [themeMode]
  );
  const safeAssistantContent = useMemo(
    () => truncateLongContent(sanitizeMessageContent(message.content || '')),
    [message.content]
  );
  // Generate timestamp (using relative offset since messages lack explicit timestamps)
  const timestamp = new Date();
  timestamp.setMinutes(timestamp.getMinutes() - (messagesLength - index));

  // Ref for the markdown wrapper to check overflow
  const markdownWrapperRef = useRef<HTMLDivElement>(null);

  // Mark message as animated when streaming completes (isLoading becomes false and message has content)
  useEffect(() => {
    if (
      isLatestAssistantMessage &&
      !hasBeenAnimated(message.id) &&
      message.content &&
      !showTypingAnimation
    ) {
      // Mark as animated when streaming is done (showTypingAnimation is false means isLoading is false)
      onMarkMessageAnimated(message.id, messagesLength, scrollToBottom);
    }
  }, [isLatestAssistantMessage, message.id, message.content, showTypingAnimation, onMarkMessageAnimated, messagesLength, scrollToBottom, hasBeenAnimated]);

  // Force scrollbar to be visible when content overflows (workaround for macOS hiding scrollbars)
  useEffect(() => {
    const wrapper = markdownWrapperRef.current;
    if (!wrapper || message.role !== 'assistant' || !message.content) return;

    const checkOverflow = () => {
      const hasHorizontalOverflow = wrapper.scrollWidth > wrapper.clientWidth;
      if (hasHorizontalOverflow) {
        // Add class to ensure visibility
        wrapper.classList.add('has-horizontal-scroll');
        
        // Force scrollbar to appear on macOS by programmatically scrolling
        // This triggers the system to show the scrollbar
        const currentScroll = wrapper.scrollLeft;
        // Temporarily scroll slightly to trigger scrollbar visibility
        wrapper.scrollLeft = currentScroll + 1;
        // Use requestAnimationFrame to ensure the scroll happens
        requestAnimationFrame(() => {
          wrapper.scrollLeft = currentScroll;
          // Trigger another small scroll to keep scrollbar visible
          setTimeout(() => {
            wrapper.scrollLeft = currentScroll + 0.5;
            requestAnimationFrame(() => {
              wrapper.scrollLeft = currentScroll;
            });
          }, 50);
        });
      } else {
        wrapper.classList.remove('has-horizontal-scroll');
      }
    };

    // Check immediately and after delays (to account for markdown rendering)
    checkOverflow();
    const timeoutId = setTimeout(checkOverflow, 100);
    const timeoutId2 = setTimeout(checkOverflow, 500);
    const timeoutId3 = setTimeout(checkOverflow, 1000);

    // Also check on resize and when content changes
    const resizeObserver = new ResizeObserver(checkOverflow);
    resizeObserver.observe(wrapper);

    // Also check when mouse enters the wrapper (to show scrollbar on hover)
    const handleMouseEnter = () => {
      if (wrapper.scrollWidth > wrapper.clientWidth) {
        checkOverflow();
      }
    };

    wrapper.addEventListener('mouseenter', handleMouseEnter);

    return () => {
      clearTimeout(timeoutId);
      clearTimeout(timeoutId2);
      clearTimeout(timeoutId3);
      resizeObserver.disconnect();
      wrapper.removeEventListener('mouseenter', handleMouseEnter);
    };
  }, [message.content, message.role]);

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
          color: message.role === 'user' ? theme.message.userText : (theme.message.assistantText || theme.text.primary),
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
            <div className="flex items-center gap-2">
              <div className="typing-dots-container">
                <div className="typing-dot"></div>
                <div className="typing-dot"></div>
                <div className="typing-dot"></div>
              </div>
            </div>
          ) : (
            <div 
              ref={markdownWrapperRef}
              className="markdown-content-wrapper"
              style={{
                overflowX: 'scroll', // Use 'scroll' instead of 'auto' to always show scrollbar when content overflows
                overflowY: 'visible',
                width: '100%',
                maxWidth: '100%',
                minWidth: 0,
                // Ensure scrollbar is always visible when content overflows
                scrollbarWidth: 'thin',
                scrollbarColor: 'rgba(0, 0, 0, 0.4) rgba(0, 0, 0, 0.15)',
              }}
            >
              <MarkdownRenderer
                content={safeAssistantContent}
                className={markdownRendererClassName}
                syntaxTheme={syntaxTheme}
              />
            </div>
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

// Memoize Message component to prevent re-renders when other messages or input changes
export const Message = React.memo(MessageComponent, (prevProps, nextProps) => {
  // Only re-render if this specific message's data changes
  return (
    prevProps.message.id === nextProps.message.id &&
    prevProps.message.content === nextProps.message.content &&
    prevProps.message.role === nextProps.message.role &&
    prevProps.index === nextProps.index &&
    prevProps.isLatestAssistantMessage === nextProps.isLatestAssistantMessage &&
    prevProps.showTypingAnimation === nextProps.showTypingAnimation &&
    prevProps.copiedMessageId === nextProps.copiedMessageId &&
    prevProps.messagesLength === nextProps.messagesLength &&
    prevProps.theme === nextProps.theme
  );
});
