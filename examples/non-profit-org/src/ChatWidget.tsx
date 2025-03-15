import React, { useState, useRef, useEffect } from 'react';
import { MessageSquare, X, Minimize2, Send, Copy, Trash2, Heart } from 'lucide-react';
import { useChatStore, Message } from './store/chatStore';
import ReactMarkdown from 'react-markdown';
import clsx from 'clsx';

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

const ChatWidget: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [message, setMessage] = useState('');
  const [hasNewMessage, setHasNewMessage] = useState(false);
  const [isButtonHovered, setIsButtonHovered] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  
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

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col items-end">
      {/* Chat Window */}
      {isOpen && (
        <div className="mb-4 w-96 sm:w-[500px] md:w-[600px] bg-white rounded-xl shadow-xl flex flex-col overflow-hidden border border-gray-200 transition-all duration-300 ease-in-out">
          {/* Header */}
          <div className="bg-[#2C3E50] text-white p-3 flex justify-between items-center">
            <div className="flex items-center">
              <Heart size={20} className="mr-2 text-orange-400" />
              <h3 className="font-medium">Community Support</h3>
            </div>
            <div className="flex items-center space-x-2">
              <button 
                onClick={() => clearMessages()}
                className="text-white hover:text-orange-400 transition-colors p-1 rounded-full hover:bg-[#3a526a]"
                aria-label="Clear conversation"
              >
                <Trash2 size={18} />
              </button>
              <button 
                onClick={toggleChat}
                className="text-white hover:text-orange-400 transition-colors p-1 rounded-full hover:bg-[#3a526a]"
                aria-label="Minimize chat"
              >
                <Minimize2 size={18} />
              </button>
            </div>
          </div>
          
          {/* Messages */}
          <div className="flex-1 p-3 overflow-y-auto max-h-[500px] bg-gray-50">
            {messages.length === 0 ? (
              <div className="text-center py-8">
                <Heart size={40} className="mx-auto text-orange-400 mb-3" />
                <h4 className="font-medium text-[#2C3E50] mb-1">Welcome to Community Support!</h4>
                <p className="text-sm text-gray-600 mb-4">
                  I can help you learn about our programs, services, and how to get involved with our organization.
                </p>
                <div className="space-y-2">
                  <button 
                    onClick={() => sendMessage("What programs do you offer for youth?")}
                    className="w-full text-left text-sm bg-orange-50 hover:bg-orange-100 text-[#2C3E50] p-2 rounded-lg transition-colors"
                  >
                    What programs do you offer for youth?
                  </button>
                  <button 
                    onClick={() => sendMessage("How can I volunteer with your organization?")}
                    className="w-full text-left text-sm bg-orange-50 hover:bg-orange-100 text-[#2C3E50] p-2 rounded-lg transition-colors"
                  >
                    How can I volunteer with your organization?
                  </button>
                  <button 
                    onClick={() => sendMessage("What services do you provide for seniors?")}
                    className="w-full text-left text-sm bg-orange-50 hover:bg-orange-100 text-[#2C3E50] p-2 rounded-lg transition-colors"
                  >
                    What services do you provide for seniors?
                  </button>
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
                          msg.role === 'user' 
                            ? "bg-[#2C3E50] text-white rounded-tr-none" 
                            : "bg-white border border-gray-200 rounded-tl-none"
                        )}
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
          <div className="p-3 border-t border-gray-200 bg-white">
            <div className="flex items-end">
              <textarea
                ref={inputRef}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Type your message..."
                className="flex-1 resize-none border border-gray-300 rounded-lg py-2 px-3 focus:outline-none focus:ring-2 focus:ring-orange-500 min-h-[44px] max-h-32 bg-gray-50"
                rows={1}
              />
              <button
                onClick={handleSendMessage}
                disabled={!message.trim() || isLoading}
                className={clsx(
                  "ml-2 p-2 rounded-full transition-all duration-200",
                  message.trim() && !isLoading
                    ? "bg-orange-500 text-white hover:bg-orange-600 hover:shadow-md transform hover:-translate-y-0.5"
                    : "bg-gray-200 text-gray-400 cursor-not-allowed"
                )}
                aria-label="Send message"
              >
                <Send size={18} />
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
            isOpen 
              ? "bg-red-500 hover:bg-red-600" 
              : "bg-[#2C3E50] hover:bg-[#3a526a]",
            isButtonHovered && !isOpen && "animate-pulse"
          )}
          aria-label={isOpen ? "Close chat" : "Open chat"}
        >
          {isOpen ? (
            <X size={24} className="text-white" />
          ) : (
            <MessageSquare size={24} className="text-white" />
          )}
        </button>
      </div>
    </div>
  );
};

export default ChatWidget;