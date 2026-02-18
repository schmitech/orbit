import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowUp,
  Check,
  CircleUserRound,
  ChevronDown,
  ChevronUp,
  Copy,
  File,
  HelpCircle,
  Loader2,
  MessageSquare,
  RotateCcw,
  Sparkles,
  ThumbsDown,
  ThumbsUp
} from 'lucide-react';
import { Message as MessageType } from '../types';
import { MarkdownRenderer } from '@schmitech/markdown-renderer';
import { debugError } from '../utils/debug';
import { getEnableFeedbackButtons, getEnableConversationThreads } from '../utils/runtimeConfig';
import { AudioPlayer } from './AudioPlayer';
import { sanitizeMessageContent, truncateLongContent } from '../utils/contentValidation';
import { AppConfig } from '../utils/config';
import { useTheme } from '../contexts/ThemeContext';

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
  const threadTextareaRef = useRef<HTMLTextAreaElement>(null);
  const threadRepliesRef = useRef<HTMLDivElement>(null);
  const prevThreadReplyCountRef = useRef(0);
  const prevThreadContentRef = useRef<string>('');
  const shouldAutoScrollThreadRef = useRef(true);

  const isAssistant = message.role === 'assistant';
  const threadReplies = threadMessages ?? EMPTY_THREAD_REPLIES;
  const threadReplyCount = threadReplies.filter(msg => !(msg.role === 'assistant' && msg.isStreaming)).length;
  const threadMessageCount = threadReplies.filter(msg => !(msg.role === 'assistant' && msg.isStreaming)).length;
  const threadHasStreaming = threadReplies.some(msg => msg.isStreaming);
  const locale = import.meta.env.VITE_LOCALE || 'en-US';
  const threadsEnabled = getEnableConversationThreads();
  const threadCharLimit = AppConfig.maxMessageLength;
  const threadLimit = AppConfig.maxMessagesPerThread;
  const threadLimitReached = threadLimit !== null && threadMessageCount >= threadLimit;
  const threadLimitMessage =
    threadLimitReached && threadLimit !== null
      ? `This thread reached the ${threadLimit} message limit. Start a new conversation for more follow-ups.`
      : null;
  const { theme, isDark } = useTheme();
  const threadPlaceholder = 'Reply in thread...';
  const threadInputId = `thread-input-${message.id}`;

  const forcedThemeClass =
    theme.mode === 'dark' ? 'dark' : theme.mode === 'light' ? 'light' : '';
  const syntaxTheme: 'dark' | 'light' = isDark ? 'dark' : 'light';

  const assistantMarkdownClass = useMemo(
    () =>
      ['message-markdown w-full min-w-0', 'prose prose-slate dark:prose-invert max-w-none', forcedThemeClass]
        .filter(Boolean)
        .join(' '),
    [forcedThemeClass]
  );

  const userMarkdownClass = useMemo(
    () =>
      ['message-markdown w-full min-w-0', 'prose prose-invert max-w-none', forcedThemeClass]
        .filter(Boolean)
        .join(' '),
    [forcedThemeClass]
  );

  const mainMarkdownClassName = isAssistant ? assistantMarkdownClass : userMarkdownClass;
  const threadAssistantMarkdownClass = `${assistantMarkdownClass} text-sm leading-6`;
  const threadUserMarkdownClass = `${userMarkdownClass} text-sm leading-6`;

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

  const handleThreadRepliesScroll = useCallback(() => {
    if (!threadRepliesRef.current) {
      return;
    }
    const { scrollTop, scrollHeight, clientHeight } = threadRepliesRef.current;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    shouldAutoScrollThreadRef.current = distanceFromBottom < 120;
  }, []);

  const scrollThreadRepliesToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      if (!threadRepliesRef.current) {
        return;
      }
      threadRepliesRef.current.scrollTop = threadRepliesRef.current.scrollHeight;
    });
  }, []);

  // Auto-scroll thread replies with the same strategy as the main conversation:
  // new message -> scroll; streaming updates -> scroll; otherwise only when near bottom.
  useEffect(() => {
    if (!isThreadOpen) {
      return;
    }

    const replyCount = threadReplies.length;
    const hasNewReply = replyCount > prevThreadReplyCountRef.current;
    const lastReply = threadReplies[threadReplies.length - 1];
    const currentContent = lastReply?.content || '';
    const contentChanged = currentContent !== prevThreadContentRef.current;
    const isStreaming = lastReply?.isStreaming ?? false;

    if (hasNewReply) {
      scrollThreadRepliesToBottom();
      shouldAutoScrollThreadRef.current = true;
    } else if (isStreaming && contentChanged) {
      scrollThreadRepliesToBottom();
      shouldAutoScrollThreadRef.current = true;
    } else if (shouldAutoScrollThreadRef.current && contentChanged) {
      scrollThreadRepliesToBottom();
    }

    prevThreadReplyCountRef.current = replyCount;
    prevThreadContentRef.current = currentContent;
  }, [isThreadOpen, threadReplies, scrollThreadRepliesToBottom]);

  // Ensure a thread opens at its latest reply.
  useEffect(() => {
    if (!isThreadOpen) {
      return;
    }
    scrollThreadRepliesToBottom();
    shouldAutoScrollThreadRef.current = true;
  }, [isThreadOpen, scrollThreadRepliesToBottom]);

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

  const avatarClasses = isAssistant
    ? 'text-blue-700 dark:text-[#c5d7ff]'
    : 'text-emerald-700 dark:text-[#9ef0d5]';

  const bubbleClasses = `message-bubble min-w-0 break-words leading-relaxed ${
    isAssistant
      ? 'border border-blue-100/80 bg-transparent text-[#0f172a] shadow-[0_15px_35px_-20px_rgba(15,23,42,0.25)] dark:border-[#1f2a36] dark:bg-transparent dark:text-[#e5edff]'
      : 'border border-slate-200 bg-transparent text-[#1c3226] shadow-[0_12px_30px_-18px_rgba(15,52,33,0.25)] dark:border-[#1a2b21] dark:bg-transparent dark:text-[#dffbea]'
  } rounded-2xl px-4 py-3`;

  const attachmentClasses = isAssistant
    ? 'border-blue-100 bg-white/80 dark:border-[#1f2a36] dark:bg-white/5'
    : 'border-emerald-100 bg-white/80 dark:border-[#1a2b21] dark:bg-white/5';

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
    if (!onSendThreadMessage || !message.threadInfo || threadLimitReached) {
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
      // Refocus the thread input field after sending
      setTimeout(() => {
        if (threadTextareaRef.current) {
          threadTextareaRef.current.focus();
        }
      }, 100);
    } catch (error) {
      debugError('Failed to send thread message:', error);
      // Refocus even on error so user can retry
      setTimeout(() => {
        if (threadTextareaRef.current) {
          threadTextareaRef.current.focus();
        }
      }, 100);
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
    isSendingThreadMessage ||
    threadLimitReached;

  useEffect(() => {
    if (!isThreadOpen || threadComposerDisabled) {
      return;
    }
    const textarea = threadTextareaRef.current;
    if (!textarea) {
      return;
    }

    // Wait for the textarea to be visible before focusing.
    const frame = requestAnimationFrame(() => {
      textarea.focus({ preventScroll: true });
      // Place the caret at the end so users can start typing immediately.
      const caretPos = textarea.value.length;
      textarea.setSelectionRange(caretPos, caretPos);
    });

    return () => cancelAnimationFrame(frame);
  }, [isThreadOpen, threadComposerDisabled, isSendingThreadMessage]);

  useEffect(() => {
    if (threadTextareaRef.current) {
      const maxHeight = 120;
      const textarea = threadTextareaRef.current;
      textarea.style.height = 'auto';
      const scrollHeight = textarea.scrollHeight;
      textarea.style.height = `${Math.min(scrollHeight, maxHeight)}px`;
      textarea.style.overflowY = scrollHeight > maxHeight ? 'auto' : 'hidden';
    }
  }, [threadInput]);

  const renderedMessageContent = useMemo(() => {
    if (message.isStreaming && (!message.content || message.content === '…')) {
      return (
        <div className={mainMarkdownClassName}>
          <div className="flex items-center gap-1.5 py-1">
            <span className="inline-block h-2.5 w-2.5 animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]" style={{ animationDelay: '0ms' }} />
            <span className="inline-block h-2.5 w-2.5 animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]" style={{ animationDelay: '150ms' }} />
            <span className="inline-block h-2.5 w-2.5 animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]" style={{ animationDelay: '300ms' }} />
          </div>
        </div>
      );
    }

    return (
      <MarkdownRenderer
        content={truncateLongContent(sanitizeMessageContent(message.content || ''))}
        className={mainMarkdownClassName}
        syntaxTheme={syntaxTheme}
      />
    );
  }, [mainMarkdownClassName, message.content, message.isStreaming, syntaxTheme]);

  const renderedThreadReplies = useMemo(() => {
    // Sort replies by timestamp to maintain chronological order
    // Show all messages in order, just like the main conversation
    const sortedReplies = [...threadReplies].sort((a, b) => {
      const timeA = a.timestamp instanceof Date ? a.timestamp.getTime() : new Date(a.timestamp).getTime();
      const timeB = b.timestamp instanceof Date ? b.timestamp.getTime() : new Date(b.timestamp).getTime();
      return timeA - timeB;
    });
    
    return sortedReplies.map(reply => {
      const replyIsAssistant = reply.role === 'assistant';

      const replyMarkdownClass = replyIsAssistant ? threadAssistantMarkdownClass : threadUserMarkdownClass;
      const replyContent = reply.isStreaming && (!reply.content || reply.content === '…') ? (
        <div className={replyMarkdownClass}>
          <div className="flex items-center gap-1.5 py-1">
            <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]" style={{ animationDelay: '0ms' }} />
            <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]" style={{ animationDelay: '150ms' }} />
            <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]" style={{ animationDelay: '300ms' }} />
          </div>
        </div>
      ) : (
        <MarkdownRenderer
          content={truncateLongContent(sanitizeMessageContent(reply.content || ''))}
          className={replyMarkdownClass}
          syntaxTheme={syntaxTheme}
        />
      );

      return (
        <div key={reply.id} className="flex items-start gap-3">
          <div
            className={`mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center ${
              replyIsAssistant
                ? 'text-blue-700 dark:text-[#c5d7ff]'
                : 'text-emerald-700 dark:text-[#9ef0d5]'
            }`}
          >
            {replyIsAssistant ? <Sparkles className="h-3.5 w-3.5" /> : <CircleUserRound className="h-3.5 w-3.5" />}
          </div>
          <div className="flex-1 min-w-0 rounded-2xl border border-white/70 bg-white/90 px-4 py-3 text-sm shadow-sm dark:border-white/5 dark:bg-white/5 backdrop-blur overflow-hidden">
            <div className="mb-1 flex items-center justify-between text-[11px] font-semibold uppercase tracking-wide text-blue-900/70 dark:text-[#c5d7ff]">
              <span>{replyIsAssistant ? 'Assistant' : 'You'}</span>
              <span>{formatThreadTimestamp(reply.timestamp)}</span>
            </div>
            <div className="thread-markdown-wrapper overflow-x-auto">
              {replyContent}
            </div>
          </div>
        </div>
      );
    });
  }, [formatThreadTimestamp, syntaxTheme, threadAssistantMarkdownClass, threadReplies, threadUserMarkdownClass]);

  return (
    <div className="group flex items-start gap-3 px-1 animate-fadeIn min-w-0 sm:px-0">
      <div
        className={`flex h-10 w-10 flex-shrink-0 items-center justify-center self-start -mt-2 ml-1 sm:-mt-3 sm:ml-2 ${avatarClasses}`}
      >
        {isAssistant ? <Sparkles className="h-5 w-5" /> : <CircleUserRound className="h-5 w-5" />}
      </div>

      <div className="flex-1 min-w-0 space-y-2">
        <div className="flex flex-col gap-1.5 mb-1">
          <span className="text-xs font-semibold uppercase tracking-wide text-gray-700 dark:text-[#ececf1]">
            {isAssistant ? 'Assistant' : 'You'}
          </span>
          <span className="text-xs text-gray-500 dark:text-[#bfc2cd]">{timestamp}</span>
        </div>

        <div className={bubbleClasses}>
          {renderedMessageContent}

          {message.attachments && message.attachments.length > 0 && (
            <div className="mt-3 space-y-2">
              {message.attachments.map(file => (
                <div key={file.file_id} className={`flex items-center gap-3 rounded-xl border p-3 ${attachmentClasses}`}>
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
          <>
            <div className="flex flex-wrap items-center gap-1 md:gap-2 text-xs text-gray-500 transition-opacity dark:text-[#bfc2cd]">
              <button
                onClick={copyToClipboard}
                className="inline-flex items-center gap-1 rounded px-2 py-1 hover:bg-gray-200 dark:hover:bg-[#3c3f4a]"
                title="Copy to clipboard"
                aria-label="Copy to clipboard"
              >
                <Copy className="h-4 w-4" />
                <span className="hidden sm:inline">Copy</span>
              </button>

              {onRegenerate && (
                <button
                  onClick={() => onRegenerate(message.id)}
                  className="inline-flex items-center gap-1 rounded px-2 py-1 hover:bg-gray-200 dark:hover:bg-[#3c3f4a]"
                  title="Regenerate response"
                  aria-label="Regenerate response"
                >
                  <RotateCcw className="h-4 w-4" />
                  <span className="hidden sm:inline">Retry</span>
                </button>
              )}

              {threadsEnabled && onStartThread && message.supportsThreading && !message.threadInfo && sessionId && (
                <div className="inline-flex items-center gap-1">
                  <button
                    onClick={() => onStartThread(message.id, sessionId)}
                    className="inline-flex items-center gap-1 rounded px-2 py-1 hover:bg-gray-200 dark:hover:bg-[#3c3f4a]"
                    title="Reply in thread"
                    aria-label="Reply in thread"
                  >
                    <MessageSquare className="h-4 w-4" />
                    <span className="hidden sm:inline">Reply in thread</span>
                  </button>
                  <span
                    className="inline-flex items-center rounded p-1 text-gray-500 dark:text-[#bfc2cd]"
                    title="Use this when your question is about this specific answer. Use the main input for unrelated topics."
                    aria-label="Thread help"
                  >
                    <HelpCircle className="h-4 w-4" />
                  </span>
                </div>
              )}

              {getEnableFeedbackButtons() && (
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => handleFeedback('up')}
                    className={`rounded p-1 hover:bg-gray-200 dark:hover:bg-[#3c3f4a] ${feedback === 'up' ? 'text-[#353740] dark:text-[#ececf1]' : ''}`}
                    title="Good response"
                    aria-label="Good response"
                  >
                    <ThumbsUp className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => handleFeedback('down')}
                    className={`rounded p-1 hover:bg-gray-200 dark:hover:bg-[#3c3f4a] ${feedback === 'down' ? 'text-[#353740] dark:text-[#ececf1]' : ''}`}
                    title="Poor response"
                    aria-label="Poor response"
                  >
                    <ThumbsDown className="h-4 w-4" />
                  </button>
                </div>
              )}

              {copied && (
                <div className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider text-white shadow-sm animate-fadeIn dark:bg-emerald-600">
                  <Check className="h-3.5 w-3.5" />
                  <span>Copied</span>
                </div>
              )}
            </div>
          </>
        )}

        {threadsEnabled && message.threadInfo && (
          <div className="thread-panel mt-4 rounded-xl border border-blue-100/80 bg-blue-50/70 p-3 sm:p-4 text-sm shadow-sm ring-1 ring-blue-100/60 dark:border-white/10 dark:bg-white/[0.035] dark:ring-white/5">
            <div className="flex items-center justify-between gap-2 text-sm font-semibold text-blue-900 dark:text-[#e1e8ff]">
              <div className="inline-flex items-center gap-2 uppercase tracking-wide text-xs sm:text-sm">
                <MessageSquare className="h-3.5 w-3.5" />
                <span>
                  Replies{threadReplyCount > 0 ? ` (${threadReplyCount})` : ''}
                </span>
              </div>
              <button
                onClick={() => setIsThreadOpen(prev => !prev)}
                className="inline-flex items-center gap-1.5 sm:gap-2 rounded-full border border-blue-200/80 px-2.5 sm:px-3 py-1.5 text-xs uppercase tracking-wide text-blue-900 transition hover:bg-white/70 dark:border-white/10 dark:text-[#c5d7ff] dark:hover:bg-white/[0.08]"
              >
                {isThreadOpen ? (
                  <>
                    <span className="hidden sm:inline">Hide replies</span>
                    <ChevronUp className="h-4 w-4 sm:h-3 sm:w-3" />
                  </>
                ) : (
                  <>
                    <span className="hidden sm:inline">Show replies</span>
                    <ChevronDown className="h-4 w-4 sm:h-3 sm:w-3" />
                  </>
                )}
              </button>
            </div>

            {isThreadOpen && (
              <>
                <div
                  ref={threadRepliesRef}
                  className="mt-3 space-y-3 max-h-96 overflow-y-auto"
                  style={{ scrollBehavior: 'auto', overflowAnchor: 'none' }}
                  onScroll={handleThreadRepliesScroll}
                >
                  {threadReplyCount === 0 ? (
                    <div className="rounded-lg border border-dashed border-blue-200/80 bg-white/60 px-3 py-2 text-xs text-blue-900/70 dark:border-white/10 dark:bg-white/[0.04] dark:text-[#b4c7ff]">
                      No replies yet. Ask a clarifying question here.
                    </div>
                  ) : (
                    renderedThreadReplies
                  )}
                </div>

                {threadLimitMessage && (
                  <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-500/30 dark:bg-[#2f2410] dark:text-amber-100">
                    {threadLimitMessage}
                  </div>
                )}

                <div className="mt-3 rounded-2xl border border-slate-200/80 bg-gradient-to-b from-white to-slate-50/80 p-3 shadow-[0_12px_28px_-22px_rgba(15,23,42,0.5)] dark:border-[#3f4354] dark:bg-gradient-to-b dark:from-[#252937]/90 dark:to-[#1d202b]/90">
                  {threadReplyCount === 0 && (
                    <p className="mb-2 text-xs font-medium text-blue-900/80 dark:text-[#b4c7ff]">
                      Replying in thread keeps this discussion linked to this message.
                    </p>
                  )}
                  {/* Mobile: stacked layout, Desktop: inline */}
                  <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
                    <label htmlFor={threadInputId} className="sr-only">
                      Reply in thread
                    </label>
                    <textarea
                      id={threadInputId}
                      ref={threadTextareaRef}
                      className="flex-1 w-full sm:w-auto min-w-0 resize-none rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-base sm:text-sm text-[#1f2937] placeholder-slate-500 shadow-inner outline-none transition focus:border-blue-400 focus:ring-2 focus:ring-blue-200/70 disabled:opacity-60 dark:border-[#4d5368] dark:bg-[#171a22] dark:text-[#ececf1] dark:placeholder-[#8e8ea0] dark:focus:border-blue-400 dark:focus:ring-blue-500/30"
                      placeholder={threadPlaceholder}
                      aria-label="Reply in thread"
                      value={threadInput}
                      onChange={e => setThreadInput(e.target.value)}
                      onKeyDown={handleThreadKeyDown}
                      disabled={threadComposerDisabled}
                      rows={1}
                      maxLength={threadCharLimit}
                      style={{
                        minHeight: '44px',
                        maxHeight: '120px',
                        outline: 'none',
                        boxShadow: 'none',
                        WebkitAppearance: 'none',
                        MozAppearance: 'none',
                        appearance: 'none'
                      }}
                    />
                    <div className="flex items-center justify-between sm:justify-end gap-2">
                      {threadInput.length > 0 && (
                        <div className="text-xs text-gray-500 dark:text-[#bfc2cd] whitespace-nowrap">
                          <span className={threadInput.length >= threadCharLimit ? 'text-red-600 font-semibold' : ''}>
                            {threadInput.length}/{threadCharLimit}
                          </span>
                        </div>
                      )}
                      <button
                        type="button"
                        onClick={handleThreadSubmit}
                        disabled={threadComposerDisabled || threadInput.trim().length === 0}
                        className={`flex h-11 w-11 sm:h-9 sm:w-9 items-center justify-center rounded-full transition active:scale-95 ${
                          threadInput.trim().length > 0 && !threadComposerDisabled
                            ? 'bg-blue-600 text-white hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-400'
                            : 'bg-slate-200 text-slate-400 dark:bg-[#2f313a] dark:text-[#6b6f7a]'
                        } disabled:cursor-not-allowed`}
                        title="Send thread message"
                      >
                        {isSendingThreadMessage ? <Loader2 className="h-5 w-5 sm:h-4 sm:w-4 animate-spin" /> : <ArrowUp className="h-5 w-5 sm:h-4 sm:w-4" />}
                      </button>
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
