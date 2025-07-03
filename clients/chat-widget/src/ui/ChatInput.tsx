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
  // Force opaque background color - this is the key fix
  const getOpaqueBackground = () => {
    // If the theme background is transparent or has alpha, use white
    const bg = theme.input.background;
    if (!bg || bg === 'transparent' || bg.includes('rgba') || bg.includes('hsla')) {
      return '#ffffff';
    }
    // If it's a hex color with alpha (8 digits), remove the alpha
    if (bg.match(/^#[0-9A-Fa-f]{8}$/)) {
      return bg.substring(0, 7);
    }
    return bg;
  };

  const opaqueBackground = getOpaqueBackground();

  return (
    <div
      className="border-t-0 shrink-0 relative"
      style={{
        background: opaqueBackground,
        backgroundColor: opaqueBackground,
        borderTopLeftRadius: 0,
        borderTopRightRadius: 0,
        zIndex: 10,
        position: 'relative',
        marginTop: '-2px',
        paddingTop: '18px',
        paddingLeft: '16px',
        paddingRight: '16px',
        paddingBottom: '16px',
        // Add isolation to create a new stacking context
        isolation: 'isolate'
      }}
    >
      {/* Multiple solid background barriers to ensure no bleed-through */}
      <div 
        className="absolute inset-0"
        style={{
          background: opaqueBackground,
          backgroundColor: opaqueBackground,
          zIndex: -2,
          pointerEvents: 'none'
        }}
      />
      <div 
        className="absolute inset-0"
        style={{
          background: opaqueBackground,
          backgroundColor: opaqueBackground,
          zIndex: -1,
          pointerEvents: 'none'
        }}
      />
      
      {/* Input Container with integrated send button */}
      <div
        className="relative rounded-2xl transition-all duration-300 overflow-hidden input-modern shadow-soft"
        style={{
          borderColor: theme.secondary || theme.input.border || '#9ca3af',
          border: '1.5px solid',
          background: opaqueBackground,
          backgroundColor: opaqueBackground,
          boxShadow: 'none',
          // Ensure this container also blocks any bleed-through
          isolation: 'isolate',
          // Explicitly remove focus rings
          outline: 'none',
          outlineOffset: '0px'
        }}
      >
        {/* Additional background layer inside the input container */}
        <div 
          className="absolute inset-0 rounded-2xl"
          style={{
            background: opaqueBackground,
            backgroundColor: opaqueBackground,
            zIndex: 0,
            pointerEvents: 'none'
          }}
        />
        
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
          className="w-full resize-none relative"
          style={{
            background: opaqueBackground,
            backgroundColor: opaqueBackground,
            color: theme.text.primary,
            height: '52px',
            minHeight: '52px',
            maxHeight: '120px',
            overflow: 'auto',
            lineHeight: '1.5',
            boxSizing: 'border-box',
            fontWeight: '400',
            textAlign: 'left',
            border: 'none',
            boxShadow: 'none',
            outline: 'none',
            paddingLeft: '24px',
            paddingRight: '60px',
            paddingTop: '16px',
            paddingBottom: '16px',
            fontSize: '16px',
            fontFamily: 'inherit',
            position: 'relative',
            zIndex: 1
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
            boxShadow: 'none',
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
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.setProperty('transform', 'translateY(-50%)', 'important');
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
        

      </div>
    </div>
  );
};