import React, { useState, useRef } from 'react';
import Draggable from 'react-draggable';
import { MessageCircle, X, Minimize2, Send } from 'lucide-react';
import { useChatStore } from '../store/chatStore';

export const ChatbotWidget: React.FC = () => {
  const { messages, isOpen, config, addMessage, toggleChat } = useChatStore();
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const nodeRef = useRef(null);
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    setIsTyping(true);
    addMessage({
      content: input,
      sender: 'user',
    });
    setIsTyping(false);
    setInput('');
  };

  const { primaryColor = '#007bff', size = 'medium', font } = config.theme || {};
  const sizeClasses = {
    small: 'w-12 h-12',
    medium: 'w-14 h-14',
    large: 'w-16 h-16',
  };

  return (
    <div
      className="fixed bottom-5 right-5 z-[9999]"
      style={{
        bottom: config.position?.bottom,
        right: config.position?.right,
        fontFamily: font,
        position: 'fixed',
        willChange: 'transform',
        transform: 'translateZ(0)',
      }}
    >
      {!isOpen && (
        <button
          onClick={toggleChat}
          className={`${
            sizeClasses[size]
          } rounded-full flex items-center justify-center shadow-lg transition-all duration-300 hover:scale-110`}
          style={{ backgroundColor: primaryColor }}
        >
          <MessageCircle className="text-white w-6 h-6" />
        </button>
      )}

      {isOpen && (
        <Draggable handle=".drag-handle" bounds="parent" nodeRef={nodeRef}>
          <div
            ref={nodeRef}
            className="bg-white rounded-lg shadow-xl"
            style={{
              width: config.dimensions?.width || 350,
              height: config.dimensions?.height || 500,
              maxHeight: 'calc(100vh - 40px)',
              maxWidth: 'calc(100vw - 40px)',
            }}
          >
            <div
              className="drag-handle p-4 flex justify-between items-center rounded-t-lg cursor-move"
              style={{ backgroundColor: primaryColor }}
            >
              <h3 className="text-white font-medium">{config.messages?.title || 'Chat Support'}</h3>
              <div className="flex gap-2">
                <button
                  onClick={toggleChat}
                  className="text-white hover:text-gray-200"
                >
                  <Minimize2 className="w-5 h-5" />
                </button>
                <button
                  onClick={toggleChat}
                  className="text-white hover:text-gray-200"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            <div className="h-[calc(100%-8rem)] overflow-y-auto p-4 scrollbar-thin">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`mb-4 flex ${
                    message.sender === 'user' ? 'justify-end' : 'justify-start'
                  }`}
                >
                  <div
                    className={`rounded-lg p-3 max-w-[80%] ${
                      message.sender === 'user'
                        ? 'bg-blue-500 text-white'
                        : 'bg-gray-100'
                    }`}
                    style={message.sender === 'user' ? { backgroundColor: primaryColor } : {}}
                  >
                    {message.content}
                  </div>
                </div>
              ))}
              {isTyping && (
                <div className="flex justify-start mb-4">
                  <div className="bg-gray-100 rounded-lg p-3">
                    <div className="flex gap-1">
                      <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce"></span>
                      <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce [animation-delay:0.2s]"></span>
                      <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce [animation-delay:0.4s]"></span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            <form
              onSubmit={handleSubmit}
              className="absolute bottom-0 left-0 right-0 p-4 bg-white border-t"
            >
              <div className="flex gap-2">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Type your message..."
                  className="flex-1 p-2 border rounded-lg focus:outline-none focus:ring-2"
                  style={{ '--tw-ring-color': primaryColor } as React.CSSProperties}
                />
                <button
                  type="submit"
                  className="p-2 rounded-lg text-white"
                  style={{ backgroundColor: primaryColor }}
                >
                  <Send className="w-5 h-5" />
                </button>
              </div>
            </form>
          </div>
        </Draggable>
      )}
    </div>
  );
};