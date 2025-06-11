import React from 'react';
import { ChevronUp, ChevronDown, MessageCircle } from 'lucide-react';
import { Message as MessageType } from '../store/chatStore';
import { ChatIcon } from '../shared/ChatIcon';
import { Message } from './Message';
import { CHAT_CONSTANTS } from '../shared/styles';

export interface MessagesListProps {
  messages: MessageType[];
  isLoading: boolean;
  theme: any; // TODO: Type this properly
  currentConfig: any; // TODO: Type this properly
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
  return (
    <div
      ref={messagesContainerRef}
      className="flex-1 p-2 overflow-y-auto scroll-smooth relative messages-container"
      style={{
        background: theme.input.background,
        overflowY: 'auto'
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
        <div className="text-center py-4">
          <ChatIcon
            iconName={currentConfig.icon}
            size={CHAT_CONSTANTS.BUTTON_SIZES.ICON_SIZES.WELCOME}
            className="mx-auto mb-2"
            style={{ color: theme.iconColor }}
          />
          <h4 className="font-medium text-2xl mb-3" style={{ color: theme.text.primary }}>{currentConfig.welcome.title}</h4>
          <div className="w-full px-3 mb-4">
            <div className="max-w-lg mx-auto sm:max-w-2xl">
              <p className="text-xl text-left px-1 py-2" style={{ color: theme.text.secondary }}>
                {currentConfig.welcome.description}
              </p>
            </div>
          </div>
          <div className="w-full px-2">
            <div className="grid gap-2 max-w-2xl mx-auto grid-cols-1 sm:grid-cols-2">
              {currentConfig.suggestedQuestions.map((question: any, index: number) => (
                <div
                  key={index}
                  onClick={() => {
                    const maxQueryLen = maxSuggestedQuestionQueryLength ?? CHAT_CONSTANTS.MAX_SUGGESTED_QUESTION_QUERY_LENGTH;
                    const safeQuery = question.query?.length > maxQueryLen
                      ? question.query.substring(0, maxQueryLen)
                      : question.query;
                    sendMessage(safeQuery);
                    setTimeout(() => {
                      focusInput();
                    }, CHAT_CONSTANTS.ANIMATIONS.TOGGLE_DELAY);
                  }}
                  className="flex items-center cursor-pointer p-2.5 text-left text-base rounded-lg transition-all duration-300 ease-in-out hover:opacity-80 hover:translate-x-1 hover:shadow-sm transform-gpu"
                  style={{
                    backgroundColor: 'transparent',
                    color: theme.suggestedQuestions.text,
                  }}
                  title={question.text}
                >
                  <MessageCircle size={CHAT_CONSTANTS.BUTTON_SIZES.ICON_SIZES.BUTTON} className="mr-2.5 flex-shrink-0 opacity-70" />
                  <span className="flex-1 text-ellipsis overflow-hidden whitespace-nowrap font-medium">
                    {(question.text?.length > (maxSuggestedQuestionLength ?? CHAT_CONSTANTS.MAX_SUGGESTED_QUESTION_LENGTH))
                      ? `${question.text.substring(0, (maxSuggestedQuestionLength ?? CHAT_CONSTANTS.MAX_SUGGESTED_QUESTION_LENGTH))}...`
                      : question.text
                    }
                  </span>
                </div>
              ))}
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
  );
};