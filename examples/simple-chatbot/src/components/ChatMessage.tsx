import React from 'react';
import { Bot, User } from 'lucide-react';
import { Message } from '../types';
import { marked } from 'marked';

interface ChatMessageProps {
  message: Message;
}

const renderMarkdown = (text: string) => {
  return marked(text);
};

export const ChatMessage: React.FC<ChatMessageProps> = ({ message }) => {
  const isAssistant = message.role === 'assistant';

  return (
    <div className={`flex gap-4 ${isAssistant ? 'bg-gray-50' : 'bg-white'} p-6`}>
      <div className={`w-10 h-10 flex items-center justify-center rounded-full ${isAssistant ? 'bg-green-100' : 'bg-blue-500'}`}>
        {isAssistant ? (
          <Bot size={24} className="text-green-600" />
        ) : (
          <User size={24} className="text-white" />
        )}
      </div>
      <div className="flex-1">
        <div className={`font-medium mb-2 text-sm uppercase ${isAssistant ? 'text-green-600' : 'text-blue-500'}`}>
          {isAssistant ? 'AI Assistant' : 'You'}
        </div>
        <div 
          className="text-gray-800 whitespace-pre-wrap"
          dangerouslySetInnerHTML={{ __html: renderMarkdown(message.content) }}
        />
      </div>
    </div>
  );
};