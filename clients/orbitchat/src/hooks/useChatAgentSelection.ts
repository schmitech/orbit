import { useCallback, useEffect, useRef, useState } from 'react';
import { getApi } from '../apiClient';
import { useChatStore, debouncedSaveToLocalStorage } from '../stores/chatStore';
import type { Conversation } from '../types';
import { debugError, debugLog, debugWarn } from '../utils/debug';
import { getApiUrl } from '../utils/runtimeConfig';
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

export function useChatAgentSelection({
  currentConversation,
  showEmptyState,
  createConversation,
  configureApiSettings,
  clearError,
  clearCurrentConversationAdapter
}: UseChatAgentSelectionOptions) {
  const [isConfiguringAdapter, setIsConfiguringAdapter] = useState(false);
  const [adapterNotesError, setAdapterNotesError] = useState<string | null>(null);

  const initialPathSlugRef = useRef<string | null>(
    typeof window !== 'undefined' ? getAgentSlugFromPath(window.location.pathname) : null
  );
  const initialAgentSelectionVisible = showEmptyState && !initialPathSlugRef.current;
  const [isAgentSelectionVisible, setIsAgentSelectionVisible] = useState(initialAgentSelectionVisible);
  const agentSelectionConversationRef = useRef<string | null>(null);
  const adapterInfoLoadedRef = useRef<string | null>(null);
  const adapterInfoRetryTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const adapterInfoRateLimitCooldownMs = 30000;
  const currentConversationHasDraftContent = !!currentConversation && (
    currentConversation.messages.length > 0 ||
    (currentConversation.attachedFiles?.length || 0) > 0
  );

  const persistChatState = useCallback(() => {
    debouncedSaveToLocalStorage(() => useChatStore.getState());
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
        setAdapterNotesError(null);
      }

      persistChatState();
      return { ok: true };
    } catch (error) {
      const friendlyMessage = getAdapterInfoErrorMessage(error);
      const latestState = useChatStore.getState();
      if (latestState.currentConversationId === conversation.id) {
        setAdapterNotesError(friendlyMessage);
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
    clearConversationAdapterError,
    clearError,
    configureApiSettings,
    fetchAdapterInfoForConversation,
    getAdapterInfoErrorMessage,
    markConversationAdapterError
  ]);

  const handleAgentCardSelection = useCallback((adapterName: string) => {
    ensureConversationReadyForAgent();
    setIsAgentSelectionVisible(false);
    replaceAgentSlug(slugifyAdapterName(adapterName));
    void handleEmptyStateAdapterChange(adapterName);
  }, [ensureConversationReadyForAgent, handleEmptyStateAdapterChange]);

  const handleChangeAgent = useCallback(() => {
    clearCurrentConversationAdapter();
    replaceAgentSlug(null);
    setIsAgentSelectionVisible(true);
  }, [clearCurrentConversationAdapter]);

  useEffect(() => {
    if (currentConversation?.adapterLoadError) {
      setAdapterNotesError(currentConversation.adapterLoadError);
    } else {
      setAdapterNotesError(null);
    }
  }, [currentConversation?.id, currentConversation?.adapterName, currentConversation?.adapterLoadError]);

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
    const shouldShowSelectionForConversation =
      !currentConversation?.adapterName && !currentConversationHasDraftContent;
    if (agentSelectionConversationRef.current !== conversationId) {
      agentSelectionConversationRef.current = conversationId;
      setIsAgentSelectionVisible(shouldShowSelectionForConversation);
      return;
    }

    if (isAgentSelectionVisible !== shouldShowSelectionForConversation) {
      setIsAgentSelectionVisible(shouldShowSelectionForConversation);
    }
  }, [
    showEmptyState,
    currentConversation?.adapterName,
    currentConversation?.id,
    currentConversationHasDraftContent,
    isAgentSelectionVisible
  ]);

  useEffect(() => {
    const shouldShowAgentSelectionList = showEmptyState && isAgentSelectionVisible;
    if (initialPathSlugRef.current) {
      return;
    }

    if (shouldShowAgentSelectionList || !currentConversation?.adapterName) {
      replaceAgentSlug(null);
      return;
    }
    replaceAgentSlug(slugifyAdapterName(currentConversation.adapterName));
  }, [showEmptyState, isAgentSelectionVisible, currentConversation?.adapterName]);

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
      await handleEmptyStateAdapterChange(adapterName);
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
  }, [clearCurrentConversationAdapter, ensureConversationReadyForAgent, handleEmptyStateAdapterChange]);

  useEffect(() => {
    debugLog('[ChatInterface] Conversation state:', {
      hasConversation: !!currentConversation,
      adapterName: currentConversation?.adapterName,
      hasAdapterInfo: !!currentConversation?.adapterInfo,
      hasNotes: !!currentConversation?.adapterInfo?.notes,
      notes: currentConversation?.adapterInfo?.notes?.substring(0, 50) + '...'
    });
  }, [currentConversation]);

  useEffect(() => {
    const loadMissingAdapterInfo = async () => {
      const adapterName = currentConversation?.adapterName;
      if (adapterInfoLoadedRef.current === adapterName) {
        return;
      }

      const needsRefresh = !currentConversation?.adapterInfo ||
        (currentConversation?.adapterInfo && currentConversation.adapterInfo.notes === undefined);

      if (adapterName && needsRefresh) {
        adapterInfoLoadedRef.current = adapterName;
        debugLog('[ChatInterface] Loading adapter info - adapterName:', adapterName, 'reason:', !currentConversation?.adapterInfo ? 'missing' : 'notes undefined');
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
            adapterInfoLoadedRef.current = null;
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

    void loadMissingAdapterInfo();
  }, [
    fetchAdapterInfoForConversation,
    currentConversation,
    currentConversation?.adapterInfo,
    currentConversation?.adapterLoadError,
    currentConversation?.adapterName,
    currentConversation?.apiUrl,
    currentConversation?.id
  ]);

  useEffect(() => {
    const retryTimers = adapterInfoRetryTimersRef.current;
    return () => {
      retryTimers.forEach(timer => clearTimeout(timer));
      retryTimers.clear();
    };
  }, []);

  return {
    adapterNotesError,
    handleAgentCardSelection,
    handleChangeAgent,
    hasAdapterConfigurationError: !!adapterNotesError,
    isAgentSelectionVisible,
    isConfiguringAdapter,
    setIsAgentSelectionVisible,
    shouldShowAgentSelectionList: showEmptyState && isAgentSelectionVisible
  };
}
