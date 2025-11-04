import React, { useMemo, useState } from 'react';
import { Bot, Copy, RotateCcw, ThumbsDown, ThumbsUp, User2, File } from 'lucide-react';
import { Message as MessageType } from '../types';
import { MarkdownRenderer } from '@schmitech/markdown-renderer';
import { debugError } from '../utils/debug';

interface MessageProps {
  message: MessageType;
  onRegenerate?: (messageId: string) => void;
}

export function Message({ message, onRegenerate }: MessageProps) { 
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null);

  const isAssistant = message.role === 'assistant';
  const timestamp = useMemo(() => {
    const value = message.timestamp instanceof Date
      ? message.timestamp
      : new Date(message.timestamp);
    return value.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit'
    });
  }, [message.timestamp]);

  const contentClass = isAssistant
    ? 'markdown-content prose prose-slate dark:prose-invert max-w-none'
    : 'markdown-content prose prose-invert max-w-none';

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      debugError('Failed to copy text:', error);
    }
  };

  const handleFeedback = (type: 'up' | 'down') => {
    setFeedback(feedback === type ? null : type);
  };

  return (
    <div className="group flex items-start gap-3 animate-fadeIn">
      <div
        className={`mt-1 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full ${
          isAssistant
            ? 'bg-gray-100 text-gray-700 dark:bg-[#4a4b54] dark:text-white'
            : 'bg-gray-100 text-gray-700 dark:bg-[#202123] dark:text-[#ececf1]'
        }`}
      >
        {isAssistant ? <Bot className="h-4 w-4" /> : <User2 className="h-4 w-4" />}
      </div>

      <div className="flex-1 space-y-2">
        <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500 dark:text-[#bfc2cd]">
          <span className="font-medium uppercase tracking-wide">
            {isAssistant ? 'Assistant' : 'You'}
          </span>
          <span>{timestamp}</span>
        </div>

        <div
          className={`rounded-lg border px-4 py-3 leading-relaxed ${
            isAssistant
              ? 'border-gray-300 bg-gray-100 text-[#353740] dark:border-[#4a4b54] dark:bg-[#202123] dark:text-[#ececf1]'
              : 'border-gray-300 bg-gray-100 text-[#353740] dark:bg-[#202123] dark:text-[#ececf1]'
          }`}
        >
          <div className={contentClass}>
            {message.isStreaming && (!message.content || message.content === '…') ? (
              <div className="flex items-center gap-1.5 py-1">
                <span className="inline-block h-2.5 w-2.5 animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]" style={{ animationDelay: '0ms' }} />
                <span className="inline-block h-2.5 w-2.5 animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]" style={{ animationDelay: '150ms' }} />
                <span className="inline-block h-2.5 w-2.5 animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]" style={{ animationDelay: '300ms' }} />
              </div>
            ) : (
              <MarkdownRenderer content={message.content || ''} />
            )}
          </div>

          {message.attachments && message.attachments.length > 0 && (
            <div className="mt-3 space-y-2">
              {message.attachments.map((file) => (
                <div
                  key={file.file_id}
                  className={`flex items-center gap-3 rounded-md border p-3 ${
                    isAssistant
                      ? 'border-gray-300 bg-white dark:border-[#4a4b54] dark:bg-[#343541]'
                      : 'border-gray-300 bg-white dark:border-[#4a4b54] dark:bg-[#343541]'
                  }`}
                >
                  <File className="h-4 w-4 text-gray-500 dark:text-[#bfc2cd]" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-[#353740] dark:text-[#ececf1]">
                      {file.filename}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-[#bfc2cd]">
                      {(file.file_size / 1024).toFixed(1)} KB
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {message.isStreaming && message.content && message.content !== '…' && (
            <div className="mt-3 flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]" style={{ animationDelay: '0ms' }} />
              <span className="inline-block h-2.5 w-2.5 animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]" style={{ animationDelay: '150ms' }} />
              <span className="inline-block h-2.5 w-2.5 animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]" style={{ animationDelay: '300ms' }} />
            </div>
          )}
        </div>

        {isAssistant && !message.isStreaming && (
          <div className="flex items-center gap-2 text-xs text-gray-500 opacity-0 transition-opacity group-hover:opacity-100 dark:text-[#bfc2cd]">
            <button
              onClick={copyToClipboard}
              className="inline-flex items-center gap-1 rounded px-2 py-1 hover:bg-gray-200 dark:hover:bg-[#3c3f4a]"
              title="Copy message"
            >
              <Copy className="h-4 w-4" />
              Copy
            </button>

            {onRegenerate && (
              <button
                onClick={() => onRegenerate(message.id)}
                className="inline-flex items-center gap-1 rounded px-2 py-1 hover:bg-gray-200 dark:hover:bg-[#3c3f4a]"
                title="Regenerate response"
              >
                <RotateCcw className="h-4 w-4" />
                Retry
              </button>
            )}

            {import.meta.env.VITE_ENABLE_FEEDBACK_BUTTONS !== 'false' && (
              <div className="flex items-center gap-1">
                <button
                  onClick={() => handleFeedback('up')}
                  className={`rounded p-1 hover:bg-gray-200 dark:hover:bg-[#3c3f4a] ${
                    feedback === 'up' ? 'text-[#353740] dark:text-[#ececf1]' : ''
                  }`}
                  title="Good response"
                >
                  <ThumbsUp className="h-4 w-4" />
                </button>
                <button
                  onClick={() => handleFeedback('down')}
                  className={`rounded p-1 hover:bg-gray-200 dark:hover:bg-[#3c3f4a] ${
                    feedback === 'down' ? 'text-[#353740] dark:text-[#ececf1]' : ''
                  }`}
                  title="Poor response"
                >
                  <ThumbsDown className="h-4 w-4" />
                </button>
              </div>
            )}

            {copied && <span>Copied</span>}
          </div>
        )}
      </div>
    </div>
  );
}
