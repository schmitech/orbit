import React from 'react';
import { Send } from 'lucide-react';
import clsx from 'clsx';
import { CHAT_CONSTANTS, getCharacterCountStyle } from '../shared/styles';

export interface ChatInputProps {
  message: string;
  isFocused: boolean;
  isLoading: boolean;
  theme: any; // TODO: Type this properly
  inputRef: React.RefObject<HTMLTextAreaElement>;
  handleMessageChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  handleKeyDown: (e: React.KeyboardEvent) => void;
  handleSendMessage: () => void;
  setIsFocused: (focused: boolean) => void;
}

/**
 * ChatInput component handles the message input area
 * Includes textarea, character counter, and send button with proper styling
 */
export const ChatInput: React.FC<ChatInputProps> = ({
  message,
  isFocused,
  isLoading,
  theme,
  inputRef,
  handleMessageChange,
  handleKeyDown,
  handleSendMessage,
  setIsFocused,
}) => {
  return (
    <div
      className="p-4 border-t shrink-0"
      style={{
        borderColor: theme.input.border,
        background: theme.background,
        boxShadow: '0 -2px 10px rgba(0,0,0,0.05)'
      }}
    >
      <div className="flex items-end gap-3">
        {/* Input Container */}
        <div
          className={clsx(
            "flex-1 relative rounded-xl transition-all duration-200 overflow-hidden",
            isFocused ? "ring-0" : "ring-0"
          )}
          style={{
            borderColor: isFocused ? theme.secondary : theme.input.border,
            border: '1px solid',
            boxShadow: 'none',
            background: theme.input.background
          }}
        >
          {/* Textarea */}
          <textarea
            ref={inputRef}
            value={message}
            onChange={handleMessageChange}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder="Type your message..."
            maxLength={CHAT_CONSTANTS.MAX_MESSAGE_LENGTH}
            className="w-full resize-none outline-none p-3 pr-12 text-base custom-scrollbar focus:ring-0 focus:outline-none"
            style={{
              background: 'transparent',
              color: theme.text.primary,
              height: '48px',
              minHeight: '48px',
              maxHeight: '96px',
              overflow: 'auto',
              lineHeight: '1.5',
              boxSizing: 'border-box'
            }}
          />
          
          {/* Character Counter */}
          {message.length > 0 && (
            <div
              className="absolute bottom-2 right-3 text-xs px-2 py-1 rounded-full"
              style={getCharacterCountStyle(message.length, CHAT_CONSTANTS.MAX_MESSAGE_LENGTH)}
            >
              {message.length}/{CHAT_CONSTANTS.MAX_MESSAGE_LENGTH}
            </div>
          )}
        </div>
        
        {/* Send Button */}
        <button
          onClick={handleSendMessage}
          disabled={!message.trim() || isLoading}
          className={clsx(
            "rounded-full transition-all duration-200 flex items-center justify-center shrink-0",
            message.trim() && !isLoading
              ? "hover:shadow-md transform hover:-translate-y-0.5"
              : "bg-gray-200 text-gray-400 cursor-not-allowed"
          )}
          style={{
            backgroundColor: message.trim() && !isLoading ? theme.secondary : undefined,
            color: message.trim() && !isLoading ? 'white' : undefined,
            width: CHAT_CONSTANTS.BUTTON_SIZES.SEND_BUTTON.width,
            height: CHAT_CONSTANTS.BUTTON_SIZES.SEND_BUTTON.height,
            padding: '12px'
          }}
          aria-label="Send message"
        >
          <Send size={CHAT_CONSTANTS.BUTTON_SIZES.ICON_SIZES.SEND} />
        </button>
      </div>
    </div>
  );
};