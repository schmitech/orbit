import { useEffect, useCallback } from 'react';
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
} from '../utils/runtimeConfig';
import { useSettings } from '../contexts/SettingsContext';
import { audioStreamManager } from '../utils/audioStreamManager';
import { MarkdownRenderer } from './markdown';
import { useTheme } from '../contexts/ThemeContext';
import { AgentSelectionList } from './AgentSelectionList';
import { AuthStatus } from './AuthStatus';
import { useIsAuthenticated } from '../hooks/useIsAuthenticated';
import { useChatAgentSelection } from '../hooks/useChatAgentSelection';

const MOBILE_FRAME_CLASSES =
  'rounded-t-[32px] border border-white/40 bg-transparent px-4 pb-4 pt-[max(env(safe-area-inset-top),1rem)] shadow-none backdrop-blur-0 dark:border-[#2f303d] dark:bg-transparent md:rounded-none md:border-0 md:bg-transparent md:px-0 md:pb-0 md:pt-3 md:shadow-none md:backdrop-blur-0 md:dark:bg-transparent md:dark:border-0';

const MOBILE_INPUT_WRAPPER_CLASSES =
  'shrink-0 sticky bottom-[calc(var(--app-footer-height,0px)+0.25rem)] z-10 -mx-4 mt-auto overflow-visible bg-transparent pb-[max(env(safe-area-inset-bottom),0.5rem)] shadow-none backdrop-blur-0 transition-all duration-200 dark:bg-transparent md:bottom-[calc(var(--app-footer-height,0px)+0.5rem)] md:z-10 md:mx-0 md:mt-0 md:overflow-visible md:rounded-none md:border-0 md:bg-transparent md:pb-0 md:shadow-none md:backdrop-blur-0 md:dark:bg-transparent md:dark:border-0 [&>div]:bg-transparent md:[&>div]:rounded-none md:[&>div]:px-0';

const MOBILE_INPUT_WRAPPER_NON_STICKY_CLASSES =
  'shrink-0 mt-3 overflow-visible bg-transparent pb-[max(env(safe-area-inset-bottom),0.5rem)] shadow-none backdrop-blur-0 transition-all duration-200 dark:bg-transparent md:mx-0 md:mt-0 md:overflow-visible md:rounded-none md:border-0 md:bg-transparent md:pb-0 md:shadow-none md:backdrop-blur-0 md:dark:bg-transparent md:dark:border-0 [&>div]:bg-transparent md:[&>div]:rounded-none md:[&>div]:px-0';

const MOBILE_HEADER_CLASSES =
  'relative z-20 shrink-0 -mx-4 px-4 pt-2 pb-2 bg-white border-b border-slate-200 dark:border-[#3b3d49] dark:bg-[#1e1f29] md:static md:mx-0 md:px-0 md:pt-6 md:pb-6 md:bg-transparent md:border-gray-200 md:dark:border-[#4a4b54] md:dark:bg-transparent';

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

  const currentConversation = conversations.find(c => c.id === currentConversationId);
  const showEmptyState = !currentConversation || currentConversation.messages.length === 0;
  const defaultInputPlaceholder = getDefaultInputPlaceholder();
  const applicationName = getApplicationName();
  const applicationDescription = getApplicationDescription().trim();
  const hasIntroDescription = applicationDescription.length > 0;

  const {
    adapterNotesError,
    handleAgentCardSelection,
    handleChangeAgent,
    hasAdapterConfigurationError,
    isAgentSelectionVisible,
    isConfiguringAdapter,
    shouldShowAdapterNotesPanel,
    shouldShowAgentSelectionList
  } = useChatAgentSelection({
    currentConversation,
    showEmptyState,
    createConversation,
    configureApiSettings,
    clearError,
    clearCurrentConversationAdapter
  });

  const chatMaxWidthClass = 'max-w-[96rem]';
  const inputMaxWidthClass = 'max-w-[48rem]';
  const prominentWidthClass = `mx-auto w-full ${chatMaxWidthClass}`;
  const messageInputWidthClass = `mx-auto w-full ${inputMaxWidthClass}`;
  const emptyStateStageClass = shouldShowAdapterNotesPanel
    ? `relative isolate mx-auto w-full ${inputMaxWidthClass}`
    : prominentWidthClass;
  const emptyStateNotesPanelClass =
    'relative overflow-hidden rounded-[2rem] border border-slate-300/90 bg-[linear-gradient(180deg,rgba(255,255,255,0.94),rgba(248,250,252,0.9))] px-5 py-5 shadow-[0_12px_36px_rgba(15,23,42,0.05)] backdrop-blur-xl dark:border-white/6 dark:bg-[linear-gradient(180deg,rgba(35,36,44,0.92),rgba(26,27,35,0.9))] dark:shadow-[0_18px_48px_rgba(0,0,0,0.22)] md:px-7 md:py-6';
  const emptyStateNotesMarkdownClass = [
    adapterNotesMarkdownClass,
    'max-w-none text-[1.02rem] leading-8 text-[#434654] dark:text-[#d7dae3]',
    '[&_h1]:text-[2rem] [&_h1]:font-semibold [&_h1]:tracking-[-0.03em] [&_h1]:text-[#17191f] dark:[&_h1]:text-white',
    '[&_h2]:text-[1.35rem] [&_h2]:font-semibold [&_h2]:tracking-[-0.02em] [&_h2]:text-[#20232b] dark:[&_h2]:text-white',
    '[&_p]:max-w-[58ch] [&_ul]:max-w-[56ch] [&_ol]:max-w-[56ch] [&_li]:leading-8'
  ].join(' ');
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
              <div className={`flex-1 flex flex-col justify-between ${shouldShowAgentSelectionList ? 'md:justify-start min-h-0 overflow-hidden' : shouldShowAdapterNotesPanel ? 'md:justify-start md:pt-8 md:gap-6 overflow-y-auto' : 'md:justify-start md:flex-none'}`}>
                <div className={`w-full ${shouldShowAgentSelectionList ? 'flex flex-col min-h-0 overflow-hidden flex-1' : shouldShowAdapterNotesPanel ? 'flex flex-col' : 'space-y-6'}`}>
                  {showBodyHeading && !shouldShowAdapterNotesPanel && bodyHeadingText && (
                    <div className={prominentWidthClass}>
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
                    <div className={`${emptyStateStageClass} px-0 py-0`}>
                      <div className="pointer-events-none absolute inset-x-12 top-0 -z-10 h-32 rounded-full bg-[radial-gradient(circle_at_top,rgba(96,165,250,0.14),rgba(255,255,255,0))] blur-3xl dark:bg-[radial-gradient(circle_at_top,rgba(96,165,250,0.14),rgba(15,23,42,0))]" />
                      <div className="pointer-events-none absolute left-1/2 top-8 -z-10 h-44 w-full max-w-[36rem] -translate-x-1/2 rounded-full bg-[radial-gradient(circle,rgba(255,255,255,0.18),rgba(255,255,255,0))] blur-3xl dark:bg-[radial-gradient(circle,rgba(59,130,246,0.06),rgba(15,23,42,0))]" />

                      <div className={emptyStateNotesPanelClass}>
                        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.22),rgba(255,255,255,0))] dark:bg-[linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0))]" />
                        <div className="relative text-left">
                          {currentConversation?.adapterInfo?.notes ? (
                            <MarkdownRenderer
                              content={currentConversation.adapterInfo.notes}
                              className={emptyStateNotesMarkdownClass}
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
                    </div>
                  ) : (
                    <div className={`${prominentWidthClass} mb-2`}>
                      {currentConversation?.adapterInfo?.notes ? (
                        <div className="text-base text-gray-600 dark:text-[#bfc2cd] leading-relaxed">
                          <MarkdownRenderer
                            content={currentConversation.adapterInfo.notes}
                            className={adapterNotesMarkdownClass}
                            syntaxTheme={syntaxTheme}
                          />
                        </div>
                      ) : (
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
