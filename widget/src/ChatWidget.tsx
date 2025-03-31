import React, { useState, useRef, useEffect } from 'react';
import { MessageSquare, X, Minimize2, Send, Copy, Trash2, Heart, HelpCircle, Info, MessageCircle, Bot, Sparkles, ChevronUp } from 'lucide-react';
import { useChatStore, Message } from './store/chatStore';
import ReactMarkdown from 'react-markdown';
import clsx from 'clsx';
import { getChatConfig, defaultTheme, ChatConfig } from './config/index';

// Custom link component for ReactMarkdown
const MarkdownLink = (props: React.AnchorHTMLAttributes<HTMLAnchorElement>) => {
  return (
    <a
      {...props}
      target="_blank"
      rel="noopener noreferrer"
      className="text-orange-500 hover:text-orange-700 underline"
    >
      {props.children}
    </a>
  );
};

// Component to render the appropriate icon
const ChatIcon = ({ iconName, size, className, style }: {
  iconName?: string,
  size?: number,
  className?: string,
  style?: React.CSSProperties
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
    default:
      return <MessageSquare size={size} className={className} style={style} />;
  }
};

export interface ChatWidgetProps extends Partial<ChatConfig> {
  config?: never; // Make sure no one tries to use the config prop
}

export const ChatWidget: React.FC<ChatWidgetProps> = (props) => {
  const [isOpen, setIsOpen] = useState(false);
  const [message, setMessage] = useState('');
  const [hasNewMessage, setHasNewMessage] = useState(false);
  const [isButtonHovered, setIsButtonHovered] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const MAX_MESSAGE_LENGTH = 500;
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const [showScrollTop, setShowScrollTop] = useState(false);

  // Auto-resize the input field
  const [inputHeight, setInputHeight] = useState(56); // Starting height
  const [isFocused, setIsFocused] = useState(false);

  // Load configuration
  const baseConfig = getChatConfig();
  const [currentConfig, setCurrentConfig] = useState({
    ...baseConfig,
    ...props // Use all props as config values
  });
  const theme = currentConfig.theme || defaultTheme;

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

  const toggleChat = () => {
    setIsOpen(!isOpen);
    if (!isOpen) {
      setHasNewMessage(false);
    }
  };

  const handleSendMessage = () => {
    if (message.trim() && !isLoading) {
      sendMessage(message);
      setMessage('');
      // Reset textarea height
      setInputHeight(56);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  // Helper function to convert URLs to markdown links in plain text and preserve line breaks
  const linkifyText = (text: string): string => {
    // URL regex pattern - don't include trailing punctuation in the URL
    const urlRegex = /(https?:\/\/[^\s]+?)([.,;:!?)]*)(?=\s|$)/g;

    // Replace URLs with markdown links, preserving trailing punctuation outside the link
    const linkedText = text.replace(urlRegex, (match, url, punctuation) =>
      `[${url}](${url})${punctuation}`
    );

    // Process the text to handle line breaks properly
    const processedText = linkedText
      .replace(/\n{2,}/g, '\n\n') // Keep multiple newlines as is
      .replace(/\n/g, '\n'); // Keep single newlines as is

    return processedText;
  };

  // Format timestamp
  const formatTime = (date: Date): string => {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  // Check scroll position to determine if scroll-to-top button should be shown
  const handleScroll = () => {
    if (messagesContainerRef.current) {
      const { scrollTop } = messagesContainerRef.current;
      setShowScrollTop(scrollTop > 200);
    }
  };

  // Scroll to top function
  const scrollToTop = () => {
    if (messagesContainerRef.current) {
      messagesContainerRef.current.scrollTo({
        top: 0,
        behavior: 'smooth'
      });
    }
  };

  // Auto-resize textarea based on content
  const adjustHeight = () => {
    if (inputRef.current) {
      // Reset height to auto to correctly calculate the new height
      inputRef.current.style.height = 'auto';

      // Set new height (with min of 56px)
      const newHeight = Math.max(56, Math.min(inputRef.current.scrollHeight, 120));
      setInputHeight(newHeight);
    }
  };

  // Scroll to bottom when messages change
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }

    // If chat is not open and we receive a new message, show notification
    if (!isOpen && messages.length > 0 && messages[messages.length - 1].role === 'assistant') {
      setHasNewMessage(true);
    }
  }, [messages, isOpen]);

  // Focus input when chat opens
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  // Handle message input changes
  const handleMessageChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const input = e.target.value;
    if (input.length <= MAX_MESSAGE_LENGTH) {
      setMessage(input);
      // Adjust height after content change
      adjustHeight();
    }
  };

  // Typing effect component for the latest message only
  const TypingEffect = ({ content, onComplete }: { content: string, onComplete: () => void }) => {
    const [displayedContent, setDisplayedContent] = useState('');
    const [isThinking, setIsThinking] = useState(true);
    const [typingDots, setTypingDots] = useState('.');
    const contentRef = useRef(content);
    const charIndexRef = useRef(0);
    const [userIsTyping, setUserIsTyping] = useState(false);

    // Reset animation when content changes
    useEffect(() => {
      if (content !== contentRef.current) {
        contentRef.current = content;
        charIndexRef.current = 0;
        setDisplayedContent('');
        setIsThinking(true);
      }
    }, [content]);

    // Handle typing animation
    useEffect(() => {
      if (charIndexRef.current < contentRef.current.length && !userIsTyping) {
        const typingTimer = setTimeout(() => {
          charIndexRef.current += 1;
          const newContent = contentRef.current.substring(0, charIndexRef.current);
          setDisplayedContent(newContent);
          
          // Hide thinking indicator as soon as we have content
          if (newContent.length > 0 && isThinking) {
            setIsThinking(false);
          }

          // If we've reached the end, mark as complete
          if (charIndexRef.current >= contentRef.current.length) {
            onComplete();
          }
        }, 20); // 20ms delay per character
        
        return () => clearTimeout(typingTimer);
      } else if (userIsTyping) {
        // If user is typing, show full content immediately
        setDisplayedContent(contentRef.current);
        setIsThinking(false);
        onComplete();
      }
    }, [displayedContent, isThinking, userIsTyping]);

    // Listen for user typing
    useEffect(() => {
      const handleMessageChange = () => {
        setUserIsTyping(true);
      };

      // Add event listener to the textarea
      const textarea = document.querySelector('textarea');
      if (textarea) {
        textarea.addEventListener('input', handleMessageChange);
      }

      return () => {
        if (textarea) {
          textarea.removeEventListener('input', handleMessageChange);
        }
      };
    }, []);

    // Animate the typing indicator dots
    useEffect(() => {
      if (!isThinking) return;
      
      const dotsTimer = setInterval(() => {
        setTypingDots(prev => {
          if (prev === '.') return '..';
          if (prev === '..') return '...';
          return '.';
        });
      }, 400);
      
      return () => clearInterval(dotsTimer);
    }, [isThinking]);

    return (
      <>
        {displayedContent && (
          <div className="prose prose-base max-w-full whitespace-pre-wrap" style={{ 
            overflowWrap: 'anywhere',
            wordBreak: 'break-word', 
            width: '100%',
            maxWidth: '100%',
          }}>
            <ReactMarkdown
              components={{
                a: (props) => <MarkdownLink {...props} />,
                p: (props) => <p className="mb-4" style={{ overflowWrap: 'anywhere', wordBreak: 'break-word' }} {...props} />,
                code: (props) => <code style={{ display: 'block', whiteSpace: 'pre-wrap', overflowX: 'auto', overflowWrap: 'anywhere' }} {...props} />
              }}
            >
              {linkifyText(displayedContent)}
            </ReactMarkdown>
          </div>
        )}
        {isThinking && (
          <div className="text-gray-500">
            <span className="font-medium">thinking</span>
            <span className="font-mono">{typingDots}</span>
          </div>
        )}
      </>
    );
  };

  // Track which messages have completed their animation
  const [animatedMessages, setAnimatedMessages] = useState<{[key: number]: boolean}>({});
  
  // Mark a message as having completed its animation
  const markMessageAnimated = (index: number) => {
    setAnimatedMessages(prev => ({
      ...prev,
      [index]: true
    }));
  };

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col items-end">
      {/* Chat Window */}
      {isOpen && (
        <div
          className="mb-4 w-full sm:w-[500px] md:w-[650px] lg:w-[700px] rounded-xl shadow-xl flex flex-col overflow-hidden border border-gray-200 transition-all duration-300 ease-in-out"
          style={{
            background: theme.background,
            height: '650px',
            maxHeight: 'calc(100vh - 100px)',
            width: window.innerWidth < 640 ? '100%' :
              window.innerWidth < 768 ? '500px' :
                window.innerWidth < 1024 ? '650px' : '700px',
            minWidth: window.innerWidth < 640 ? '100%' : '500px',
          }}
        >
          {/* Header */}
          <div
            className="p-4 flex justify-between items-center shrink-0"
            style={{ background: theme.primary, color: theme.text.inverse }}
          >
            <div className="flex items-center">
              <ChatIcon iconName={currentConfig.icon} size={32} className="mr-3" style={{ color: theme.secondary }} />
              <h3 className="text-xl font-medium">{currentConfig.header.title}</h3>
            </div>
            <div className="flex items-center space-x-3">
              <button
                onClick={() => clearMessages()}
                className="transition-colors p-2 rounded-full hover:bg-opacity-20 hover:bg-black"
                style={{ color: theme.text.inverse }}
                aria-label="Clear conversation"
                title="Clear conversation"
              >
                <Trash2 size={20} />
              </button>
              <button
                onClick={toggleChat}
                className="transition-colors p-2 rounded-full hover:bg-opacity-20 hover:bg-black"
                style={{ color: theme.text.inverse }}
                aria-label="Minimize chat"
              >
                <Minimize2 size={20} />
              </button>
            </div>
          </div>

          {/* Messages */}
          <div
            ref={messagesContainerRef}
            className="flex-1 p-4 overflow-y-auto scroll-smooth"
            style={{
              background: theme.input.background,
              overflowY: 'auto',
              scrollbarWidth: 'thin',
              scrollbarColor: `${theme.secondary} transparent`
            }}
            onScroll={handleScroll}
          >
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
                <ChevronUp size={20} />
              </button>
            )}

            {messages.length === 0 ? (
              <div className="text-center py-16">
                <ChatIcon
                  iconName={currentConfig.icon}
                  size={56}
                  className="mx-auto mb-4"
                  style={{ color: theme.iconColor }}
                />
                <h4 className="font-medium text-xl text-[#2C3E50] mb-2">{currentConfig.welcome.title}</h4>
                <p className="text-lg text-gray-600 mb-6">
                  {currentConfig.welcome.description}
                </p>
                <div className="space-y-3 max-w-md mx-auto">
                  {currentConfig.suggestedQuestions.map((question, index) => (
                    <button
                      key={index}
                      onClick={() => sendMessage(question.query)}
                      className="w-full text-left text-base p-3 rounded-lg transition-colors"
                      style={{
                        backgroundColor: theme.suggestedQuestions.background,
                        color: theme.suggestedQuestions.text
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.backgroundColor = theme.suggestedQuestions.hoverBackground;
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.backgroundColor = theme.suggestedQuestions.background;
                      }}
                    >
                      {question.text}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="space-y-5">
                {messages.map((msg: Message, index: number) => {
                  // Create a timestamp for each message
                  const timestamp = new Date();
                  timestamp.setMinutes(timestamp.getMinutes() - (messages.length - index));
                  
                  // Check if this is the last assistant message and we're still loading
                  const isLatestAssistantMessage = msg.role === 'assistant' && index === messages.length - 1;
                  const showTypingAnimation = isLatestAssistantMessage && isLoading;
                  const hasBeenAnimated = animatedMessages[index];
                  
                  return (
                    <div 
                      key={index} 
                      className={clsx(
                        "flex",
                        msg.role === 'user' ? "justify-end" : "justify-start"
                      )}
                    >
                      <div 
                        className={clsx(
                          "max-w-[85%] rounded-xl p-4 shadow-sm",
                          msg.role === 'user' ? "rounded-tr-none" : "rounded-tl-none"
                        )}
                        style={{
                          background: msg.role === 'user' ? theme.message.user : theme.message.assistant,
                          color: msg.role === 'user' ? theme.message.userText : theme.text.primary,
                          border: msg.role === 'assistant' ? `1px solid ${theme.input.border}` : 'none',
                          width: '100%',
                          maxWidth: '85%',
                          wordWrap: 'break-word',
                          overflowWrap: 'anywhere'
                        }}
                      >
                        {msg.role === 'assistant' ? (
                          showTypingAnimation ? (
                            // If the message is still loading, show the thinking indicator
                            <div className="text-gray-500">
                              <span className="font-medium">thinking</span>
                              <span className="font-mono">...</span>
                            </div>
                          ) : !hasBeenAnimated && isLatestAssistantMessage ? (
                            // Only animate the latest assistant message and only once
                            <TypingEffect 
                              content={msg.content} 
                              onComplete={() => markMessageAnimated(index)}
                            />
                          ) : (
                            // For messages that have already been animated, display as static
                            <div className="prose prose-base max-w-full whitespace-pre-wrap" style={{ 
                              overflowWrap: 'anywhere',
                              wordBreak: 'break-word', 
                              width: '100%',
                              maxWidth: '100%',
                            }}>
                              <ReactMarkdown
                                components={{
                                  a: (props) => <MarkdownLink {...props} />,
                                  p: (props) => <p className="mb-4" style={{ overflowWrap: 'anywhere', wordBreak: 'break-word' }} {...props} />,
                                  code: (props) => <code style={{ display: 'block', whiteSpace: 'pre-wrap', overflowX: 'auto', overflowWrap: 'anywhere' }} {...props} />
                                }}
                              >
                                {linkifyText(msg.content)}
                              </ReactMarkdown>
                            </div>
                          )
                        ) : (
                          <p className="text-base" style={{ 
                            overflowWrap: 'anywhere', 
                            wordBreak: 'break-word',
                            whiteSpace: 'pre-wrap',
                            width: '100%'
                          }}>
                            {msg.content}
                          </p>
                        )}
                        
                        <div className={clsx(
                          "flex text-xs mt-2",
                          msg.role === 'user' ? "justify-start text-white/70" : "justify-between text-gray-400"
                        )}>
                          <span>{formatTime(timestamp)}</span>
                          
                          {msg.role === 'assistant' && !showTypingAnimation && (
                            <button 
                              onClick={() => copyToClipboard(msg.content)}
                              className="text-gray-400 hover:text-gray-600 transition-colors ml-2"
                              aria-label="Copy to clipboard"
                            >
                              <Copy size={16} />
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
                {isLoading && messages.length === 0 && (
                  <div className="flex justify-start">
                    <div className="bg-white border border-gray-200 rounded-xl rounded-tl-none max-w-[85%] p-4 shadow-sm">
                      <div className="text-gray-500">
                        <span className="font-medium">thinking</span>
                        <span className="font-mono">...</span>
                      </div>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          {/* Input Area */}
          <div
            className="p-4 border-t shrink-0"
            style={{
              borderColor: theme.input.border,
              background: theme.background,
              boxShadow: '0 -2px 10px rgba(0,0,0,0.05)'
            }}
          >
            <div className="flex items-end gap-3">
              <div
                className={clsx(
                  "flex-1 relative rounded-xl transition-all duration-200 overflow-hidden",
                  isFocused ? "ring-2" : "ring-0"
                )}
                style={{
                  borderColor: theme.input.border,
                  border: '1px solid',
                  boxShadow: isFocused ? '0 0 0 2px rgba(236, 153, 75, 0.2)' : 'none',
                  ['--tw-ring-color' as any]: theme.secondary,
                  background: theme.input.background
                }}
              >
                <textarea
                  ref={inputRef}
                  value={message}
                  onChange={handleMessageChange}
                  onKeyDown={handleKeyDown}
                  onFocus={() => setIsFocused(true)}
                  onBlur={() => setIsFocused(false)}
                  placeholder="Type your message..."
                  maxLength={MAX_MESSAGE_LENGTH}
                  className="w-full resize-none outline-none p-4 pr-12 text-base"
                  style={{
                    background: 'transparent',
                    color: theme.text.primary,
                    height: `${inputHeight}px`,
                    minHeight: '56px',
                    maxHeight: '120px',
                    overflow: inputHeight >= 120 ? 'auto' : 'hidden',
                    lineHeight: '1.5',
                    boxSizing: 'border-box'
                  }}
                />
                {message.length > 0 && (
                  <div
                    className="absolute bottom-2 right-3 text-xs px-2 py-1 rounded-full"
                    style={{
                      color: message.length >= MAX_MESSAGE_LENGTH * 0.9 ? '#ef4444' : '#6b7280',
                      backgroundColor: message.length >= MAX_MESSAGE_LENGTH * 0.9 ? 'rgba(239, 68, 68, 0.1)' : 'rgba(107, 114, 128, 0.1)',
                      fontSize: '0.7rem'
                    }}
                  >
                    {message.length}/{MAX_MESSAGE_LENGTH}
                  </div>
                )}
              </div>
              <button
                onClick={handleSendMessage}
                disabled={!message.trim() || isLoading}
                className={clsx(
                  "rounded-full p-4 transition-all duration-200 flex items-center justify-center shrink-0",
                  message.trim() && !isLoading
                    ? "hover:shadow-md transform hover:-translate-y-0.5"
                    : "bg-gray-200 text-gray-400 cursor-not-allowed"
                )}
                style={{
                  backgroundColor: message.trim() && !isLoading ? theme.secondary : undefined,
                  color: message.trim() && !isLoading ? 'white' : undefined,
                  width: '56px',
                  height: '56px'
                }}
                aria-label="Send message"
              >
                <Send size={24} />
              </button>
            </div>
          </div>
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
            isButtonHovered && !isOpen && "animate-pulse"
          )}
          style={{
            backgroundColor: theme.primary,
            color: theme.text.inverse,
            width: '64px',
            height: '64px'
          }}
          aria-label={isOpen ? "Minimize chat" : "Open chat"}
        >
          {isOpen ? (
            <X size={32} className="text-white" style={{ opacity: 0.9 }} />
          ) : (
            <ChatIcon iconName="message-square" size={32} className="text-white" />
          )}
        </button>
      </div>
    </div>
  );
};