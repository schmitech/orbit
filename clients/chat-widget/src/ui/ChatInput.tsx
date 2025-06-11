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
      className="p-4 border-t-0 shrink-0 relative"
      style={{
        background: `linear-gradient(180deg, transparent, ${theme.background}f8)`,
        backdropFilter: 'blur(10px)',
        WebkitBackdropFilter: 'blur(10px)',
      }}
    >
      {/* Subtle top border gradient */}
      <div 
        className="absolute top-0 left-0 right-0 h-px"
        style={{
          background: 'linear-gradient(90deg, transparent, rgba(0,0,0,0.1), transparent)'
        }}
      />
      
      {/* Aligned container for input and button */}
      <div className="flex items-end gap-3">
        {/* Input Container */}
        <div
          className={clsx(
            "flex-1 relative rounded-2xl transition-all duration-300 overflow-hidden input-modern shadow-soft",
            isFocused ? "ring-2 ring-opacity-50" : "ring-0"
          )}
          style={{
            borderColor: isFocused ? theme.secondary : 'rgba(0, 0, 0, 0.1)',
            border: '1px solid',
            background: `linear-gradient(145deg, ${theme.input.background}, ${theme.input.background}f8)`,
            backdropFilter: 'blur(10px)',
            WebkitBackdropFilter: 'blur(10px)',
            boxShadow: isFocused 
              ? `0 8px 25px -8px rgba(0, 0, 0, 0.1), 0 0 0 1px ${theme.secondary}40`
              : '0 2px 10px -3px rgba(0, 0, 0, 0.1)'
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
            className="w-full resize-none outline-none p-4 pr-12 text-base custom-scrollbar focus:ring-0 focus:outline-none placeholder-gray-400 transition-all duration-200"
            style={{
              background: 'transparent',
              color: theme.text.primary,
              height: '52px',
              minHeight: '52px',
              maxHeight: '120px',
              overflow: 'auto',
              lineHeight: '1.5',
              boxSizing: 'border-box',
              fontWeight: '400'
            }}
          />
          
          {/* Character Counter */}
          {message.length > 0 && (
            <div
              className="absolute bottom-2 right-3 text-xs px-2.5 py-1 rounded-full transition-all duration-200 backdrop-blur-sm"
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
        
        {/* Send Button - Perfectly aligned and centered */}
        <button
          onClick={handleSendMessage}
          disabled={!message.trim() || isLoading}
          className={clsx(
            "btn-modern rounded-2xl transition-all duration-300 flex items-center justify-center shrink-0 shadow-soft relative overflow-hidden group",
            message.trim() && !isLoading
              ? "animate-button-hover"
              : "cursor-not-allowed opacity-50"
          )}
          style={{
            background: message.trim() && !isLoading 
              ? `linear-gradient(135deg, ${theme.secondary}, ${theme.secondary}e6)` 
              : 'linear-gradient(135deg, #e5e7eb, #f3f4f6)',
            color: message.trim() && !isLoading ? 'white' : '#9ca3af',
            // Make button height match input container exactly
            width: '52px', // Square button for perfect alignment
            height: '54px', // Match input height + border (52px + 2px border)
            minHeight: '54px',
            // Slight upward adjustment for perfect visual centering
            transform: 'translateY(-2px)',
            padding: '0',
            border: 'none',
            boxShadow: message.trim() && !isLoading
              ? `0 4px 12px -2px ${theme.secondary}40`
              : '0 2px 4px -1px rgba(0, 0, 0, 0.1)',
            // Perfect alignment properties
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            position: 'relative'
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
          
          {/* Perfectly centered send icon */}
          <div 
            className="absolute inset-0 flex items-center justify-center"
            style={{
              // Extra centering container to ensure perfect alignment
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '100%',
              height: '100%'
            }}
          >
            <Send 
              size={CHAT_CONSTANTS.BUTTON_SIZES.ICON_SIZES.SEND} 
              className="transition-transform duration-200 group-hover:translate-x-0.5 drop-shadow-sm" 
              style={{
                // Ensure icon is perfectly centered
                display: 'block',
                strokeWidth: 2, // Enterprise-grade icon weight
                // Fine-tune positioning for perfect visual centering
                transform: 'translate(0.5px, -0.5px)'
              }}
            />
          </div>
        </button>
      </div>
    </div>
  );
};