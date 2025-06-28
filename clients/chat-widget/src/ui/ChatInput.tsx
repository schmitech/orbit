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
      className="border-t-0 shrink-0 relative"
      style={{
        background: `${theme.input.background}`,
        backgroundColor: `${theme.input.background}`,
        borderTopLeftRadius: 0,
        borderTopRightRadius: 0,
        zIndex: 10,
        position: 'relative',
        marginTop: '-2px',
        paddingTop: '18px',
        paddingLeft: '16px',
        paddingRight: '16px',
        paddingBottom: '16px'
      }}
    >
      {/* Solid background barrier to block any background bleeding */}
      <div 
        className="absolute inset-0"
        style={{
          background: `${theme.input.background}`,
          backgroundColor: `${theme.input.background}`,
          zIndex: -1
        }}
      />
      
      {/* Input Container with integrated send button */}
      <div
        className={clsx(
          "relative rounded-2xl transition-all duration-300 overflow-hidden input-modern shadow-soft",
          isFocused ? "ring-2 ring-opacity-50" : "ring-0"
        )}
        style={{
          borderColor: isFocused ? theme.secondary : theme.input.border,
          border: '1px solid',
          background: `${theme.input.background} !important`,
          backgroundColor: `${theme.input.background} !important`,
          boxShadow: 'none'
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
          id="chat-message-input"
          name="chat-message-input"
          className="w-full resize-none"
          style={{
            background: `${theme.input.background} !important`,
            backgroundColor: `${theme.input.background} !important`,
            color: theme.text.primary,
            height: '52px',
            minHeight: '52px',
            maxHeight: '120px',
            overflow: 'auto',
            lineHeight: '1.5',
            boxSizing: 'border-box',
            fontWeight: '400',
            textAlign: 'left',
            border: 'none !important',
            boxShadow: 'none !important',
            outline: 'none !important',
            paddingLeft: '24px',
            paddingRight: '60px',
            paddingTop: '16px',
            paddingBottom: '16px',
            fontSize: '16px',
            fontFamily: 'inherit'
          }}
        />
        
        {/* Send Button - Professional positioning */}
        <button
          onClick={handleSendMessage}
          disabled={!message.trim() || isLoading}
          className={clsx(
            "absolute right-2 top-1/2 transform -translate-y-1/2 rounded-xl transition-all duration-300 flex items-center justify-center shrink-0 overflow-hidden group",
            message.trim() && !isLoading
              ? "hover:scale-105"
              : "cursor-not-allowed opacity-50"
          )}
          style={{
            background: message.trim() && !isLoading 
              ? `linear-gradient(135deg, ${theme.secondary}, ${theme.secondary}e6)` 
              : 'linear-gradient(135deg, #e5e7eb, #f3f4f6)',
            color: message.trim() && !isLoading ? 'white' : '#9ca3af',
            width: '48px',
            height: '44px',
            minHeight: '44px',
            padding: '0',
            border: 'none',
            boxShadow: message.trim() && !isLoading
              ? `0 4px 12px -2px ${theme.secondary}40, 0 2px 4px -1px ${theme.secondary}20`
              : '0 2px 4px -1px rgba(0, 0, 0, 0.1)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            position: 'absolute',
            zIndex: 10,
            transform: 'translateY(-50%)'
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.setProperty('transform', 'translateY(-50%)', 'important');
            if (message.trim() && !isLoading) {
              e.currentTarget.style.setProperty('boxShadow', `0 6px 16px -2px ${theme.secondary}50, 0 4px 8px -1px ${theme.secondary}30`, 'important');
            }
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.setProperty('transform', 'translateY(-50%)', 'important');
            if (message.trim() && !isLoading) {
              e.currentTarget.style.setProperty('boxShadow', `0 4px 12px -2px ${theme.secondary}40, 0 2px 4px -1px ${theme.secondary}20`, 'important');
            }
          }}
          aria-label="Send message"
        >
          {/* Hover effect overlay */}
          <div 
            className="absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
            style={{
              background: 'linear-gradient(135deg, rgba(255, 255, 255, 0.2), rgba(255, 255, 255, 0))'
            }}
          />
          
          {/* Send icon */}
          <Send 
            size={CHAT_CONSTANTS.BUTTON_SIZES.ICON_SIZES.SEND} 
            className="transition-transform duration-200 drop-shadow-sm" 
            style={{
              strokeWidth: 2
            }}
          />
        </button>
        
        {/* Character Counter */}
        {message.length > 0 && (
          <div
            className="absolute bottom-2 right-16 text-xs px-2.5 py-1 rounded-full transition-all duration-200 backdrop-blur-sm"
            style={{
              ...getCharacterCountStyle(message.length, CHAT_CONSTANTS.MAX_MESSAGE_LENGTH),
              backdropFilter: 'blur(8px)',
              WebkitBackdropFilter: 'blur(8px)',
              fontWeight: '500'
            }}
          >
            {message.length}/{CHAT_CONSTANTS.MAX_MESSAGE_LENGTH}
          </div>
        )}
      </div>
    </div>
  );
};