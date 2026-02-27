import { useState, useEffect, useRef, useCallback } from 'react';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { useChatStore } from '../stores/chatStore';
import { Settings, Menu, Plus } from 'lucide-react';
import { debugError, debugLog, debugWarn } from '../utils/debug';
import { getApi } from '../api/loader';
import {
  getApiUrl,
  getApplicationName,
  getApplicationDescription,
  getDefaultInputPlaceholder,
  getIsAuthConfigured,
  getEnableHeader,
} from '../utils/runtimeConfig';
import { useSettings } from '../contexts/SettingsContext';
import { audioStreamManager } from '../utils/audioStreamManager';
import { MarkdownRenderer } from '@schmitech/markdown-renderer';
import { useTheme } from '../contexts/ThemeContext';
import { AgentSelectionList } from './AgentSelectionList';
import { AuthStatus } from './AuthStatus';
import { useIsAuthenticated } from '../hooks/useIsAuthenticated';
import type { Conversation } from '../types';
import {
  getAgentSlugFromPath,
  replaceAgentSlug,
  resolveAdapterNameFromSlug,
  slugifyAdapterName
} from '../utils/agentRouting';

const MOBILE_FRAME_CLASSES =
  'rounded-t-[32px] border border-white/40 bg-transparent px-4 pb-4 pt-[max(env(safe-area-inset-top),1rem)] shadow-none backdrop-blur-0 dark:border-[#2f303d] dark:bg-transparent md:rounded-none md:border-0 md:bg-transparent md:px-0 md:pb-0 md:pt-3 md:shadow-none md:backdrop-blur-0 md:dark:bg-transparent md:dark:border-0';

const MOBILE_INPUT_WRAPPER_CLASSES =
  'shrink-0 sticky bottom-[calc(var(--app-footer-height,0px)+0.25rem)] z-10 -mx-4 mt-auto overflow-visible bg-transparent pb-[max(env(safe-area-inset-bottom),0.5rem)] shadow-none backdrop-blur-0 transition-all duration-200 dark:bg-transparent md:bottom-[calc(var(--app-footer-height,0px)+0.5rem)] md:z-10 md:mx-0 md:mt-0 md:overflow-visible md:rounded-none md:border-0 md:bg-transparent md:pb-0 md:shadow-none md:backdrop-blur-0 md:dark:bg-transparent md:dark:border-0 [&>div]:bg-transparent md:[&>div]:rounded-none md:[&>div]:px-0';

const MOBILE_INPUT_WRAPPER_NON_STICKY_CLASSES =
  'shrink-0 mt-3 overflow-visible bg-transparent pb-[max(env(safe-area-inset-bottom),0.5rem)] shadow-none backdrop-blur-0 transition-all duration-200 dark:bg-transparent md:mx-0 md:mt-0 md:overflow-visible md:rounded-none md:border-0 md:bg-transparent md:pb-0 md:shadow-none md:backdrop-blur-0 md:dark:bg-transparent md:dark:border-0 [&>div]:bg-transparent md:[&>div]:rounded-none md:[&>div]:px-0';

// Mobile header classes for native-like sticky behavior
const MOBILE_HEADER_CLASSES =
  'relative z-20 shrink-0 -mx-4 px-4 pt-2 pb-2 bg-white border-b border-slate-200 dark:border-[#3b3d49] dark:bg-[#1e1f29] md:static md:mx-0 md:px-0 md:pt-6 md:pb-6 md:bg-transparent md:border-gray-200 md:dark:border-[#4a4b54] md:dark:bg-transparent';

// Note: We use getApiUrl() directly when needed
// to ensure we always read the latest runtime config (including CLI args)

interface ChatInterfaceProps {
  onOpenSettings: () => void;
  onOpenSidebar?: () => void;
}

export function ChatInterface({ onOpenSettings, onOpenSidebar }: ChatInterfaceProps) {
  const {
    conversations,
    currentConversationId,
    createConversation,
    canCreateNewConversation,
    sendMessage,
    regenerateResponse,
    isLoading,
    configureApiSettings,
    error,
    clearError,
    createThread,
    clearCurrentConversationAdapter
  } = useChatStore();

  const { settings } = useSettings();
  const isAuthenticated = useIsAuthenticated();
  const isGuest = getIsAuthConfigured() && !isAuthenticated;
  const { theme, isDark } = useTheme();
  const forcedThemeClass =
    theme.mode === 'dark' ? 'dark' : theme.mode === 'light' ? 'light' : '';
  const syntaxTheme: 'dark' | 'light' = isDark ? 'dark' : 'light';
  const adapterNotesMarkdownClass = [
    'message-markdown w-full min-w-0',
    'prose prose-slate dark:prose-invert max-w-none md:prose-lg',
    '[&>:first-child]:mt-0 [&>:last-child]:mb-0',
    forcedThemeClass
  ]
    .filter(Boolean)
    .join(' ');
  const introDescriptionMarkdownClass = [
    'application-description prose prose-slate dark:prose-invert max-w-none text-sm md:text-base leading-relaxed',
    'text-[#4a4c5a] dark:text-[#bfc2cd]',
    '[&>:first-child]:mt-0 [&>:last-child]:mb-0',
    forcedThemeClass
  ]
    .filter(Boolean)
    .join(' ');

  const [isConfiguringAdapter, setIsConfiguringAdapter] = useState(false);
  const [adapterNotesError, setAdapterNotesError] = useState<string | null>(null);

  const currentConversation = conversations.find(c => c.id === currentConversationId);
  const showEmptyState = !currentConversation || currentConversation.messages.length === 0;
  const defaultInputPlaceholder = getDefaultInputPlaceholder();
  const applicationName = getApplicationName();
  const applicationDescription = getApplicationDescription().trim();
  const hasIntroDescription = applicationDescription.length > 0;
  const initialPathSlugRef = useRef<string | null>(
    typeof window !== 'undefined' ? getAgentSlugFromPath(window.location.pathname) : null
  );
  const initialAgentSelectionVisible = showEmptyState && !initialPathSlugRef.current;
  const [isAgentSelectionVisible, setIsAgentSelectionVisible] = useState(initialAgentSelectionVisible);
  const agentSelectionConversationRef = useRef<string | null>(null);
  const shouldShowAgentSelectionList =
    showEmptyState && isAgentSelectionVisible;
  const shouldShowAdapterNotesPanel =
    showEmptyState && !isAgentSelectionVisible && !!currentConversation?.adapterName;
  const chatMaxWidthClass = 'max-w-7xl';
  const inputMaxWidthClass = 'max-w-3xl';
  const prominentWidthClass = `mx-auto w-full ${chatMaxWidthClass}`;
  const messageInputWidthClass = 'w-full';
  const emptyStateInputWrapperClass = shouldShowAdapterNotesPanel
    ? MOBILE_INPUT_WRAPPER_NON_STICKY_CLASSES
    : MOBILE_INPUT_WRAPPER_CLASSES;
  const canStartNewConversation = canCreateNewConversation();
  const canChangeAgent = !!currentConversation?.adapterName && (currentConversation?.messages.length || 0) === 0;
  const newConversationTooltip = canStartNewConversation
    ? 'Start a new conversation'
    : isGuest
    ? 'Guest conversation limit reached. Sign in for more conversations.'
    : 'Finish your current conversation before starting a new one.';
  const showHeaderMetadata = !!(currentConversation && !shouldShowAgentSelectionList);
  const showBodyHeading = showEmptyState && !shouldShowAgentSelectionList;
  const bodyHeadingText =
    currentConversation?.adapterName && !shouldShowAgentSelectionList
      ? currentConversation.adapterName
      : shouldShowAgentSelectionList
        ? applicationName
        : '';
  const headerBorderClass = shouldShowAgentSelectionList
    ? 'border-transparent dark:border-transparent md:border-transparent md:dark:border-transparent'
    : '';
  const compactSelectionHeaderSpacingClass =
    !getEnableHeader() && shouldShowAgentSelectionList
      ? 'pt-0 pb-0 md:pt-0 md:pb-1'
      : '';
  const headerClasses = `${MOBILE_HEADER_CLASSES} ${headerBorderClass} ${compactSelectionHeaderSpacingClass}`.trim();
  const effectiveHeaderClasses = headerClasses;
  const emptyStateTopSpacingClass = shouldShowAgentSelectionList
    ? 'pt-0 md:pt-0'
    : shouldShowAdapterNotesPanel
      ? 'pt-5 md:pt-0'
      : 'pt-4 md:pt-6';
  const hasAdapterConfigurationError = !!adapterNotesError;
  const ensureConversationReadyForAgent = useCallback((): string | null => {
    const state = useChatStore.getState();
    const activeConversation = state.currentConversationId
      ? state.conversations.find(conv => conv.id === state.currentConversationId)
      : null;

    if (!activeConversation || activeConversation.messages.length > 0) {
      try {
        const newConversationId = createConversation();
        agentSelectionConversationRef.current = newConversationId;
        return newConversationId;
      } catch (error) {
        debugWarn(
          'Cannot create a new conversation for agent selection:',
          error instanceof Error ? error.message : 'Unknown error'
        );
      }
    }
    return activeConversation?.id || null;
  }, [createConversation]);

  useEffect(() => {
    if (currentConversation?.adapterLoadError) {
      setAdapterNotesError(currentConversation.adapterLoadError);
    } else {
      setAdapterNotesError(null);
    }
  }, [currentConversation?.id, currentConversation?.adapterName, currentConversation?.adapterLoadError]);

  const persistChatState = useCallback(() => {
    if (typeof window === 'undefined') {
      return;
    }
    setTimeout(() => {
      const currentState = useChatStore.getState();
      localStorage.setItem('chat-state', JSON.stringify({
        conversations: currentState.conversations,
        currentConversationId: currentState.currentConversationId
      }));
    }, 0);
  }, []);

  const markConversationAdapterError = useCallback((conversationId?: string, message?: string) => {
    if (!conversationId) {
      return;
    }
    const friendlyMessage = message || 'Unable to configure this agent.';
    let updated = false;
    useChatStore.setState(state => {
      const target = state.conversations.find(conv => conv.id === conversationId);
      if (!target || target.messages.length > 0) {
        return state;
      }
      updated = true;
      return {
        conversations: state.conversations.map(conv =>
          conv.id === conversationId
            ? { ...conv, adapterLoadError: friendlyMessage }
            : conv
        )
      };
    });
    if (updated) {
      persistChatState();
    }
  }, [persistChatState]);

  const clearConversationAdapterError = useCallback((conversationId?: string) => {
    if (!conversationId) {
      return;
    }
    let updated = false;
    useChatStore.setState(state => {
      const target = state.conversations.find(conv => conv.id === conversationId);
      if (!target || !target.adapterLoadError) {
        return state;
      }
      updated = true;
      return {
        conversations: state.conversations.map(conv =>
          conv.id === conversationId
            ? { ...conv, adapterLoadError: null }
            : conv
        )
      };
    });
    if (updated) {
      persistChatState();
    }
  }, [persistChatState]);

  const getAdapterInfoErrorMessage = useCallback((error: unknown): string => {
    if (error instanceof Error) {
      if (error.message.includes('401')) {
        return 'We couldn’t load this agent. It may not exist or you might not have access to it.';
      }
      if (error.message.includes('404')) {
        return 'This agent was not found on the server. Please pick another agent.';
      }
      return error.message;
    }
    return 'Unable to load agent overview right now.';
  }, []);

  type AdapterInfoFetchResult = { ok: true } | { ok: false; error?: unknown };

  const fetchAdapterInfoForConversation = useCallback(async (conversation?: Conversation | null): Promise<AdapterInfoFetchResult> => {
    if (!conversation) {
      return { ok: false };
    }

    const adapterName = conversation.adapterName;
    if (!adapterName) {
      return { ok: false };
    }

    try {
      const api = await getApi();
      const adapterClient = new api.ApiClient({
        apiUrl: conversation.apiUrl || getApiUrl(),
        sessionId: null,
        adapterName: adapterName
      });

      if (typeof adapterClient.getAdapterInfo !== 'function') {
        return { ok: false };
      }

      const adapterInfo = await adapterClient.getAdapterInfo();
      useChatStore.setState(state => ({
        conversations: state.conversations.map(conv =>
          conv.id === conversation.id
            ? { ...conv, adapterInfo, adapterLoadError: null, updatedAt: new Date() }
            : conv
        )
      }));

      const latestState = useChatStore.getState();
      if (latestState.currentConversationId === conversation.id) {
        setAdapterNotesError(null);
      }

      persistChatState();
      return { ok: true };
    } catch (error) {
      const latestState = useChatStore.getState();
      const friendlyMessage = getAdapterInfoErrorMessage(error);
      if (latestState.currentConversationId === conversation.id) {
        setAdapterNotesError(friendlyMessage);
      }
      const latestConversation = latestState.conversations.find(conv => conv.id === conversation.id);
      if (latestConversation && latestConversation.messages.length === 0) {
        markConversationAdapterError(conversation.id, friendlyMessage);
      }
      return { ok: false, error };
    }
  }, [getAdapterInfoErrorMessage, markConversationAdapterError, persistChatState, setAdapterNotesError]);

  // Reset agent selection visibility when conversations change
  useEffect(() => {
    if (!showEmptyState) {
      if (isAgentSelectionVisible) {
        setIsAgentSelectionVisible(false);
      }
      agentSelectionConversationRef.current = currentConversation?.id || null;
      return;
    }

    if (initialPathSlugRef.current) {
      agentSelectionConversationRef.current = currentConversation?.id || null;
      return;
    }

    const conversationId = currentConversation?.id || null;
    if (agentSelectionConversationRef.current !== conversationId) {
      agentSelectionConversationRef.current = conversationId;
      setIsAgentSelectionVisible(true);
    }
  }, [showEmptyState, currentConversation?.id, isAgentSelectionVisible]);


  useEffect(() => {
    if (initialPathSlugRef.current) {
      return;
    }

    if (shouldShowAgentSelectionList || !currentConversation?.adapterName) {
      replaceAgentSlug(null);
      return;
    }
    replaceAgentSlug(slugifyAdapterName(currentConversation.adapterName));
  }, [shouldShowAgentSelectionList, currentConversation?.adapterName]);

  useEffect(() => {
    let cancelled = false;

    const synchronizeFromLocation = async () => {
      if (typeof window === 'undefined') {
        return;
      }
      const slug = getAgentSlugFromPath(window.location.pathname);
      if (!slug) {
        return;
      }
      const adapterName = await resolveAdapterNameFromSlug(slug);
      if (cancelled) {
        return;
      }
      if (!adapterName) {
        ensureConversationReadyForAgent();
        replaceAgentSlug(null);
        clearCurrentConversationAdapter();
        setIsAgentSelectionVisible(true);
        initialPathSlugRef.current = null;
        return;
      }
      ensureConversationReadyForAgent();
      setIsAgentSelectionVisible(false);
      replaceAgentSlug(slug);
      const configure = adapterSelectionRef.current;
      if (configure) {
        await configure(adapterName);
      }
      initialPathSlugRef.current = null;
    };

    void synchronizeFromLocation();

    const handlePopState = () => {
      void synchronizeFromLocation();
    };

    window.addEventListener('popstate', handlePopState);
    return () => {
      cancelled = true;
      window.removeEventListener('popstate', handlePopState);
    };
  }, [ensureConversationReadyForAgent, clearCurrentConversationAdapter]);

  // Debug: Log current conversation state
  useEffect(() => {
    debugLog('[ChatInterface] Conversation state:', {
      hasConversation: !!currentConversation,
      adapterName: currentConversation?.adapterName,
      hasAdapterInfo: !!currentConversation?.adapterInfo,
      hasNotes: !!currentConversation?.adapterInfo?.notes,
      notes: currentConversation?.adapterInfo?.notes?.substring(0, 50) + '...'
    });
  }, [currentConversation]);

  // Load adapter info if in middleware mode and adapter is selected but info is missing or incomplete
  // This handles: 1) race conditions, 2) stale localStorage without notes field
  const adapterInfoLoadedRef = useRef<string | null>(null);
  const adapterInfoRetryTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const adapterInfoRateLimitCooldownMs = 30000;
  useEffect(() => {
    const loadMissingAdapterInfo = async () => {
      const adapterName = currentConversation?.adapterName;
      // Only load once per adapter to avoid duplicate requests
      if (adapterInfoLoadedRef.current === adapterName) return;

      // Check if adapterInfo is missing OR if notes field is missing (stale data from before notes feature)
      const needsRefresh = !currentConversation?.adapterInfo ||
                          (currentConversation?.adapterInfo && currentConversation.adapterInfo.notes === undefined);

      if (adapterName && needsRefresh) {
        adapterInfoLoadedRef.current = adapterName;
        debugLog('[ChatInterface] Loading adapter info - adapterName:', adapterName, 'reason:', !currentConversation?.adapterInfo ? 'missing' : 'notes undefined');
        try {
          const apiUrl = currentConversation?.apiUrl || getApiUrl();
          debugLog('[ChatInterface] Calling configureApiSettings for:', adapterName);
          await configureApiSettings(apiUrl, undefined, adapterName);
          debugLog('[ChatInterface] Adapter info loaded successfully');
        } catch (error) {
          debugError('[ChatInterface] Failed to load adapter info:', error);
          const errorMessage = error instanceof Error ? error.message : String(error);
          const isRateLimited = errorMessage.includes('429') || errorMessage.includes('Too Many Requests');

          if (isRateLimited && adapterName) {
            const existingTimer = adapterInfoRetryTimersRef.current.get(adapterName);
            if (existingTimer) {
              clearTimeout(existingTimer);
            }
            const retryTimer = setTimeout(() => {
              if (adapterInfoLoadedRef.current === adapterName) {
                adapterInfoLoadedRef.current = null;
              }
              adapterInfoRetryTimersRef.current.delete(adapterName);
            }, adapterInfoRateLimitCooldownMs);
            adapterInfoRetryTimersRef.current.set(adapterName, retryTimer);
            debugWarn(`[ChatInterface] Adapter info request rate-limited; retrying in ${adapterInfoRateLimitCooldownMs / 1000}s`);
          } else {
            // Reset flag on non-rate-limit errors so it can retry
            adapterInfoLoadedRef.current = null;
          }

          if (currentConversation?.adapterName === adapterName) {
            const friendlyMessage = getAdapterInfoErrorMessage(error);
            setAdapterNotesError(friendlyMessage);
            markConversationAdapterError(currentConversation.id, friendlyMessage);
          }
        }
      } else {
        debugLog('[ChatInterface] Skipping adapter info load:', {
          adapterName,
          hasAdapterInfo: !!currentConversation?.adapterInfo,
          hasNotes: currentConversation?.adapterInfo?.notes !== undefined,
          refValue: adapterInfoLoadedRef.current
        });
      }
    };
    loadMissingAdapterInfo();
  }, [
    currentConversation?.adapterName,
    currentConversation?.adapterInfo,
    currentConversation?.apiUrl,
    currentConversation?.adapterLoadError,
    currentConversation?.id,
    configureApiSettings,
    getAdapterInfoErrorMessage,
    markConversationAdapterError
  ]);

  useEffect(() => {
    const retryTimers = adapterInfoRetryTimersRef.current;
    return () => {
      retryTimers.forEach(timer => clearTimeout(timer));
      retryTimers.clear();
    };
  }, []);

  // Clean up any orphaned streaming messages on mount (only once, not on every render)
  // Removed automatic cleanup to preserve streaming state when switching conversations
  // Streaming messages will be cleaned up when they complete naturally

  // Don't save API settings to localStorage when modal fields change
  // Only save when explicitly configured via configureApiSettings
  // This prevents default values from overwriting localStorage

  // Enable/disable audio streaming based on Voice Responses setting
  useEffect(() => {
    let removeGestureListeners: (() => void) | null = null;

    const cleanupGestureListeners = () => {
      if (removeGestureListeners) {
        removeGestureListeners();
        removeGestureListeners = null;
      }
    };

    if (settings.voiceEnabled) {
      if (audioStreamManager.isAudioEnabled()) {
        debugLog('[ChatInterface] Audio streaming already enabled');
        return cleanupGestureListeners;
      }

      const attachGestureListeners = () => {
        cleanupGestureListeners();
        const handleUserGesture = async () => {
          cleanupGestureListeners();
          const success = await audioStreamManager.enableAudio();
          if (success) {
            debugLog('[ChatInterface] Audio streaming enabled after user gesture');
          } else {
            debugWarn('[ChatInterface] User gesture did not enable audio streaming');
            attachGestureListeners();
          }
        };

        document.addEventListener('pointerdown', handleUserGesture, { once: true });
        document.addEventListener('keydown', handleUserGesture, { once: true });
        removeGestureListeners = () => {
          document.removeEventListener('pointerdown', handleUserGesture);
          document.removeEventListener('keydown', handleUserGesture);
        };

        debugLog('[ChatInterface] Waiting for user gesture to enable audio streaming');
      };

      attachGestureListeners();
      return cleanupGestureListeners;
    }

    cleanupGestureListeners();
    audioStreamManager.disableAudio();
    debugLog('[ChatInterface] Audio streaming disabled via settings');

    return cleanupGestureListeners;
  }, [settings.voiceEnabled]);

  const handleSendMessage = (content: string, fileIds?: string[], threadId?: string) => {
    sendMessage(content, fileIds, threadId);
  };

  const handleSendThreadMessage = async (threadId: string, _parentMessageId: string, content: string) => {
    await sendMessage(content, undefined, threadId);
  };

  const handleStartNewConversation = () => {
    try {
      createConversation();
    } catch (error) {
      debugWarn('Cannot create new conversation:', error instanceof Error ? error.message : 'Unknown error');
    }
  };

  const handleEmptyStateAdapterChange = useCallback(async (adapterName: string) => {
    if (!adapterName) {
      return;
    }
    const state = useChatStore.getState();
    const activeConversation = state.currentConversationId
      ? state.conversations.find(conv => conv.id === state.currentConversationId)
      : null;
    if (!activeConversation) {
      return;
    }
    setIsConfiguringAdapter(true);
    setAdapterNotesError(null);
    clearConversationAdapterError(activeConversation.id);
    try {
      const runtimeApiUrl = activeConversation.apiUrl || getApiUrl();
      await configureApiSettings(runtimeApiUrl, undefined, adapterName);
      clearError();
      const latestState = useChatStore.getState();
      const latestConversation = latestState.conversations.find(conv => conv.id === latestState.currentConversationId);
      if (latestConversation?.adapterName === adapterName && (!latestConversation.adapterInfo || latestConversation.adapterInfo.notes === undefined)) {
        const result = await fetchAdapterInfoForConversation(latestConversation);
        if (!result.ok && result.error) {
          debugError('Failed to load adapter info after selecting adapter:', result.error);
        }
      }
    } catch (error) {
      debugError('Failed to configure adapter from empty state:', error);
      const friendlyMessage = getAdapterInfoErrorMessage(error);
      setAdapterNotesError(friendlyMessage);
      markConversationAdapterError(activeConversation.id, friendlyMessage);
    } finally {
      setIsConfiguringAdapter(false);
    }
  }, [
    configureApiSettings,
    clearError,
    fetchAdapterInfoForConversation,
    markConversationAdapterError,
    clearConversationAdapterError,
    getAdapterInfoErrorMessage
  ]);

  const handleAgentCardSelection = (adapterName: string) => {
    ensureConversationReadyForAgent();
    setIsAgentSelectionVisible(false);
    replaceAgentSlug(slugifyAdapterName(adapterName));
    void handleEmptyStateAdapterChange(adapterName);
  };
  const adapterSelectionRef = useRef(handleEmptyStateAdapterChange);
  useEffect(() => {
    adapterSelectionRef.current = handleEmptyStateAdapterChange;
  }, [handleEmptyStateAdapterChange]);

  return (
    <main className="flex-1 flex flex-col bg-transparent overflow-hidden" aria-label="Chat workspace">
      <div className="flex h-full w-full flex-col px-3 sm:px-6 overflow-hidden">
        <div className={`mx-auto flex h-full w-full ${chatMaxWidthClass} flex-col overflow-hidden md:pb-4 ${MOBILE_FRAME_CLASSES}`}>

          {/* Error Banner */}
          {error && (
            <div 
              role="alert"
              className="mt-6 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-600/40 dark:bg-red-900/30 dark:text-red-200"
            >
              <div className="flex items-start justify-between">
                <p>{error}</p>
                <button
                  onClick={clearError}
                  className="ml-4 rounded p-1 text-red-500 hover:bg-red-100 hover:text-red-700 dark:text-red-200 dark:hover:bg-red-800/40"
                  aria-label="Dismiss error"
                >
                  ×
                </button>
              </div>
            </div>
          )}

          {/* Chat Header */}
          <div className={effectiveHeaderClasses}>
            {/* Mobile navigation buttons - inside header so they stick with it */}
            {onOpenSidebar && (
              <div className="mb-2 flex items-center justify-between gap-2 md:hidden">
                <div className="flex items-center gap-2">
                  <button
                    onClick={onOpenSidebar}
                    className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-white/50 bg-white/80 px-3 py-2 text-xs font-semibold text-gray-800 shadow-sm active:scale-[0.97] transition-all duration-150 hover:bg-white dark:border-[#2f303d] dark:bg-[#232430] dark:text-[#ececf1]"
                    aria-label="Open conversations menu"
                  >
                    <Menu className="h-4 w-4" />
                    Chats
                  </button>
                  <button
                    onClick={onOpenSettings}
                    className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-white/50 bg-[#11121a]/90 px-3 py-2 text-xs font-semibold text-white shadow-sm active:scale-[0.97] transition-all duration-150 hover:bg-[#0c0d14] dark:border-[#3b3c49] dark:bg-[#565869] dark:hover:bg-[#6b6f7a]"
                    aria-label="Open settings"
                  >
                    <Settings className="h-4 w-4" />
                    Settings
                  </button>
                </div>
                <div className="ml-auto flex-shrink-0">
                  <AuthStatus />
                </div>
              </div>
            )}
            <div className="flex flex-col gap-2 md:gap-4 sm:flex-row sm:items-end sm:justify-between">
              <div className="min-w-0 flex-1">
                {/* Adapter Info - show first when available */}
                {showHeaderMetadata && (
                  <div className="space-y-1.5 md:space-y-3">
                    <div className="hidden md:flex min-w-0 flex-wrap items-center gap-2 justify-start md:flex-nowrap">
                      {currentConversation?.adapterInfo?.model && (
                        <div
                          className="inline-flex max-w-full flex-shrink items-center gap-2 rounded-full border border-gray-200 bg-gray-100 px-2.5 py-1 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:border-[#4a4b54] dark:bg-[#343541] dark:text-[#bfc2cd] min-w-0"
                          title={currentConversation.adapterInfo.model}
                          aria-label={`Model: ${currentConversation.adapterInfo.model}`}
                        >
                          <span>Model</span>
                          <span className="block truncate text-gray-800 normal-case dark:text-[#ececf1]">
                            {currentConversation.adapterInfo.model}
                          </span>
                        </div>
                      )}
                      <div
                        className="inline-flex max-w-full flex-shrink items-center gap-2 rounded-md border border-gray-200 bg-gray-100 px-2.5 py-1 text-xs font-semibold uppercase tracking-wider text-gray-600 dark:border-[#4a4b54] dark:bg-[#343541] dark:text-[#bfc2cd] min-w-0"
                        title={
                          currentConversation?.adapterName ||
                          currentConversation?.adapterInfo?.adapter_name ||
                          'Configured Agent'
                        }
                        aria-label={`Agent: ${
                          currentConversation?.adapterName ||
                          currentConversation?.adapterInfo?.adapter_name ||
                          'Configured Agent'
                        }`}
                      >
                        <span>Agent</span>
                        <span className="block truncate text-gray-800 normal-case dark:text-[#ececf1]">
                          {currentConversation?.adapterName ||
                            currentConversation?.adapterInfo?.adapter_name ||
                            'Configured Agent'}
                        </span>
                      </div>
                    </div>
                    <div className="md:space-y-1">
                      <div className="flex items-baseline justify-between gap-2">
                        <h1 className="min-w-0 truncate text-lg md:text-2xl font-semibold text-[#353740] dark:text-[#ececf1]">
                          {currentConversation?.title || 'New Chat'}
                        </h1>
                        {currentConversation && (
                          <span className="flex-shrink-0 text-xs md:hidden text-gray-500 dark:text-[#bfc2cd]">
                            {currentConversation.updatedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </span>
                        )}
                      </div>
                      {currentConversation && (
                        <div className="hidden md:flex items-center gap-2 text-sm text-gray-500 dark:text-[#bfc2cd]">
                          <span className="font-medium">{currentConversation.messages.length}</span>
                          <span>Updated {currentConversation.updatedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
              <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto md:justify-end md:gap-3">
                {!shouldShowAgentSelectionList && !getEnableHeader() && (
                  <AuthStatus />
                )}
                {!shouldShowAgentSelectionList && !!currentConversation?.adapterName && (
                  <button
                    type="button"
                    onClick={() => {
                      if (!canChangeAgent) {
                        return;
                      }
                      clearCurrentConversationAdapter();
                      replaceAgentSlug(null);
                      setIsAgentSelectionVisible(true);
                    }}
                    disabled={!canChangeAgent}
                    className={`order-2 sm:order-1 inline-flex h-8 md:h-[42px] w-[calc(50%-0.25rem)] min-w-[140px] md:w-[190px] items-center justify-center gap-1 md:gap-2 rounded-full border px-2.5 md:px-3.5 py-1.5 md:py-2.5 text-[11px] md:text-[13px] font-medium tracking-[0.01em] transition-colors focus-visible:outline-none focus-visible:ring-2 ${
                      canChangeAgent
                        ? 'border-blue-300 text-blue-700 hover:bg-blue-50 hover:border-blue-400 focus-visible:ring-blue-500 dark:border-blue-500/40 dark:text-blue-300 dark:hover:bg-blue-900/20 dark:hover:border-blue-400/60 dark:focus-visible:ring-blue-400/60'
                        : 'cursor-not-allowed border-gray-200 text-gray-400 bg-transparent dark:border-[#3c3f4a] dark:text-[#6b6f7a]'
                    }`}
                    title={canChangeAgent ? 'Switch to a different agent before starting this conversation' : 'Agent cannot be changed after the conversation has started'}
                  >
                    Change Agent
                  </button>
                )}
                {!shouldShowAgentSelectionList && (
                  <button
                    onClick={handleStartNewConversation}
                    disabled={!canStartNewConversation}
                    className={`order-3 sm:order-2 inline-flex h-8 md:h-[42px] w-[calc(50%-0.25rem)] min-w-[140px] md:w-[190px] items-center justify-center gap-1 md:gap-2 rounded-full border px-2.5 md:px-3.5 py-1.5 md:py-2.5 text-[11px] md:text-[13px] font-medium tracking-[0.01em] ${
                      canStartNewConversation
                        ? 'border-[#1f2937] bg-[#1f2937] text-white shadow-[0_2px_8px_rgba(15,23,42,0.12)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1f2937]/40 dark:border-[#4b5568] dark:bg-[#2f3747] dark:text-[#e9edf8] dark:shadow-[0_2px_8px_rgba(0,0,0,0.25)] dark:focus-visible:ring-[#6f809f]/35'
                        : 'cursor-not-allowed border-gray-200 text-gray-400 bg-white/40 dark:border-[#3c3f4a] dark:text-[#6b6f7a] dark:bg-transparent'
                    }`}
                    title={newConversationTooltip}
                  >
                    <Plus className="h-3.5 w-3.5" />
                    New Conversation
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Messages and Input - Conditional Layout */}
          {showEmptyState ? (
            // Empty state: Flex layout that pushes input to bottom on mobile, left-aligned on desktop
            <div className={`flex flex-1 flex-col min-h-0 ${emptyStateTopSpacingClass} ${shouldShowAgentSelectionList ? 'overflow-hidden' : ''}`}>
              <div className={`flex-1 flex flex-col justify-between ${shouldShowAgentSelectionList ? 'md:justify-start min-h-0 overflow-hidden' : shouldShowAdapterNotesPanel ? 'md:justify-start md:pt-10 md:gap-6 overflow-y-auto' : 'md:justify-start md:flex-none'}`}>
                <div className={`w-full ${shouldShowAgentSelectionList ? 'flex flex-col min-h-0 overflow-hidden flex-1' : shouldShowAdapterNotesPanel ? 'flex flex-col' : 'space-y-6'}`}>
                  {showBodyHeading && !shouldShowAdapterNotesPanel && bodyHeadingText && (
                    <div className={`${prominentWidthClass}`}>
                      <MarkdownRenderer
                        content={bodyHeadingText}
                        className="prose prose-slate dark:prose-invert max-w-none [&>:first-child]:mt-0 [&>:last-child]:mb-0 text-2xl font-semibold text-[#11111b] dark:text-white [&_p]:text-2xl [&_p]:font-semibold [&_p]:leading-tight [&_p]:m-0"
                        syntaxTheme={syntaxTheme}
                      />
                      {bodyHeadingText === applicationName && hasIntroDescription && shouldShowAgentSelectionList && (
                        <div className="mt-2">
                          <MarkdownRenderer
                            content={applicationDescription}
                            className={introDescriptionMarkdownClass}
                            syntaxTheme={syntaxTheme}
                          />
                        </div>
                      )}
                    </div>
                  )}
                  {shouldShowAgentSelectionList ? (
                    <div className="flex flex-col min-h-0 flex-1 gap-3 md:gap-6 overflow-y-auto md:overflow-hidden">
                      <div className={`${prominentWidthClass} flex-shrink-0 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between`}>
                        <div className="flex-1">
                          <MarkdownRenderer
                            content={applicationName}
                            className="prose prose-slate dark:prose-invert max-w-none [&>:first-child]:mt-0 [&>:last-child]:mb-0 text-2xl font-semibold text-[#11111b] dark:text-white text-center md:text-left [&_p]:text-2xl [&_p]:font-semibold [&_p]:leading-tight [&_p]:m-0"
                            syntaxTheme={syntaxTheme}
                          />
                          {hasIntroDescription && (
                            <div className="mt-2">
                              <MarkdownRenderer
                                content={applicationDescription}
                                className={introDescriptionMarkdownClass}
                                syntaxTheme={syntaxTheme}
                              />
                            </div>
                          )}
                        </div>
                        <div className="flex flex-col items-end gap-2">
                          {!getEnableHeader() && <AuthStatus />}
                        </div>
                      </div>
                      <AgentSelectionList
                        onAdapterSelect={handleAgentCardSelection}
                        className={`${prominentWidthClass} md:flex-1 md:min-h-0 md:overflow-hidden`}
                      />
                    </div>
                  ) : shouldShowAdapterNotesPanel ? (
                    <div className="mx-auto w-full max-w-3xl py-0">
                      <div className="px-1 pb-2 pt-2 md:pb-2 md:pt-0">
                        {currentConversation?.adapterInfo?.notes ? (
                          <MarkdownRenderer
                            content={currentConversation.adapterInfo.notes}
                            className={adapterNotesMarkdownClass}
                            syntaxTheme={syntaxTheme}
                          />
                        ) : adapterNotesError ? (
                          <p className="text-sm text-red-600 dark:text-red-400">
                            {adapterNotesError}
                          </p>
                        ) : isConfiguringAdapter ? (
                          <p className="text-sm text-gray-600 dark:text-[#bfc2cd]">
                            Configuring your agent… hang tight for just a moment.
                          </p>
                        ) : (
                          <p className="text-sm text-gray-600 dark:text-[#bfc2cd]">
                            Fetching agent overview… this only takes a moment.
                          </p>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className={`${prominentWidthClass} mb-2`}>
                      {currentConversation?.adapterInfo?.notes ? (
                        // Show adapter notes as the main prompt with markdown rendering
                        <div className="text-base text-gray-600 dark:text-[#bfc2cd] leading-relaxed">
                          <MarkdownRenderer
                            content={currentConversation.adapterInfo.notes}
                            className={adapterNotesMarkdownClass}
                            syntaxTheme={syntaxTheme}
                          />
                        </div>
                      ) : (
                        // Fallback to default message
                        <h2 className="text-xl md:text-2xl font-medium text-[#353740] dark:text-[#ececf1]">
                          How can I assist you today?
                        </h2>
                      )}
                    </div>
                  )}
                </div>
                {!shouldShowAgentSelectionList && (
                  <div className={emptyStateInputWrapperClass}>
                    <div className={messageInputWidthClass}>
                      <MessageInput
                        onSend={handleSendMessage}
                        disabled={
                          isLoading ||
                          !currentConversation ||
                          !currentConversation?.adapterName ||
                          hasAdapterConfigurationError
                        }
                        autoFocusEnabled
                        suppressMobileAutoFocus={shouldShowAdapterNotesPanel}
                        placeholder={defaultInputPlaceholder}
                        maxWidthClass={inputMaxWidthClass}
                        isCentered={shouldShowAdapterNotesPanel}
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            // Has messages: Normal layout with messages at top and input at bottom
            <div className="flex flex-1 flex-col min-h-0">
              <MessageList
                messages={currentConversation.messages}
                onRegenerate={regenerateResponse}
                onStartThread={async (messageId: string, sessionId: string) => {
                  try {
                    await createThread(messageId, sessionId);
                  } catch (error) {
                    debugError('Failed to create thread:', error);
                  }
                }}
                onSendThreadMessage={handleSendThreadMessage}
                sessionId={currentConversation.sessionId}
                isLoading={isLoading}
              />
              <div className={MOBILE_INPUT_WRAPPER_CLASSES}>
                <div className="w-full">
                  <MessageInput
                    onSend={handleSendMessage}
                    disabled={
                      isLoading ||
                      !currentConversation ||
                      !currentConversation.adapterName ||
                      isAgentSelectionVisible ||
                      hasAdapterConfigurationError
                    }
                    autoFocusEnabled
                    placeholder="Start a new topic..."
                    maxWidthClass="max-w-4xl"
                    isCentered
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
