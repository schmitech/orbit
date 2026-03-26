import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowUp,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  File,
  MessageSquare,
  RotateCcw,
  ThumbsDown,
  ThumbsUp
} from 'lucide-react';
import { Message as MessageType } from '../types';
import { MarkdownRenderer } from './markdown';
import { debugError } from '../utils/debug';
import { getEnableFeedbackButtons, getEnableConversationThreads, getIsAuthConfigured } from '../utils/runtimeConfig';
import { AudioPlayer } from './AudioPlayer';
import { ConfirmationModal } from './ConfirmationModal';
import { sanitizeMessageContent, truncateLongContent } from '../utils/contentValidation';
import { AppConfig } from '../utils/config';
import { useTheme } from '../contexts/ThemeContext';
import { useIsAuthenticated } from '../hooks/useIsAuthenticated';
import { useLoginPromptStore } from '../stores/loginPromptStore';
import { useChatStore } from '../stores/chatStore';

interface MessageProps {
  message: MessageType;
  onRegenerate?: (messageId: string) => void;
  onStartThread?: (messageId: string, sessionId: string) => void;
  onClearThread?: (messageId: string, threadId: string) => Promise<void> | void;
  onSendThreadMessage?: (threadId: string, parentMessageId: string, content: string) => Promise<void> | void;
  threadMessages?: MessageType[];
  sessionId?: string;
  isThreadSendDisabled?: boolean;
}

const EMPTY_THREAD_REPLIES: MessageType[] = [];

function ThreadReplyFeedback({ reply }: { reply: MessageType }) {
  const [isLoading, setIsLoading] = useState(false);
  const [showAcknowledgement, setShowAcknowledgement] = useState(false);
  const acknowledgementTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const submitFeedbackAction = useChatStore(state => state.submitFeedback);

  useEffect(() => {
    return () => {
      if (acknowledgementTimeoutRef.current) {
        clearTimeout(acknowledgementTimeoutRef.current);
      }
    };
  }, []);

  const handleClick = async (type: 'up' | 'down') => {
    if (!reply.databaseMessageId || isLoading) return;
    const shouldShowAcknowledgement = reply.feedback !== type;
    setIsLoading(true);
    try {
      await submitFeedbackAction(reply.id, type);
      if (shouldShowAcknowledgement) {
        setShowAcknowledgement(true);
        if (acknowledgementTimeoutRef.current) {
          clearTimeout(acknowledgementTimeoutRef.current);
        }
        acknowledgementTimeoutRef.current = setTimeout(() => {
          setShowAcknowledgement(false);
          acknowledgementTimeoutRef.current = null;
        }, 2000);
      } else {
        setShowAcknowledgement(false);
      }
    } catch (error) {
      debugError('Failed to submit thread reply feedback:', error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex items-center gap-0.5 mt-0.5">
      <button
        onClick={() => handleClick('up')}
        disabled={isLoading}
        className={`rounded-md p-1.5 hover:bg-gray-100 dark:hover:bg-[#3c3f4a] transition-colors ${isLoading ? 'opacity-50 cursor-not-allowed' : ''} ${reply.feedback === 'up' ? 'text-green-600 dark:text-green-400' : 'text-gray-400 dark:text-[#6e6e80] hover:text-gray-700 dark:hover:text-[#ececf1]'}`}
        title="Good response"
        aria-label="Good response"
      >
        <ThumbsUp className="h-3.5 w-3.5" />
      </button>
      <button
        onClick={() => handleClick('down')}
        disabled={isLoading}
        className={`rounded-md p-1.5 hover:bg-gray-100 dark:hover:bg-[#3c3f4a] transition-colors ${isLoading ? 'opacity-50 cursor-not-allowed' : ''} ${reply.feedback === 'down' ? 'text-red-600 dark:text-red-400' : 'text-gray-400 dark:text-[#6e6e80] hover:text-gray-700 dark:hover:text-[#ececf1]'}`}
        title="Poor response"
        aria-label="Poor response"
      >
        <ThumbsDown className="h-3.5 w-3.5" />
      </button>
      {showAcknowledgement && (
        <span className="ml-1 inline-flex items-center gap-1 rounded-md bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 animate-fadeIn dark:bg-emerald-500/15 dark:text-emerald-300">
          <Check className="h-3 w-3" />
          Thanks!
        </span>
      )}
    </div>
  );
}

export function Message({
  message,
  onRegenerate,
  onStartThread,
  onClearThread,
  onSendThreadMessage,
  threadMessages,
  sessionId,
  isThreadSendDisabled
}: MessageProps) {
  const [copied, setCopied] = useState(false);
  const [isFeedbackLoading, setIsFeedbackLoading] = useState(false);
  const [showFeedbackAcknowledgement, setShowFeedbackAcknowledgement] = useState(false);
  const [threadInput, setThreadInput] = useState('');
  const [isThreadOpen, setIsThreadOpen] = useState(false);
  const [isSendingThreadMessage, setIsSendingThreadMessage] = useState(false);
  const [showClearThreadConfirmation, setShowClearThreadConfirmation] = useState(false);
  const [isClearingThread, setIsClearingThread] = useState(false);
  const prevThreadIdRef = useRef<string | null>(message.threadInfo?.thread_id || null);
  const threadTextareaRef = useRef<HTMLTextAreaElement>(null);
  const threadComposerRef = useRef<HTMLDivElement>(null);
  const threadRepliesRef = useRef<HTMLDivElement>(null);
  const pendingThreadFocusRef = useRef(false);
  const prevThreadReplyCountRef = useRef(0);
  const prevThreadContentRef = useRef<string>('');
  const prevThreadStreamingRef = useRef(false);
  const shouldAutoScrollThreadRef = useRef(true);
  const prevIsSendingThreadMessageRef = useRef(false);
  const copiedTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const feedbackAcknowledgementTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isAssistant = message.role === 'assistant';
  const threadReplies = threadMessages ?? EMPTY_THREAD_REPLIES;
  const threadMessageCount = threadReplies.filter(msg => !(msg.role === 'assistant' && msg.isStreaming)).length;
  const threadReplyCount = threadMessageCount;
  const threadHasStreaming = threadReplies.some(msg => msg.isStreaming);
  const isAuthenticated = useIsAuthenticated();
  const isGuest = getIsAuthConfigured() && !isAuthenticated;
  const threadsEnabled = getEnableConversationThreads();
  const threadCharLimit = AppConfig.maxMessageLength;
  const threadLimit = AppConfig.maxMessagesPerThread;
  const threadLimitReached = threadLimit !== null && threadMessageCount >= threadLimit;
  const threadLimitMessage =
    threadLimitReached && threadLimit !== null
      ? (isGuest
          ? `You've reached the guest limit of ${threadLimit} messages per thread. Sign in to continue this thread.`
          : `This thread reached the ${threadLimit} message limit. Start a new conversation for more follow-ups.`)
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
      ['message-markdown w-full min-w-0', 'prose dark:prose-invert max-w-none', forcedThemeClass]
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

  useEffect(() => {
    return () => {
      if (copiedTimeoutRef.current) {
        clearTimeout(copiedTimeoutRef.current);
      }
      if (feedbackAcknowledgementTimeoutRef.current) {
        clearTimeout(feedbackAcknowledgementTimeoutRef.current);
      }
    };
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
    const streamingJustFinished = prevThreadStreamingRef.current && !isStreaming;

    if (hasNewReply) {
      scrollThreadRepliesToBottom();
      shouldAutoScrollThreadRef.current = true;
    } else if (isStreaming && contentChanged) {
      scrollThreadRepliesToBottom();
      shouldAutoScrollThreadRef.current = true;
    } else if (streamingJustFinished) {
      scrollThreadRepliesToBottom();
      shouldAutoScrollThreadRef.current = true;
    } else if (shouldAutoScrollThreadRef.current && contentChanged) {
      scrollThreadRepliesToBottom();
    }

    prevThreadReplyCountRef.current = replyCount;
    prevThreadContentRef.current = currentContent;
    prevThreadStreamingRef.current = isStreaming;
  }, [isThreadOpen, threadReplies, scrollThreadRepliesToBottom]);

  // Ensure a thread opens at its latest reply.
  useEffect(() => {
    if (!isThreadOpen) {
      return;
    }
    scrollThreadRepliesToBottom();
    shouldAutoScrollThreadRef.current = true;
  }, [isThreadOpen, scrollThreadRepliesToBottom]);

  const bubbleClasses = isAssistant
    ? 'message-bubble message-bubble-assistant min-w-0 break-words leading-relaxed text-[#353740] dark:text-[#ececf1]'
    : 'message-bubble message-bubble-user inline-block min-w-0 break-words leading-relaxed rounded-[1.75rem] bg-[#f4f4f4] px-4 py-3 text-[#111827] dark:bg-[#303030] dark:text-[#f5f5f5]';

  const attachmentClasses = 'border-gray-200 bg-white/80 dark:border-[#3b3c49] dark:bg-white/5';

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      if (copiedTimeoutRef.current) {
        clearTimeout(copiedTimeoutRef.current);
      }
      copiedTimeoutRef.current = setTimeout(() => {
        setCopied(false);
        copiedTimeoutRef.current = null;
      }, 2000);
    } catch (error) {
      debugError('Failed to copy text:', error);
    }
  };

  const submitFeedback = useChatStore(state => state.submitFeedback);

  const handleFeedback = async (type: 'up' | 'down') => {
    if (!message.databaseMessageId || isFeedbackLoading) return;
    const shouldShowAcknowledgement = message.feedback !== type;
    setIsFeedbackLoading(true);
    try {
      await submitFeedback(message.id, type);
      if (shouldShowAcknowledgement) {
        setShowFeedbackAcknowledgement(true);
        if (feedbackAcknowledgementTimeoutRef.current) {
          clearTimeout(feedbackAcknowledgementTimeoutRef.current);
        }
        feedbackAcknowledgementTimeoutRef.current = setTimeout(() => {
          setShowFeedbackAcknowledgement(false);
          feedbackAcknowledgementTimeoutRef.current = null;
        }, 2000);
      } else {
        setShowFeedbackAcknowledgement(false);
      }
    } catch (error) {
      debugError('Failed to submit feedback:', error);
    } finally {
      setIsFeedbackLoading(false);
    }
  };

  const handleThreadSubmit = async () => {
    if (!onSendThreadMessage || !message.threadInfo || threadLimitReached) {
      return;
    }
    const trimmed = threadInput.trim();
    if (!trimmed) {
      return;
    }
    const previousDraft = threadInput;
    setThreadInput('');
    setIsSendingThreadMessage(true);
    try {
      await onSendThreadMessage(message.threadInfo.thread_id, message.id, trimmed);
      // Refocus the thread input field after sending
      setTimeout(() => {
        if (threadTextareaRef.current) {
          threadTextareaRef.current.focus();
        }
      }, 100);
    } catch (error) {
      debugError('Failed to send thread message:', error);
      setThreadInput(previousDraft);
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
  const canClearThread =
    !!message.threadInfo &&
    !!onClearThread &&
    threadReplyCount > 0 &&
    !threadHasStreaming &&
    !isSendingThreadMessage &&
    !isThreadSendDisabled;

  const handleClearThread = async () => {
    if (!message.threadInfo || !onClearThread) {
      return;
    }

    setIsClearingThread(true);
    try {
      await onClearThread(message.id, message.threadInfo.thread_id);
      setShowClearThreadConfirmation(false);
      setIsThreadOpen(false);
      setThreadInput('');
    } catch (error) {
      debugError('Failed to clear thread:', error);
    } finally {
      setIsClearingThread(false);
    }
  };

  useEffect(() => {
    if (!isThreadOpen || threadComposerDisabled) {
      prevIsSendingThreadMessageRef.current = isSendingThreadMessage;
      return;
    }
    const textarea = threadTextareaRef.current;
    if (!textarea) {
      prevIsSendingThreadMessageRef.current = isSendingThreadMessage;
      return;
    }

    const shouldFocusThreadComposer =
      pendingThreadFocusRef.current || prevIsSendingThreadMessageRef.current;

    if (!shouldFocusThreadComposer) {
      prevIsSendingThreadMessageRef.current = isSendingThreadMessage;
      return;
    }

    const frame = requestAnimationFrame(() => {
      // Keep scroll adjustment instant so caret appears right away.
      if (pendingThreadFocusRef.current) {
        threadComposerRef.current?.scrollIntoView({
          behavior: 'auto',
          block: 'nearest',
          inline: 'nearest'
        });
      }
      textarea.focus();
      const caretPos = textarea.value.length;
      textarea.setSelectionRange(caretPos, caretPos);
      pendingThreadFocusRef.current = false;
      prevIsSendingThreadMessageRef.current = isSendingThreadMessage;
    });

    return () => {
      cancelAnimationFrame(frame);
      prevIsSendingThreadMessageRef.current = isSendingThreadMessage;
    };
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

    const streamingClass = message.isStreaming && isAssistant ? ' streaming-cursor' : '';

    return (
      <div className={streamingClass || undefined}>
        <MarkdownRenderer
          content={truncateLongContent(sanitizeMessageContent(message.content || ''))}
          className={mainMarkdownClassName}
          syntaxTheme={syntaxTheme}
        />
      </div>
    );
  }, [mainMarkdownClassName, message.content, message.isStreaming, isAssistant, syntaxTheme]);

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
      const replyStreamingClass = reply.isStreaming && replyIsAssistant ? ' streaming-cursor' : '';
      const replyContent = reply.isStreaming && (!reply.content || reply.content === '…') ? (
        <div className={replyMarkdownClass}>
          <div className="flex items-center gap-1.5 py-1">
            <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]" style={{ animationDelay: '0ms' }} />
            <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]" style={{ animationDelay: '150ms' }} />
            <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]" style={{ animationDelay: '300ms' }} />
          </div>
        </div>
      ) : (
        <div className={replyStreamingClass || undefined}>
          <MarkdownRenderer
            content={truncateLongContent(sanitizeMessageContent(reply.content || ''))}
            className={replyMarkdownClass}
            syntaxTheme={syntaxTheme}
          />
        </div>
      );

      return (
        <div key={reply.id} className={`min-w-0 flex ${replyIsAssistant ? 'justify-start' : 'justify-end'}`}>
          <div className={replyIsAssistant ? 'min-w-0 w-full max-w-full' : 'min-w-0 max-w-[85%]'}>
            <div className={replyIsAssistant
              ? 'thread-markdown-wrapper overflow-x-visible text-sm text-[#353740] dark:text-[#ececf1]'
              : 'thread-markdown-wrapper overflow-x-visible text-sm rounded-[1.75rem] bg-[#f4f4f4] px-4 py-3 text-[#111827] dark:bg-[#303030] dark:text-[#f5f5f5]'
            }>
              {replyContent}
            </div>
            {replyIsAssistant && !reply.isStreaming && getEnableFeedbackButtons() && (
              <ThreadReplyFeedback reply={reply} />
            )}
          </div>
        </div>
      );
    });
  }, [syntaxTheme, threadAssistantMarkdownClass, threadReplies, threadUserMarkdownClass]);

  return (
    <div className="group animate-fadeIn min-w-0 w-full px-0">
      <div className="min-w-0 space-y-1">
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
            <div className="flex flex-wrap items-center gap-1 md:gap-1 text-xs text-gray-500 transition-opacity dark:text-[#bfc2cd]">
              <div className="flex min-w-0 flex-wrap items-center gap-1 md:gap-1">
                <button
                  onClick={copyToClipboard}
                  className="inline-flex items-center gap-1.5 rounded-md px-3.5 py-2.5 md:px-3 md:py-1.5 hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-[#3c3f4a] dark:hover:text-[#ececf1] transition-colors"
                  title="Copy to clipboard"
                  aria-label="Copy to clipboard"
                >
                  <Copy className="h-4 w-4 md:h-3.5 md:w-3.5" />
                  <span className="hidden sm:inline">Copy</span>
                </button>

                {onRegenerate && (
                  <button
                    onClick={() => onRegenerate(message.id)}
                    className="inline-flex items-center gap-1.5 rounded-md px-3.5 py-2.5 md:px-3 md:py-1.5 hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-[#3c3f4a] dark:hover:text-[#ececf1] transition-colors"
                    title="Regenerate response"
                    aria-label="Regenerate response"
                  >
                    <RotateCcw className="h-4 w-4 md:h-3.5 md:w-3.5" />
                    <span className="hidden sm:inline">Retry</span>
                  </button>
                )}

                {threadsEnabled && message.supportsThreading && !message.threadInfo && onStartThread && sessionId && (
                  <button
                    type="button"
                    onClick={() => {
                      pendingThreadFocusRef.current = true;
                      setIsThreadOpen(true);
                      onStartThread(message.id, sessionId);
                    }}
                    className="inline-flex items-center gap-1.5 rounded-md px-3.5 py-2.5 md:px-3 md:py-1.5 hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-[#3c3f4a] dark:hover:text-[#ececf1] transition-colors"
                    title="Follow up on this answer"
                    aria-label="Follow up on this answer"
                  >
                    <MessageSquare className="h-4 w-4 md:h-3.5 md:w-3.5" />
                    <span>Follow up</span>
                  </button>
                )}

              </div>


              {getEnableFeedbackButtons() && (
                <>
                <div className="hidden md:block w-px h-4 shrink-0 bg-gray-200 dark:bg-[#3c3f4a] mx-1" />
                <div className="flex shrink-0 items-center gap-0.5">
                  <button
                    onClick={() => handleFeedback('up')}
                    disabled={isFeedbackLoading}
                    className={`rounded-md p-2.5 md:p-1.5 hover:bg-gray-100 dark:hover:bg-[#3c3f4a] transition-colors ${isFeedbackLoading ? 'opacity-50 cursor-not-allowed' : ''} ${message.feedback === 'up' ? 'text-green-600 dark:text-green-400' : 'hover:text-gray-700 dark:hover:text-[#ececf1]'}`}
                    title="Good response"
                    aria-label="Good response"
                  >
                    <ThumbsUp className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => handleFeedback('down')}
                    disabled={isFeedbackLoading}
                    className={`rounded-md p-2.5 md:p-1.5 hover:bg-gray-100 dark:hover:bg-[#3c3f4a] transition-colors ${isFeedbackLoading ? 'opacity-50 cursor-not-allowed' : ''} ${message.feedback === 'down' ? 'text-red-600 dark:text-red-400' : 'hover:text-gray-700 dark:hover:text-[#ececf1]'}`}
                    title="Poor response"
                    aria-label="Poor response"
                  >
                    <ThumbsDown className="h-3.5 w-3.5" />
                  </button>
                </div>
                </>
              )}

              {threadsEnabled && message.threadInfo && (
                <>
                  <div className="hidden md:block w-px h-4 shrink-0 bg-gray-200 dark:bg-[#3c3f4a] mx-1" />
                  <button
                    onClick={() => setIsThreadOpen(prev => !prev)}
                    className="inline-flex min-w-0 items-center gap-1.5 rounded-md px-3.5 py-2.5 md:px-3 md:py-1.5 hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-[#3c3f4a] dark:hover:text-[#ececf1] transition-colors"
                  >
                    <MessageSquare className="h-4 w-4 md:h-3.5 md:w-3.5" />
                    <span className="truncate">{threadReplyCount} {threadReplyCount === 1 ? 'reply' : 'replies'}</span>
                    {isThreadOpen
                      ? <ChevronUp className="h-3 w-3" />
                      : <ChevronDown className="h-3 w-3" />
                    }
                  </button>
                  {canClearThread && (
                    <button
                      type="button"
                      onClick={() => setShowClearThreadConfirmation(true)}
                      className="inline-flex items-center rounded-md px-2 py-1 text-xs font-medium text-red-600 transition-colors hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-900/30"
                      title="Clear replies"
                      aria-label="Clear replies"
                    >
                      Clear
                    </button>
                  )}
                </>
              )}

              {copied && (
                <div className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider text-white shadow-sm animate-fadeIn dark:bg-emerald-600">
                  <Check className="h-3.5 w-3.5" />
                  <span>Copied</span>
                </div>
              )}

              {showFeedbackAcknowledgement && (
                <div className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider text-white shadow-sm animate-fadeIn dark:bg-emerald-600">
                  <Check className="h-3.5 w-3.5" />
                  <span>Thanks For The Feedback</span>
                </div>
              )}
            </div>

          </>
        )}

        {threadsEnabled && message.threadInfo && isThreadOpen && (
          <div className="thread-panel mt-3 md:mt-3 border-l-2 border-gray-200 pl-3 sm:pl-4 dark:border-[#3b3c49]">
                <div
                  ref={threadRepliesRef}
                  className="thread-replies-scroll mt-2 space-y-2 pb-3"
                  onScroll={() => {
                    if (!threadRepliesRef.current) return;
                    const { scrollTop, scrollHeight, clientHeight } = threadRepliesRef.current;
                    shouldAutoScrollThreadRef.current = scrollHeight - scrollTop - clientHeight < 100;
                  }}
                >
                  {threadReplyCount > 0 ? renderedThreadReplies : null}
                </div>

                {threadLimitMessage && (
                  <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-500/30 dark:bg-[#2f2410] dark:text-amber-100">
                    {threadLimitMessage}
                    {isGuest && (
                      <div className="mt-2">
                        <button
                          type="button"
                          onClick={() => useLoginPromptStore.getState().openLoginPrompt('Sign in to unlock higher message limits and continue this thread.')}
                          className="inline-flex items-center gap-1 rounded-md bg-blue-600 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600"
                        >
                          Sign in for higher limits
                        </button>
                      </div>
                    )}
                  </div>
                )}

                <div
                  ref={threadComposerRef}
                  className="mt-1 w-full max-w-[64rem] bg-transparent pt-1"
                >
                  <div className="flex items-center gap-2 bg-transparent">
                    <label htmlFor={threadInputId} className="sr-only">
                      Reply in thread
                    </label>
                    <textarea
                      id={threadInputId}
                      ref={threadTextareaRef}
                      className="flex-1 w-full sm:w-auto min-w-0 resize-none bg-transparent px-0 py-1.5 sm:py-1 text-base sm:text-sm text-[#353740] placeholder-slate-500 outline-none transition focus:outline-none disabled:opacity-60 dark:text-[#ececf1] dark:placeholder-[#8e8ea0]"
                      placeholder={threadPlaceholder}
                      aria-label="Reply in thread"
                      value={threadInput}
                      onChange={e => setThreadInput(e.target.value)}
                      onKeyDown={handleThreadKeyDown}
                      disabled={threadComposerDisabled}
                      rows={1}
                      maxLength={threadCharLimit}
                      style={{
                        minHeight: '36px',
                        maxHeight: '120px',
                        outline: 'none',
                        boxShadow: 'none',
                        WebkitAppearance: 'none',
                        MozAppearance: 'none',
                        appearance: 'none'
                      }}
                    />
                    <div className="flex items-center justify-between sm:justify-end gap-2">
                      {threadInput.trim().length > 0 && (
                        <button
                          type="button"
                          onClick={handleThreadSubmit}
                          disabled={threadComposerDisabled || threadInput.trim().length === 0}
                          className="flex h-10 w-10 sm:h-8 sm:w-8 items-center justify-center rounded-full transition active:scale-95 bg-blue-600 text-white hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-400 disabled:cursor-not-allowed"
                          title="Send thread message"
                        >
                          <ArrowUp className="h-5 w-5 sm:h-4 sm:w-4" />
                        </button>
                      )}
                    </div>
                  </div>
                </div>

                {threadReplyCount > 0 && (
                  <div className="mt-2 flex justify-end">
                    <button
                      type="button"
                      onClick={() => setIsThreadOpen(false)}
                      className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700 dark:text-[#bfc2cd] dark:hover:bg-[#2f313a] dark:hover:text-white"
                      aria-label="Hide replies"
                    >
                      <ChevronUp className="h-3 w-3" />
                      <span>Hide replies</span>
                    </button>
                  </div>
                )}
          </div>
        )}
      </div>
      <ConfirmationModal
        isOpen={showClearThreadConfirmation}
        onClose={() => {
          if (!isClearingThread) {
            setShowClearThreadConfirmation(false);
          }
        }}
        onConfirm={handleClearThread}
        title="Clear Replies"
        message="Are you sure you want to clear these replies? This removes the child thread from the backend without deleting the main conversation."
        confirmText="Clear"
        cancelText="Cancel"
        type="danger"
        isLoading={isClearingThread}
      />
    </div>
  );
}
