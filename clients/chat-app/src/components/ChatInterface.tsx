import { useState, useEffect, useRef, FormEvent, MouseEvent } from 'react';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { AdapterSelector } from './AdapterSelector';
import { useChatStore } from '../stores/chatStore';
import { Eye, EyeOff, Settings, RefreshCw, Menu } from 'lucide-react';
import { debugError, debugLog, debugWarn } from '../utils/debug';
import { getApi } from '../api/loader';
import { getDefaultKey, getApiUrl, getEnableApiMiddleware } from '../utils/runtimeConfig';
import { PACKAGE_VERSION } from '../utils/version';
import { useSettings } from '../contexts/SettingsContext';
import { audioStreamManager } from '../utils/audioStreamManager';
import { MarkdownRenderer } from '@schmitech/markdown-renderer';

const MOBILE_FRAME_CLASSES =
  'rounded-t-[32px] border border-white/40 bg-white/95 px-4 pb-4 pt-[max(env(safe-area-inset-top),1rem)] shadow-[0_25px_60px_rgba(15,23,42,0.15)] backdrop-blur-xl dark:border-[#2f303d] dark:bg-[#1c1d23]/95 md:rounded-none md:border-0 md:bg-transparent md:px-0 md:pb-0 md:pt-0 md:shadow-none md:backdrop-blur-0 md:dark:bg-transparent md:dark:border-0';

const MOBILE_INPUT_WRAPPER_CLASSES =
  '-mx-4 mt-auto overflow-hidden rounded-t-[28px] border-t border-x border-white/40 bg-white/98 pb-[max(env(safe-area-inset-bottom),0.75rem)] shadow-[0_-12px_45px_rgba(15,23,42,0.2)] backdrop-blur-xl transition-all duration-200 dark:border-[#2f303d] dark:bg-[#1c1d23]/98 md:mx-0 md:mt-0 md:overflow-visible md:rounded-none md:border-0 md:bg-transparent md:pb-0 md:shadow-none md:backdrop-blur-0 md:dark:bg-transparent md:dark:border-0 [&>div]:rounded-t-[28px] md:[&>div]:rounded-none [&>div]:bg-transparent md:[&>div]:px-0';

// Mobile header classes for native-like sticky behavior
const MOBILE_HEADER_CLASSES =
  'sticky top-0 z-10 -mx-4 px-4 pt-2 pb-4 bg-white/95 backdrop-blur-xl dark:bg-[#1c1d23]/95 border-b border-white/50 dark:border-white/10 md:static md:mx-0 md:px-0 md:pt-6 md:pb-6 md:bg-transparent md:backdrop-blur-0 md:border-gray-200 md:dark:border-[#4a4b54] md:dark:bg-transparent';

// Note: We use getApiUrl() and getDefaultKey() directly when needed
// to ensure we always read the latest runtime config (including CLI args)

interface ChatInterfaceProps {
  onOpenSettings: () => void;
  onOpenSidebar?: () => void;
}

export function ChatInterface({ onOpenSettings, onOpenSidebar }: ChatInterfaceProps) {
  const {
    conversations,
    currentConversationId,
    sendMessage,
    regenerateResponse,
    isLoading,
    configureApiSettings,
    error,
    clearError,
    createThread
  } = useChatStore();

  const { settings } = useSettings();

  // Configuration state for API settings
  const [showConfig, setShowConfig] = useState(false);
  // Initialize with runtime config defaults (will be updated when modal opens)
  const [apiUrl, setApiUrl] = useState(() => getApiUrl());
  const [apiKey, setApiKey] = useState(() => getDefaultKey());
  const [selectedAdapter, setSelectedAdapter] = useState<string | null>(null);
  const [showApiKey, setShowApiKey] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isRefreshingAdapterInfo, setIsRefreshingAdapterInfo] = useState(false);

  const currentConversation = conversations.find(c => c.id === currentConversationId);
  const isMiddlewareEnabled = getEnableApiMiddleware();

  // Initialize selected adapter from conversation
  useEffect(() => {
    if (isMiddlewareEnabled && currentConversation?.adapterName) {
      setSelectedAdapter(currentConversation.adapterName);
    }
  }, [isMiddlewareEnabled, currentConversation?.adapterName]);

  // Debug: Log current conversation state for middleware mode debugging
  useEffect(() => {
    if (isMiddlewareEnabled) {
      debugLog('[ChatInterface] Middleware mode state:', {
        hasConversation: !!currentConversation,
        adapterName: currentConversation?.adapterName,
        hasAdapterInfo: !!currentConversation?.adapterInfo,
        hasNotes: !!currentConversation?.adapterInfo?.notes,
        notes: currentConversation?.adapterInfo?.notes?.substring(0, 50) + '...'
      });
    }
  }, [isMiddlewareEnabled, currentConversation?.adapterName, currentConversation?.adapterInfo]);

  // Load adapter info if in middleware mode and adapter is selected but info is missing or incomplete
  // This handles: 1) race conditions, 2) stale localStorage without notes field
  const adapterInfoLoadedRef = useRef<string | null>(null);
  useEffect(() => {
    const loadMissingAdapterInfo = async () => {
      const adapterName = currentConversation?.adapterName;
      // Only load once per adapter to avoid duplicate requests
      if (adapterInfoLoadedRef.current === adapterName) return;

      // Check if adapterInfo is missing OR if notes field is missing (stale data from before notes feature)
      const needsRefresh = !currentConversation?.adapterInfo ||
                          (currentConversation?.adapterInfo && currentConversation.adapterInfo.notes === undefined);

      if (isMiddlewareEnabled && adapterName && needsRefresh) {
        adapterInfoLoadedRef.current = adapterName;
        debugLog('[ChatInterface] Loading adapter info - adapterName:', adapterName, 'reason:', !currentConversation?.adapterInfo ? 'missing' : 'notes undefined');
        try {
          const apiUrl = currentConversation?.apiUrl || getApiUrl();
          debugLog('[ChatInterface] Calling configureApiSettings for:', adapterName);
          await configureApiSettings(apiUrl, undefined, undefined, adapterName);
          debugLog('[ChatInterface] Adapter info loaded successfully');
        } catch (error) {
          debugError('[ChatInterface] Failed to load adapter info:', error);
          // Reset flag on error so it can retry
          adapterInfoLoadedRef.current = null;
        }
      } else {
        debugLog('[ChatInterface] Skipping adapter info load:', {
          isMiddlewareEnabled,
          adapterName,
          hasAdapterInfo: !!currentConversation?.adapterInfo,
          hasNotes: currentConversation?.adapterInfo?.notes !== undefined,
          refValue: adapterInfoLoadedRef.current
        });
      }
    };
    loadMissingAdapterInfo();
  }, [isMiddlewareEnabled, currentConversation?.adapterName, currentConversation?.adapterInfo, currentConversation?.apiUrl, configureApiSettings]);

  // Disable Configure API button once conversation has started (has messages)
  // API key should remain immutable per conversation to prevent issues with conversation history
  const canConfigureApi = !currentConversation || currentConversation.messages.length === 0;

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

  const handleRefreshAdapterInfo = async () => {
    if (!currentConversation || (!currentConversation.apiKey && !currentConversation.adapterName)) {
      debugWarn('Cannot refresh adapter info: no conversation or API key/adapter');
      return;
    }

    setIsRefreshingAdapterInfo(true);
    try {
      const api = await getApi();
      const conversationApiUrl = currentConversation.apiUrl || getApiUrl();
      const conversationApiKey = currentConversation.apiKey;
      const conversationAdapterName = currentConversation.adapterName;

      const adapterClient = new api.ApiClient({
        apiUrl: conversationApiUrl,
        apiKey: conversationApiKey || null,
        sessionId: null,
        adapterName: conversationAdapterName || null
      });

      if (typeof adapterClient.getAdapterInfo === 'function') {
        const adapterInfo = await adapterClient.getAdapterInfo();
        debugLog('Adapter info refreshed:', adapterInfo);

        // Update the conversation's adapter info in the store
        useChatStore.setState((state) => ({
          conversations: state.conversations.map(conv =>
            conv.id === currentConversationId
              ? { ...conv, adapterInfo: adapterInfo, updatedAt: new Date() }
              : conv
          )
        }));

        // Save to localStorage
        setTimeout(() => {
          const currentState = useChatStore.getState();
          localStorage.setItem('chat-state', JSON.stringify({
            conversations: currentState.conversations,
            currentConversationId: currentState.currentConversationId
          }));
        }, 0);
      }
    } catch (error) {
      debugError('Failed to refresh adapter info:', error);
      // Optionally show an error message to the user
    } finally {
      setIsRefreshingAdapterInfo(false);
    }
  };

  const handleConfigureApi = async (event?: FormEvent<HTMLFormElement> | MouseEvent<HTMLButtonElement>) => {
    if (event) {
      event.preventDefault();
    }
    
    if (isMiddlewareEnabled) {
      // Middleware mode: use adapter name
      if (apiUrl && selectedAdapter) {
        setIsValidating(true);
        setValidationError(null);
        
        try {
          await configureApiSettings(apiUrl, undefined, undefined, selectedAdapter);
          clearError();
          setValidationError(null);
          setShowConfig(false);
        } catch (error) {
          debugError('Failed to configure adapter:', error);
          const errorMessage = error instanceof Error ? error.message : 'Failed to configure adapter';
          setValidationError(errorMessage);
        } finally {
          setIsValidating(false);
        }
      }
    } else {
      // Normal mode: use API key
      if (apiUrl && apiKey) {
        setIsValidating(true);
        setValidationError(null);
        
        try {
          await configureApiSettings(apiUrl, apiKey);
          // Clear any existing error after successful configuration
          clearError();
          // After successful configuration, the conversation now has the new API key
          // So we keep the configured values (they'll be loaded next time the modal opens)
          // But we still close the modal
          setValidationError(null);
          setShowApiKey(false);
          setShowConfig(false);
        } catch (error) {
          debugError('Failed to configure API:', error);
          // Set validation error for display in the modal
          const errorMessage = error instanceof Error ? error.message : 'Failed to configure API settings';
          setValidationError(errorMessage);
          // Also set error in the store for global error banner
          // (The store will handle this, but we can also show it in the modal)
          // Don't reset fields on error - let user see what they entered
        } finally {
          setIsValidating(false);
        }
      }
    }
  };

  const handleAdapterChange = (adapterName: string) => {
    setSelectedAdapter(adapterName);
    setValidationError(null);
  };

  return (
    <div className="flex-1 flex flex-col bg-gray-50 dark:bg-[#202123] overflow-hidden">
      <div className="flex h-full w-full flex-col px-3 sm:px-6 overflow-hidden">
        <div className={`mx-auto flex h-full w-full max-w-5xl flex-col overflow-hidden ${MOBILE_FRAME_CLASSES}`}>

          {/* API Configuration Modal */}
          {showConfig && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
              <form
                onSubmit={handleConfigureApi}
                className="w-full max-w-md rounded-lg border border-gray-200 bg-white p-6 shadow-lg dark:border-[#444654] dark:bg-[#202123]"
              >
                <h2 className="text-lg font-medium text-[#353740] dark:text-[#ececf1] mb-4">
                  {isMiddlewareEnabled ? 'Select Adapter' : 'Configure API Settings'}
                </h2>
                <div className="space-y-5">
                  {!isMiddlewareEnabled && (
                    <div>
                      <label className="block text-sm font-medium text-[#353740] dark:text-[#d1d5db] mb-2">
                        API URL
                      </label>
                      <input
                        type="text"
                        value={apiUrl}
                        onChange={(e) => setApiUrl(e.target.value)}
                        className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-[#353740] focus:border-gray-400 focus:outline-none dark:border-[#4a4b54] dark:bg-[#343541] dark:text-[#ececf1]"
                        placeholder="https://api.example.com"
                      />
                    </div>
                  )}
                  {isMiddlewareEnabled ? (
                    <AdapterSelector
                      selectedAdapter={selectedAdapter}
                      onAdapterChange={handleAdapterChange}
                      disabled={isValidating}
                    />
                  ) : (
                    <div>
                      <label className="block text-sm font-medium text-[#353740] dark:text-[#d1d5db] mb-2">
                        API Key
                      </label>
                      <div className="relative">
                        <input
                          type={showApiKey ? 'text' : 'password'}
                          value={apiKey}
                          onChange={(e) => {
                            setApiKey(e.target.value);
                            setValidationError(null); // Clear validation error when user types
                          }}
                          className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 pr-10 text-sm text-[#353740] focus:border-gray-400 focus:outline-none dark:border-[#4a4b54] dark:bg-[#343541] dark:text-[#ececf1]"
                          placeholder="your-api-key"
                          disabled={isValidating}
                        />
                        <button
                          type="button"
                          onClick={() => setShowApiKey(!showApiKey)}
                          className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-gray-500 hover:text-gray-700 dark:text-[#d1d5db] dark:hover:text-white"
                          aria-label={showApiKey ? 'Hide API key' : 'Show API key'}
                          disabled={isValidating}
                        >
                          {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                        </button>
                      </div>
                    </div>
                  )}
                  {validationError && (
                    <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-600/40 dark:bg-red-900/30 dark:text-red-200">
                      {validationError}
                    </div>
                  )}
                  <div className="flex justify-end gap-3 pt-2">
                    <button
                      type="button"
                      onClick={() => {
                        // Reset to current conversation's values when canceling (or defaults if none)
                        // Read dynamically to ensure we get the latest runtime config
                        const currentApiUrl = currentConversation?.apiUrl || getApiUrl();
                        const currentApiKey = currentConversation?.apiKey || getDefaultKey();
                        setApiUrl(currentApiUrl);
                        setApiKey(currentApiKey);
                        setValidationError(null);
                        setShowApiKey(false);
                        setShowConfig(false);
                      }}
                      className="rounded-md border border-transparent px-4 py-2 text-sm text-gray-600 hover:border-gray-300 hover:text-gray-900 dark:text-[#d1d5db] dark:hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                      disabled={isValidating}
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={isValidating || (isMiddlewareEnabled ? !selectedAdapter : (!apiUrl || !apiKey))}
                      className="rounded-md bg-[#343541] px-4 py-2 text-sm font-medium text-white hover:bg-[#282b32] disabled:cursor-not-allowed disabled:opacity-50 dark:bg-[#565869] dark:hover:bg-[#6b6f7a]"
                    >
                      {isValidating ? 'Validating...' : 'Update'}
                    </button>
                  </div>
                </div>
              </form>
            </div>
          )}

          {/* Error Banner */}
          {error && (
            <div className="mt-6 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-600/40 dark:bg-red-900/30 dark:text-red-200">
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
          <div className={MOBILE_HEADER_CLASSES}>
            {/* Mobile navigation buttons - inside header so they stick with it */}
            {onOpenSidebar && (
              <div className="mb-4 grid grid-cols-2 gap-3 md:hidden">
                <button
                  onClick={onOpenSidebar}
                  className="inline-flex items-center justify-center gap-2 rounded-2xl border border-white/50 bg-white/80 px-4 py-3.5 text-sm font-semibold text-gray-800 shadow-sm active:scale-[0.97] transition-all duration-150 hover:bg-white dark:border-[#2f303d] dark:bg-[#232430] dark:text-[#ececf1]"
                  aria-label="Open conversations menu"
                >
                  <Menu className="h-5 w-5" />
                  Chats
                </button>
                <button
                  onClick={onOpenSettings}
                  className="inline-flex items-center justify-center gap-2 rounded-2xl border border-white/50 bg-[#11121a]/90 px-4 py-3.5 text-sm font-semibold text-white shadow-sm active:scale-[0.97] transition-all duration-150 hover:bg-[#0c0d14] dark:border-[#3b3c49] dark:bg-[#565869] dark:hover:bg-[#6b6f7a]"
                  aria-label="Open settings"
                >
                  <Settings className="h-5 w-5" />
                  Settings
                </button>
              </div>
            )}
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0 flex-1">
                {/* Adapter Info - show first when available */}
                {currentConversation?.adapterInfo && (
                  <div className="mb-4">
                    <div className="flex flex-wrap items-center gap-2 mb-3">
                      {currentConversation.adapterInfo.model && (
                        <div className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-gray-100 px-2.5 py-1 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:border-[#4a4b54] dark:bg-[#343541] dark:text-[#bfc2cd]">
                          <span>Model</span>
                          <span className="text-gray-800 normal-case dark:text-[#ececf1]">
                            {currentConversation.adapterInfo.model}
                          </span>
                        </div>
                      )}
                      <div className="inline-flex items-center gap-2 rounded-md border border-gray-200 bg-gray-100 px-2.5 py-1 text-xs font-semibold uppercase tracking-wider text-gray-600 dark:border-[#4a4b54] dark:bg-[#343541] dark:text-[#bfc2cd]">
                        <span>Agent</span>
                        <span className="text-gray-800 normal-case dark:text-[#ececf1]">
                          {currentConversation.adapterInfo.client_name}
                        </span>
                      </div>
                      <button
                        onClick={handleRefreshAdapterInfo}
                        disabled={isRefreshingAdapterInfo || (!currentConversation?.apiKey && !currentConversation?.adapterName)}
                        className="inline-flex items-center gap-1 rounded-full border border-gray-200 px-2.5 py-1 text-xs font-semibold text-gray-600 transition-colors hover:bg-gray-200 hover:text-gray-900 dark:border-[#4a4b54] dark:text-[#bfc2cd] dark:hover:bg-[#4a4b54] dark:hover:text-white disabled:opacity-50 disabled:cursor-not-allowed"
                        title="Refresh adapter info"
                      >
                        <RefreshCw className={`h-4 w-4 ${isRefreshingAdapterInfo ? 'animate-spin' : ''}`} />
                        <span className="hidden sm:inline">Refresh</span>
                      </button>
                    </div>
                    {/* Title and metadata */}
                    <h1 className="text-2xl font-semibold text-[#353740] dark:text-[#ececf1] mb-2">
                      {currentConversation?.title || 'New Chat'}
                    </h1>
                    {currentConversation && (
                      <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-[#bfc2cd]">
                        <span className="font-medium">{currentConversation.messages.length}</span>
                        <span>Updated {currentConversation.updatedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
              <div className="flex w-full flex-wrap items-center gap-3 sm:w-auto sm:flex-nowrap sm:justify-end">
                <span className="text-sm text-gray-500 dark:text-[#bfc2cd] sm:text-right">
                  v{PACKAGE_VERSION}
                </span>
                {!isMiddlewareEnabled && (
                  <button
                    onClick={() => {
                      // Load current conversation's API settings if available, otherwise use defaults
                      // This allows users to see and modify their previously configured API key
                      // Always use runtime config defaults (from CLI args) when no conversation exists
                      // Read dynamically to ensure we get the latest runtime config
                      const runtimeApiUrl = getApiUrl();
                      const conversationApiUrl = currentConversation?.apiUrl;
                      const currentApiUrl = conversationApiUrl && conversationApiUrl !== runtimeApiUrl
                        ? conversationApiUrl
                        : runtimeApiUrl;
                      const currentApiKey = currentConversation?.apiKey || getDefaultKey();
                      setApiUrl(currentApiUrl);
                      setApiKey(currentApiKey);
                      setValidationError(null);
                      setShowApiKey(false);
                      setShowConfig(true);
                    }}
                    disabled={!canConfigureApi}
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:border-gray-300 dark:border-[#4a4b54] dark:text-[#ececf1] dark:hover:bg-[#3c3f4a] dark:hover:border-[#6b6f7a] dark:disabled:hover:bg-transparent dark:disabled:hover:border-[#4a4b54] sm:w-auto"
                    title={!canConfigureApi ? "API key cannot be changed once conversation has started. Create a new conversation to use a different API key." : "Configure API settings"}
                  >
                    Configure API
                  </button>
                )}
                {isMiddlewareEnabled && (
                  <div className="w-full sm:w-auto">
                    <AdapterSelector
                      selectedAdapter={selectedAdapter || currentConversation?.adapterName || null}
                      onAdapterChange={async (adapterName) => {
                        setSelectedAdapter(adapterName);
                        const apiUrl = currentConversation?.apiUrl || getApiUrl();
                        try {
                          await configureApiSettings(apiUrl, undefined, undefined, adapterName);
                          clearError();
                        } catch (error) {
                          debugError('Failed to configure adapter:', error);
                        }
                      }}
                      disabled={!canConfigureApi}
                    />
                  </div>
                )}
                <button
                  onClick={onOpenSettings}
                  className="hidden rounded-md bg-[#343541] p-2 text-white hover:bg-[#282b32] transition-colors dark:bg-[#565869] dark:hover:bg-[#6b6f7a] md:inline-flex"
                  title="Settings"
                >
                  <Settings className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>

          {/* Messages and Input - Conditional Layout */}
          {!currentConversation || currentConversation.messages.length === 0 ? (
            // Empty state: Flex layout that pushes input to bottom on mobile, left-aligned on desktop
            <div className="flex flex-1 flex-col min-h-0 pt-4 md:pt-6">
              <div className="flex-1 flex flex-col justify-between md:justify-start md:flex-none">
                <div className="w-full space-y-3">
                  <div className="mb-2">
                    {currentConversation?.adapterInfo?.notes ? (
                      // Show adapter notes as the main prompt with markdown rendering
                      <div className="text-base text-gray-600 dark:text-[#bfc2cd] leading-relaxed prose prose-sm dark:prose-invert prose-p:my-1 prose-ul:my-2 prose-ol:my-2 prose-li:my-0.5">
                        <MarkdownRenderer content={currentConversation.adapterInfo.notes} />
                      </div>
                    ) : (
                      // Fallback to default message
                      <h2 className="text-xl md:text-2xl font-medium text-[#353740] dark:text-[#ececf1]">
                        How can I assist you today?
                      </h2>
                    )}
                  </div>
                  <div className={MOBILE_INPUT_WRAPPER_CLASSES}>
                    <MessageInput
                      onSend={handleSendMessage}
                      disabled={isLoading || !currentConversation || (isMiddlewareEnabled ? !currentConversation.adapterName : !currentConversation.apiKey)}
                      placeholder="Message ORBIT..."
                    />
                  </div>
                </div>
              </div>
            </div>
          ) : (
            // Has messages: Normal layout with messages at top and input at bottom
            <div className="flex flex-1 flex-col">
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
                <MessageInput
                  onSend={handleSendMessage}
                  disabled={isLoading || !currentConversation || (isMiddlewareEnabled ? !currentConversation.adapterName : !currentConversation.apiKey)}
                  placeholder="Message ORBIT..."
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
