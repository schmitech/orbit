import React, { useState, useRef, useEffect } from 'react';
import { MessageSquare, X, Minimize2, Send, Copy, Trash2, Heart, HelpCircle, Info, MessageCircle, Bot, Sparkles, ChevronUp, ChevronDown, Check } from 'lucide-react';
import { useChatStore, Message } from './store/chatStore';
import ReactMarkdown from 'react-markdown';
import clsx from 'clsx';
import { getChatConfig, defaultTheme, ChatConfig } from './config/index';
import { configureApi } from '@schmitech/chatbot-api';
import MessagesSquareIcon from './config/messages-square.svg?react';
import remarkGfm from 'remark-gfm';
import rehypeSanitize from 'rehype-sanitize';
import rehypeHighlight from 'rehype-highlight';

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
              <span style={{ width: size ? size * 0.12 : 3, height: size ? size * 0.12 : 3, borderRadius: '50%', background: 'white', display: 'inline-block' }} />
              <span style={{ width: size ? size * 0.12 : 3, height: size ? size * 0.12 : 3, borderRadius: '50%', background: 'white', display: 'inline-block' }} />
              <span style={{ width: size ? size * 0.12 : 3, height: size ? size * 0.12 : 3, borderRadius: '50%', background: 'white', display: 'inline-block' }} />
            </span>
          )}
        </span>
      );
    default:
      return <MessageSquare size={size} className={className} style={style} />;
  }
};

// Custom component for rendering Markdown content
const MarkdownRenderer = ({ content }: { content: string }) => {
  return (
    <div className="prose prose-slate max-w-full dark:prose-invert overflow-hidden break-words" style={{ color: 'inherit' }}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize, rehypeHighlight]}
        components={{
          a: ({ node, ...props }) => (
            <a
              {...props}
              target="_blank"
              rel="noopener noreferrer"
              className="text-orange-500 hover:text-orange-700 underline"
            />
          ),
          p: ({ node, ...props }) => (
            <p style={{ color: 'inherit', margin: '0 0 0.5em 0' }} {...props} />
          ),
          pre: ({ node, ...props }) => (
            <pre className="overflow-x-auto p-4 rounded-md bg-gray-100 dark:bg-gray-800" {...props} />
          ),
          code: ({ node, ...props }) => (
            <code className="px-1 py-0.5 rounded-md bg-gray-100 dark:bg-gray-800 text-sm" {...props} />
          ),
          ul: ({ node, ...props }) => (
            <ul style={{ color: 'inherit', margin: '0.5em 0', paddingLeft: '1.5em' }} {...props} />
          ),
          ol: ({ node, ...props }) => (
            <ol style={{ color: 'inherit', margin: '0.5em 0', paddingLeft: '1.5em' }} {...props} />
          ),
          li: ({ node, ...props }) => (
            <li style={{ color: 'inherit', marginBottom: '0.25em' }} {...props} />
          ),
          h1: ({ node, ...props }) => (
            <h1 style={{ color: 'inherit', margin: '1em 0 0.5em 0' }} {...props} />
          ),
          h2: ({ node, ...props }) => (
            <h2 style={{ color: 'inherit', margin: '1em 0 0.5em 0' }} {...props} />
          ),
          h3: ({ node, ...props }) => (
            <h3 style={{ color: 'inherit', margin: '1em 0 0.5em 0' }} {...props} />
          ),
          h4: ({ node, ...props }) => (
            <h4 style={{ color: 'inherit', margin: '1em 0 0.5em 0' }} {...props} />
          ),
          h5: ({ node, ...props }) => (
            <h5 style={{ color: 'inherit', margin: '1em 0 0.5em 0' }} {...props} />
          ),
          h6: ({ node, ...props }) => (
            <h6 style={{ color: 'inherit', margin: '1em 0 0.5em 0' }} {...props} />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
};

export default MarkdownRenderer;

export interface ChatWidgetProps extends Partial<ChatConfig> {
  config?: never;
  sessionId: string;
  apiUrl: string;
  apiKey: string;
}

export const ChatWidget: React.FC<ChatWidgetProps> = (props) => {
  const [isOpen, setIsOpen] = useState(false);
  const [message, setMessage] = useState('');
  const [hasNewMessage, setHasNewMessage] = useState(false);
  const [isButtonHovered, setIsButtonHovered] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const MAX_MESSAGE_LENGTH = 250;
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const [showScrollTop, setShowScrollTop] = useState(false);
  const [showScrollBottom, setShowScrollBottom] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const [isScrolling, setIsScrolling] = useState(false);
  const animatedMessagesRef = useRef<Set<number>>(new Set());
  const typingProgressRef = useRef<Map<number, number>>(new Map());
  const shouldScrollRef = useRef(true);
  const scrollTimeoutRef = useRef<number>();
  const lastMessageRef = useRef<HTMLDivElement>(null);
  const isTypingRef = useRef(false);
  const [isAnimating, setIsAnimating] = useState(false);
  const [copiedMessageId, setCopiedMessageId] = useState<number | null>(null);

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
  
  // Clear animated messages tracker when conversation resets
  useEffect(() => {
    if (messages.length === 0) {
      animatedMessagesRef.current.clear();
    }
  }, [messages.length]);

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
    
    // Only add the two spaces to lines that aren't already part of a paragraph break
    // This preserves intentional single line breaks without adding extra spacing
    return linkedText;
  };

  // Normalize text for consistent paragraph spacing
  const normalizeText = (text: string): string => {
    // Replace 3+ newlines with just 2 (Markdown paragraph)
    let normalized = text.replace(/\n{3,}/g, '\n\n');
    
    // Fix spacing between list items 
    normalized = normalized.replace(/\n(\s*[-*+]|\s*\d+\.)\s*/g, '\n$1 ');
    
    // Ensure paragraphs have consistent spacing
    normalized = normalized.replace(/\n\n\n+/g, '\n\n');
    
    return normalized.trim();
  };

  // Format timestamp (note: uses a relative offset since messages lack explicit timestamps)
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

  // Typing effect component with inputRef support
  const TypingEffect = ({ content, onComplete, messageIndex, inputRef }: { 
    content: string, 
    onComplete: () => void, 
    messageIndex: number,
    inputRef: React.RefObject<HTMLTextAreaElement>
  }) => {
    // Use a ref to store the current animation progress
    const [displayedContent, setDisplayedContent] = useState(() => {
      // Restore progress if available
      const progress = typingProgressRef.current.get(messageIndex);
      return progress ? content.slice(0, progress) : '';
    });
    const [isThinking, setIsThinking] = useState(true);
    const currentIndexRef = useRef(typingProgressRef.current.get(messageIndex) || 0);
    const isAnimatingRef = useRef(false);
    const animationFrameRef = useRef<number>();
    // This flag tracks whether animation has been initialized
    const hasInitializedRef = useRef(false);
    // We'll use this to store the full content to ensure continuity
    const fullContentRef = useRef(content);

    // Initialize animation only once
    useEffect(() => {
      // Skip if this message has already been animated
      if (hasBeenAnimated(messageIndex)) {
        setDisplayedContent(content);
        setIsThinking(false);
        onComplete();
        typingProgressRef.current.set(messageIndex, content.length);
        return;
      }

      // Skip if we've already initialized
      if (hasInitializedRef.current) {
        return;
      }

      // Mark as initialized to prevent restart on re-render
      hasInitializedRef.current = true;
      fullContentRef.current = content;

      // Start the animation
      startTypingAnimation();

      return () => {
        if (animationFrameRef.current) {
          cancelAnimationFrame(animationFrameRef.current);
        }
      };
    }, [messageIndex, content]);

    // Function to handle animation
    const startTypingAnimation = () => {
      if (isAnimatingRef.current) return;

      isAnimatingRef.current = true;
      isTypingRef.current = true;
      setIsAnimating(true);
      
      // Start from current position (important for resuming after tab switching)
      let currentIndex = currentIndexRef.current;
      let lastScrollTime = 0;

      // Show thinking state only at the beginning
      if (currentIndex === 0) {
        setIsThinking(true);
      } else {
        setIsThinking(false);
      }

      const animateText = (timestamp: number) => {
        if (currentIndex < fullContentRef.current.length) {
          const newContent = fullContentRef.current.slice(0, currentIndex + 1);
          setDisplayedContent(newContent);
          typingProgressRef.current.set(messageIndex, currentIndex + 1);
          
          // Exit thinking state after first character
          if (currentIndex === 0) {
            setIsThinking(false);
          }

          // Scroll occasionally during animation
          if (timestamp - lastScrollTime > 100) {
            scrollToBottom();
            lastScrollTime = timestamp;
          }

          // Save the current position (crucial for resuming)
          currentIndex++;
          currentIndexRef.current = currentIndex;
          
          animationFrameRef.current = requestAnimationFrame(animateText);
        } else {
          // Animation is complete
          completeAnimation();
        }
      };

      animationFrameRef.current = requestAnimationFrame(animateText);
    };

    // Handle animation completion
    const completeAnimation = () => {
      isTypingRef.current = false;
      onComplete();
      isAnimatingRef.current = false;
      setIsAnimating(false);
      scrollToBottom();
      typingProgressRef.current.set(messageIndex, fullContentRef.current.length);
    };

    // Handle user input to skip animation
    useEffect(() => {
      const handleUserInput = () => {
        if (isAnimatingRef.current) {
          if (animationFrameRef.current) {
            cancelAnimationFrame(animationFrameRef.current);
          }
          setDisplayedContent(fullContentRef.current);
          setIsThinking(false);
          completeAnimation();
          typingProgressRef.current.set(messageIndex, fullContentRef.current.length);
        }
      };

      const textarea = inputRef.current;
      if (textarea) {
        textarea.addEventListener('input', handleUserInput);
      }

      return () => {
        if (textarea) {
          textarea.removeEventListener('input', handleUserInput);
        }
      };
    }, [inputRef, onComplete]);

    // This is the key handler for document visibility changes
    useEffect(() => {
      let hiddenAt: number | null = null;
      const handleVisibilityChange = () => {
        if (document.hidden) {
          // Page is hidden, pause by canceling current animation
          if (animationFrameRef.current) {
            cancelAnimationFrame(animationFrameRef.current);
            isAnimatingRef.current = false;
          }
          hiddenAt = Date.now();
        } else if (hasInitializedRef.current && !isAnimatingRef.current && currentIndexRef.current > 0 && currentIndexRef.current < fullContentRef.current.length) {
          // Page is visible again
          const now = Date.now();
          if (hiddenAt && now - hiddenAt > 1000) {
            // If away for more than 1s, instantly finish animation
            setDisplayedContent(fullContentRef.current);
            setIsThinking(false);
            completeAnimation();
            typingProgressRef.current.set(messageIndex, fullContentRef.current.length);
          } else {
            // Resume animation
            startTypingAnimation();
          }
          hiddenAt = null;
        }
      };

      document.addEventListener('visibilitychange', handleVisibilityChange);
      
      return () => {
        document.removeEventListener('visibilitychange', handleVisibilityChange);
      };
    }, []);

    return (
      <>
        {displayedContent && (
          <div className="prose prose-base max-w-full whitespace-pre-wrap" style={{ 
            overflowWrap: 'anywhere',
            wordBreak: 'break-word', 
            width: '100%',
            maxWidth: '100%',
            fontSize: '16px',
          }}>
            <ReactMarkdown
              components={{
                a: (props) => <MarkdownLink {...props} />,
                p: (props) => <p style={{ 
                  overflowWrap: 'anywhere', 
                  wordBreak: 'break-word',
                  margin: '0 0 0.2em 0'
                }} {...props} />,
                code: (props) => <code style={{ display: 'block', whiteSpace: 'pre-wrap', overflowX: 'auto', overflowWrap: 'anywhere' }} {...props} />
              }}
            >
              {normalizeText(linkifyText(displayedContent))}
            </ReactMarkdown>
          </div>
        )}
        {isThinking && (
          <div className="text-gray-500">
            <span className="font-medium">Thinking</span>
            <span className="animate-dots ml-1">
              <span className="dot">.</span>
              <span className="dot">.</span>
              <span className="dot">.</span>
            </span>
          </div>
        )}
      </>
    );
  };

  return (
    <div className="fixed bottom-8 right-8 z-50 flex flex-col items-end font-sans" style={{ fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif' }}>
      {/* Chat Window */}
      {isOpen && (
        <div
          className="mb-4 w-full sm:w-[480px] md:w-[600px] lg:w-[700px] rounded-xl shadow-xl flex flex-col overflow-hidden border border-gray-200 transition-all duration-300 ease-in-out"
          style={{
            background: theme.background,
            height: '600px',
            maxHeight: 'calc(100vh - 80px)',
            width: windowWidth < 640 ? '100%' :
              windowWidth < 768 ? '480px' :
                windowWidth < 1024 ? '600px' : '700px',
            minWidth: windowWidth < 640 ? '100%' : '480px',
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
                onClick={() => {
                  clearMessages();
                  // Clearing animated messages tracker on clear
                  animatedMessagesRef.current.clear();
                }}
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
                <Minimize2 size={40} className="text-white" style={{ opacity: 0.9 }} />
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
                <div className="w-full px-4">
                  {currentConfig.suggestedQuestions.map((question, index) => (
                    <button
                      key={index}
                      onClick={() => {
                        sendMessage(question.query);
                        // Focus the input field after sending a predefined question
                        setTimeout(() => {
                          if (inputRef.current) {
                            inputRef.current.focus();
                          }
                        }, 100);
                      }}
                      className="w-full text-left text-base p-3 rounded-lg transition-colors mb-3 flex items-center"
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
                      <MessageCircle size={20} className="mr-2 flex-shrink-0" />
                      <span>{question.text}</span>
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
                              <span className="font-medium">Thinking</span>
                              <span className="animate-dots ml-1">
                                <span className="dot">.</span>
                                <span className="dot">.</span>
                                <span className="dot">.</span>
                              </span>
                            </div>
                          ) : !hasBeenAnimated(index) && isLatestAssistantMessage ? (
                            <TypingEffect 
                              content={msg.content} 
                              onComplete={() => markMessageAnimated(index)}
                              messageIndex={index}
                              inputRef={inputRef}
                            />
                          ) : (
                            <MarkdownRenderer content={normalizeText(linkifyText(msg.content))} />
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
                        <span className="font-medium">Thinking</span>
                        <span className="animate-dots ml-1">
                          <span className="dot">.</span>
                          <span className="dot">.</span>
                          <span className="dot">.</span>
                        </span>
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
                  isFocused ? "ring-0" : "ring-0"
                )}
                style={{
                  borderColor: isFocused ? theme.secondary : theme.input.border,
                  border: '1px solid',
                  boxShadow: 'none',
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
                  "rounded-full transition-all duration-200 flex items-center justify-center shrink-0",
                  message.trim() && !isLoading
                    ? "hover:shadow-md transform hover:-translate-y-0.5"
                    : "bg-gray-200 text-gray-400 cursor-not-allowed"
                )}
                style={{
                  backgroundColor: message.trim() && !isLoading ? theme.secondary : undefined,
                  color: message.trim() && !isLoading ? 'white' : undefined,
                  width: '48px',
                  height: '48px',
                  padding: '12px'
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
            isButtonHovered && !isOpen && "animate-pulse",
            !isOpen && "animate-bounce-gentle"
          )}
          style={{
            background: isOpen ? theme.primary : 'transparent',
            color: !isOpen ? theme.iconColor : undefined,
            border: 'none',
            boxShadow: 'none',
            width: '64px',
            height: '64px',
          }}
          aria-label={isOpen ? "Close chat" : "Open chat"}
        >
          {isOpen ? (
            <Minimize2 size={40} className="text-white" style={{ opacity: 0.9 }} />
          ) : (
            <MessagesSquareIcon width={48} height={48} />
          )}
        </button>
      </div>

      <style>{`
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

body, button, input, textarea {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

/* Complete focus ring removal - covers all browsers and scenarios */
textarea,
textarea:focus,
textarea:focus-visible,
input,
input:focus,
input:focus-visible {
  outline: none !important;
  box-shadow: none !important;
  border-color: inherit !important;
  -webkit-appearance: none !important;
  -moz-appearance: none !important;
  -webkit-tap-highlight-color: transparent !important;
}

/* Alternative: Uncomment for subtle light focus ring instead of complete removal */
/*
textarea:focus,
textarea:focus-visible {
  outline: 2px solid rgba(203, 213, 225, 0.4) !important;
  outline-offset: -1px !important;
  box-shadow: 0 0 0 1px rgba(203, 213, 225, 0.2) !important;
}
*/

/* Remove webkit/safari specific styling */
textarea::-webkit-input-placeholder,
input::-webkit-input-placeholder {
  -webkit-appearance: none;
}

/* Ensure buttons also don't show focus rings */
button:focus,
button:focus-visible {
  outline: none !important;
  box-shadow: none !important;
}

@keyframes fadeInOut {
  0% { opacity: 0; transform: translateY(4px); }
  20% { opacity: 1; transform: translateY(0); }
  80% { opacity: 1; transform: translateY(0); }
  100% { opacity: 0; transform: translateY(-4px); }
}
.animate-fade-in-out {
  animation: fadeInOut 2s ease-in-out forwards;
}

@keyframes bounce-gentle {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}
.animate-bounce-gentle {
  animation: bounce-gentle 2s ease-in-out infinite;
  animation-delay: 1s;
}

@keyframes dotBlink {
  0%, 50%, 100% { opacity: 0; }
  25%, 75% { opacity: 1; }
}
.animate-dots {
  display: inline-flex;
  margin-left: 4px;
}
.animate-dots .dot {
  font-size: 1.5em;
  line-height: 0.5;
  opacity: 0;
  animation: dotBlink 1.4s infinite;
}
.animate-dots .dot:nth-child(1) {
  animation-delay: 0s;
}
.animate-dots .dot:nth-child(2) {
  animation-delay: 0.2s;
}
.animate-dots .dot:nth-child(3) {
  animation-delay: 0.4s;
}

.prose {
  max-width: 100%;
}

.prose > * {
  margin-top: 0 !important;
  margin-bottom: 0.5em !important;
}

.prose p {
  margin: 0 0 0.5em 0 !important;
  padding: 0;
  line-height: 1.5;
}

.prose p:last-child {
  margin-bottom: 0 !important;
}

.prose ul,
.prose ol {
  margin-top: 0.5em !important;
  margin-bottom: 0.5em !important;
  padding-left: 1.5em !important;
}

.prose li {
  margin-bottom: 0.25em !important;
  padding-left: 0.25em !important;
  line-height: 1.4;
}

.prose li p {
  margin: 0 !important;
}

.prose li + li {
  margin-top: 0.1em !important;
}

.prose h1, .prose h2, .prose h3, .prose h4, .prose h5, .prose h6 {
  margin-top: 1em !important;
  margin-bottom: 0.5em !important;
}
      `}</style>
    </div>
  );
};