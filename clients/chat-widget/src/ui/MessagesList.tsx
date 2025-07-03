import React from 'react';
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
  copiedMessageId: number | null;
  onCopyToClipboard: (text: string, messageIndex: number) => void;
  onMarkMessageAnimated: (index: number, messagesLength: number, scrollToBottom: () => void) => void;
  inputRef: React.RefObject<HTMLTextAreaElement>;
  hasBeenAnimated: (index: number) => boolean;
  typingProgressRef: React.MutableRefObject<Map<number, number>>;
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
export const MessagesList: React.FC<MessagesListProps> = ({
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
        <div className="py-4">
          <div className="w-full px-3 mb-6">
            <div className="max-w-lg mx-auto sm:max-w-2xl">
              <h4 className="font-bold text-xl mb-4 px-1" style={{ color: theme.text.primary }}>{currentConfig.welcome.title}</h4>
              <p className="text-lg px-1 py-2" style={{ color: theme.text.secondary }}>
                {currentConfig.welcome.description}
              </p>
            </div>
          </div>
          <div className="w-full px-3">
            <div className="flex flex-col gap-2 max-w-lg mx-auto sm:max-w-2xl">
              {currentConfig.suggestedQuestions.slice(0, 6).map((question: any, index: number) => {
                const maxQueryLen = maxSuggestedQuestionQueryLength ?? CHAT_CONSTANTS.MAX_SUGGESTED_QUESTION_QUERY_LENGTH;
                const maxDisplayLen = maxSuggestedQuestionLength ?? CHAT_CONSTANTS.MAX_SUGGESTED_QUESTION_LENGTH;
                const safeQuery = question.query?.length > maxQueryLen
                  ? question.query.substring(0, maxQueryLen)
                  : question.query;
                const displayText = question.text?.length > maxDisplayLen
                  ? `${question.text.substring(0, maxDisplayLen)}...`
                  : question.text;

                return (
                  <div
                    key={index}
                    className="flex items-center w-full px-1 py-1.5 text-lg rounded-xl"
                    style={{
                      minHeight: '36px',
                      background: 'transparent',
                    }}
                  >
                    <span
                      onClick={() => {
                        sendMessage(safeQuery);
                        setTimeout(() => {
                          focusInput();
                        }, CHAT_CONSTANTS.ANIMATIONS.TOGGLE_DELAY);
                      }}
                      className="truncate hover:text-primary transition-colors duration-200 cursor-pointer w-full text-lg"
                      style={{
                        color: theme.suggestedQuestions.text,
                        fontWeight: 500,
                      }}
                      title={safeQuery}
                    >
                      {displayText}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ) : (
        /* Messages List */
        <div className="space-y-3">
          {messages.map((msg: MessageType, index: number) => {
            const isLatestAssistantMessage = msg.role === 'assistant' && index === messages.length - 1;
            const showTypingAnimation = isLatestAssistantMessage && isLoading;
            
            return (
              <Message
                key={index}
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
          })}
          
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