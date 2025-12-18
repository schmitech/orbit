import React, { useMemo } from 'react';
import { ChevronUp, ChevronDown } from 'lucide-react';
import { Message as MessageType } from '../store/chatStore';
import { Message } from './Message';
import { CHAT_CONSTANTS } from '../shared/styles';
import { ChatConfig } from '../config/index';

export interface MessagesListProps {
  messages: MessageType[];
  isLoading: boolean;
  theme: ChatConfig['theme'];
  currentConfig: ChatConfig;
  showScrollTop: boolean;
  showScrollBottom: boolean;
  isAnimating: boolean;
  messagesContainerRef: React.RefObject<HTMLDivElement>;
  messagesEndRef: React.RefObject<HTMLDivElement>;
  scrollToTop: () => void;
  scrollToBottom: () => void;
  handleScroll: () => void;
  sendMessage: (message: string) => void;
  focusInput: () => void;
  copiedMessageId: string | null;
  onCopyToClipboard: (text: string, messageId: string) => void;
  onMarkMessageAnimated: (id: string, messagesLength: number, scrollToBottom: () => void) => void;
  inputRef: React.RefObject<HTMLTextAreaElement>;
  hasBeenAnimated: (id: string) => boolean;
  typingProgressRef: React.MutableRefObject<Map<string, number>>;
  isTypingRef: React.MutableRefObject<boolean>;
  setIsAnimating: (value: boolean) => void;
  formatTime: (date: Date) => string;
  lastMessageRef: React.RefObject<HTMLDivElement>;
  maxSuggestedQuestionLength?: number;
  maxSuggestedQuestionQueryLength?: number;
}

/**
 * MessagesList component handles the messages container area
 * Includes empty state, scroll buttons, loading states, and message rendering
 */
const MessagesListComponent: React.FC<MessagesListProps> = ({
  messages,
  isLoading,
  theme,
  currentConfig,
  showScrollTop,
  showScrollBottom,
  isAnimating,
  messagesContainerRef,
  messagesEndRef,
  scrollToTop,
  scrollToBottom,
  handleScroll,
  sendMessage,
  focusInput,
  copiedMessageId,
  onCopyToClipboard,
  onMarkMessageAnimated,
  inputRef,
  hasBeenAnimated,
  typingProgressRef,
  isTypingRef,
  setIsAnimating,
  formatTime,
  lastMessageRef,
  maxSuggestedQuestionLength,
  maxSuggestedQuestionQueryLength,
}) => {
  // Helper function to ensure opaque background
  const getOpaqueBackground = () => {
    const bg = theme.input.background;
    if (!bg || bg === 'transparent' || bg.includes('rgba') || bg.includes('hsla')) {
      return '#ffffff';
    }
    if (bg.match(/^#[0-9A-Fa-f]{8}$/)) {
      return bg.substring(0, 7);
    }
    return bg;
  };

  const opaqueBackground = getOpaqueBackground();

  // Memoize the messages list to prevent re-rendering when input changes
  const messagesList = useMemo(() => {
    return messages.map((msg: MessageType, index: number) => {
      const isLatestAssistantMessage = msg.role === 'assistant' && index === messages.length - 1;
      const showTypingAnimation = isLatestAssistantMessage && isLoading;
      
      return (
        <Message
          key={msg.id}
          message={msg}
          index={index}
          isLatestAssistantMessage={isLatestAssistantMessage}
          showTypingAnimation={showTypingAnimation}
          theme={theme}
          copiedMessageId={copiedMessageId}
          onCopyToClipboard={onCopyToClipboard}
          onMarkMessageAnimated={onMarkMessageAnimated}
          messagesLength={messages.length}
          scrollToBottom={scrollToBottom}
          inputRef={inputRef}
          hasBeenAnimated={hasBeenAnimated}
          typingProgressRef={typingProgressRef}
          isTypingRef={isTypingRef}
          setIsAnimating={setIsAnimating}
          formatTime={formatTime}
          lastMessageRef={lastMessageRef}
        />
      );
    });
  }, [
    messages,
    isLoading,
    theme,
    copiedMessageId,
    onCopyToClipboard,
    onMarkMessageAnimated,
    scrollToBottom,
    inputRef,
    hasBeenAnimated,
    typingProgressRef,
    isTypingRef,
    setIsAnimating,
    formatTime,
    lastMessageRef,
  ]);

  return (
    <div 
      className="flex-1 overflow-hidden relative" 
      style={{ 
        background: opaqueBackground,
        backgroundColor: opaqueBackground,
        isolation: 'isolate'
      }}
    >
      {/* Additional background layer to ensure no bleed-through */}
      <div 
        className="absolute inset-0"
        style={{
          background: opaqueBackground,
          backgroundColor: opaqueBackground,
          zIndex: 0,
          pointerEvents: 'none'
        }}
      />
      
      <div
        ref={messagesContainerRef}
        className="h-full w-full overflow-y-auto scroll-smooth relative messages-container"
        style={{
          background: opaqueBackground,
          backgroundColor: opaqueBackground,
          overflowY: 'auto',
          overflowX: 'hidden',
          height: '100%',
          maxHeight: '100%',
          boxSizing: 'border-box',
          paddingTop: '8px',
          paddingLeft: '8px',
          paddingRight: '8px',
          paddingBottom: '0px',
          position: 'relative',
          zIndex: 1
        }}
        onScroll={handleScroll}
      >
      {/* Scroll to Top Button */}
      {showScrollTop && (
        <button
          onClick={scrollToTop}
          className="sticky top-3 left-[calc(100%-48px)] z-10 flex items-center justify-center p-2 rounded-full shadow-md"
          style={{
            backgroundColor: theme.primary,
            color: theme.text.inverse
          }}
          aria-label="Scroll to top"
          title="Scroll to top"
        >
          <ChevronUp size={CHAT_CONSTANTS.BUTTON_SIZES.ICON_SIZES.BUTTON} />
        </button>
      )}

      {/* Scroll to Bottom Button */}
      {showScrollBottom && !isAnimating && (
        <button
          onClick={() => scrollToBottom()}
          className="sticky bottom-3 left-[calc(100%-48px)] z-10 flex items-center justify-center p-2 rounded-full shadow-md"
          style={{
            backgroundColor: theme.primary,
            color: theme.text.inverse
          }}
          aria-label="Scroll to bottom"
          title="Scroll to bottom"
        >
          <ChevronDown size={CHAT_CONSTANTS.BUTTON_SIZES.ICON_SIZES.BUTTON} />
        </button>
      )}

      {/* Empty State - Welcome Screen */}
      {messages.length === 0 ? (
        <div className="py-2">
          <div className="w-full px-3 mb-6">
            <div className="max-w-lg mx-auto sm:max-w-2xl">
              <h4 className="font-bold text-xl mb-2 px-1 mt-3" style={{ color: theme.text.primary }}>{currentConfig.welcome.title}</h4>
              <p className="text-lg px-1" style={{ color: theme.text.secondary }}>
                {currentConfig.welcome.description}
              </p>
            </div>
          </div>
          <div className="w-full px-3">
            <div className="flex flex-col gap-3 max-w-lg mx-auto sm:max-w-2xl">
              {currentConfig.suggestedQuestions.slice(0, 5).map((question: any, index: number) => {
                const maxQueryLen = maxSuggestedQuestionQueryLength ?? CHAT_CONSTANTS.MAX_SUGGESTED_QUESTION_QUERY_LENGTH;
                const maxDisplayLen = maxSuggestedQuestionLength ?? CHAT_CONSTANTS.MAX_SUGGESTED_QUESTION_LENGTH;
                const safeQuery = question.query?.length > maxQueryLen
                  ? question.query.substring(0, maxQueryLen)
                  : question.query;
                const displayText = question.text?.length > maxDisplayLen
                  ? `${question.text.substring(0, maxDisplayLen)}...`
                  : question.text;

                return (
                  <button
                    key={index}
                    onClick={() => {
                      sendMessage(safeQuery);
                      setTimeout(() => {
                        focusInput();
                      }, CHAT_CONSTANTS.ANIMATIONS.TOGGLE_DELAY);
                    }}
                    className="group w-full text-left transition-all duration-300 ease-in-out transform hover:scale-[1.02] active:scale-[0.98]"
                    style={{
                      minHeight: '48px',
                      background: 'transparent',
                    }}
                    title={safeQuery}
                  >
                    <div
                      className="w-full px-4 py-3 rounded-xl border transition-all duration-300 ease-in-out cursor-pointer group-hover:shadow-md group-active:shadow-sm"
                      style={{
                        background: theme.suggestedQuestions.questionsBackground || '#ffffff',
                        borderColor: theme.suggestedQuestions.text || '#e5e7eb',
                        color: theme.suggestedQuestions.text,
                        fontWeight: 500,
                        boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)',
                      }}
                      onMouseEnter={(e) => {
                        // Apply highlighted background immediately on hover
                        e.currentTarget.style.background = theme.suggestedQuestions.highlightedBackground || '#f8fafc';
                        e.currentTarget.style.borderColor = theme.primary;
                        e.currentTarget.style.transform = 'translateY(-1px)';
                        e.currentTarget.style.boxShadow = '0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)';
                        
                        // Change text color to ensure good contrast with highlighted background
                        const textSpan = e.currentTarget.querySelector('span');
                        if (textSpan) {
                          // Use a darker color for better readability on light backgrounds
                          textSpan.style.color = '#1F2937'; // Dark gray for good contrast
                        }
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = theme.suggestedQuestions.questionsBackground || '#ffffff';
                        e.currentTarget.style.borderColor = theme.suggestedQuestions.text || '#e5e7eb';
                        e.currentTarget.style.transform = 'translateY(0)';
                        e.currentTarget.style.boxShadow = '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)';
                        
                        // Reset text color back to original theme color
                        const textSpan = e.currentTarget.querySelector('span');
                        if (textSpan) {
                          textSpan.style.color = theme.suggestedQuestions.text || '#1F2937';
                          // Also remove any inline styles that might persist
                          textSpan.style.removeProperty('color');
                        }
                      }}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-base leading-relaxed transition-colors duration-200">
                          {displayText}
                        </span>
                        <div 
                          className="opacity-0 group-hover:opacity-100 transition-opacity duration-200 transform translate-x-1 group-hover:translate-x-0"
                          style={{ color: theme.primary }}
                        >
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M5 12h14"/>
                            <path d="m12 5 7 7-7 7"/>
                          </svg>
                        </div>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      ) : (
        /* Messages List */
        <div className="space-y-3">
          {messagesList}
          
          {/* Loading State when no messages */}
          {isLoading && messages.length === 0 && (
            <div className="flex justify-start">
              <div className="bg-white border border-gray-200 rounded-xl rounded-tl-none max-w-[85%] p-4 shadow-sm">
                <div className="text-gray-500">
                  <span className="font-medium text-lg">Thinking</span>
                  <span className="animate-dots ml-1">
                    <span className="dot">.</span>
                    <span className="dot">.</span>
                    <span className="dot">.</span>
                  </span>
                </div>
              </div>
            </div>
          )}
          
          {/* Messages End Ref for Scrolling */}
          <div ref={messagesEndRef} />
        </div>
      )}
      </div>
    </div>
  );
};

// Memoize MessagesList to prevent re-renders when input message changes
export const MessagesList = React.memo(MessagesListComponent, (prevProps, nextProps) => {
  // Only re-render if these props change
  return (
    prevProps.messages === nextProps.messages &&
    prevProps.isLoading === nextProps.isLoading &&
    prevProps.showScrollTop === nextProps.showScrollTop &&
    prevProps.showScrollBottom === nextProps.showScrollBottom &&
    prevProps.isAnimating === nextProps.isAnimating &&
    prevProps.copiedMessageId === nextProps.copiedMessageId &&
    prevProps.theme === nextProps.theme &&
    prevProps.currentConfig === nextProps.currentConfig &&
    prevProps.maxSuggestedQuestionLength === nextProps.maxSuggestedQuestionLength &&
    prevProps.maxSuggestedQuestionQueryLength === nextProps.maxSuggestedQuestionQueryLength
  );
});
