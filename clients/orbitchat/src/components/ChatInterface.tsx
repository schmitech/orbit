import { useEffect, useCallback, useLayoutEffect } from 'react';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { useChatStore } from '../stores/chatStore';
import { Settings, Menu, Plus } from 'lucide-react';
import { debugError, debugLog, debugWarn } from '../utils/debug';
import {
  getApplicationName,
  getApplicationDescription,
  getDefaultInputPlaceholder,
  getIsAuthConfigured,
  getEnableHeader,
  getAdapterDisplayName,
} from '../utils/runtimeConfig';
import { useSettings } from '../contexts/SettingsContext';
import { audioStreamManager } from '../utils/audioStreamManager';
import { MarkdownRenderer } from './markdown';
import { useTheme } from '../contexts/ThemeContext';
import { AgentSelectionList } from './AgentSelectionList';
import { AuthStatus } from './AuthStatus';
import { useIsAuthenticated } from '../hooks/useIsAuthenticated';
import { useChatAgentSelection } from '../hooks/useChatAgentSelection';
import { useAgentHomeNav } from '../hooks/useAgentHomeNav';

const MOBILE_FRAME_CLASSES =
  'rounded-t-[32px] border border-white/40 bg-transparent px-4 pb-4 pt-[max(env(safe-area-inset-top),1rem)] shadow-none backdrop-blur-0 dark:border-[#2f303d] dark:bg-transparent md:rounded-none md:border-0 md:bg-transparent md:px-0 md:pb-0 md:pt-3 md:shadow-none md:backdrop-blur-0 md:dark:bg-transparent md:dark:border-0';

const MOBILE_INPUT_WRAPPER_CLASSES =
  'shrink-0 sticky bottom-[calc(var(--app-footer-height,0px)+0.25rem)] z-10 -mx-4 mt-auto overflow-visible bg-transparent pb-[max(env(safe-area-inset-bottom),0.5rem)] shadow-none backdrop-blur-0 transition-all duration-200 dark:bg-transparent md:bottom-[calc(var(--app-footer-height,0px)+0.5rem)] md:z-10 md:mx-0 md:mt-0 md:overflow-visible md:rounded-none md:border-0 md:bg-transparent md:pb-0 md:shadow-none md:backdrop-blur-0 md:dark:bg-transparent md:dark:border-0 [&>div]:bg-transparent md:[&>div]:rounded-none md:[&>div]:px-0';

const MOBILE_HEADER_CLASSES =
  'relative z-20 shrink-0 -mx-4 px-4 pt-2 pb-2 bg-transparent border-b border-transparent dark:border-transparent dark:bg-transparent md:static md:mx-0 md:px-0 md:pt-6 md:pb-6 md:bg-transparent md:border-gray-200 md:dark:border-[#4a4b54] md:dark:bg-transparent';

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
  const introDescriptionMarkdownClass = [
    'application-description prose prose-slate dark:prose-invert max-w-none text-sm md:text-base leading-relaxed',
    'text-[#4a4c5a] dark:text-[#bfc2cd]',
    '[&>:first-child]:mt-0 [&>:last-child]:mb-0',
    forcedThemeClass
  ]
    .filter(Boolean)
    .join(' ');

  const currentConversation = conversations.find(c => c.id === currentConversationId);
  const showEmptyState = !currentConversation || currentConversation.messages.length === 0;
  const defaultInputPlaceholder = getDefaultInputPlaceholder();
  const applicationName = getApplicationName();
  const applicationDescription = getApplicationDescription().trim();
  const hasIntroDescription = applicationDescription.length > 0;

  const { registerGoHome } = useAgentHomeNav();

  const {
    adapterNotesError,
    handleAgentCardSelection,
    handleChangeAgent,
    goToAgentSelectionHome,
    hasAdapterConfigurationError,
    isAgentSelectionVisible,
    isConfiguringAdapter,
    shouldShowAgentSelectionList
  } = useChatAgentSelection({
    currentConversation,
    showEmptyState,
    createConversation,
    configureApiSettings,
    clearError,
    clearCurrentConversationAdapter
  });

  useLayoutEffect(() => {
    registerGoHome(() => goToAgentSelectionHome());
    return () => registerGoHome(null);
  }, [registerGoHome, goToAgentSelectionHome]);

  const chatMaxWidthClass = 'max-w-[96rem]';
  const inputMaxWidthClass = 'max-w-[64rem]';
  const emptyStateInputMaxWidthClass = 'max-w-[56rem]';
  const prominentWidthClass = `mx-auto w-full ${chatMaxWidthClass}`;
  const canStartNewConversation = canCreateNewConversation();
  const canChangeAgent = !!currentConversation?.adapterName && (currentConversation?.messages.length || 0) === 0;
  const newConversationTooltip = canStartNewConversation
    ? 'Start a new conversation'
    : isGuest
    ? 'Guest conversation limit reached. Sign in for more conversations.'
    : 'Finish your current conversation before starting a new one.';
  const showHeaderMetadata = !!(currentConversation && !shouldShowAgentSelectionList);
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
    : 'pt-4 md:pt-6';

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

  const handleClearThread = useCallback(async (messageId: string, threadId: string) => {
    if (!currentConversation) {
      return;
    }
    try {
      await useChatStore.getState().deleteThread(currentConversation.id, messageId, threadId);
    } catch (error) {
      debugError('Failed to clear thread:', error);
    }
  }, [currentConversation]);

  return (
    <main className="flex-1 flex flex-col bg-transparent overflow-hidden" aria-label="Chat workspace">
      <div className="flex h-full w-full flex-col overflow-hidden px-3 sm:px-5 lg:px-8">
        <div className={`mx-auto flex h-full w-full ${chatMaxWidthClass} flex-col overflow-hidden md:pb-4 ${MOBILE_FRAME_CLASSES}`}>

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

          <div className={effectiveHeaderClasses}>
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
              <div className="flex w-full flex-wrap items-center gap-2 my-2 md:my-0 sm:w-auto md:justify-end md:gap-3">
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
                      handleChangeAgent();
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

          {showEmptyState ? (
            <div className={`flex flex-1 flex-col min-h-0 ${emptyStateTopSpacingClass} ${shouldShowAgentSelectionList ? 'overflow-hidden' : ''}`}>
              {shouldShowAgentSelectionList ? (
                <div className="flex-1 flex flex-col md:justify-start min-h-0 overflow-hidden">
                  <div className="w-full flex flex-col min-h-0 overflow-hidden flex-1">
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
                  </div>
                </div>
              ) : (
                <div className="flex flex-1 w-full min-h-0 flex-col pt-[8vh] md:pt-[12vh]">
                  <div className={`mx-auto flex w-full ${emptyStateInputMaxWidthClass} flex-col items-center gap-6`}>
                    {adapterNotesError ? (
                      <p className="w-full text-center text-sm text-red-600 dark:text-red-400">
                        {adapterNotesError}
                      </p>
                    ) : isConfiguringAdapter ? (
                      <p className="w-full text-center text-sm text-gray-500 dark:text-[#bfc2cd]">
                        Configuring your agent…
                      </p>
                    ) : currentConversation?.adapterName ? (
                      <h2
                        className="w-full text-center text-xl font-semibold tracking-tight text-[#353740] dark:text-[#ececf1] md:text-2xl"
                        style={{ fontFamily: '-apple-system, "SF Pro Display", BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif' }}
                      >
                        {getAdapterDisplayName(currentConversation.adapterName) || currentConversation.adapterName}
                      </h2>
                    ) : null}
                    <div className="w-full min-w-0">
                      <MessageInput
                        onSend={handleSendMessage}
                        disabled={
                          isLoading ||
                          !currentConversation ||
                          !currentConversation?.adapterName ||
                          hasAdapterConfigurationError
                        }
                        autoFocusEnabled
                        placeholder={defaultInputPlaceholder}
                        isCentered
                        maxWidthClass={emptyStateInputMaxWidthClass}
                        adapterNotes={currentConversation?.adapterInfo?.notes}
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>
          ) : (
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
                onClearThread={handleClearThread}
                onSendThreadMessage={handleSendThreadMessage}
                sessionId={currentConversation.sessionId}
                isLoading={isLoading}
                contentMaxWidthClass={inputMaxWidthClass}
              />
              <div className={MOBILE_INPUT_WRAPPER_CLASSES}>
                <div className="mx-auto w-full max-w-[96rem] px-3 sm:px-5 md:px-6 lg:px-8 xl:px-10">
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
                    maxWidthClass={inputMaxWidthClass}
                    isCentered={false}
                    adapterNotes={currentConversation?.adapterInfo?.notes}
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
