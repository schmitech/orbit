import React, { useEffect, useRef, useState } from 'react';
import { Message } from './Message';
import { Message as MessageType } from '../types';
import orbitLogo from '../assets/orbit.png';

interface MessageListProps {
  messages: MessageType[];
  onRegenerate?: (messageId: string) => void;
  isLoading?: boolean;
}

export function MessageList({ messages, onRegenerate, isLoading }: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [lastMessageCount, setLastMessageCount] = useState(0);
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);

  // Check if user has scrolled up manually
  const handleScroll = () => {
    if (!containerRef.current) return;
    
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;
    setShouldAutoScroll(isNearBottom);
  };

  // Only auto-scroll when new messages are added (not when content updates)
  useEffect(() => {
    const messageCount = messages.length;
    
    // Only scroll if:
    // 1. New message was added (count increased)
    // 2. User hasn't manually scrolled up
    if (messageCount > lastMessageCount && shouldAutoScroll) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
    
    setLastMessageCount(messageCount);
  }, [messages.length, shouldAutoScroll, lastMessageCount]);

  // Scroll to bottom when loading starts (new assistant message)
  useEffect(() => {
    if (isLoading && shouldAutoScroll) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [isLoading, shouldAutoScroll]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="text-center max-w-lg">
          <div className="relative mb-8">
            <div className="absolute inset-0 bg-gradient-to-r from-blue-400 to-purple-500 rounded-full blur-2xl opacity-20"></div>
            <img 
              src={orbitLogo} 
              alt="ORBIT" 
              className="relative w-48 h-48 object-contain mx-auto drop-shadow-2xl" 
            />
          </div>
          
          <div className="space-y-4">
            <h3 className="text-3xl font-bold bg-gradient-to-r from-slate-900 to-slate-700 dark:from-slate-100 dark:to-slate-300 bg-clip-text text-transparent">
              Welcome to ORBIT Chat
            </h3>
            
            <p className="text-lg text-slate-600 dark:text-slate-400 leading-relaxed font-medium">
              Your AI assistant is ready to help
            </p>
            
            <p className="text-base text-slate-500 dark:text-slate-500 leading-relaxed max-w-md mx-auto">
              Start a conversation by typing a message below. I'm here to help with questions, creative tasks, analysis, and more.
            </p>
          </div>
          
          <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-4 max-w-2xl mx-auto">
            <div className="p-4 bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 rounded-2xl shadow-sm">
              <div className="w-10 h-10 bg-gradient-to-r from-blue-500 to-blue-600 rounded-lg flex items-center justify-center mb-3 mx-auto">
                <span className="text-white font-semibold text-sm">?</span>
              </div>
              <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-sm mb-1">Ask Questions</h4>
              <p className="text-slate-600 dark:text-slate-400 text-xs">Get instant answers to your questions</p>
            </div>
            
            <div className="p-4 bg-gradient-to-br from-purple-50 to-pink-50 dark:from-purple-900/20 dark:to-pink-900/20 rounded-2xl shadow-sm">
              <div className="w-10 h-10 bg-gradient-to-r from-purple-500 to-pink-600 rounded-lg flex items-center justify-center mb-3 mx-auto">
                <span className="text-white font-semibold text-sm">✨</span>
              </div>
              <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-sm mb-1">Creative Tasks</h4>
              <p className="text-slate-600 dark:text-slate-400 text-xs">Get help with writing and brainstorming</p>
            </div>
            
            <div className="p-4 bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 rounded-2xl shadow-sm">
              <div className="w-10 h-10 bg-gradient-to-r from-green-500 to-emerald-600 rounded-lg flex items-center justify-center mb-3 mx-auto">
                <span className="text-white font-semibold text-sm">📊</span>
              </div>
              <h4 className="font-semibold text-slate-800 dark:text-slate-200 text-sm mb-1">Analysis</h4>
              <p className="text-slate-600 dark:text-slate-400 text-xs">Analyze data and solve problems</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div 
      ref={containerRef}
      className="flex-1 overflow-y-auto"
      onScroll={handleScroll}
    >
      <div className="max-w-4xl mx-auto py-8">
        {messages.map((message) => (
          <Message
            key={message.id}
            message={message}
            onRegenerate={onRegenerate}
          />
        ))}
        
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}