import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ArrowUp,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  Edit2,
  File,
  MessageSquare,
  RotateCcw,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  X
} from 'lucide-react';
import { Message as MessageType } from '../types';
import type { AllowedModel } from '../types';
import { MarkdownRenderer } from './markdown';
import { debugError } from '../utils/debug';
import { getEnableFeedbackButtons, getEnableConversationThreads, getIsAuthConfigured } from '../utils/runtimeConfig';
import { AudioPlayer } from './AudioPlayer';
import { ImageDisplay } from './ImageDisplay';
import { VideoDisplay } from './VideoDisplay';
import { DocumentDisplay } from './DocumentDisplay';
import { ConfirmationModal } from './ConfirmationModal';
import { sanitizeMessageContent, truncateLongContent } from '../utils/contentValidation';
import { AppConfig } from '../utils/config';
import { useTheme } from '../contexts/ThemeContext';
import { useIsAuthenticated } from '../hooks/useIsAuthenticated';
import { useSkills } from '../hooks/useSkills';
import { useLoginPromptStore } from '../stores/loginPromptStore';
import { useChatStore } from '../stores/chatStore';
import { SkillPicker } from './SkillPicker';
import { ModelPickerButton } from './ModelPickerButton';

interface MessageProps {
  message: MessageType;
  onRegenerate?: (messageId: string) => void;
  onEdit?: (messageId: string, newContent: string) => void;
  onStartThread?: (messageId: string, sessionId: string) => void;
  onClearThread?: (messageId: string, threadId: string) => Promise<void> | void;
  onSendThreadMessage?: (threadId: string, parentMessageId: string, content: string, skill?: string, model?: string) => Promise<void> | void;
  threadMessages?: MessageType[];
  sessionId?: string;
  isThreadSendDisabled?: boolean;
  availableModels?: AllowedModel[];
  defaultModel?: string | null;
  selectedModel?: string | null;
}

const EMPTY_THREAD_REPLIES: MessageType[] = [];

const getImageMimeType = (format = 'png') => {
  const normalizedFormat = format.toLowerCase().replace(/^image\//, '');
  if (normalizedFormat === 'jpg') {
    return 'image/jpeg';
  }
  return `image/${normalizedFormat || 'png'}`;
};

const base64ToBlob = (base64: string, mimeType: string) => {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new Blob([bytes], { type: mimeType });
};

const convertBlobToPng = async (blob: Blob) => {
  const url = URL.createObjectURL(blob);
  try {
    const image = new Image();
    image.decoding = 'async';
    const loadedImage = new Promise<HTMLImageElement>((resolve, reject) => {
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error('Failed to load generated image for clipboard copy'));
    });
    image.src = url;
    await loadedImage;

    const canvas = document.createElement('canvas');
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;

    const context = canvas.getContext('2d');
    if (!context) {
      throw new Error('Could not create canvas context for image clipboard copy');
    }

    context.drawImage(image, 0, 0);

    return await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((pngBlob) => {
        if (pngBlob) {
          resolve(pngBlob);
        } else {
          reject(new Error('Could not encode generated image for clipboard copy'));
        }
      }, 'image/png');
    });
  } finally {
    URL.revokeObjectURL(url);
  }
};

const getGeneratedImageBlob = async (message: MessageType, adapterName?: string | null) => {
  const mimeType = getImageMimeType(message.imageFormat);
  if (message.image) {
    return base64ToBlob(message.image, mimeType);
  }

  if (!message.imageUrl) {
    return null;
  }

  const response = await fetch(message.imageUrl, {
    headers: adapterName ? { 'X-Adapter-Name': adapterName } : {},
  });

  if (!response.ok) {
    throw new Error(`Could not fetch generated image for clipboard copy: ${response.status}`);
  }

  const blob = await response.blob();
  return blob.type ? blob : new Blob([blob], { type: mimeType });
};

const getGeneratedImageFallbackText = (message: MessageType) => {
  if (message.imageUrl) {
    return new URL(message.imageUrl, window.location.origin).toString();
  }
  return message.imageRevisedPrompt || message.content;
};

function StreamingDots({ size = 'md' }: { size?: 'sm' | 'md' }) {
  const cls = size === 'sm' ? 'h-2 w-2' : 'h-2.5 w-2.5';
  return (
    <div className="flex items-center gap-1.5 py-1">
      {([0, 150, 300] as const).map(delay => (
        <span key={delay} className={`inline-block ${cls} animate-bounce rounded-full bg-gray-400 dark:bg-[#bfc2cd]`} style={{ animationDelay: `${delay}ms` }} />
      ))}
    </div>
  );
}

function ThreadReplyFeedback({ reply }: { reply: MessageType }) {
  const { t } = useTranslation();
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
        title={t('message.feedback.good')}
        aria-label={t('message.feedback.good')}
      >
        <ThumbsUp className="h-3.5 w-3.5" />
      </button>
      <button
        onClick={() => handleClick('down')}
        disabled={isLoading}
        className={`rounded-md p-1.5 hover:bg-gray-100 dark:hover:bg-[#3c3f4a] transition-colors ${isLoading ? 'opacity-50 cursor-not-allowed' : ''} ${reply.feedback === 'down' ? 'text-red-600 dark:text-red-400' : 'text-gray-400 dark:text-[#6e6e80] hover:text-gray-700 dark:hover:text-[#ececf1]'}`}
        title={t('message.feedback.poor')}
        aria-label={t('message.feedback.poor')}
      >
        <ThumbsDown className="h-3.5 w-3.5" />
      </button>
      {showAcknowledgement && (
        <span className="ml-1 inline-flex items-center gap-1 rounded-md bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 animate-fadeIn dark:bg-emerald-500/15 dark:text-emerald-300">
          <Check className="h-3 w-3" />
          {t('message.feedback.thanks')}
        </span>
      )}
    </div>
  );
}

export function Message({
  message,
  onRegenerate,
  onEdit,
  onStartThread,
  onClearThread,
  onSendThreadMessage,
  threadMessages,
  sessionId,
  isThreadSendDisabled,
  availableModels = [],
  defaultModel = null,
  selectedModel = null,
}: MessageProps) {
  const { t } = useTranslation();
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(message.content || '');
  const [isEditComposing, setIsEditComposing] = useState(false);
  const editTextareaRef = useRef<HTMLTextAreaElement>(null);
  const [copied, setCopied] = useState(false);
  const [isFeedbackLoading, setIsFeedbackLoading] = useState(false);
  const [showFeedbackAcknowledgement, setShowFeedbackAcknowledgement] = useState(false);
  const [threadInput, setThreadInput] = useState('');
  const [isThreadOpen, setIsThreadOpen] = useState(false);
  const [isSendingThreadMessage, setIsSendingThreadMessage] = useState(false);
  const [showThreadSkillPicker, setShowThreadSkillPicker] = useState(false);
  const [activeThreadSkillIndex, setActiveThreadSkillIndex] = useState(0);
  const [showClearThreadConfirmation, setShowClearThreadConfirmation] = useState(false);
  const [isClearingThread, setIsClearingThread] = useState(false);
  // Each thread manages its own model independently from the main input.
  // Initialized from the current global selection so it starts consistent.
  const [threadSelectedModel, setThreadSelectedModel] = useState<string | null>(
    () => selectedModel ?? defaultModel
  );
  const latestSelectedModelRef = useRef<string | null>(selectedModel);
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
  const threadReplyCount = threadReplies.filter(msg => !(msg.role === 'assistant' && msg.isStreaming)).length;
  const threadHasStreaming = threadReplies.some(msg => msg.isStreaming);
  const isAuthenticated = useIsAuthenticated();
  const isGuest = getIsAuthConfigured() && !isAuthenticated;
  const currentConversation = useChatStore(state =>
    state.conversations.find(c => c.id === state.currentConversationId)
  );
  const hasGeneratedImage = Boolean((message.image || message.imageUrl) && isAssistant && !message.isStreaming);
  const hasGeneratedVideo = Boolean((message.video || message.videoUrl) && isAssistant && !message.isStreaming);
  const copyLabel = hasGeneratedImage ? t('message.copyImageLabel') : t('message.copyLabel');
  const threadsEnabled = getEnableConversationThreads();
  const threadCharLimit = AppConfig.maxMessageLength;
  const threadLimit = AppConfig.maxMessagesPerThread;
  const threadLimitReached = threadLimit !== null && threadReplyCount >= threadLimit;
  const threadLimitMessage = threadLimitReached
    ? (isGuest
        ? t('message.thread.limitReachedGuest', { count: threadLimit })
        : t('message.thread.limitReachedUser', { count: threadLimit }))
    : null;
  const { theme, isDark } = useTheme();
  const threadPlaceholder = t('message.thread.placeholder');
  const threadInputId = `thread-input-${message.id}`;
  const { skills, isLoading: skillsLoading, selectedSkill, selectSkill, clearSkill } = useSkills({
    adapterName: currentConversation?.adapterName,
    enabled: threadsEnabled && Boolean(message.threadInfo),
    selectionScopeKey: message.threadInfo?.thread_id || message.id,
  });
  const threadSkillQuery = threadInput.startsWith('/') ? threadInput.slice(1) : '';
  const normalizedThreadSkillQuery = threadSkillQuery.toLowerCase().replace(/-/g, ' ');
  const filteredThreadSkills = normalizedThreadSkillQuery
    ? skills.filter(skill =>
        skill.name.replace(/-/g, ' ').toLowerCase().includes(normalizedThreadSkillQuery) ||
        skill.description.toLowerCase().includes(normalizedThreadSkillQuery)
      )
    : skills;
  const safeActiveThreadSkillIndex =
    filteredThreadSkills.length > 0 ? Math.min(activeThreadSkillIndex, filteredThreadSkills.length - 1) : 0;
  const activeThreadSkill = filteredThreadSkills[safeActiveThreadSkillIndex] ?? null;
  const activeThreadSkillDisplayName = activeThreadSkill?.name.replace(/-/g, ' ') ?? '';
  const threadSkillInlineSuggestion =
    showThreadSkillPicker &&
    activeThreadSkill &&
    threadInput.startsWith('/') &&
    activeThreadSkillDisplayName.toLowerCase().startsWith(threadSkillQuery.toLowerCase()) &&
    activeThreadSkillDisplayName.length > threadSkillQuery.length
      ? activeThreadSkillDisplayName.slice(threadSkillQuery.length)
      : null;

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
      setTimeout(() => {
        setThreadInput('');
        setIsThreadOpen(false);
        setIsSendingThreadMessage(false);
        setShowThreadSkillPicker(false);
        clearSkill();
      }, 0);
    }
  }, [message.threadInfo, clearSkill]);

  useEffect(() => {
    if (threadReplyCount > 0) {
      setTimeout(() => {
        setIsThreadOpen(true);
      }, 0);
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


  // Focus and place cursor at end when edit mode first opens
  useEffect(() => {
    if (!isEditing || !editTextareaRef.current) return;
    const el = editTextareaRef.current;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  }, [isEditing]);

  // Auto-resize textarea as content changes
  useEffect(() => {
    if (!isEditing || !editTextareaRef.current) return;
    const el = editTextareaRef.current;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [isEditing, editContent]);

  const handleEditSubmit = useCallback(() => {
    const trimmed = editContent.trim();
    if (!trimmed || trimmed === message.content) {
      setIsEditing(false);
      return;
    }
    onEdit?.(message.id, trimmed);
    setIsEditing(false);
  }, [editContent, message.content, message.id, onEdit]);

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
    : 'message-bubble message-bubble-user relative inline-block min-w-0 break-words leading-relaxed rounded-[1.75rem] bg-[#f4f4f4] px-4 py-3 text-[#111827] dark:bg-[#303030] dark:text-[#f5f5f5]';

  const attachmentClasses = 'border-gray-200 bg-white/80 dark:border-[#3b3c49] dark:bg-white/5';

  const markCopied = useCallback(() => {
    setCopied(true);
    if (copiedTimeoutRef.current) {
      clearTimeout(copiedTimeoutRef.current);
    }
    copiedTimeoutRef.current = setTimeout(() => {
      setCopied(false);
      copiedTimeoutRef.current = null;
    }, 2000);
  }, []);

  const copyToClipboard = async () => {
    try {
      if (hasGeneratedImage) {
        if ('ClipboardItem' in window && navigator.clipboard.write) {
          try {
            const adapterName =
              currentConversation?.adapterName ||
              (typeof window !== 'undefined' ? window.localStorage.getItem('chat-adapter-name') : null);
            const imageBlob = await getGeneratedImageBlob(message, adapterName);
            if (imageBlob) {
              const clipboardBlob = imageBlob.type === 'image/png' ? imageBlob : await convertBlobToPng(imageBlob);
              await navigator.clipboard.write([
                new ClipboardItem({ [clipboardBlob.type || 'image/png']: clipboardBlob }),
              ]);
              markCopied();
              return;
            }
          } catch (imageCopyError) {
            debugError('Failed to copy generated image, falling back to text:', imageCopyError);
          }
        }

        const fallbackText = getGeneratedImageFallbackText(message);
        if (fallbackText) {
          await navigator.clipboard.writeText(fallbackText);
          markCopied();
          return;
        }
        return;
      }

      await navigator.clipboard.writeText(message.content);
      markCopied();
    } catch (error) {
      debugError(hasGeneratedImage ? 'Failed to copy generated image:' : 'Failed to copy text:', error);
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
    const previousSkill = selectedSkill;
    const activeSkillName = selectedSkill?.name;
    setThreadInput('');
    setIsSendingThreadMessage(true);
    setShowThreadSkillPicker(false);
    if (activeSkillName) {
      clearSkill();
    }
    try {
      await onSendThreadMessage(message.threadInfo.thread_id, message.id, trimmed, activeSkillName, threadSelectedModel ?? defaultModel ?? undefined);
      // Refocus the thread input field after sending
      setTimeout(() => {
        if (threadTextareaRef.current) {
          threadTextareaRef.current.focus();
        }
      }, 100);
    } catch (error) {
      debugError('Failed to send thread message:', error);
      setThreadInput(previousDraft);
      if (previousSkill) {
        selectSkill(previousSkill);
      }
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

  const selectThreadSkillAndClose = useCallback((skill: typeof skills[number]) => {
    selectSkill(skill);
    setShowThreadSkillPicker(false);
    setThreadInput('');
    setActiveThreadSkillIndex(0);
    threadTextareaRef.current?.focus();
  }, [selectSkill]);

  const closeThreadSkillPicker = useCallback(() => {
    setShowThreadSkillPicker(false);
    setThreadInput('');
    setActiveThreadSkillIndex(0);
    threadTextareaRef.current?.focus();
  }, []);

  // Opens the thread skill picker from the "/ Skills" hint — mirrors typing "/"
  // so the existing thread picker logic applies unchanged (and covers mobile).
  const openThreadSkillPicker = useCallback(() => {
    setThreadInput('/');
    setShowThreadSkillPicker(true);
    setActiveThreadSkillIndex(0);
    threadTextareaRef.current?.focus();
  }, []);

  const handleThreadKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (showThreadSkillPicker) {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        setActiveThreadSkillIndex(prev => {
          if (filteredThreadSkills.length === 0) {
            return 0;
          }
          return (prev + 1) % filteredThreadSkills.length;
        });
        return;
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault();
        setActiveThreadSkillIndex(prev => {
          if (filteredThreadSkills.length === 0) {
            return 0;
          }
          return (prev - 1 + filteredThreadSkills.length) % filteredThreadSkills.length;
        });
        return;
      }
      if (event.key === 'Home') {
        event.preventDefault();
        setActiveThreadSkillIndex(0);
        return;
      }
      if (event.key === 'End') {
        event.preventDefault();
        setActiveThreadSkillIndex(Math.max(filteredThreadSkills.length - 1, 0));
        return;
      }
      if ((event.key === 'Enter' && !event.shiftKey) || event.key === 'Tab') {
        if (activeThreadSkill) {
          event.preventDefault();
          selectThreadSkillAndClose(activeThreadSkill);
          return;
        }
      }
      if (event.key === 'Escape') {
        event.preventDefault();
        closeThreadSkillPicker();
        return;
      }
    }
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
    latestSelectedModelRef.current = selectedModel;
  }, [selectedModel]);

  useEffect(() => {
    setThreadSelectedModel(latestSelectedModelRef.current ?? defaultModel);
  }, [defaultModel]);

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
          <StreamingDots />
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
    const toMs = (ts: Date | string) => ts instanceof Date ? ts.getTime() : new Date(ts).getTime();
    const sortedReplies = [...threadReplies].sort((a, b) => toMs(a.timestamp) - toMs(b.timestamp));
    
    return sortedReplies.map((reply) => {
      const replyIsAssistant = reply.role === 'assistant';

      const replyMarkdownClass = replyIsAssistant ? threadAssistantMarkdownClass : threadUserMarkdownClass;
      const replyStreamingClass = reply.isStreaming && replyIsAssistant ? ' streaming-cursor' : '';
      const replyContent = reply.isStreaming && (!reply.content || reply.content === '…') ? (
        <div className={replyMarkdownClass}>
          <StreamingDots size="sm" />
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
              {reply.audio && replyIsAssistant && !reply.isStreaming && (
                <AudioPlayer audio={reply.audio} audioFormat={reply.audioFormat} autoPlay={false} />
              )}
              {(reply.image || reply.imageUrl) && replyIsAssistant && !reply.isStreaming && (
                <ImageDisplay
                  image={reply.image}
                  imageUrl={reply.imageUrl}
                  imageFormat={reply.imageFormat}
                  revisedPrompt={reply.imageRevisedPrompt}
                />
              )}
              {(reply.video || reply.videoUrl) && replyIsAssistant && !reply.isStreaming && (
                <VideoDisplay
                  video={reply.video}
                  videoUrl={reply.videoUrl}
                  videoFormat={reply.videoFormat}
                  revisedPrompt={reply.videoRevisedPrompt}
                  adapterName={currentConversation?.adapterName}
                />
              )}
              {(reply.document || reply.documentUrl) && replyIsAssistant && !reply.isStreaming && (
                <DocumentDisplay
                  document={reply.document}
                  documentUrl={reply.documentUrl}
                  documentFormat={reply.documentFormat}
                  revisedPrompt={reply.documentRevisedPrompt}
                  adapterName={currentConversation?.adapterName}
                />
              )}
            </div>
            {replyIsAssistant && !reply.isStreaming && getEnableFeedbackButtons() && (
              <ThreadReplyFeedback reply={reply} />
            )}
          </div>
        </div>
      );
    });
  }, [currentConversation?.adapterName, syntaxTheme, threadAssistantMarkdownClass, threadReplies, threadUserMarkdownClass]);

  return (
    <div className="group animate-fadeIn min-w-0 w-full px-0">
      <div className="min-w-0 space-y-1">
        <div className={bubbleClasses}>
          {isEditing ? (
            <div className="flex flex-col gap-2">
              <textarea
                ref={editTextareaRef}
                className="w-full resize-none overflow-hidden bg-transparent outline-none text-[#111827] dark:text-[#f5f5f5] leading-relaxed"
                value={editContent}
                onChange={e => setEditContent(e.target.value)}
                onCompositionStart={() => setIsEditComposing(true)}
                onCompositionEnd={() => setIsEditComposing(false)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey && !isEditComposing) {
                    e.preventDefault();
                    e.stopPropagation();
                    handleEditSubmit();
                  }
                  if (e.key === 'Escape') {
                    e.stopPropagation();
                    setIsEditing(false);
                    setEditContent(message.content || '');
                  }
                }}
                maxLength={AppConfig.maxMessageLength}
                rows={1}
                style={{ minHeight: '24px' }}
              />
              <div className="flex items-center justify-between gap-2 mt-1">
                <span className="text-xs text-gray-400 dark:text-[#6e6e80]">{t('message.edit.willRegenerateHint')}</span>
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      setIsEditing(false);
                      setEditContent(message.content || '');
                    }}
                    className="px-3 py-1.5 text-xs font-medium rounded-full bg-gray-200 text-gray-700 hover:bg-gray-300 dark:bg-[#4a4b54] dark:text-gray-200 dark:hover:bg-[#565869] transition-colors"
                  >
                    {t('common.cancel')}
                  </button>
                  <button
                    onClick={handleEditSubmit}
                    className="px-3 py-1.5 text-xs font-medium rounded-full bg-blue-600 text-white hover:bg-blue-700 transition-colors flex items-center gap-1.5"
                  >
                    <ArrowUp className="w-3.5 h-3.5" />
                    {t('common.send')}
                  </button>
                </div>
              </div>
            </div>
          ) : (
            renderedMessageContent
          )}

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

          {(message.image || message.imageUrl) && isAssistant && !message.isStreaming && (
            <ImageDisplay
              image={message.image}
              imageUrl={message.imageUrl}
              imageFormat={message.imageFormat}
              revisedPrompt={message.imageRevisedPrompt}
            />
          )}

          {(message.video || message.videoUrl) && isAssistant && !message.isStreaming && (
            <VideoDisplay
              video={message.video}
              videoUrl={message.videoUrl}
              videoFormat={message.videoFormat}
              revisedPrompt={message.videoRevisedPrompt}
              adapterName={currentConversation?.adapterName}
            />
          )}

            {(message.document || message.documentUrl) && isAssistant && !message.isStreaming && (
              <DocumentDisplay
                document={message.document}
                documentUrl={message.documentUrl}
                documentFormat={message.documentFormat}
                revisedPrompt={message.documentRevisedPrompt}
                adapterName={currentConversation?.adapterName}
              />
            )}
          
        </div>

        {!isAssistant && onEdit && !isEditing && (
            <button
              onClick={() => {
                setEditContent(message.content || '');
                setIsEditing(true);
              }}
              className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-gray-900 dark:text-gray-200 dark:hover:text-white transition-all duration-200 "
              title={t('message.editAriaLabel')}
              aria-label={t('message.editAriaLabel')}
            >
              <Edit2 className=" h-6 w-4 ml-1" />
            </button>
          )}

        {isAssistant && !message.isStreaming && (
          <div className="py-1 flex flex-nowrap items-center gap-0.5 text-gray-400 dark:text-[#8e8ea0] transition-opacity">
              {/* Copy */}
              {!hasGeneratedVideo && (
                <button
                  onClick={copyToClipboard}
                  className="rounded-md p-1.5 transition-colors hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-[#3c3f4a] dark:hover:text-[#ececf1]"
                  title={copyLabel}
                  aria-label={copyLabel}
                >
                  {copied
                    ? <Check className="h-4 w-4 text-emerald-500 dark:text-emerald-400" />
                    : <Copy className="h-4 w-4" />
                  }
                </button>
              )}

              {/* Feedback */}
              {getEnableFeedbackButtons() && (
                <div className="relative flex items-center gap-0.5">
                  <button
                    onClick={() => handleFeedback('up')}
                    disabled={isFeedbackLoading}
                    className={`rounded-md p-1.5 transition-colors ${isFeedbackLoading ? 'opacity-50 cursor-not-allowed' : ''} ${message.feedback === 'up' ? 'text-green-600 dark:text-green-400' : 'hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-[#3c3f4a] dark:hover:text-[#ececf1]'}`}
                    title={t('message.feedback.good')}
                    aria-label={t('message.feedback.good')}
                  >
                    <ThumbsUp className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => handleFeedback('down')}
                    disabled={isFeedbackLoading}
                    className={`rounded-md p-1.5 transition-colors ${isFeedbackLoading ? 'opacity-50 cursor-not-allowed' : ''} ${message.feedback === 'down' ? 'text-red-600 dark:text-red-400' : 'hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-[#3c3f4a] dark:hover:text-[#ececf1]'}`}
                    title={t('message.feedback.poor')}
                    aria-label={t('message.feedback.poor')}
                  >
                    <ThumbsDown className="h-4 w-4" />
                  </button>
                  {showFeedbackAcknowledgement && (
                    <div className="absolute bottom-full left-1/2 mb-2 -translate-x-1/2 whitespace-nowrap rounded-lg bg-emerald-500 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider text-white shadow-sm animate-fadeIn dark:bg-emerald-600">
                      <div className="absolute left-1/2 top-full h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rotate-45 bg-emerald-500 dark:bg-emerald-600" />
                      <div className="relative flex items-center gap-1.5">
                        <Check className="h-3.5 w-3.5" />
                        <span>{t('message.feedback.thanks')}</span>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Regenerate */}
              {onRegenerate && (
                <button
                  onClick={() => onRegenerate(message.id)}
                  className="rounded-md p-1.5 transition-colors hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-[#3c3f4a] dark:hover:text-[#ececf1]"
                  title={t('message.regenerateTitle')}
                  aria-label={t('message.regenerateAriaLabel')}
                >
                  <RotateCcw className="h-4 w-4" />
                </button>
              )}

              {/* Continue thread */}
              {threadsEnabled && message.supportsThreading && !message.threadInfo && onStartThread && sessionId && (
                <button
                  type="button"
                  onClick={() => {
                    pendingThreadFocusRef.current = true;
                    setIsThreadOpen(true);
                    onStartThread(message.id, sessionId);
                  }}
                  className="ml-1 inline-flex items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1.5 text-xs text-blue-700 shadow-sm transition-all hover:border-blue-300 hover:bg-blue-100 hover:text-blue-800 hover:shadow-md dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-200 dark:hover:border-blue-400/50 dark:hover:bg-blue-500/20 dark:hover:text-blue-100 animate-follow-up-enter whitespace-nowrap"
                  title={t('message.thread.continueDiscussionTitle')}
                  aria-label={t('message.thread.continueDiscussionAriaLabel')}
                >
                  <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                  <span>{t('message.thread.continueLabel')}</span>
                </button>
              )}

              {/* Thread reply count */}
              {threadsEnabled && message.threadInfo && (
                <>
                  <div className="w-px h-4 shrink-0 bg-gray-200 dark:bg-[#3c3f4a] mx-1" />
                  <button
                    onClick={() => setIsThreadOpen(prev => !prev)}
                    className="inline-flex min-w-0 items-center gap-1.5 rounded-md px-2 py-1.5 hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-[#3c3f4a] dark:hover:text-[#ececf1] transition-colors text-xs"
                  >
                    <MessageSquare className="h-4 w-4" />
                    <span className="truncate">{t('message.thread.replyCount', { count: threadReplyCount })}</span>
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
                      title={t('message.thread.clearTitle')}
                      aria-label={t('message.thread.clearAriaLabel')}
                    >
                      {t('common.clear')}
                    </button>
                  )}
                </>
              )}
          </div>
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
                          onClick={() => useLoginPromptStore.getState().openLoginPrompt(t('message.thread.signInPromptMessage'))}
                          className="inline-flex items-center gap-1 rounded-md bg-blue-600 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600"
                        >
                          {t('message.thread.signInForHigherLimits')}
                        </button>
                      </div>
                    )}
                  </div>
                )}

                <div
                  ref={threadComposerRef}
                  className="mt-1 w-full max-w-[64rem] bg-transparent pt-1"
                >
                  <div className="flex items-center gap-2 rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 dark:border-[#242424] dark:bg-[#101010]">
                    {selectedSkill && (
                      <div className="flex h-8 shrink-0 items-center gap-1.5 self-center rounded-full border border-gray-300 bg-white px-2.5 text-xs text-gray-700 shadow-sm dark:border-[#3a3a3a] dark:bg-[#1a1a1a] dark:text-gray-200">
                        <Sparkles className="h-3.5 w-3.5 shrink-0 text-gray-500 dark:text-gray-400" aria-hidden="true" />
                        <span className="min-w-0 truncate font-medium capitalize">
                          {selectedSkill.name.replace(/-/g, ' ')}
                        </span>
                        <button
                          type="button"
                          onClick={() => clearSkill()}
                          className="-mr-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-gray-100"
                          aria-label={t('message.thread.removeSkillAriaLabel')}
                        >
                          <X className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                      </div>
                    )}
                    {/* Skills hint — shown when the thread exposes skills, none
                        is selected, and the reply input is empty. Mirrors the
                        main composer's "/ Skills" affordance. */}
                    {!selectedSkill && skills.length > 0 && threadInput.length === 0 && !threadComposerDisabled && (
                      <button
                        type="button"
                        onClick={openThreadSkillPicker}
                        className="flex h-8 shrink-0 items-center gap-1.5 self-center rounded-full border border-gray-300 bg-white px-2.5 text-xs font-medium text-gray-600 shadow-sm transition-colors hover:bg-gray-100 hover:text-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-300 dark:border-[#3a3a3a] dark:bg-[#1a1a1a] dark:text-gray-300 dark:hover:bg-white/10 dark:hover:text-gray-100 dark:focus-visible:ring-gray-600"
                        aria-label={t('message.thread.skillsHintAriaLabel')}
                        title={t('message.thread.skillsHint')}
                      >
                        <span
                          className="flex h-4 w-4 shrink-0 items-center justify-center rounded bg-gray-200 font-mono text-[10px] leading-none text-gray-600 dark:bg-[#2a2a2a] dark:text-gray-300"
                          aria-hidden="true"
                        >
                          /
                        </span>
                        {t('messageInput.skillsHint.text')}
                      </button>
                    )}
                    <div className="relative flex min-h-8 flex-1 items-center min-w-0">
                      <label htmlFor={threadInputId} className="sr-only">
                        {t('message.thread.placeholder')}
                      </label>
                      {threadSkillInlineSuggestion && (
                        <div
                          className="pointer-events-none absolute inset-0 whitespace-pre-wrap px-0 py-0 text-base leading-8 text-gray-400 dark:text-[#8e8ea0] sm:text-sm sm:leading-8"
                          aria-hidden="true"
                        >
                          <span className="invisible">{threadInput}</span>
                          <span>{threadSkillInlineSuggestion}</span>
                        </div>
                      )}
                      <textarea
                        id={threadInputId}
                        ref={threadTextareaRef}
                        className="relative z-10 block h-8 w-full min-w-0 resize-none overflow-hidden bg-transparent px-0 py-0 text-base leading-8 text-[#353740] placeholder-slate-500 outline-none transition focus:outline-none disabled:opacity-60 dark:text-[#ececf1] dark:placeholder-[#70707c] sm:text-sm sm:leading-8"
                        placeholder={threadPlaceholder}
                        aria-label={t('message.thread.placeholder')}
                        value={threadInput}
                        onChange={e => {
                          const value = e.target.value;
                          setThreadInput(value);
                          if (value.startsWith('/')) {
                            setActiveThreadSkillIndex(0);
                          }
                          setShowThreadSkillPicker(value.startsWith('/'));
                        }}
                        onKeyDown={handleThreadKeyDown}
                        disabled={threadComposerDisabled}
                        rows={1}
                        maxLength={threadCharLimit}
                        style={{
                          minHeight: '32px',
                          maxHeight: '120px',
                          outline: 'none',
                          boxShadow: 'none',
                          WebkitAppearance: 'none',
                          MozAppearance: 'none',
                          appearance: 'none'
                        }}
                      />
                    </div>
                    <div className="flex items-center justify-between sm:justify-end gap-2">
                      <ModelPickerButton
                        availableModels={availableModels}
                        defaultModel={defaultModel}
                        selectedModel={threadSelectedModel}
                        onSelect={setThreadSelectedModel}
                        maxWidthClass="max-w-[120px]"
                        triggerPaddingClass="px-2 py-1"
                        staticPaddingClass="px-2 py-1"
                        triggerTitle={t('message.thread.selectModelTitle')}
                        listboxLabel={t('message.thread.selectModelTitle')}
                      />
                      {threadInput.trim().length > 0 && (
                        <button
                          type="button"
                          onClick={handleThreadSubmit}
                          disabled={threadComposerDisabled || threadInput.trim().length === 0}
                          className="flex h-10 w-10 sm:h-8 sm:w-8 items-center justify-center rounded-full transition active:scale-95 bg-blue-600 text-white hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-400 disabled:cursor-not-allowed"
                          title={t('message.thread.sendMessageTitle')}
                        >
                          <ArrowUp className="h-5 w-5 sm:h-4 sm:w-4" />
                        </button>
                      )}
                    </div>
                  </div>
                  {showThreadSkillPicker && (
                    <div className="w-full pt-1">
                      <SkillPicker
                        skills={skills}
                        isLoading={skillsLoading}
                        selectedSkill={selectedSkill}
                        activeSkillName={activeThreadSkill?.name}
                        query={threadSkillQuery}
                        onActiveSkillChange={(skill) => {
                          const nextIndex = filteredThreadSkills.findIndex(item => item.name === skill.name);
                          if (nextIndex >= 0) {
                            setActiveThreadSkillIndex(nextIndex);
                          }
                        }}
                        onSelect={selectThreadSkillAndClose}
                        onClose={closeThreadSkillPicker}
                      />
                    </div>
                  )}
                </div>

                {threadReplyCount > 0 && (
                  <div className="mt-2 flex justify-end">
                    <button
                      type="button"
                      onClick={() => setIsThreadOpen(false)}
                      className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700 dark:text-[#bfc2cd] dark:hover:bg-[#2f313a] dark:hover:text-white"
                      aria-label={t('message.thread.hideRepliesAriaLabel')}
                    >
                      <ChevronUp className="h-3 w-3" />
                      <span>{t('message.thread.hideRepliesLabel')}</span>
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
        title={t('message.confirmation.clearRepliesTitle')}
        message={t('message.confirmation.clearRepliesMessage')}
        confirmText={t('common.clear')}
        cancelText={t('common.cancel')}
        type="danger"
        isLoading={isClearingThread}
      />
    </div>
  );
}
