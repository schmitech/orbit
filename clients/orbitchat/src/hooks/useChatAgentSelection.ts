import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiRequestError, getApi } from '../apiClient';
import { useChatStore, debouncedSaveToLocalStorage } from '../stores/chatStore';
import type { Conversation } from '../types';
import { debugError, debugLog, debugWarn } from '../utils/debug';
import { getApiUrl, getConfiguredSingleAdapterId, getIsSingleAdapterMode } from '../utils/runtimeConfig';
import {
  getAgentSlugFromPath,
  replaceAgentSlug,
  resolveAdapterNameFromSlug,
  slugifyAdapterName
} from '../utils/agentRouting';

type ConfigureApiSettings = (apiUrl: string, sessionId?: string, adapterName?: string) => Promise<void>;

interface UseChatAgentSelectionOptions {
  currentConversation?: Conversation | null;
  showEmptyState: boolean;
  createConversation: () => string;
  configureApiSettings: ConfigureApiSettings;
  clearError: () => void;
  clearCurrentConversationAdapter: () => void;
}

type AdapterInfoFetchResult = { ok: true } | { ok: false; error?: unknown };
type AdapterNotesErrorState = { conversationId: string; message: string } | null;

export function useChatAgentSelection({
  currentConversation,
  showEmptyState,
  createConversation,
  configureApiSettings,
  clearError,
  clearCurrentConversationAdapter
}: UseChatAgentSelectionOptions) {
  const { t } = useTranslation();
  const missingSingleAdapterMessage = t('agent.error.singleAdapterMissing');
  const [isConfiguringAdapter, setIsConfiguringAdapter] = useState(false);
  const [adapterNotesAsyncError, setAdapterNotesAsyncError] = useState<AdapterNotesErrorState>(null);
  const isSingleAdapterMode = getIsSingleAdapterMode();
  const singleAdapterId = getConfiguredSingleAdapterId();
  const initialPathSlug = typeof window !== 'undefined'
    ? getAgentSlugFromPath(window.location.pathname)
    : null;

  const [pendingInitialPathSlug, setPendingInitialPathSlug] = useState<string | null>(initialPathSlug);
  const [isAgentSelectionVisible, setIsAgentSelectionVisible] = useState(() => !isSingleAdapterMode && showEmptyState && !initialPathSlug);
  const adapterInfoLoadedRef = useRef<string | null>(null);
  const adapterInfoRetryTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const locationSyncVersionRef = useRef(0);
  const adapterInfoRateLimitCooldownMs = 30000;
  const hasCurrentConversation = !!currentConversation;
  const currentConversationMessageCount = currentConversation?.messages.length ?? 0;
  const currentConversationAttachedFileCount = currentConversation?.attachedFiles?.length ?? 0;
  const currentConversationHasDraftContent = useMemo(
    () => hasCurrentConversation && (
      currentConversationMessageCount > 0 ||
      currentConversationAttachedFileCount > 0
    ),
    [
      currentConversationAttachedFileCount,
      currentConversationMessageCount,
      hasCurrentConversation
    ]
  );

  const persistChatState = useCallback(() => {
    debouncedSaveToLocalStorage(() => useChatStore.getState());
  }, []);

  const markConversationAdapterError = useCallback((conversationId?: string, message?: string) => {
    if (!conversationId) {
      return;
    }
    const friendlyMessage = message || t('agent.error.configurationFailed');
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
  }, [persistChatState, t]);

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
    if (error instanceof ApiRequestError) {
      if (error.status === 401) {
        return t('agent.error.authenticationFailed');
      }
      if (error.status === 404) {
        return t('agent.error.notFound');
      }
      return error.message;
    }
    if (error instanceof Error) {
      return error.message;
    }
    return t('agent.error.loadFailed');
  }, [t]);

  const ensureConversationReadyForAgent = useCallback((): string | null => {
    const state = useChatStore.getState();
    const activeConversation = state.currentConversationId
      ? state.conversations.find(conv => conv.id === state.currentConversationId)
      : null;

    if (!activeConversation || activeConversation.messages.length > 0) {
      try {
        const newConversationId = createConversation();
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

  const fetchAdapterInfoForConversation = useCallback(async (conversation?: Conversation | null): Promise<AdapterInfoFetchResult> => {
    if (!conversation?.adapterName) {
      return { ok: false };
    }

    try {
      const api = await getApi();
      const adapterClient = new api.ApiClient({
        apiUrl: conversation.apiUrl || getApiUrl(),
        sessionId: null,
        adapterName: conversation.adapterName
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

      if (useChatStore.getState().currentConversationId === conversation.id) {
        setAdapterNotesAsyncError(null);
      }

      persistChatState();
      return { ok: true };
    } catch (error) {
      const friendlyMessage = getAdapterInfoErrorMessage(error);
      const latestState = useChatStore.getState();
      if (latestState.currentConversationId === conversation.id) {
        setAdapterNotesAsyncError({ conversationId: conversation.id, message: friendlyMessage });
      }
      const latestConversation = latestState.conversations.find(conv => conv.id === conversation.id);
      if (latestConversation && latestConversation.messages.length === 0) {
        markConversationAdapterError(conversation.id, friendlyMessage);
      }
      return { ok: false, error };
    }
  }, [getAdapterInfoErrorMessage, markConversationAdapterError, persistChatState]);

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
    setAdapterNotesAsyncError(null);
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
      setAdapterNotesAsyncError({ conversationId: activeConversation.id, message: friendlyMessage });
      markConversationAdapterError(activeConversation.id, friendlyMessage);
    } finally {
      setIsConfiguringAdapter(false);
    }
  }, [
    clearConversationAdapterError,
    clearError,
    configureApiSettings,
    fetchAdapterInfoForConversation,
    getAdapterInfoErrorMessage,
    markConversationAdapterError
  ]);

  const handleAgentCardSelection = useCallback((adapterName: string) => {
    if (isSingleAdapterMode) {
      return;
    }
    ensureConversationReadyForAgent();
    setIsAgentSelectionVisible(false);
    replaceAgentSlug(slugifyAdapterName(adapterName));
    void handleEmptyStateAdapterChange(adapterName);
  }, [ensureConversationReadyForAgent, handleEmptyStateAdapterChange, isSingleAdapterMode]);

  const handleChangeAgent = useCallback(() => {
    if (isSingleAdapterMode) {
      return;
    }
    clearCurrentConversationAdapter();
    replaceAgentSlug(null);
    setIsAgentSelectionVisible(true);
  }, [clearCurrentConversationAdapter, isSingleAdapterMode]);

  const goToAgentSelectionHome = useCallback(() => {
    if (isSingleAdapterMode) {
      const state = useChatStore.getState();
      const conv = state.currentConversationId
        ? state.conversations.find(c => c.id === state.currentConversationId)
        : null;
      const hasContent = !!conv && (
        conv.messages.length > 0 || (conv.attachedFiles?.length || 0) > 0
      );

      if (hasContent) {
        try {
          createConversation();
        } catch (error) {
          debugWarn(
            'Cannot go home (new conversation):',
            error instanceof Error ? error.message : 'Unknown error'
          );
        }
      }

      replaceAgentSlug(null);
      setIsAgentSelectionVisible(false);
      return;
    }

    setPendingInitialPathSlug(null);

    const state = useChatStore.getState();
    const conv = state.currentConversationId
      ? state.conversations.find(c => c.id === state.currentConversationId)
      : null;
    const hasContent = !!conv && (
      conv.messages.length > 0 || (conv.attachedFiles?.length || 0) > 0
    );

    if (hasContent) {
      try {
        createConversation();
      } catch (error) {
        debugWarn(
          'Cannot go home (new conversation):',
          error instanceof Error ? error.message : 'Unknown error'
        );
        return;
      }
    } else if (conv?.adapterName) {
      clearCurrentConversationAdapter();
    }

    replaceAgentSlug(null);
    setIsAgentSelectionVisible(true);
  }, [clearCurrentConversationAdapter, createConversation, isSingleAdapterMode]);

  const shouldShowSelectionForConversation =
    !isSingleAdapterMode &&
    showEmptyState &&
    !pendingInitialPathSlug &&
    !currentConversation?.adapterName &&
    !currentConversationHasDraftContent;

  const shouldShowAgentSelectionList =
    shouldShowSelectionForConversation ||
    (
      !isSingleAdapterMode &&
      showEmptyState &&
      isAgentSelectionVisible &&
      !currentConversation?.adapterName &&
      !currentConversationHasDraftContent
    );

  useEffect(() => {
    if (isSingleAdapterMode) {
      replaceAgentSlug(null);
      return;
    }

    if (pendingInitialPathSlug) {
      return;
    }

    if (shouldShowAgentSelectionList || !currentConversation?.adapterName) {
      replaceAgentSlug(null);
      return;
    }
    replaceAgentSlug(slugifyAdapterName(currentConversation.adapterName));
  }, [
    currentConversation?.adapterName,
    isSingleAdapterMode,
    pendingInitialPathSlug,
    shouldShowAgentSelectionList
  ]);

  const synchronizeFromLocation = useCallback(async () => {
    if (typeof window === 'undefined') {
      return;
    }
    const syncVersion = ++locationSyncVersionRef.current;

    if (isSingleAdapterMode) {
      replaceAgentSlug(null);
      setPendingInitialPathSlug(null);
      return;
    }

    const slug = getAgentSlugFromPath(window.location.pathname);
    if (!slug) {
      return;
    }
    const adapterName = await resolveAdapterNameFromSlug(slug);
    if (syncVersion !== locationSyncVersionRef.current) {
      return;
    }
    if (!adapterName) {
      ensureConversationReadyForAgent();
      replaceAgentSlug(null);
      clearCurrentConversationAdapter();
      setIsAgentSelectionVisible(true);
      setPendingInitialPathSlug(null);
      return;
    }
    ensureConversationReadyForAgent();
    setIsAgentSelectionVisible(false);
    replaceAgentSlug(slug);
    await handleEmptyStateAdapterChange(adapterName);
    setPendingInitialPathSlug(null);
  }, [clearCurrentConversationAdapter, ensureConversationReadyForAgent, handleEmptyStateAdapterChange, isSingleAdapterMode]);

  // Keep a ref to the latest synchronizeFromLocation so the mount/popstate effect below
  // doesn't rerun (and re-sync the route) every time an unrelated dependency — like the
  // `t` function identity changing on language switch — recreates the callback chain.
  const synchronizeFromLocationRef = useRef(synchronizeFromLocation);
  useEffect(() => {
    synchronizeFromLocationRef.current = synchronizeFromLocation;
  }, [synchronizeFromLocation]);

  useEffect(() => {
    const syncTimer = window.setTimeout(() => {
      void synchronizeFromLocationRef.current();
    }, 0);

    const handlePopState = () => {
      void synchronizeFromLocationRef.current();
    };

    window.addEventListener('popstate', handlePopState);
    return () => {
      window.clearTimeout(syncTimer);
      locationSyncVersionRef.current += 1;
      window.removeEventListener('popstate', handlePopState);
    };
  }, []);

  const singleAdapterConversationId = currentConversation?.id;
  const singleAdapterConversationAdapterName = currentConversation?.adapterName;
  const singleAdapterConversationApiUrl = currentConversation?.apiUrl;
  const singleAdapterConversationHasInfo = !!currentConversation?.adapterInfo;

  useEffect(() => {
    if (!isSingleAdapterMode) {
      return;
    }

    if (!singleAdapterId) {
      return;
    }

    if (!showEmptyState || !singleAdapterConversationId || currentConversationHasDraftContent || isConfiguringAdapter) {
      return;
    }

    const targetAdapterId = singleAdapterConversationAdapterName?.trim() || singleAdapterId;
    const requiresConfiguration =
      singleAdapterConversationAdapterName?.trim() !== targetAdapterId ||
      !singleAdapterConversationHasInfo;

    if (!targetAdapterId || !requiresConfiguration) {
      return;
    }

    let cancelled = false;

    const configureSingleAdapter = async () => {
      setIsConfiguringAdapter(true);
      setAdapterNotesAsyncError(null);
      clearConversationAdapterError(singleAdapterConversationId);

      try {
        const runtimeApiUrl = singleAdapterConversationApiUrl || getApiUrl();
        await configureApiSettings(runtimeApiUrl, undefined, targetAdapterId);
        clearError();
      } catch (error) {
        if (!cancelled) {
          const friendlyMessage = getAdapterInfoErrorMessage(error);
          setAdapterNotesAsyncError({ conversationId: singleAdapterConversationId, message: friendlyMessage });
          markConversationAdapterError(singleAdapterConversationId, friendlyMessage);
        }
      } finally {
        if (!cancelled) {
          setIsConfiguringAdapter(false);
        }
      }
    };

    void configureSingleAdapter();

    return () => {
      cancelled = true;
    };
  }, [
    clearConversationAdapterError,
    clearError,
    configureApiSettings,
    currentConversationHasDraftContent,
    getAdapterInfoErrorMessage,
    isConfiguringAdapter,
    isSingleAdapterMode,
    markConversationAdapterError,
    showEmptyState,
    singleAdapterConversationAdapterName,
    singleAdapterConversationApiUrl,
    singleAdapterConversationHasInfo,
    singleAdapterConversationId,
    singleAdapterId
  ]);

  useEffect(() => {
    const refreshAdapterInfo = async () => {
      const adapterName = currentConversation?.adapterName;
      // Keyed by conversation id + adapter name (not adapter name alone) so that
      // creating a new conversation for the same adapter (common in single mode,
      // where every conversation shares the configured default adapter) still
      // receives a fresh intro from the backend when ChatInterface mounts.
      const loadKey = currentConversation ? `${currentConversation.id}:${adapterName}` : null;
      if (!loadKey || adapterInfoLoadedRef.current === loadKey) {
        return;
      }

      if (adapterName) {
        adapterInfoLoadedRef.current = loadKey;
        debugLog('[ChatInterface] Refreshing adapter info from the backend - adapterName:', adapterName);
        // Use fetchAdapterInfoForConversation which creates an isolated ApiClient,
        // avoiding mutation of the shared API state that could corrupt active streams.
        const result = await fetchAdapterInfoForConversation(currentConversation);
        if (result.ok) {
          debugLog('[ChatInterface] Adapter info loaded successfully');
        } else {
          const error = result.error;
          debugError('[ChatInterface] Failed to load adapter info:', error);
          const errorMessage = error instanceof Error ? error.message : String(error);
          const isRateLimited = errorMessage.includes('429') || errorMessage.includes('Too Many Requests');

          if (isRateLimited && adapterName) {
            const existingTimer = adapterInfoRetryTimersRef.current.get(loadKey);
            if (existingTimer) {
              clearTimeout(existingTimer);
            }
            const retryTimer = setTimeout(() => {
              if (adapterInfoLoadedRef.current === loadKey) {
                adapterInfoLoadedRef.current = null;
              }
              adapterInfoRetryTimersRef.current.delete(loadKey);
            }, adapterInfoRateLimitCooldownMs);
            adapterInfoRetryTimersRef.current.set(loadKey, retryTimer);
            debugWarn(`[ChatInterface] Adapter info request rate-limited; retrying in ${adapterInfoRateLimitCooldownMs / 1000}s`);
          } else {
            adapterInfoLoadedRef.current = null;
          }
        }
      } else {
        debugLog('[ChatInterface] Skipping adapter info refresh: no adapter selected');
      }
    };

    void refreshAdapterInfo();
  }, [fetchAdapterInfoForConversation, currentConversation]);

  useEffect(() => {
    const retryTimers = adapterInfoRetryTimersRef.current;
    return () => {
      retryTimers.forEach(timer => clearTimeout(timer));
      retryTimers.clear();
    };
  }, []);

  const adapterNotesError = isSingleAdapterMode && !singleAdapterId
    ? missingSingleAdapterMessage
    : currentConversation?.adapterLoadError ??
      (adapterNotesAsyncError && adapterNotesAsyncError.conversationId === currentConversation?.id
        ? adapterNotesAsyncError.message
        : null);

  return {
    adapterNotesError,
    handleAgentCardSelection,
    handleChangeAgent,
    goToAgentSelectionHome,
    hasAdapterConfigurationError: !!adapterNotesError,
    isAgentSelectionVisible,
    isConfiguringAdapter,
    isSingleAdapterMode,
    setIsAgentSelectionVisible,
    shouldShowAgentSelectionList
  };
}
