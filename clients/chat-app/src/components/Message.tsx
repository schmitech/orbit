import React, { useState } from 'react';
import { Copy, RotateCcw, ThumbsUp, ThumbsDown } from 'lucide-react';
import { Message as MessageType } from '../types';
import { MarkdownRenderer } from '@schmitech/markdown-renderer';

interface MessageProps {
  message: MessageType;
  onRegenerate?: (messageId: string) => void;
}

export function Message({ message, onRegenerate }: MessageProps) { 
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null);

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error('Failed to copy text:', error);
    }
  };

  const handleFeedback = (type: 'up' | 'down') => {
    setFeedback(feedback === type ? null : type);
  };

  return (
    <div className={`group flex gap-4 p-4 bg-transparent ${message.isStreaming ? 'animate-pulse' : ''}`}>
      
      {/* Avatar */}
      <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-medium ${
        message.role === 'user'
          ? 'bg-gradient-to-br from-blue-500 to-blue-600'
          : 'bg-gradient-to-br from-purple-500 to-purple-600'
      }`}>
        {message.role === 'user' ? 'U' : 'AI'}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-2">
          {message.isStreaming ? (
            <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
              Assistant
            </span>
          ) : (
            <>
              <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {message.role === 'user' ? 'You' : 'Assistant'}
              </span>
              <span className="text-xs text-gray-500 dark:text-gray-400">
                {message.timestamp.toLocaleTimeString([], { 
                  hour: '2-digit', 
                  minute: '2-digit' 
                })}
              </span>
            </>
          )}
        </div>

        {message.isStreaming ? (
          <div className="flex items-center gap-1 mt-1">
            <span className="inline-block w-2 h-2 bg-gray-400 rounded-full animate-bounce"></span>
            <span className="inline-block w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-150"></span>
            <span className="inline-block w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-300"></span>
          </div>
        ) : (
          <MarkdownRenderer
            content={message.content}
          />
        )}

        {/* Actions */}
        {message.role === 'assistant' && !message.isStreaming && (
          <div className="flex items-center gap-2 mt-3 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={copyToClipboard}
              className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-md transition-colors"
              title="Copy message"
            >
              <Copy className="w-4 h-4 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200" />
            </button>

            {onRegenerate && (
              <button
                onClick={() => onRegenerate(message.id)}
                className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-md transition-colors"
                title="Regenerate response"
              >
                <RotateCcw className="w-4 h-4 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200" />
              </button>
            )}

            <button
              onClick={() => handleFeedback('up')}
              className={`p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-md transition-colors ${
                feedback === 'up' ? 'text-green-600 dark:text-green-400' : 'text-gray-500 dark:text-gray-400'
              }`}
              title="Good response"
            >
              <ThumbsUp className="w-4 h-4" />
            </button>

            <button
              onClick={() => handleFeedback('down')}
              className={`p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-md transition-colors ${
                feedback === 'down' ? 'text-red-600 dark:text-red-400' : 'text-gray-500 dark:text-gray-400'
              }`}
              title="Poor response"
            >
              <ThumbsDown className="w-4 h-4" />
            </button>

            {copied && (
              <span className="text-xs text-green-600 dark:text-green-400 px-2 py-1 bg-green-50 dark:bg-green-900/20 rounded">
                Copied!
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}