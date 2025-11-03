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
    : 'markdown-content prose prose-invert dark:prose-slate max-w-none';

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
    <div
      className={`group flex items-start gap-4 md:gap-5 animate-fadeIn ${
        isAssistant ? '' : 'justify-end'
      }`}
    >
      <div
        className={`flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center shadow-md ${
          isAssistant
            ? 'bg-gradient-to-br from-emerald-500 to-emerald-600 text-white'
            : 'bg-gradient-to-br from-violet-500 to-purple-600 text-white'
        } ${isAssistant ? '' : 'order-2'}`}
      >
        {isAssistant ? <Bot className="w-4 h-4" /> : <User2 className="w-4 h-4" />}
      </div>

      <div
        className={`flex-1 max-w-2xl space-y-3 ${
          isAssistant ? '' : 'flex flex-col items-end'
        }`}
      >
        <div
          className={`flex items-center gap-2 text-xs uppercase tracking-wide font-semibold ${
            isAssistant
              ? 'text-emerald-600 dark:text-emerald-400'
              : 'text-slate-500 dark:text-slate-400'
          } ${isAssistant ? '' : 'justify-end'}`}
        >
          <span>{isAssistant ? 'Orbit Assistant' : 'You'}</span>
          <span className="text-[0.7rem] uppercase tracking-[0.2em] opacity-70">
            {timestamp}
          </span>
        </div>

        <div
          className={`${
            isAssistant
              ? 'bg-white/90 dark:bg-slate-900/90 border border-emerald-100/60 dark:border-emerald-500/20 text-slate-900 dark:text-slate-100 shadow-[0_20px_60px_rgba(16,185,129,0.16)]'
              : 'bg-slate-100 text-slate-900 dark:bg-slate-900 dark:text-slate-100 shadow-[0_18px_40px_rgba(15,23,42,0.35)]'
          } relative rounded-2xl px-5 py-4 leading-relaxed backdrop-blur-sm transition-transform duration-200 overflow-visible ${
            isAssistant ? 'hover:-translate-y-0.5' : 'ml-auto hover:-translate-y-0.5'
          }`}
        >
          <div className={contentClass}>
            {message.isStreaming && (!message.content || message.content === '…') ? (
              <div className="flex items-center gap-1.5 py-1">
                <span className="inline-block w-2.5 h-2.5 bg-emerald-600 dark:bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="inline-block w-2.5 h-2.5 bg-emerald-600 dark:bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="inline-block w-2.5 h-2.5 bg-emerald-600 dark:bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            ) : (
              <MarkdownRenderer content={message.content || ''} />
            )}
          </div>

          {/* File attachments */}
          {message.attachments && message.attachments.length > 0 && (
            <div className="mt-3 space-y-2">
              {message.attachments.map((file) => (
                <div
                  key={file.file_id}
                  className="flex items-center gap-3 p-3 bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-lg"
                >
                  <File className="w-5 h-5 text-slate-500 dark:text-slate-400 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-700 dark:text-slate-300 truncate">
                      {file.filename}
                    </p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {(file.file_size / 1024).toFixed(1)} KB
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
          {message.isStreaming && message.content && message.content !== '…' && (
            <div className="inline-flex items-center gap-1.5 ml-2 mt-2 py-1">
              <span className="inline-block w-2.5 h-2.5 bg-emerald-500 dark:bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="inline-block w-2.5 h-2.5 bg-emerald-500 dark:bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="inline-block w-2.5 h-2.5 bg-emerald-500 dark:bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          )}
        </div>

        {isAssistant && !message.isStreaming && (
          <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={copyToClipboard}
              className="inline-flex items-center gap-1 rounded-lg px-2 py-1 hover:bg-emerald-50 dark:hover:bg-emerald-500/10 transition"
              title="Copy message"
            >
              <Copy className="w-4 h-4" />
              Copy
            </button>

            {onRegenerate && (
              <button
                onClick={() => onRegenerate(message.id)}
                className="inline-flex items-center gap-1 rounded-lg px-2 py-1 hover:bg-emerald-50 dark:hover:bg-emerald-500/10 transition"
                title="Regenerate response"
              >
                <RotateCcw className="w-4 h-4" />
                Retry
              </button>
            )}

            {import.meta.env.VITE_ENABLE_FEEDBACK_BUTTONS !== 'false' && (
              <div className="flex items-center gap-1">
                <button
                  onClick={() => handleFeedback('up')}
                  className={`p-1.5 rounded-lg transition ${
                    feedback === 'up'
                      ? 'text-emerald-600 bg-emerald-50 dark:text-emerald-300 dark:bg-emerald-500/10'
                      : 'hover:bg-emerald-50 dark:hover:bg-emerald-500/10'
                  }`}
                  title="Good response"
                >
                  <ThumbsUp className="w-4 h-4" />
                </button>
                <button
                  onClick={() => handleFeedback('down')}
                  className={`p-1.5 rounded-lg transition ${
                    feedback === 'down'
                      ? 'text-rose-600 bg-rose-50 dark:text-rose-300 dark:bg-rose-500/10'
                      : 'hover:bg-rose-50 dark:hover:bg-rose-500/10'
                  }`}
                  title="Poor response"
                >
                  <ThumbsDown className="w-4 h-4" />
                </button>
              </div>
            )}

            {copied && (
              <span className="text-xs text-emerald-600 dark:text-emerald-300">
                Copied!
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
