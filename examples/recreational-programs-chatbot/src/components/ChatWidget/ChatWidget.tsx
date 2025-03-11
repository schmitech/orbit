import React, { useState, useRef, useEffect } from 'react';
import { MessageSquare, X, Minimize2, Send, Copy, Trash2 } from 'lucide-react';
import { useChatStore } from '../../store/chatStore';
import ReactMarkdown from 'react-markdown';
import clsx from 'clsx';

// Custom link component for ReactMarkdown
const MarkdownLink = (props: React.AnchorHTMLAttributes<HTMLAnchorElement>) => {
  return (
    <a 
      {...props}
      target="_blank"
      rel="noopener noreferrer"
      className="text-primary-600 hover:text-primary-800 underline"
    >
      {props.children}
    </a>
  );
};

const ChatWidget: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [message, setMessage] = useState('');
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

  // Scroll to bottom when messages change
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

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
        <div className="mb-4 w-96 sm:w-[500px] md:w-[600px] bg-white rounded-xl shadow-card flex flex-col overflow-hidden border border-neutral-200">
          {/* Header */}
          <div className="bg-primary-600 text-white p-3 flex justify-between items-center">
            <div className="flex items-center">
              <MessageSquare size={20} className="mr-2 text-accent-300" />
              <h3 className="font-medium font-heading">Recreation Assistant</h3>
            </div>
            <div className="flex items-center space-x-2">
              <button 
                onClick={() => clearMessages()}
                className="text-white hover:text-accent-200 transition-colors"
                aria-label="Clear conversation"
              >
                <Trash2 size={18} />
              </button>
              <button 
                onClick={toggleChat}
                className="text-white hover:text-accent-200 transition-colors"
                aria-label="Minimize chat"
              >
                <Minimize2 size={18} />
              </button>
            </div>
          </div>
          
          {/* Messages */}
          <div className="flex-1 p-3 overflow-y-auto max-h-[500px] bg-neutral-50">
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
                        "max-w-[85%] rounded-xl p-3",
                        msg.role === 'user' 
                          ? "bg-primary-600 text-white rounded-tr-none" 
                          : "bg-white border border-neutral-200 rounded-tl-none"
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
      )}
      
      {/* Chat Button */}
      <button
        onClick={toggleChat}
        className={clsx(
          "rounded-full p-3 shadow-lg flex items-center justify-center transition-colors",
          isOpen 
            ? "bg-red-500 hover:bg-red-600" 
            : "bg-primary-600 hover:opacity-90"
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
  );
};

export default ChatWidget;