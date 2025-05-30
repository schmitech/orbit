import React, { useState, useEffect, useCallback } from 'react';
import { Minimize2, Trash2 } from 'lucide-react';
import { useChatStore, Message } from './store/chatStore';
import { getChatConfig, defaultTheme, ChatConfig } from './config/index';
import { configureApi } from '@schmitech/chatbot-api';
import MessagesSquareIcon from './config/messages-square.svg?react';
import { ChatIcon } from './shared/ChatIcon';
import { 
  CHAT_CONSTANTS, 
  CHAT_WIDGET_STYLES, 
  getResponsiveWidth, 
  getResponsiveMinWidth,
  FONT_FAMILY,
  getCharacterCountStyle
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
}

export const ChatWidget: React.FC<ChatWidgetProps> = (props) => {
  const [isOpen, setIsOpen] = useState(false);
  const [hasNewMessage, setHasNewMessage] = useState(false);
  const [isButtonHovered, setIsButtonHovered] = useState(false);
  const [copiedMessageId, setCopiedMessageId] = useState<number | null>(null);

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
      setCurrentConfig(event.detail);
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

  const {
    messages,
    isLoading,
    sendMessage,
    clearMessages
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

  const copyToClipboard = async (text: string, messageIndex: number) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedMessageId(messageIndex);
      setTimeout(() => {
        setCopiedMessageId(null);
      }, CHAT_CONSTANTS.ANIMATIONS.COPY_FEEDBACK_DURATION);
    } catch (err) {
      console.error('Failed to copy text: ', err);
    }
  };

  // Helper function to convert URLs to markdown links in plain text and preserve line breaks
  const linkifyText = useCallback((text: string): string => {
    const urlRegex = /(https?:\/\/[^\s]+?)([.,;:!?)]*)(?=\s|$)/g;
    const linkedText = text.replace(urlRegex, (match, url, punctuation) =>
      `[${url}](${url})${punctuation}`
    );
    
    // Only add the two spaces to lines that aren't already part of a paragraph break
    // This preserves intentional single line breaks without adding extra spacing
    return linkedText;
  }, []);

  // Normalize text for consistent paragraph spacing
  const normalizeText = useCallback((text: string): string => {
    // Replace 3+ newlines with just 2 (Markdown paragraph)
    let normalized = text.replace(/\n{3,}/g, '\n\n');
    
    // Fix spacing between list items 
    normalized = normalized.replace(/\n(\s*[-*+]|\s*\d+\.)\s*/g, '\n$1 ');
    
    // Ensure paragraphs have consistent spacing
    normalized = normalized.replace(/\n\n\n+/g, '\n\n');
    
    return normalized.trim();
  }, []);

  // Format timestamp (note: uses a relative offset since messages lack explicit timestamps)
  const formatTime = (date: Date): string => {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

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

  return (
    <div className="fixed bottom-8 right-8 z-50 flex flex-col items-end font-sans" style={{ fontFamily: FONT_FAMILY }}>
      {/* Chat Window */}
      {isOpen && (
        <div
          className="mb-4 w-full sm:w-[480px] md:w-[600px] lg:w-[700px] rounded-xl shadow-xl flex flex-col overflow-hidden border border-gray-200 transition-all duration-300 ease-in-out"
          style={{
            background: theme.background,
            height: CHAT_CONSTANTS.WINDOW_DIMENSIONS.HEIGHT,
            maxHeight: CHAT_CONSTANTS.WINDOW_DIMENSIONS.MAX_HEIGHT,
            width: getResponsiveWidth(windowWidth),
            minWidth: getResponsiveMinWidth(windowWidth),
          }}
        >
          {/* Header */}
          <div
            className="p-4 flex justify-between items-center shrink-0"
            style={{ background: theme.primary, color: theme.text.inverse }}
          >
            <div className="flex items-center">
              <ChatIcon iconName={currentConfig.icon} size={CHAT_CONSTANTS.BUTTON_SIZES.ICON_SIZES.HEADER} className="mr-3" style={{ color: theme.secondary }} />
              <h3 className="text-xl font-medium">{currentConfig.header.title}</h3>
            </div>
            <div className="flex items-center space-x-3">
              <button
                onClick={() => {
                  clearMessages();
                  // Clearing animated messages tracker on clear
                  clearAnimationTrackers();
                }}
                className="transition-colors p-2 rounded-full hover:bg-opacity-20 hover:bg-black"
                style={{ color: theme.text.inverse }}
                aria-label="Clear conversation"
                title="Clear conversation"
              >
                <Trash2 size={CHAT_CONSTANTS.BUTTON_SIZES.ICON_SIZES.BUTTON} />
              </button>
              <button
                onClick={toggleChat}
                className="transition-colors p-2 rounded-full hover:bg-opacity-20 hover:bg-black"
                style={{ color: theme.text.inverse }}
                aria-label="Minimize chat"
              >
                <Minimize2 size={CHAT_CONSTANTS.BUTTON_SIZES.ICON_SIZES.MINIMIZE} className="text-white" style={{ opacity: 0.9 }} />
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
            normalizeText={normalizeText}
            linkifyText={linkifyText}
            formatTime={formatTime}
            lastMessageRef={lastMessageRef}
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
          <span className="absolute -top-1 -right-1 h-4 w-4 bg-orange-500 rounded-full animate-pulse z-10"></span>
        )}
        <button
          onClick={toggleChat}
          onMouseEnter={() => setIsButtonHovered(true)}
          onMouseLeave={() => setIsButtonHovered(false)}
          className={clsx(
            "rounded-full shadow-lg flex items-center justify-center transition-all duration-300",
            isButtonHovered && !isOpen && "animate-pulse",
            !isOpen && "animate-bounce-gentle"
          )}
          style={{
            background: isOpen ? theme.primary : 'transparent',
            color: !isOpen ? theme.iconColor : undefined,
            border: 'none',
            boxShadow: 'none',
            width: CHAT_CONSTANTS.BUTTON_SIZES.CHAT_BUTTON.width,
            height: CHAT_CONSTANTS.BUTTON_SIZES.CHAT_BUTTON.height,
          }}
          aria-label={isOpen ? "Close chat" : "Open chat"}
        >
          {isOpen ? (
            <Minimize2 size={CHAT_CONSTANTS.BUTTON_SIZES.ICON_SIZES.MINIMIZE} className="text-white" style={{ opacity: 0.9 }} />
          ) : (
            <MessagesSquareIcon width={48} height={48} />
          )}
        </button>
      </div>

      <style>{CHAT_WIDGET_STYLES}</style>
    </div>
  );
};