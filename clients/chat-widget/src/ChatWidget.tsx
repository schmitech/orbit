import React, { useState, useEffect, useCallback } from 'react';
import { Minimize2, Trash2 } from 'lucide-react';
import { useChatStore, Message } from './store/chatStore';
import { getChatConfig, defaultTheme, ChatConfig } from './config/index';
import { configureApi } from '@schmitech/chatbot-api';
import * as LucideIcons from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { 
  CHAT_CONSTANTS, 
  CHAT_WIDGET_STYLES, 
  getResponsiveWidth, 
  getResponsiveMinWidth,
  FONT_FAMILY,
  getCharacterCountStyle,
  setChatConstants
} from './shared/styles';
import { useScrollManagement } from './hooks/useScrollManagement';
import { useAnimationManagement } from './hooks/useAnimationManagement';
import { useInputManagement } from './hooks/useInputManagement';
import { Message as MessageComponent } from './ui/Message';
import { MessagesList } from './ui/MessagesList';
import { ChatInput } from './ui/ChatInput';
import clsx from 'clsx';

export interface ChatWidgetProps extends Partial<ChatConfig> {
  config?: never;
  sessionId: string;
  apiUrl: string;
  apiKey: string;
  maxSuggestedQuestionLength?: number;
  maxSuggestedQuestionQueryLength?: number;
}

export const ChatWidget: React.FC<ChatWidgetProps> = (props) => {
  const [isOpen, setIsOpen] = useState(false);
  const [hasNewMessage, setHasNewMessage] = useState(false);
  const [isButtonHovered, setIsButtonHovered] = useState(false);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);

  // Use animation management hook
  const {
    isAnimating,
    animatedMessagesRef,
    typingProgressRef,
    isTypingRef,
    lastMessageRef,
    markMessageAnimated,
    hasBeenAnimated,
    clearAnimationTrackers,
    setIsAnimating,
  } = useAnimationManagement();

  // Use scroll management hook
  const {
    showScrollTop,
    showScrollBottom,
    isScrolling,
    messagesContainerRef,
    messagesEndRef,
    shouldScrollRef,
    scrollTimeoutRef,
    scrollToBottom,
    scrollToTop,
    handleScroll,
  } = useScrollManagement(isAnimating);

  // Responsive window width state
  const [windowWidth, setWindowWidth] = useState(window.innerWidth);

  // Update window width on resize for responsiveness
  useEffect(() => {
    const handleResize = () => setWindowWidth(window.innerWidth);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Load configuration and configure API
  const baseConfig = getChatConfig();
  const [currentConfig, setCurrentConfig] = useState({
    ...baseConfig,
    ...props
  });
  const theme = currentConfig.theme || defaultTheme;

  // Configure API on mount
  useEffect(() => {
    if (props.apiUrl && props.apiKey && props.sessionId) {
      configureApi(props.apiUrl, props.apiKey, props.sessionId);
    }
  }, [props.apiUrl, props.apiKey, props.sessionId]);

  // Listen for configuration updates
  useEffect(() => {
    const handleConfigUpdate = (event: CustomEvent) => {
      setCurrentConfig(prev => ({
        ...prev,
        ...event.detail,
        theme: {
          ...prev.theme,
          ...event.detail.theme,
          suggestedQuestions: {
            ...prev.theme?.suggestedQuestions,
            ...event.detail.theme?.suggestedQuestions
          },
          chatButton: {
            ...prev.theme?.chatButton,
            ...event.detail.theme?.chatButton
          }
        }
      }));
    };

    window.addEventListener('chatbot-config-update', handleConfigUpdate as EventListener);
    return () => {
      window.removeEventListener('chatbot-config-update', handleConfigUpdate as EventListener);
    };
  }, []);

  // Update config when prop changes
  useEffect(() => {
    if (props) {
      setCurrentConfig(prev => ({
        ...prev,
        ...props
      }));
    }
  }, [props]);

  // Set runtime config for max lengths
  useEffect(() => {
    setChatConstants({
      MAX_SUGGESTED_QUESTION_LENGTH: props.maxSuggestedQuestionLength ?? CHAT_CONSTANTS.MAX_SUGGESTED_QUESTION_LENGTH,
      MAX_SUGGESTED_QUESTION_QUERY_LENGTH: props.maxSuggestedQuestionQueryLength ?? CHAT_CONSTANTS.MAX_SUGGESTED_QUESTION_QUERY_LENGTH,
    });
  }, [props.maxSuggestedQuestionLength, props.maxSuggestedQuestionQueryLength]);

  const {
    messages,
    isLoading,
    sendMessage,
    deleteConversation
  } = useChatStore();

  // Use input management hook
  const {
    message,
    isFocused,
    inputRef,
    handleMessageChange,
    handleKeyDown,
    handleSendMessage: handleInputSend,
    setIsFocused,
    clearMessage,
    focusInput,
  } = useInputManagement({
    onSendMessage: (msg) => {
      shouldScrollRef.current = true;
      sendMessage(msg);
      setTimeout(() => scrollToBottom(true), CHAT_CONSTANTS.ANIMATIONS.TOGGLE_DELAY);
    },
    isLoading,
    isOpen,
  });
  
  // Clear animated messages tracker when conversation resets
  useEffect(() => {
    if (messages.length === 0) {
      clearAnimationTrackers();
    }
  }, [messages.length, clearAnimationTrackers]);

  const toggleChat = () => {
    setIsOpen(!isOpen);
    if (!isOpen) {
      setHasNewMessage(false);
      setTimeout(() => scrollToBottom(true), CHAT_CONSTANTS.ANIMATIONS.TOGGLE_DELAY);
    }
  };

  const copyToClipboard = useCallback(async (text: string, messageId: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedMessageId(messageId);
      setTimeout(() => {
        setCopiedMessageId(null);
      }, CHAT_CONSTANTS.ANIMATIONS.COPY_FEEDBACK_DURATION);
    } catch (err) {
      console.error('Failed to copy text: ', err);
    }
  }, []);

  const handleDeleteConversation = useCallback(async () => {
    try {
      await deleteConversation();
    } catch (error) {
      console.error('Failed to delete conversation:', error);
    } finally {
      clearAnimationTrackers();
    }
  }, [deleteConversation, clearAnimationTrackers]);

  // Format timestamp (note: uses a relative offset since messages lack explicit timestamps)
  const formatTime = useCallback((date: Date): string => {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }, []);

  // Scroll to bottom when messages change or loading state changes
  useEffect(() => {
    if (isLoading || messages.length === 0) {
      scrollToBottom(true);
    }
  }, [messages, isLoading, scrollToBottom]);

  // Cleanup scroll timeout
  useEffect(() => {
    return () => {
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }
    };
  }, [scrollTimeoutRef]);

  // Map demo icon names to actual Lucide React icon names
  const iconNameMap: Record<string, keyof typeof LucideIcons> = {
    // Chat and Communication
    'MessageSquare': 'MessageSquare',
    'MessageCircle': 'MessageCircle',
    'MessageCircleMore': 'MoreHorizontal', // Use MoreHorizontal for dots
    'MessageSquareText': 'MessageSquareText',
    'MessageSquareDots': 'MessageSquareDot',
    'ChatBubble': 'MessageCircle',
    'ChatBubbleLeft': 'MessageCircle',
    'ChatBubbleLeftRight': 'MessageCircle',
    'ChatBubbleLeftEllipsis': 'MessageCircle',
    'ChatBubbleLeftDots': 'MessageCircle',
    
    // Help and Info  
    'HelpCircle': 'HelpCircle',
    'QuestionMarkCircle': 'HelpCircle',
    'Info': 'Info',
    'Lightbulb': 'Lightbulb',
    'Sparkles': 'Sparkles',
    'Headphones': 'Headphones',
    'LifeBuoy': 'LifeBuoy',
    
    // People
    'Bot': 'Bot',
    'Brain': 'Brain',
    'Cpu2': 'Cpu',
    'User': 'User',
    'Users': 'Users',
    'UserCheck': 'UserCheck',
    'UserPlus': 'UserPlus',
    'UserRound': 'UserRound',
    'Smile': 'Smile',
    
    // Communication
    'Phone': 'Phone',
    'Mail': 'Mail',
    'MailOpen': 'MailOpen',
    'Send': 'Send',
    'Reply': 'Reply',
    
    // Actions and Interface
    'Heart': 'Heart',
    'Star': 'Star',
    'ThumbsUp': 'ThumbsUp',
    'Laugh': 'Laugh',
    
    // Settings and Tools
    'Settings': 'Settings',
    'Cog': 'Settings', // Map to Settings since Cog might not exist
    'Wrench': 'Wrench',
    'Tool': 'Wrench', // Map to Wrench
    'Hammer': 'Hammer',
    
    // Navigation
    'Home': 'Home',
    'Search': 'Search',
    'Menu': 'Menu',
    'Grid': 'Grid3X3',
    'List': 'List',
    
    // Basic Actions
    'Plus': 'Plus',
    'Minus': 'Minus',
    'X': 'X',
    'Check': 'Check',
    'ArrowRight': 'ArrowRight',
    
    // Special
    'Zap': 'Zap',
    'Target': 'Target',
    'Flag': 'Flag',
    'Bookmark': 'Bookmark',
    'Gift': 'Gift',
    
    // Additional common icons
    'Bell': 'Bell',
    'BellRing': 'BellRing',
    'Calendar': 'Calendar',
    'Clock': 'Clock',
    'MapPin': 'MapPin',
    'Globe': 'Globe',
    'Link': 'Link',
    'Download': 'Download',
    'Upload': 'Upload',
    'Share': 'Share',
    'Copy': 'Copy',
    'Edit': 'Edit',
    'Trash': 'Trash',
    'Eye': 'Eye',
    'EyeOff': 'EyeOff',
    'Lock': 'Lock',
    'Unlock': 'Unlock',
    'Shield': 'Shield',
    'AlertCircle': 'AlertCircle',
    'AlertTriangle': 'AlertTriangle',
    'CheckCircle': 'CheckCircle',
    'XCircle': 'XCircle',
    'MinusCircle': 'MinusCircle',
    'PlusCircle': 'PlusCircle',
    'Play': 'Play',
    'Pause': 'Pause',
    'Stop': 'Square',
    'SkipBack': 'SkipBack',
    'SkipForward': 'SkipForward',
    'Volume': 'Volume2',
    'VolumeX': 'VolumeX',
    'Mic': 'Mic',
    'MicOff': 'MicOff',
    'Camera': 'Camera',
    'Video': 'Video',
    'Image': 'Image',
    'File': 'File',
    'FileText': 'FileText',
    'Folder': 'Folder',
    'FolderOpen': 'FolderOpen',
    'Database': 'Database',
    'Server': 'Server',
    'Monitor': 'Monitor',
    'Smartphone': 'Smartphone',
    'Tablet': 'Tablet',
    'Laptop': 'Laptop',
    'Activity': 'Activity'
  };

  const requestedIconName = theme.chatButton?.iconName || 'MessageSquare';
  const mappedIconName = iconNameMap[requestedIconName] || 'MessageSquare';
  
  const IconComponent: LucideIcon = (LucideIcons as any)[mappedIconName] || LucideIcons.MessageSquare;

  return (
    <div className="fixed bottom-8 right-8 z-50 flex flex-col items-end font-sans" style={{ fontFamily: FONT_FAMILY }}>
      {/* Chat Window */}
      {isOpen && (
        <div
          className="mb-4 w-full rounded-2xl shadow-elegant flex flex-col overflow-hidden border-0 transition-all duration-300 ease-in-out animate-slide-in-up backdrop-blur-lg"
          style={{
            background: theme.input.background,
            height: CHAT_CONSTANTS.WINDOW_DIMENSIONS.HEIGHT,
            maxHeight: CHAT_CONSTANTS.WINDOW_DIMENSIONS.MAX_HEIGHT,
            width: getResponsiveWidth(windowWidth),
            minWidth: getResponsiveMinWidth(windowWidth),
            backdropFilter: 'blur(20px)',
            WebkitBackdropFilter: 'blur(20px)',
            border: '1px solid rgba(255, 255, 255, 0.2)',
            boxShadow: `
              0 25px 50px -12px rgba(0, 0, 0, 0.15),
              0 0 0 1px rgba(255, 255, 255, 0.1),
              inset 0 1px 0 rgba(255, 255, 255, 0.1)
            `
          }}
        >
          {/* Header */}
          <div
            className="p-2.5 flex justify-between items-center shrink-0 relative overflow-hidden"
            style={{ 
              background: `linear-gradient(135deg, ${theme.primary}, ${theme.primary}e6)`,
              color: theme.text.inverse
            }}
          >
            {/* Subtle gradient overlay for depth */}
            <div 
              className="absolute inset-0 opacity-20"
              style={{
                background: 'linear-gradient(135deg, rgba(255, 255, 255, 0.2), rgba(255, 255, 255, 0))'
              }}
            />
            
            <div className="flex items-center relative z-10 w-full px-3">
              <div className="max-w-lg mx-auto sm:max-w-2xl w-full">
                <h3 className="text-xl font-semibold tracking-tight text-left px-1">{currentConfig.header.title}</h3>
              </div>
            </div>
            <div className="flex items-center space-x-2 relative z-10">
              <button
                onClick={handleDeleteConversation}
                className="btn-modern transition-all duration-200 p-2 rounded-xl hover:bg-white hover:bg-opacity-20 animate-button-hover"
                style={{ color: theme.text.inverse }}
                aria-label="Clear conversation"
                title="Clear conversation"
              >
                <Trash2 size={CHAT_CONSTANTS.BUTTON_SIZES.ICON_SIZES.SEND} className="drop-shadow-sm" />
              </button>
              <button
                onClick={toggleChat}
                className="btn-modern transition-all duration-200 p-2 rounded-xl hover:bg-white hover:bg-opacity-20 animate-button-hover"
                style={{ color: theme.text.inverse }}
                aria-label="Minimize chat"
              >
                <Minimize2 size={CHAT_CONSTANTS.BUTTON_SIZES.ICON_SIZES.MINIMIZE} className="text-white opacity-90 drop-shadow-sm" />
              </button>
            </div>
          </div>

          {/* Messages */}
          <MessagesList
            messages={messages}
            isLoading={isLoading}
            theme={theme}
            currentConfig={currentConfig}
            showScrollTop={showScrollTop}
            showScrollBottom={showScrollBottom}
            isAnimating={isAnimating}
            messagesContainerRef={messagesContainerRef}
            messagesEndRef={messagesEndRef}
            scrollToTop={scrollToTop}
            scrollToBottom={scrollToBottom}
            handleScroll={handleScroll}
            sendMessage={sendMessage}
            focusInput={focusInput}
            copiedMessageId={copiedMessageId}
            onCopyToClipboard={copyToClipboard}
            onMarkMessageAnimated={markMessageAnimated}
            inputRef={inputRef}
            hasBeenAnimated={hasBeenAnimated}
            typingProgressRef={typingProgressRef}
            isTypingRef={isTypingRef}
            setIsAnimating={setIsAnimating}
            formatTime={formatTime}
            lastMessageRef={lastMessageRef}
            maxSuggestedQuestionLength={props.maxSuggestedQuestionLength}
            maxSuggestedQuestionQueryLength={props.maxSuggestedQuestionQueryLength}
          />

          {/* Input Area */}
          <ChatInput
            message={message}
            isFocused={isFocused}
            isLoading={isLoading}
            theme={theme}
            inputRef={inputRef}
            handleMessageChange={handleMessageChange}
            handleKeyDown={handleKeyDown}
            handleSendMessage={handleInputSend}
            setIsFocused={setIsFocused}
          />
        </div>
      )}

      {/* Chat Button */}
      <div className="relative">
        {hasNewMessage && !isOpen && (
          <span className="absolute -top-2 -right-2 h-5 w-5 bg-gradient-to-r from-orange-500 to-red-500 rounded-full animate-pulse-glow z-10 shadow-lg">
            <span className="absolute inset-0 rounded-full bg-white opacity-30"></span>
          </span>
        )}
        <button
          onClick={toggleChat}
          onMouseEnter={() => setIsButtonHovered(true)}
          onMouseLeave={() => setIsButtonHovered(false)}
          className={clsx(
            "btn-modern rounded-2xl shadow-floating flex items-center justify-center transition-all duration-500 relative overflow-hidden group",
            isButtonHovered && !isOpen && "animate-pulse-glow",
            !isOpen && "animate-float"
          )}
          style={{
            background: isOpen 
              ? `linear-gradient(135deg, ${theme.primary}, ${theme.primary}e6)` 
              : isButtonHovered 
                ? theme.chatButton?.hoverBackground || theme.chatButton?.background || '#ffffff'
                : theme.chatButton?.background || '#ffffff',
            color: !isOpen ? theme.text.primary : undefined,
            border: isOpen ? 'none' : `1px solid ${theme.chatButton?.borderColor || '#e5e7eb'}`,
            width: CHAT_CONSTANTS.BUTTON_SIZES.CHAT_BUTTON.width,
            height: CHAT_CONSTANTS.BUTTON_SIZES.CHAT_BUTTON.height,
            transform: isButtonHovered ? 'translateY(-2px) scale(1.05)' : 'translateY(0) scale(1)',
            boxShadow: isOpen 
              ? `0 20px 25px -5px rgba(0, 0, 0, 0.15), 0 10px 10px -5px rgba(0, 0, 0, 0.04)`
              : `0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)`
          }}
          aria-label={isOpen ? "Close chat" : "Open chat"}
        >
          {/* Animated background gradient */}
          <div 
            className={clsx(
              "absolute inset-0 opacity-0 transition-opacity duration-300",
              isButtonHovered && "opacity-100"
            )}
            style={{
              background: 'linear-gradient(135deg, rgba(255, 255, 255, 0.2), rgba(255, 255, 255, 0))'
            }}
          />
          
          {isOpen ? (
            <Minimize2 
              size={CHAT_CONSTANTS.BUTTON_SIZES.ICON_SIZES.MINIMIZE} 
              className="text-white opacity-90 drop-shadow-sm relative z-10" 
            />
          ) : (
            <IconComponent
              width={48}
              height={48}
              className="relative z-10 transition-transform duration-300 group-hover:scale-110 drop-shadow-sm"
              style={{
                filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.1))',
                fill: theme.chatButton?.iconColor || '#f97316',
                stroke: theme.chatButton?.iconBorderColor || '#111',
                strokeWidth: 1
              }}
            />
          )}
        </button>
      </div>

      <style>{CHAT_WIDGET_STYLES}</style>
    </div>
  );
};
