import React, { FormEvent, MouseEvent, useEffect, useState } from 'react';
import { Search, MessageSquare, Trash2, Edit2, Trash, Paperclip, Settings, Eye, EyeOff } from 'lucide-react';
import { useChatStore } from '../stores/chatStore';
import { Conversation } from '../types';
import { ConfirmationModal } from './ConfirmationModal';
import { debugError } from '../utils/debug';
import { useGitHubStats } from '../hooks/useGitHubStats';
import { getShowGitHubStats, getGitHubOwner, getGitHubRepo, getApiUrl, getDefaultKey, getEnableApiMiddleware, getDefaultAdapterName } from '../utils/runtimeConfig';
import { useTheme } from '../contexts/ThemeContext';
import { AdapterSelector } from './AdapterSelector';
import { PACKAGE_VERSION } from '../utils/version';

interface SidebarProps {
  /**
   * Optional callback invoked after an action that should close the sidebar on mobile
   * (e.g. selecting a conversation or creating a new one).
   */
  onRequestClose?: () => void;
  onOpenSettings?: () => void;
}

const MAX_TITLE_LENGTH = 100;

const conversationSizeStyles: Record<
  'small' | 'medium' | 'large',
  {
    cardText: string;
    cardPadding: string;
    cardGap: string;
    titleText: string;
    metaText: string;
    metaGap: string;
    badgePadding: string;
    badgeText: string;
    badgeIcon: string;
    actionButton: string;
    actionIcon: string;
  }
> = {
  small: {
    cardText: 'text-xs',
    cardPadding: 'px-2.5 py-2',
    cardGap: 'gap-0',
    titleText: 'text-sm',
    metaText: 'text-[10px]',
    metaGap: 'gap-1',
    badgePadding: 'px-1.5 py-0.5',
    badgeText: 'text-[10px]',
    badgeIcon: 'h-3 w-3',
    actionButton: 'p-1.5',
    actionIcon: 'h-3.5 w-3.5'
  },
  medium: {
    cardText: 'text-sm',
    cardPadding: 'px-3 py-3',
    cardGap: 'gap-0',
    titleText: 'text-sm',
    metaText: 'text-[11px]',
    metaGap: 'gap-1.5',
    badgePadding: 'px-2 py-0.5',
    badgeText: 'text-[11px]',
    badgeIcon: 'h-3.5 w-3.5',
    actionButton: 'p-2',
    actionIcon: 'h-4 w-4'
  },
  large: {
    cardText: 'text-base',
    cardPadding: 'px-4 py-4',
    cardGap: 'gap-0',
    titleText: 'text-base',
    metaText: 'text-sm',
    metaGap: 'gap-2',
    badgePadding: 'px-2.5 py-1',
    badgeText: 'text-sm',
    badgeIcon: 'h-4 w-4',
    actionButton: 'p-2',
    actionIcon: 'h-4 w-4'
  }
};

export function Sidebar({ onRequestClose, onOpenSettings }: SidebarProps) {
  const {
    conversations,
    currentConversationId,
    selectConversation,
    deleteConversation,
    deleteAllConversations,
    updateConversationTitle,
    getConversationCount,
    configureApiSettings,
    clearError
  } = useChatStore();
  
  const currentConversation = conversations.find(conv => conv.id === currentConversationId);
  const [searchQuery, setSearchQuery] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [deleteConfirmation, setDeleteConfirmation] = useState<{
    isOpen: boolean;
    conversationId: string;
    conversationTitle: string;
    isDeleting: boolean;
  }>({
    isOpen: false,
    conversationId: '',
    conversationTitle: '',
    isDeleting: false
  });

  const [clearAllConfirmation, setClearAllConfirmation] = useState<{
    isOpen: boolean;
    isDeleting: boolean;
  }>({
    isOpen: false,
    isDeleting: false
  });
  const [showConfig, setShowConfig] = useState(false);
  const [apiUrl, setApiUrl] = useState(() => getApiUrl());
  const [apiKey, setApiKey] = useState(() => getDefaultKey());
  const [selectedAdapter, setSelectedAdapter] = useState<string | null>(null);
  const [showApiKey, setShowApiKey] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  const isMiddlewareEnabled = getEnableApiMiddleware();
  const defaultAdapterName = isMiddlewareEnabled ? getDefaultAdapterName() : null;
  const canConfigureApi = !currentConversation || currentConversation.messages.length === 0;
  const { theme } = useTheme();
  const sizeStyles = conversationSizeStyles[theme.fontSize ?? 'medium'];
  useEffect(() => {
    if (!isMiddlewareEnabled) {
      setSelectedAdapter(null);
      return;
    }
    if (currentConversation?.adapterName) {
      setSelectedAdapter(currentConversation.adapterName);
    } else {
      setSelectedAdapter(null);
    }
  }, [isMiddlewareEnabled, currentConversation?.adapterName]);
  useEffect(() => {
    setValidationError(null);
  }, [currentConversationId]);

  const filteredConversations = conversations.filter(conv =>
    conv.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    conv.messages.some(msg => 
      msg.content.toLowerCase().includes(searchQuery.toLowerCase())
    )
  );

  const totalConversations = getConversationCount();
  // GitHub stats for ORBIT project info
  const showGitHubStats = getShowGitHubStats();
  const githubStats = useGitHubStats(
    getGitHubOwner(),
    getGitHubRepo()
  );

  const handleOpenConfigureModal = () => {
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
  };

  const handleAdapterSelection = async (adapterName: string) => {
    if (!isMiddlewareEnabled || !canConfigureApi || !adapterName) {
      return;
    }

    setSelectedAdapter(adapterName);
    setValidationError(null);
    setIsValidating(true);
    try {
      const runtimeApiUrl = currentConversation?.apiUrl || getApiUrl();
      await configureApiSettings(runtimeApiUrl, undefined, undefined, adapterName);
      clearError();
      setShowConfig(false);
    } catch (error) {
      debugError('Failed to configure adapter:', error);
      const errorMessage = error instanceof Error ? error.message : 'Failed to configure adapter';
      setValidationError(errorMessage);
    } finally {
      setIsValidating(false);
    }
  };

  const handleConfigureApi = async (event?: FormEvent<HTMLFormElement> | MouseEvent<HTMLButtonElement>) => {
    if (event) {
      event.preventDefault();
    }

    if (!isMiddlewareEnabled && apiUrl && apiKey) {
      setIsValidating(true);
      setValidationError(null);
      try {
        await configureApiSettings(apiUrl, apiKey);
        clearError();
        setValidationError(null);
        setShowApiKey(false);
        setShowConfig(false);
      } catch (error) {
        debugError('Failed to configure API:', error);
        const errorMessage = error instanceof Error ? error.message : 'Failed to configure API settings';
        setValidationError(errorMessage);
      } finally {
        setIsValidating(false);
      }
    }
  };

  const handleSelectConversation = async (conversationId: string) => {
    try {
      await selectConversation(conversationId);
      onRequestClose?.();
    } catch (error) {
      debugError('Failed to select conversation:', error);
    }
  };

  const handleDeleteConversation = (e: React.MouseEvent, conversation: Conversation) => {
    e.stopPropagation();
    setDeleteConfirmation({
      isOpen: true,
      conversationId: conversation.id,
      conversationTitle: conversation.title,
      isDeleting: false
    });
  };

  const confirmDelete = async () => {
    setDeleteConfirmation(prev => ({ ...prev, isDeleting: true }));
    try {
      await deleteConversation(deleteConfirmation.conversationId);
      setDeleteConfirmation({
        isOpen: false,
        conversationId: '',
        conversationTitle: '',
        isDeleting: false
      });
    } catch (error) {
      debugError('Failed to delete conversation:', error);
      // Still close the modal even if there was an error
      setDeleteConfirmation({
        isOpen: false,
        conversationId: '',
        conversationTitle: '',
        isDeleting: false
      });
    }
  };

  const cancelDelete = () => {
    setDeleteConfirmation({
      isOpen: false,
      conversationId: '',
      conversationTitle: '',
      isDeleting: false
    });
  };

  const handleEditStart = (e: React.MouseEvent, conversation: Conversation) => {
    e.stopPropagation();
    setEditingId(conversation.id);
    setEditTitle(conversation.title.slice(0, MAX_TITLE_LENGTH));
  };

  const handleEditSubmit = (id: string) => {
    const sanitized = editTitle.slice(0, MAX_TITLE_LENGTH).trim();
    if (sanitized) {
      updateConversationTitle(id, sanitized);
    }
    setEditingId(null);
    setEditTitle('');
  };

  const handleEditCancel = () => {
    setEditingId(null);
    setEditTitle('');
  };

  const handleClearAll = () => {
    setClearAllConfirmation({
      isOpen: true,
      isDeleting: false
    });
  };

  const confirmClearAll = async () => {
    setClearAllConfirmation(prev => ({ ...prev, isDeleting: true }));
    try {
      await deleteAllConversations();
      setClearAllConfirmation({
        isOpen: false,
        isDeleting: false
      });
    } catch (error) {
      debugError('Failed to clear all conversations:', error);
      setClearAllConfirmation({
        isOpen: false,
        isDeleting: false
      });
    }
  };

  const cancelClearAll = () => {
    setClearAllConfirmation({
      isOpen: false,
      isDeleting: false
    });
  };

  const formatConversationTimestamp = (date: Date) => {
    const formattedDate = date.toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' });
    const formattedTime = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return `${formattedDate} · ${formattedTime}`;
  };

  const getConversationAgentLabel = (conversation: Conversation): string | null => {
    if (conversation.adapterName && conversation.adapterName.trim().length > 0) {
      return conversation.adapterName;
    }
    if (conversation.adapterInfo?.adapter_name && conversation.adapterInfo.adapter_name.trim().length > 0) {
      return conversation.adapterInfo.adapter_name;
    }
    return null;
  };

  return (
    <>
      {/* API Configuration Modal */}
      {showConfig && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
          <form
            onSubmit={handleConfigureApi}
            className="w-full max-w-md rounded-lg border border-gray-200 bg-white p-6 shadow-lg dark:border-[#444654] dark:bg-[#202123]"
          >
            <h2 className="mb-4 text-lg font-medium text-[#353740] dark:text-[#ececf1]">
              {isMiddlewareEnabled ? 'Select an Agent' : 'Configure API Settings'}
            </h2>
            <div className="space-y-5">
              {!isMiddlewareEnabled && (
                <div>
                  <label className="mb-2 block text-sm font-medium text-[#353740] dark:text-[#d1d5db]">
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
                  selectedAdapter={selectedAdapter || currentConversation?.adapterName || null}
                  onAdapterChange={handleAdapterSelection}
                  disabled={isValidating}
                  defaultAdapterName={defaultAdapterName}
                  variant="prominent"
                  showDescriptions
                  showLabel={false}
                />
              ) : (
                <div>
                  <label className="mb-2 block text-sm font-medium text-[#353740] dark:text-[#d1d5db]">
                    API Key
                  </label>
                  <div className="relative">
                    <input
                      type={showApiKey ? 'text' : 'password'}
                      value={apiKey}
                      onChange={(e) => {
                        setApiKey(e.target.value);
                        setValidationError(null);
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
                    const currentApiUrl = currentConversation?.apiUrl || getApiUrl();
                    const currentApiKey = currentConversation?.apiKey || getDefaultKey();
                    setApiUrl(currentApiUrl);
                    setApiKey(currentApiKey);
                    setValidationError(null);
                    setShowApiKey(false);
                    setShowConfig(false);
                  }}
                  className="rounded-md border border-transparent px-4 py-2 text-sm text-gray-600 hover:border-gray-300 hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-50 dark:text-[#d1d5db] dark:hover:text-white"
                    disabled={isValidating}
                  >
                    Cancel
                  </button>
                {!isMiddlewareEnabled && (
                  <button
                    type="submit"
                    disabled={isValidating || (!apiUrl || !apiKey)}
                    className="rounded-md bg-[#343541] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#282b32] disabled:cursor-not-allowed disabled:opacity-50 dark:bg-[#565869] dark:hover:bg-[#6b6f7a]"
                  >
                    {isValidating ? 'Validating...' : 'Update'}
                  </button>
                )}
              </div>
            </div>
          </form>
        </div>
      )}

      <div className="flex h-full w-full md:w-72 flex-col border-r border-b border-gray-200 bg-gradient-to-b from-white via-gray-50 to-gray-100 dark:border-[#4a4b54] dark:bg-[#202123] dark:bg-none">
        <div className="border-b border-gray-200 bg-white/95 p-4 shadow-sm dark:border-[#4a4b54] dark:bg-[#202123] dark:shadow-none">
          <div className="space-y-3 border-b border-gray-200 pb-3 dark:border-[#4a4b54]">
            <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-[#bfc2cd]">
              <span>Version</span>
              <span className="text-gray-900 dark:text-white">v{PACKAGE_VERSION}</span>
            </div>
            <button
              onClick={onOpenSettings}
              disabled={!onOpenSettings}
              className="flex w-full items-center justify-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 hover:border-gray-400 disabled:cursor-not-allowed disabled:opacity-50 dark:border-[#4a4b54] dark:text-[#ececf1] dark:hover:bg-[#3c3f4a] dark:hover:border-[#6b6f7a] dark:disabled:hover:bg-transparent dark:disabled:hover:border-[#4a4b54]"
            >
              <Settings className="h-4 w-4" />
              Settings
            </button>
            {conversations.length > 0 && conversations.some(conv => conv.messages.length > 0) && (
              <button
                onClick={handleClearAll}
                className="flex w-full items-center justify-center gap-2 rounded-md border border-red-300 px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50 hover:border-red-400 dark:border-red-600/40 dark:text-red-400 dark:hover:bg-red-900/20 dark:hover:border-red-500/60 transition-colors"
                title="Delete all conversations"
              >
                <Trash className="h-4 w-4" />
                Clear All
              </button>
            )}
          </div>
          <div className="mt-4 space-y-3">
            {!isMiddlewareEnabled && (
              <button
                onClick={handleOpenConfigureModal}
                disabled={!canConfigureApi}
                className="flex w-full items-center justify-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 hover:border-gray-400 disabled:cursor-not-allowed disabled:opacity-50 dark:border-[#4a4b54] dark:text-[#ececf1] dark:hover:bg-[#3c3f4a] dark:hover:border-[#6b6f7a] dark:disabled:hover:bg-transparent dark:disabled:hover:border-[#4a4b54]"
              >
                Configure API
              </button>
            )}
            {validationError && !showConfig && (
              <p className="text-xs text-red-600 dark:text-red-400">{validationError}</p>
            )}
          </div>
        </div>

        <div className="border-b border-gray-200 bg-white/90 px-4 py-3 shadow-sm dark:border-[#4a4b54] dark:bg-[#202123] dark:bg-none dark:shadow-none">
          <div className="relative flex items-center">
            <Search className="pointer-events-none absolute left-3 h-4 w-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search conversations"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-md border border-gray-300 bg-white py-2 pl-9 pr-3 text-sm text-[#353740] placeholder-gray-400 shadow-inner focus:border-gray-400 focus:outline-none dark:border-[#4a4b54] dark:bg-[#343541] dark:text-[#ececf1] dark:shadow-none"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-3 dark:bg-[#202123] dark:bg-none">
          {filteredConversations.length === 0 ? (
            <div className="rounded-xl border border-dashed border-gray-300 bg-white/90 p-6 text-center text-sm text-gray-500 shadow-sm dark:border-[#4a4b54] dark:bg-[#252830] dark:text-[#bfc2cd] dark:shadow-none">
              <MessageSquare className="mx-auto mb-3 h-6 w-6 text-gray-400 dark:text-[#6b6f7a]" />
              <p>
                {searchQuery ? 'No conversations found' : 'No conversations yet'}
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {filteredConversations.map((conversation) => {
                const agentLabel = getConversationAgentLabel(conversation);
                return (
                  <div
                    key={conversation.id}
                    onClick={() => handleSelectConversation(conversation.id)}
                    className={`group flex cursor-pointer items-start rounded-xl border text-left transition shadow-sm ${sizeStyles.cardGap} ${sizeStyles.cardPadding} ${sizeStyles.cardText} dark:shadow-none ${
                      currentConversationId === conversation.id
                        ? 'border-[#343541] bg-white dark:border-[#6b6f7a] dark:bg-[#2c2f36]'
                        : 'border-gray-100 bg-white hover:border-gray-300 hover:bg-gray-50 dark:border-transparent dark:bg-[#252830] dark:hover:border-[#4a4b54] dark:hover:bg-[#2f323c]'
                    }`}
                  >
                    {editingId === conversation.id ? (
                      <input
                        type="text"
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value.slice(0, MAX_TITLE_LENGTH))}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleEditSubmit(conversation.id);
                          if (e.key === 'Escape') handleEditCancel();
                        }}
                        onBlur={() => handleEditSubmit(conversation.id)}
                        maxLength={MAX_TITLE_LENGTH}
                        className={`flex-1 border-none bg-transparent text-[#353740] focus:outline-none dark:text-[#ececf1] ${sizeStyles.titleText}`}
                        autoFocus
                      />
                    ) : (
                      <div className="flex-1 min-w-0 space-y-2">
                        <div className={`flex items-center gap-2 ${sizeStyles.cardText}`}>
                          <h3
                            className={`flex-1 truncate font-semibold ${sizeStyles.titleText} ${
                              currentConversationId === conversation.id ? 'text-[#1f2937] dark:text-white' : 'text-gray-700 dark:text-[#d4d7e2]'
                            }`}
                          >
                            {conversation.title}
                          </h3>
                          <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                            <button
                              onClick={(e) => handleEditStart(e, conversation)}
                              className={`rounded-full text-gray-500 hover:bg-gray-200 hover:text-[#353740] dark:text-[#bfc2cd] dark:hover:bg-[#3c3f4a] ${sizeStyles.actionButton}`}
                              title="Rename conversation"
                            >
                              <Edit2 className={sizeStyles.actionIcon} />
                            </button>
                            <button
                              onClick={(e) => handleDeleteConversation(e, conversation)}
                              className={`rounded-full text-red-500 hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-900/30 ${sizeStyles.actionButton}`}
                              title="Delete conversation"
                            >
                              <Trash2 className={sizeStyles.actionIcon} />
                            </button>
                          </div>
                        </div>
                        <div className={`mt-1 flex items-center overflow-hidden pr-1 text-gray-500 dark:text-[#a6acc5] ${sizeStyles.metaGap} ${sizeStyles.metaText}`}>
                          <span className="min-w-0 flex-1 truncate leading-none">
                            {formatConversationTimestamp(conversation.updatedAt)}
                          </span>
                          <span className={`inline-flex shrink-0 items-center gap-1 rounded-full bg-white/80 font-medium text-gray-600 shadow-sm dark:bg-white/10 dark:text-[#e5e7f4] leading-none ${sizeStyles.badgePadding} ${sizeStyles.badgeText}`}>
                            <MessageSquare className={sizeStyles.badgeIcon} />
                            {conversation.messages.length}
                          </span>
                          {conversation.attachedFiles && conversation.attachedFiles.length > 0 && (
                            <span className={`inline-flex shrink-0 items-center gap-1 rounded-full bg-white/80 font-medium text-gray-600 shadow-sm dark:bg-white/10 dark:text-[#e5e7f4] leading-none ${sizeStyles.badgePadding} ${sizeStyles.badgeText}`}>
                              <Paperclip className={sizeStyles.badgeIcon} />
                              {conversation.attachedFiles.length}
                            </span>
                          )}
                        </div>
                        {agentLabel && (
                          <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-gray-500 dark:text-[#a6acc5]">
                            <span className="inline-flex items-center rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-semibold text-blue-700 dark:bg-blue-900/30 dark:text-blue-200">
                              Agent
                            </span>
                            <span className="min-w-0 flex-1 truncate text-gray-600 dark:text-[#d4d7e2]">
                              {agentLabel}
                            </span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* ORBIT Project Information */}
        {showGitHubStats && (
          <div className="border-t border-gray-200 p-4 dark:border-[#4a4b54]">
            <div className="text-center">
              <div className="flex items-center justify-center mb-3">
                <span className="text-sm font-medium text-gray-900 dark:text-[#ececf1]">Powered by ORBIT</span>
              </div>
              
              {githubStats.isLoading ? (
                <div className="flex items-center justify-center gap-2 text-xs text-gray-500 dark:text-[#bfc2cd] mb-3">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-400"></div>
                  <span>Loading stats...</span>
                </div>
              ) : githubStats.error ? (
                <div className="flex items-center justify-center gap-2 text-xs text-red-500 dark:text-red-400 mb-3">
                  <span>⚠️ Failed to load stats</span>
                </div>
              ) : (
                <div className="flex items-center justify-center gap-4 text-xs text-gray-500 dark:text-[#bfc2cd] mb-3">
                  <div className="flex items-center gap-1">
                    <svg className="w-4 h-4 text-yellow-500" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/>
                    </svg>
                    <span>{githubStats.stars.toLocaleString()} stars</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 16 16">
                      <path d="M5 3.25a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm0 2.122a2.25 2.25 0 10-1.5 0v.878A2.25 2.25 0 005.75 8.5h1.5v2.128a2.251 2.251 0 101.5 0V8.5h1.5a2.25 2.25 0 002.25-2.25v-.878a2.25 2.25 0 10-1.5 0v.878a.75.75 0 01-.75.75H4.5A.75.75 0 013 6.25v-.878zm3.75 7.378a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm3-8.75a.75.75 0 100-1.5.75.75 0 000 1.5z"/>
                    </svg>
                    <span>{githubStats.forks.toLocaleString()} forks</span>
                  </div>
                </div>
              )}
              
              <a 
                href={`https://github.com/${getGitHubOwner()}/${getGitHubRepo()}`}
                target="_blank" 
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 transition-colors"
              >
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
                </svg>
                View on GitHub
              </a>
            </div>
          </div>
        )}
      </div>

      {/* Delete Confirmation Modal */}
      <ConfirmationModal
        isOpen={deleteConfirmation.isOpen}
        onClose={cancelDelete}
        onConfirm={confirmDelete}
        title="Delete Conversation"
        message={`Are you sure you want to delete "${deleteConfirmation.conversationTitle}"? This will clear the conversation history.`}
        confirmText="Delete"
        cancelText="Cancel"
        type="danger"
        isLoading={deleteConfirmation.isDeleting}
      />

      {/* Clear All Conversations Confirmation Modal */}
      <ConfirmationModal
        isOpen={clearAllConfirmation.isOpen}
        onClose={cancelClearAll}
        onConfirm={confirmClearAll}
        title="Clear All Conversations"
        message={`Are you sure you want to delete all ${totalConversations} conversation${totalConversations !== 1 ? 's' : ''}? This will clear all conversation history.`}
        confirmText="Clear All"
        cancelText="Cancel"
        type="danger"
        isLoading={clearAllConfirmation.isDeleting}
      />
    </>
  );
}
