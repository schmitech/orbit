import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowUp,
  Bot,
  ChevronDown,
  ChevronUp,
  Copy,
  File,
  Loader2,
  MessageSquare,
  RotateCcw,
  ThumbsDown,
  ThumbsUp,
  User2
} from 'lucide-react';
import { Message as MessageType } from '../types';
import { MarkdownRenderer } from '@schmitech/markdown-renderer';
import { debugError } from '../utils/debug';
import { getEnableFeedbackButtons, getEnableConversationThreads } from '../utils/runtimeConfig';
import { AudioPlayer } from './AudioPlayer';
import { sanitizeMessageContent, truncateLongContent } from '../utils/contentValidation';

interface MessageProps {
  message: MessageType;
  onRegenerate?: (messageId: string) => void;
  onStartThread?: (messageId: string, sessionId: string) => void;
  onSendThreadMessage?: (threadId: string, parentMessageId: string, content: string) => Promise<void> | void;
  threadMessages?: MessageType[];
  sessionId?: string;
  isThreadSendDisabled?: boolean;
}

const EMPTY_THREAD_REPLIES: MessageType[] = [];

export function Message({
  message,
  onRegenerate,
  onStartThread,
  onSendThreadMessage,
  threadMessages,
  sessionId,
  isThreadSendDisabled
}: MessageProps) {
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null);
  const [threadInput, setThreadInput] = useState('');
  const [isThreadOpen, setIsThreadOpen] = useState(false);
  const [isSendingThreadMessage, setIsSendingThreadMessage] = useState(false);
  const prevThreadIdRef = useRef<string | null>(message.threadInfo?.thread_id || null);

  const isAssistant = message.role === 'assistant';
  const threadReplies = threadMessages ?? EMPTY_THREAD_REPLIES;
  const threadReplyCount = threadReplies.length;
  const threadHasStreaming = threadReplies.some(msg => msg.isStreaming);
  const locale = (import.meta.env as any).VITE_LOCALE || 'en-US';
  const threadsEnabled = getEnableConversationThreads();

  useEffect(() => {
    if (!prevThreadIdRef.current && message.threadInfo?.thread_id) {
      setIsThreadOpen(true);
    }
    prevThreadIdRef.current = message.threadInfo?.thread_id || null;
  }, [message.threadInfo?.thread_id]);

  useEffect(() => {
    if (!message.threadInfo) {
      setThreadInput('');
      setIsThreadOpen(false);
      setIsSendingThreadMessage(false);
    }
  }, [message.threadInfo]);

  useEffect(() => {
    if (threadReplyCount > 0) {
      setIsThreadOpen(true);
    }
  }, [threadReplyCount]);

  const timestamp = useMemo(() => {
    const value = message.timestamp instanceof Date ? message.timestamp : new Date(message.timestamp);

    const dayOfWeek = value.toLocaleDateString(locale, { weekday: 'short' });
    const month = value.toLocaleDateString(locale, { month: 'short' });
    const day = value.getDate().toString().padStart(2, '0');
    const year = value.getFullYear();
    const time = value.toLocaleTimeString(locale, {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    });

    return `${dayOfWeek}, ${month} ${day}, ${year} ${time}`;
  }, [message.timestamp, locale]);

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

  const formatThreadTimestamp = useCallback((value: Date | string) => {
    const dateValue = value instanceof Date ? value : new Date(value);
    return dateValue.toLocaleTimeString(locale, {
      hour: '2-digit',
      minute: '2-digit'
    });
  }, [locale]);

  const handleThreadSubmit = async () => {
    if (!onSendThreadMessage || !message.threadInfo) {
      return;
    }
    const trimmed = threadInput.trim();
    if (!trimmed) {
      return;
    }
    setIsSendingThreadMessage(true);
    try {
      await onSendThreadMessage(message.threadInfo.thread_id, message.id, trimmed);
      setThreadInput('');
    } catch (error) {
      debugError('Failed to send thread message:', error);
    } finally {
      setIsSendingThreadMessage(false);
    }
  };

  const handleThreadKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleThreadSubmit();
    }
  };

  const threadComposerDisabled =
    !message.threadInfo ||
    !onSendThreadMessage ||
    isThreadSendDisabled ||
    threadHasStreaming ||
    isSendingThreadMessage;

  const renderedMessageContent = useMemo(() => {
    if (message.isStreaming && (!message.content || message.content === '…')) {
      return (
        <div className="flex items-center gap-1.5 py-1">
          <span className="inline-block h-2.5 w-2.5 animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]" style={{ animationDelay: '0ms' }} />
          <span className="inline-block h-2.5 w-2.5 animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]" style={{ animationDelay: '150ms' }} />
          <span className="inline-block h-2.5 w-2.5 animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]" style={{ animationDelay: '300ms' }} />
        </div>
      );
    }

    return <MarkdownRenderer content={truncateLongContent(sanitizeMessageContent(message.content || ''))} />;
  }, [message.content, message.isStreaming]);

  const renderedThreadReplies = useMemo(() => {
    return threadReplies.map(reply => {
      const replyIsAssistant = reply.role === 'assistant';

      const replyContent = reply.isStreaming && (!reply.content || reply.content === '…') ? (
        <div className="flex items-center gap-1.5 py-1">
          <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]" style={{ animationDelay: '0ms' }} />
          <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]" style={{ animationDelay: '150ms' }} />
          <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]" style={{ animationDelay: '300ms' }} />
        </div>
      ) : (
        <MarkdownRenderer content={truncateLongContent(sanitizeMessageContent(reply.content || ''))} />
      );

      return (
        <div key={reply.id} className="flex items-start gap-2">
          <div
            className={`mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full ${
              replyIsAssistant
                ? 'bg-gray-200 text-gray-600 dark:bg-[#4a4b54] dark:text-white'
                : 'bg-blue-100 text-blue-700 dark:bg-[#4a4b54] dark:text-white'
            }`}
          >
            {replyIsAssistant ? <Bot className="h-3.5 w-3.5" /> : <User2 className="h-3.5 w-3.5" />}
          </div>
          <div className="flex-1 rounded-lg border border-gray-200 bg-white/80 p-2 text-sm dark:border-[#3c3f4a] dark:bg-[#181920]">
            <div className="mb-1 flex items-center justify-between text-[11px] uppercase tracking-wide text-gray-500 dark:text-[#bfc2cd]">
              <span>{replyIsAssistant ? 'Assistant' : 'You'}</span>
              <span>{formatThreadTimestamp(reply.timestamp)}</span>
            </div>
            <div className="prose prose-slate max-w-none text-sm text-[#353740] dark:prose-invert dark:text-[#ececf1]">{replyContent}</div>
          </div>
        </div>
      );
    });
  }, [formatThreadTimestamp, threadReplies]);

  return (
    <div className="group flex items-start gap-3 px-1 animate-fadeIn min-w-0 sm:px-0">
      <div
        className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full self-start -mt-2 ml-1 sm:-mt-3 sm:ml-2 ${
          isAssistant
            ? 'bg-gray-100 text-gray-700 dark:bg-[#4a4b54] dark:text-white'
            : 'bg-gray-100 text-gray-700 dark:bg-[#4a4b54] dark:text-white'
        }`}
      >
        {isAssistant ? <Bot className="h-5 w-5" /> : <User2 className="h-5 w-5" />}
      </div>

      <div className="flex-1 min-w-0 space-y-2">
        <div className="flex flex-col gap-1.5 mb-1">
          <span className="text-xs font-semibold uppercase tracking-wide text-gray-700 dark:text-[#ececf1]">
            {isAssistant ? 'Assistant' : 'You'}
          </span>
          <span className="text-xs text-gray-500 dark:text-[#bfc2cd]">{timestamp}</span>
        </div>

        <div
          className={`message-bubble min-w-0 break-words leading-relaxed text-[#353740] dark:text-[#ececf1] ${
            isAssistant
              ? 'assistant-bubble dark:rounded-lg dark:border-[#4a4b54] dark:bg-[#202123] dark:px-4 dark:py-3'
              : ''
          }`}
        >
          <div className={contentClass}>{renderedMessageContent}</div>

          {message.attachments && message.attachments.length > 0 && (
            <div className="mt-3 space-y-2">
              {message.attachments.map(file => (
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
                    <p className="truncate text-sm font-medium text-[#353740] dark:text-[#ececf1]">{file.filename}</p>
                    <p className="text-xs text-gray-500 dark:text-[#bfc2cd]">{(file.file_size / 1024).toFixed(1)} KB</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {message.audio && isAssistant && !message.isStreaming && (
            <AudioPlayer audio={message.audio} audioFormat={message.audioFormat} autoPlay={false} />
          )}
        </div>

        {isAssistant && !message.isStreaming && (
          <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500 transition-opacity dark:text-[#bfc2cd] sm:opacity-0 sm:group-hover:opacity-100">
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

            {threadsEnabled && onStartThread && message.supportsThreading && !message.threadInfo && sessionId && (
              <button
                onClick={() => onStartThread(message.id, sessionId)}
                className="inline-flex items-center gap-1 rounded px-2 py-1 hover:bg-gray-200 dark:hover:bg-[#3c3f4a]"
                title="Start thread for follow-up questions"
              >
                <MessageSquare className="h-4 w-4" />
                Start Thread
              </button>
            )}

            {getEnableFeedbackButtons() && (
              <div className="flex items-center gap-1">
                <button
                  onClick={() => handleFeedback('up')}
                  className={`rounded p-1 hover:bg-gray-200 dark:hover:bg-[#3c3f4a] ${feedback === 'up' ? 'text-[#353740] dark:text-[#ececf1]' : ''}`}
                  title="Good response"
                >
                  <ThumbsUp className="h-4 w-4" />
                </button>
                <button
                  onClick={() => handleFeedback('down')}
                  className={`rounded p-1 hover:bg-gray-200 dark:hover:bg-[#3c3f4a] ${feedback === 'down' ? 'text-[#353740] dark:text-[#ececf1]' : ''}`}
                  title="Poor response"
                >
                  <ThumbsDown className="h-4 w-4" />
                </button>
              </div>
            )}

            {copied && <span>Copied</span>}
          </div>
        )}

        {threadsEnabled && message.threadInfo && (
          <div className="ml-12 mt-4 rounded-lg border border-gray-200 bg-gray-50/70 p-3 text-sm shadow-sm dark:border-[#3a3a46] dark:bg-[#202123]">
            <div className="flex items-center justify-between text-xs text-gray-600 dark:text-[#bfc2cd]">
              <div className="inline-flex items-center gap-1.5 font-semibold">
                <MessageSquare className="h-3.5 w-3.5" />
                <span>
                  Thread replies
                  {threadReplyCount > 0 ? ` (${threadReplyCount})` : ''}
                </span>
              </div>
              <button
                onClick={() => setIsThreadOpen(prev => !prev)}
                className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-gray-600 hover:bg-gray-200 dark:text-[#ececf1] dark:hover:bg-[#3c3f4a]"
              >
                {isThreadOpen ? (
                  <>
                    Hide <ChevronUp className="h-3 w-3" />
                  </>
                ) : (
                  <>
                    Show <ChevronDown className="h-3 w-3" />
                  </>
                )}
              </button>
            </div>

            {isThreadOpen && (
              <>
                <div className="mt-3 space-y-3">{renderedThreadReplies}</div>

                <div className="mt-3 rounded-lg border border-gray-200 bg-white/80 p-2 dark:border-[#3c3f4a] dark:bg-[#181920]">
                  <div className="flex items-end gap-2">
                    <textarea
                      className="min-h-[46px] flex-1 resize-none rounded-md border border-gray-300 bg-transparent px-3 py-2 text-sm text-[#353740] outline-none transition focus:border-gray-500 focus:ring-1 focus:ring-gray-400 disabled:opacity-60 dark:border-[#3c3f4a] dark:bg-[#1f2027] dark:text-[#ececf1] dark:focus:border-[#8e8ea0] dark:focus:ring-[#8e8ea0]"
                      placeholder={threadReplyCount > 0 ? 'Reply in thread...' : 'Ask a follow-up...'}
                      value={threadInput}
                      onChange={e => setThreadInput(e.target.value)}
                      onKeyDown={handleThreadKeyDown}
                      disabled={threadComposerDisabled}
                    />
                    <button
                      type="button"
                      onClick={handleThreadSubmit}
                      disabled={threadComposerDisabled || threadInput.trim().length === 0}
                      className="flex h-10 w-10 items-center justify-center rounded-full bg-[#10a37f] text-white transition hover:bg-[#0f8f6f] disabled:cursor-not-allowed disabled:bg-gray-300 disabled:text-gray-500 dark:disabled:bg-[#2f313a]"
                    >
                      {isSendingThreadMessage ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
                    </button>
                  </div>

                  {(threadHasStreaming || isThreadSendDisabled) && (
                    <p className="mt-2 text-xs text-gray-500 dark:text-[#bfc2cd]">
                      Please wait for the assistant to finish before asking another follow-up.
                    </p>
                  )}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
