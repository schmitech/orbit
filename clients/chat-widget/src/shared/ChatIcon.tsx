import React from 'react';
import { Heart, MessageCircle, HelpCircle, Info, Bot, Sparkles, MessageSquare } from 'lucide-react';

export interface ChatIconProps {
  iconName?: string;
  size?: number;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * ChatIcon component renders different icons based on the iconName prop
 * Supports various chat-related icons with consistent sizing and styling
 */
export const ChatIcon: React.FC<ChatIconProps> = ({ 
  iconName, 
  size, 
  className, 
  style 
}) => {
  switch (iconName) {
    case 'heart':
      return <Heart size={size} className={className} style={style} />;
    
    case 'message-circle':
      return <MessageCircle size={size} className={className} style={style} />;
    
    case 'help-circle':
      return <HelpCircle size={size} className={className} style={style} />;
    
    case 'info':
      return <Info size={size} className={className} style={style} />;
    
    case 'bot':
      return <Bot size={size} className={className} style={style} />;
    
    case 'sparkles':
      return <Sparkles size={size} className={className} style={style} />;
    
    case 'message-square':
    case 'message-dots':
      return (
        <span style={{ position: 'relative', display: 'inline-block' }}>
          <MessageCircle size={size} className={className} style={style} />
          {iconName === 'message-dots' && (
            <span style={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -40%)',
              display: 'flex',
              gap: size ? size * 0.12 : 3,
              alignItems: 'center',
              justifyContent: 'center',
              width: size ? size * 0.6 : 24,
              height: size ? size * 0.2 : 6,
              pointerEvents: 'none',
            }}>
              <span style={{ 
                width: size ? size * 0.12 : 3, 
                height: size ? size * 0.12 : 3, 
                borderRadius: '50%', 
                background: 'white', 
                display: 'inline-block' 
              }} />
              <span style={{ 
                width: size ? size * 0.12 : 3, 
                height: size ? size * 0.12 : 3, 
                borderRadius: '50%', 
                background: 'white', 
                display: 'inline-block' 
              }} />
              <span style={{ 
                width: size ? size * 0.12 : 3, 
                height: size ? size * 0.12 : 3, 
                borderRadius: '50%', 
                background: 'white', 
                display: 'inline-block' 
              }} />
            </span>
          )}
        </span>
      );
    
    default:
      return <MessageSquare size={size} className={className} style={style} />;
  }
};