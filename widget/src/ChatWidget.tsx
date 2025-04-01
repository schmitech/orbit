import React, { useState, useRef, useEffect } from 'react';
import { MessageSquare, X, Minimize2, Send, Copy, Trash2, Heart, HelpCircle, Info, MessageCircle, Bot, Sparkles, ChevronUp, ChevronDown, Check } from 'lucide-react';
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
  config?: never;
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
  const [showScrollBottom, setShowScrollBottom] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const [isScrolling, setIsScrolling] = useState(false);
  const animatedMessagesRef = useRef<Set<number>>(new Set());
  const shouldScrollRef = useRef(true);
  const scrollTimeoutRef = useRef<number>();
  const lastMessageRef = useRef<HTMLDivElement>(null);
  const isTypingRef = useRef(false);
  const [isAnimating, setIsAnimating] = useState(false);
  const [copiedMessageId, setCopiedMessageId] = useState<number | null>(null);

  // Load configuration
  const baseConfig = getChatConfig();
  const [currentConfig, setCurrentConfig] = useState({
    ...baseConfig,
    ...props
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
      setTimeout(() => scrollToBottom(true), 100);
    }
  };

  const handleSendMessage = () => {
    if (message.trim() && !isLoading) {
      shouldScrollRef.current = true;
      sendMessage(message);
      setMessage('');
      setTimeout(() => scrollToBottom(true), 100);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const copyToClipboard = async (text: string, messageIndex: number) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedMessageId(messageIndex);
      setTimeout(() => {
        setCopiedMessageId(null);
      }, 2000);
    } catch (err) {
      console.error('Failed to copy text: ', err);
    }
  };

  // Helper function to convert URLs to markdown links in plain text and preserve line breaks
  const linkifyText = (text: string): string => {
    const urlRegex = /(https?:\/\/[^\s]+?)([.,;:!?)]*)(?=\s|$)/g;
    const linkedText = text.replace(urlRegex, (match, url, punctuation) =>
      `[${url}](${url})${punctuation}`
    );
    return linkedText
      .replace(/\n{2,}/g, '\n\n')
      .replace(/\n/g, '\n');
  };

  // Format timestamp
  const formatTime = (date: Date): string => {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  // Scroll to bottom function with immediate option
  const scrollToBottom = (immediate = false) => {
    if (messagesContainerRef.current) {
      const { scrollHeight } = messagesContainerRef.current;
      messagesContainerRef.current.scrollTo({
        top: scrollHeight,
        behavior: immediate ? 'auto' : 'smooth'
      });
      
      // Update scroll buttons visibility after scrolling
      setTimeout(() => {
        handleScroll();
      }, immediate ? 0 : 300);
    }
  };

  // Check scroll position to determine if scroll buttons should be shown
  const handleScroll = () => {
    if (messagesContainerRef.current && !isAnimating) {
      const { scrollTop, scrollHeight, clientHeight } = messagesContainerRef.current;
      const isAtBottom = Math.abs(scrollHeight - scrollTop - clientHeight) < 10;
      const isAtTop = scrollTop < 10;
      
      setShowScrollTop(!isAtTop && scrollTop > 200);
      setShowScrollBottom(!isAtBottom);
    }
  };

  // Scroll to top function
  const scrollToTop = () => {
    if (messagesContainerRef.current) {
      setIsScrolling(true);
      messagesContainerRef.current.scrollTo({
        top: 0,
        behavior: 'smooth'
      });
      setTimeout(() => {
        setIsScrolling(false);
        handleScroll();
      }, 300);
    }
  };

  // Handle message input changes
  const handleMessageChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const input = e.target.value;
    if (input.length <= MAX_MESSAGE_LENGTH) {
      setMessage(input);
    }
  };

  // Mark a message as having completed its animation
  const markMessageAnimated = (index: number) => {
    animatedMessagesRef.current.add(index);
    if (index === messages.length - 1) {
      setIsAnimating(false);
      setTimeout(() => scrollToBottom(), 50);
    }
  };

  // Check if a message has been animated
  const hasBeenAnimated = (index: number): boolean => {
    return animatedMessagesRef.current.has(index);
  };

  // Scroll to bottom when messages change or loading state changes
  useEffect(() => {
    if (isLoading || messages.length === 0) {
      scrollToBottom(true);
    }
  }, [messages, isLoading]);

  // Focus input when chat opens
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  // Cleanup scroll timeout
  useEffect(() => {
    return () => {
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }
    };
  }, []);

  // Typing effect component
  const TypingEffect = ({ content, onComplete, messageIndex }: { 
    content: string, 
    onComplete: () => void, 
    messageIndex: number 
  }) => {
    const [displayedContent, setDisplayedContent] = useState('');
    const [isThinking, setIsThinking] = useState(true);
    const [typingDots, setTypingDots] = useState('.');
    const contentRef = useRef(content);
    const charIndexRef = useRef(0);
    const [userIsTyping, setUserIsTyping] = useState(false);
    const isAnimatingRef = useRef(false);
    const animationFrameRef = useRef<number>();

    useEffect(() => {
      if (hasBeenAnimated(messageIndex)) {
        setDisplayedContent(content);
        setIsThinking(false);
        onComplete();
        return;
      }

      if (!isAnimatingRef.current) {
        isAnimatingRef.current = true;
        isTypingRef.current = true;
        setIsAnimating(true);
        let currentIndex = 0;
        let lastScrollTime = 0;
        
        const animateText = (timestamp: number) => {
          if (currentIndex < content.length) {
            const newContent = content.slice(0, currentIndex + 1);
            setDisplayedContent(newContent);
            
            if (currentIndex === 0) {
              setIsThinking(false);
            }
            
            // Scroll every 100ms during animation
            if (timestamp - lastScrollTime > 100) {
              scrollToBottom();
              lastScrollTime = timestamp;
            }
            
            currentIndex++;
            animationFrameRef.current = requestAnimationFrame(animateText);
          } else {
            isTypingRef.current = false;
            onComplete();
            isAnimatingRef.current = false;
            setIsAnimating(false);
            scrollToBottom();
          }
        };

        animationFrameRef.current = requestAnimationFrame(animateText);
      }

      return () => {
        if (animationFrameRef.current) {
          cancelAnimationFrame(animationFrameRef.current);
        }
        isAnimatingRef.current = false;
        isTypingRef.current = false;
        setIsAnimating(false);
      };
    }, [content, messageIndex, onComplete]);

    // Listen for user typing
    useEffect(() => {
      const handleMessageChange = () => {
        if (isAnimatingRef.current) {
          if (animationFrameRef.current) {
            cancelAnimationFrame(animationFrameRef.current);
          }
          setDisplayedContent(content);
          setIsThinking(false);
          onComplete();
          isAnimatingRef.current = false;
          isTypingRef.current = false;
          setIsAnimating(false);
          scrollToBottom();
        }
      };

      const textarea = document.querySelector('textarea');
      if (textarea) {
        textarea.addEventListener('input', handleMessageChange);
      }

      return () => {
        if (textarea) {
          textarea.removeEventListener('input', handleMessageChange);
        }
      };
    }, [content, onComplete]);

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
            className="flex-1 p-4 overflow-y-auto scroll-smooth relative messages-container"
            style={{
              background: theme.input.background,
              overflowY: 'auto'
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
                <ChevronDown size={20} />
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
                  const timestamp = new Date();
                  timestamp.setMinutes(timestamp.getMinutes() - (messages.length - index));
                  
                  const isLatestAssistantMessage = msg.role === 'assistant' && index === messages.length - 1;
                  const showTypingAnimation = isLatestAssistantMessage && isLoading;
                  
                  return (
                    <div 
                      key={index} 
                      className={clsx(
                        "flex",
                        msg.role === 'user' ? "justify-end" : "justify-start"
                      )}
                      ref={index === messages.length - 1 ? lastMessageRef : null}
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
                            <div className="text-gray-500">
                              <span className="font-medium">thinking</span>
                              <span className="font-mono">...</span>
                            </div>
                          ) : !hasBeenAnimated(index) && isLatestAssistantMessage ? (
                            <TypingEffect 
                              content={msg.content} 
                              onComplete={() => markMessageAnimated(index)}
                              messageIndex={index}
                            />
                          ) : (
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
                            <div className="relative">
                              <button 
                                onClick={() => copyToClipboard(msg.content, index)}
                                className="text-gray-400 hover:text-gray-600 transition-colors ml-2 p-1 rounded-full hover:bg-gray-100"
                                aria-label="Copy to clipboard"
                              >
                                {copiedMessageId === index ? <Check size={16} /> : <Copy size={16} />}
                              </button>
                              {copiedMessageId === index && (
                                <div
                                  className="absolute bottom-full right-0 mb-1 px-2 py-1 text-xs rounded-md shadow-sm animate-fade-in-out whitespace-nowrap"
                                  style={{
                                    backgroundColor: theme.secondary,
                                    color: theme.text.inverse
                                  }}
                                >
                                  Copied!
                                </div>
                              )}
                            </div>
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
                  className="w-full resize-none outline-none p-3 pr-12 text-base custom-scrollbar"
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
                  "rounded-full p-3 transition-all duration-200 flex items-center justify-center shrink-0",
                  message.trim() && !isLoading
                    ? "hover:shadow-md transform hover:-translate-y-0.5"
                    : "bg-gray-200 text-gray-400 cursor-not-allowed"
                )}
                style={{
                  backgroundColor: message.trim() && !isLoading ? theme.secondary : undefined,
                  color: message.trim() && !isLoading ? 'white' : undefined,
                  width: '48px',
                  height: '48px'
                }}
                aria-label="Send message"
              >
                <Send size={20} />
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

      <style>{`
        @keyframes fadeInOut {
          0% { opacity: 0; transform: translateY(4px); }
          20% { opacity: 1; transform: translateY(0); }
          80% { opacity: 1; transform: translateY(0); }
          100% { opacity: 0; transform: translateY(-4px); }
        }
        .animate-fade-in-out {
          animation: fadeInOut 2s ease-in-out forwards;
        }
      `}</style>
    </div>
  );
};