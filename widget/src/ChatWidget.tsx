import React, { useState, useRef, useEffect } from 'react';
import { MessageSquare, X, Minimize2, Send, Copy, Trash2, Heart, HelpCircle, Info, MessageCircle, Bot, Sparkles } from 'lucide-react';
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
  switch(iconName) {
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

  // Modify the onChange handler to limit input
  const handleMessageChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const input = e.target.value;
    if (input.length <= MAX_MESSAGE_LENGTH) {
      setMessage(input);
    }
  };

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col items-end">
      {/* Chat Window */}
      {isOpen && (
        <div className="mb-4 w-96 sm:w-[500px] md:w-[600px] rounded-xl shadow-xl flex flex-col overflow-hidden border border-gray-200 transition-all duration-300 ease-in-out"
             style={{ background: theme.background }}>
          {/* Header */}
          <div className="p-3 flex justify-between items-center"
               style={{ background: theme.primary, color: theme.text.inverse }}>
            <div className="flex items-center">
              <ChatIcon iconName={currentConfig.icon} size={28} className="mr-2" style={{ color: theme.secondary }} />
              <h3 className="font-medium">{currentConfig.header.title}</h3>
            </div>
            <div className="flex items-center space-x-2">
              <button 
                onClick={() => clearMessages()}
                className="transition-colors p-1 rounded-full hover:bg-opacity-20 hover:bg-black"
                style={{ color: theme.text.inverse }}
                aria-label="Clear conversation"
              >
                <Trash2 size={18} />
              </button>
              <button 
                onClick={toggleChat}
                className="transition-colors p-1 rounded-full hover:bg-opacity-20 hover:bg-black"
                style={{ color: theme.text.inverse }}
                aria-label="Minimize chat"
              >
                <Minimize2 size={18} />
              </button>
            </div>
          </div>
          
          {/* Messages */}
          <div className="flex-1 p-3 overflow-y-auto max-h-[500px]"
               style={{ background: theme.input.background }}>
            {messages.length === 0 ? (
              <div className="text-center py-8">
                <ChatIcon 
                  iconName={currentConfig.icon} 
                  size={40} 
                  className="mx-auto mb-3" 
                  style={{ color: theme.iconColor }}
                />
                <h4 className="font-medium text-[#2C3E50] mb-1">{currentConfig.welcome.title}</h4>
                <p className="text-sm text-gray-600 mb-4">
                  {currentConfig.welcome.description}
                </p>
                <div className="space-y-2">
                  {currentConfig.suggestedQuestions.map((question, index) => (
                    <button 
                      key={index}
                      onClick={() => sendMessage(question.query)}
                      className="w-full text-left text-sm p-2 rounded-lg transition-colors"
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
              <div className="space-y-4">
                {messages.map((msg: Message, index: number) => {
                  // Create a timestamp for each message
                  const timestamp = new Date();
                  timestamp.setMinutes(timestamp.getMinutes() - (messages.length - index));
                  
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
                          "max-w-[85%] rounded-xl p-3 shadow-sm",
                          msg.role === 'user' ? "rounded-tr-none" : "rounded-tl-none"
                        )}
                        style={{
                          background: msg.role === 'user' ? theme.message.user : theme.message.assistant,
                          color: msg.role === 'user' ? theme.message.userText : theme.text.primary,
                          border: msg.role === 'assistant' ? `1px solid ${theme.input.border}` : 'none'
                        }}
                      >
                        {msg.role === 'assistant' && (
                          <div className="prose prose-sm max-w-none whitespace-pre-line">
                            <ReactMarkdown
                              components={{
                                a: (props) => <MarkdownLink {...props} />,
                                p: ({node, ...props}) => <p className="mb-4" {...props} />
                              }}
                            >
                              {linkifyText(msg.content)}
                            </ReactMarkdown>
                          </div>
                        )}
                        {msg.role === 'user' && (
                          <p>{msg.content}</p>
                        )}
                        
                        <div className={clsx(
                          "flex text-xs mt-1",
                          msg.role === 'user' ? "justify-start text-white/70" : "justify-between text-gray-400"
                        )}>
                          <span>{formatTime(timestamp)}</span>
                          
                          {msg.role === 'assistant' && (
                            <button 
                              onClick={() => copyToClipboard(msg.content)}
                              className="text-gray-400 hover:text-gray-600 transition-colors ml-2"
                              aria-label="Copy to clipboard"
                            >
                              <Copy size={14} />
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
                {isLoading && (
                  <div className="flex justify-start">
                    <div className="bg-white border border-gray-200 rounded-xl rounded-tl-none max-w-[85%] p-3 shadow-sm">
                      <div className="flex space-x-2">
                        <div className="h-2 w-2 bg-orange-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                        <div className="h-2 w-2 bg-orange-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                        <div className="h-2 w-2 bg-orange-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                      </div>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>
          
          {/* Input */}
          <div className="p-3 border-t bg-white"
               style={{ borderColor: theme.input.border, background: theme.background }}>
            <div className="flex items-center gap-2">
              <div className="flex-1 relative">
                <textarea
                  ref={inputRef}
                  value={message}
                  onChange={handleMessageChange}
                  onKeyDown={handleKeyDown}
                  placeholder="Type your message..."
                  maxLength={MAX_MESSAGE_LENGTH}
                  className="w-full resize-none border rounded-lg focus:outline-none focus:ring-2"
                  style={{
                    background: theme.input.background,
                    borderColor: theme.input.border,
                    color: theme.text.primary,
                    '--tw-ring-color': theme.secondary,
                    lineHeight: '20px',
                    padding: '8px 12px',
                    height: '40px',
                    minHeight: '40px',
                    boxSizing: 'border-box'
                  } as React.CSSProperties}
                />
                {message.length > 0 && (
                  <div 
                    className="absolute bottom-1 right-2 text-xs"
                    style={{ 
                      color: message.length >= MAX_MESSAGE_LENGTH * 0.9 ? '#ef4444' : '#6b7280',
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
                  "rounded-lg transition-all duration-200 flex items-center justify-center shrink-0",
                  message.trim() && !isLoading
                    ? "text-white hover:shadow-md transform hover:-translate-y-0.5"
                    : "bg-gray-200 text-gray-400 cursor-not-allowed"
                )}
                style={{
                  backgroundColor: message.trim() && !isLoading ? theme.secondary : undefined,
                  height: '40px',
                  width: '44px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
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
          <span className="absolute -top-1 -right-1 h-3 w-3 bg-orange-500 rounded-full animate-pulse z-10"></span>
        )}
        <button
          onClick={toggleChat}
          onMouseEnter={() => setIsButtonHovered(true)}
          onMouseLeave={() => setIsButtonHovered(false)}
          className={clsx(
            "rounded-full p-3 shadow-lg flex items-center justify-center transition-all duration-300",
            isButtonHovered && !isOpen && "animate-pulse"
          )}
          style={{
            backgroundColor: isOpen ? theme.primary : theme.primary,
            color: theme.text.inverse
          }}
          aria-label={isOpen ? "Minimize chat" : "Open chat"}
        >
          {isOpen ? (
            <Minimize2 size={32} className="text-white" style={{ opacity: 0.9 }} />
          ) : (
            <ChatIcon iconName="message-square" size={32} className="text-white" />
          )}
        </button>
      </div>
    </div>
  );
};