import React, { useState, useRef, useEffect } from 'react';
import { MessageSquare, X, Minimize2, Send, Copy, Trash2, ArrowLeft, Wifi, Battery, Signal } from 'lucide-react';
import { useChatStore } from '../../../store/chatStore';
import ReactMarkdown from 'react-markdown';
import clsx from 'clsx';

// Reuse the same MarkdownLink component
const MarkdownLink = (props: React.AnchorHTMLAttributes<HTMLAnchorElement>) => {
  // Extract the href and children for display
  const { href, children } = props;
  
  // If the children is just text that looks like a URL, clean it up for display
  let displayText = children;
  if (typeof children === 'string' && children.startsWith('http')) {
    // Truncate long URLs for display
    displayText = children.length > 30 ? children.substring(0, 27) + '...' : children;
  }
  
  return (
    <a 
      {...props}
      target="_blank"
      rel="noopener noreferrer"
      className="text-primary-600 hover:text-primary-800 underline break-words overflow-wrap-anywhere"
    >
      {displayText}
    </a>
  );
};

// Helper to determine device type from URL
const getDeviceType = (): string => {
  const url = window.location.href;
  if (url.includes('iphone-se')) return 'iphone-se';
  if (url.includes('iphone-12')) return 'iphone-12';
  if (url.includes('iphone-16')) return 'iphone-16';
  if (url.includes('pixel')) return 'pixel';
  if (url.includes('galaxy')) return 'galaxy';
  
  // Check for device type in URL hash
  const hash = window.location.hash.substring(1);
  if (['iphone-se', 'iphone-12', 'iphone-16', 'pixel', 'galaxy'].includes(hash)) {
    return hash;
  }
  
  return 'iphone-16'; // Default
};

const MobileChatWidget: React.FC = () => {
  const [message, setMessage] = useState('');
  const [currentTime, setCurrentTime] = useState('');
  const [deviceType, setDeviceType] = useState(getDeviceType());
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  
  const { 
    messages, 
    isLoading, 
    sendMessage, 
    clearMessages 
  } = useChatStore();

  // Update device type when URL changes
  useEffect(() => {
    const handleHashChange = () => {
      setDeviceType(getDeviceType());
    };
    
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  // Update time every minute
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      const hours = now.getHours();
      const minutes = now.getMinutes();
      const formattedHours = hours % 12 || 12; // Convert to 12-hour format
      const formattedMinutes = minutes < 10 ? `0${minutes}` : minutes;
      setCurrentTime(`${formattedHours}:${formattedMinutes}`);
    };
    
    updateTime(); // Initial update
    const interval = setInterval(updateTime, 60000); // Update every minute
    
    return () => clearInterval(interval);
  }, []);

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
    if (!text) return '';
    
    // URL regex pattern - don't include trailing punctuation in the URL
    const urlRegex = /(https?:\/\/[^\s]+?)([.,;:!?)]*)(?=\s|$)/g;
    
    // Replace URLs with markdown links, preserving trailing punctuation outside the link
    // Use proper markdown link syntax that ReactMarkdown can process correctly
    const linkedText = text.replace(urlRegex, (match, url, punctuation) => {
      // Clean the URL if it has any markdown characters
      const cleanUrl = url.replace(/[[\]()]/g, '');
      return `[${cleanUrl}](${cleanUrl})${punctuation}`;
    });
    
    // Process the text to handle line breaks properly
    const processedText = linkedText
      .replace(/\n{2,}/g, '\n\n')
      .replace(/\n/g, '\n');
    
    return processedText;
  };

  // Scroll to bottom when messages change
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  // Focus input when component mounts
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.focus();
    }
  }, []);

  return (
    <div className="flex flex-col h-full bg-neutral-50">
      {/* Status Bar */}
      <div className="bg-primary-700 text-white px-4 py-1 flex justify-between items-center text-xs">
        <div>{currentTime}</div>
        <div className="flex items-center space-x-2">
          <Signal size={12} />
          <Wifi size={12} />
          <Battery size={14} className="rotate-90" />
        </div>
      </div>
      
      {/* Mobile Header */}
      <div className={clsx(
        "bg-primary-600 text-white p-4 flex justify-between items-center",
        {
          'pt-6': deviceType === 'iphone-16',
          'pt-5': deviceType === 'iphone-12',
          'pt-3': deviceType === 'iphone-se' || deviceType === 'galaxy',
          'pt-4': deviceType === 'pixel'
        }
      )}>
        <div className="flex items-center">
          <ArrowLeft size={20} className="mr-2 text-white" onClick={() => window.history.back()} />
          <h3 className="font-medium font-heading">Recreation Assistant</h3>
        </div>
        <div className="flex items-center space-x-3">
          <button 
            onClick={() => clearMessages()}
            className="text-white hover:text-accent-200 transition-colors"
            aria-label="Clear conversation"
          >
            <Trash2 size={18} />
          </button>
        </div>
      </div>
      
      {/* Messages */}
      <div className="flex-1 p-3 overflow-y-auto bg-neutral-50">
        {messages.length === 0 ? (
          <div className="text-center py-8">
            <MessageSquare size={40} className="mx-auto text-primary-300 mb-3" />
            <h4 className="font-medium text-neutral-700 mb-1 font-heading">Welcome to Recreation Assistant!</h4>
            <p className="text-sm text-neutral-500 mb-4">
              I can help you find activities, answer questions about programs, and provide information about facilities.
            </p>
            <div className="space-y-2">
              <button 
                onClick={() => sendMessage("What activities are available for children?")}
                className="w-full text-left text-sm bg-primary-50 hover:bg-primary-100 text-primary-700 p-2 rounded-lg transition-colors"
              >
                What activities are available for children?
              </button>
              <button 
                onClick={() => sendMessage("Tell me about swimming programs")}
                className="w-full text-left text-sm bg-primary-50 hover:bg-primary-100 text-primary-700 p-2 rounded-lg transition-colors"
              >
                Tell me about swimming programs
              </button>
              <button 
                onClick={() => sendMessage("Where are the recreation centers located?")}
                className="w-full text-left text-sm bg-primary-50 hover:bg-primary-100 text-primary-700 p-2 rounded-lg transition-colors"
              >
                Where are the recreation centers located?
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((msg, index) => (
              <div 
                key={index} 
                className={clsx(
                  "flex",
                  msg.role === 'user' ? "justify-end" : "justify-start"
                )}
              >
                <div 
                  className={clsx(
                    "max-w-[85%] rounded-xl p-3 mobile-chat-message",
                    msg.role === 'user' 
                      ? "bg-primary-600 text-white rounded-tr-none" 
                      : "bg-white border border-neutral-200 rounded-tl-none"
                  )}
                >
                  {msg.role === 'assistant' && (
                    <div className="prose prose-sm max-w-none whitespace-pre-line break-words overflow-hidden">
                      <ReactMarkdown
                        components={{
                          a: (props) => <MarkdownLink {...props} />,
                          p: ({node, ...props}) => <p className="mb-4 break-words" {...props} />,
                          code: ({node, ...props}) => <code className="break-all" {...props} />
                        }}
                      >
                        {linkifyText(msg.content)}
                      </ReactMarkdown>
                    </div>
                  )}
                  {msg.role === 'user' && (
                    <p className="break-words">{msg.content}</p>
                  )}
                  
                  {msg.role === 'assistant' && (
                    <div className="flex justify-end mt-1">
                      <button 
                        onClick={() => copyToClipboard(msg.content)}
                        className="text-neutral-400 hover:text-neutral-600 transition-colors"
                        aria-label="Copy to clipboard"
                      >
                        <Copy size={14} />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-white border border-neutral-200 rounded-xl rounded-tl-none max-w-[85%] p-3">
                  <div className="flex space-x-2">
                    <div className="h-2 w-2 bg-primary-600 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                    <div className="h-2 w-2 bg-primary-600 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                    <div className="h-2 w-2 bg-primary-600 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>
      
      {/* Input */}
      <div className="p-3 border-t border-neutral-200 bg-white">
        <div className="flex items-end">
          <textarea
            ref={inputRef}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your message..."
            className="flex-1 resize-none border border-neutral-300 rounded-lg py-2 px-3 focus:outline-none focus:ring-2 focus:ring-primary-500 min-h-[44px] max-h-32 bg-neutral-50"
            rows={1}
          />
          <button
            onClick={handleSendMessage}
            disabled={!message.trim() || isLoading}
            className={clsx(
              "ml-2 p-2 rounded-full transition-colors",
              message.trim() && !isLoading
                ? "bg-primary-600 text-white hover:opacity-90"
                : "bg-neutral-200 text-neutral-400 cursor-not-allowed"
            )}
            aria-label="Send message"
          >
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default MobileChatWidget; 