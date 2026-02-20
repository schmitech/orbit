import React, { useEffect, useRef, useState } from 'react';
import { Search, MessageSquare, Trash2, Edit2, Trash, Paperclip, Settings } from 'lucide-react';
import { useChatStore } from '../stores/chatStore';
import { Conversation } from '../types';
import { ConfirmationModal } from './ConfirmationModal';
import { debugError } from '../utils/debug';
import { getApiUrl } from '../utils/runtimeConfig';
import { AdapterSelector } from './AdapterSelector';
import { useFocusTrap } from '../hooks/useFocusTrap';
import { GitHubStatsBanner } from './GitHubStatsBanner';

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
  const [selectedAdapter, setSelectedAdapter] = useState<string | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const configDialogRef = useRef<HTMLDivElement>(null);

  const canConfigureApi = !currentConversation || currentConversation.messages.length === 0;
  const sizeStyles = conversationSizeStyles.medium;
  useEffect(() => {
    if (currentConversation?.adapterName) {
      setSelectedAdapter(currentConversation.adapterName);
    } else {
      setSelectedAdapter(null);
    }
  }, [currentConversation?.adapterName]);
  useEffect(() => {
    setValidationError(null);
  }, [currentConversationId]);

  const conversationsWithHistory = conversations.filter(conv => conv.messages.length > 0 && !conv.adapterLoadError);
  const filteredConversations = conversationsWithHistory.filter(conv =>
    conv.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    conv.messages.some(msg => 
      msg.content.toLowerCase().includes(searchQuery.toLowerCase())
    )
  );
  const visibleConversations = conversationsWithHistory.length > 0 ? filteredConversations : [];
  const totalConversations = getConversationCount();
  const conversationLabel = totalConversations === 1 ? 'conversation' : 'conversations';

  const handleAdapterSelection = async (adapterName: string) => {
    if (!canConfigureApi || !adapterName) {
      return;
    }

    setSelectedAdapter(adapterName);
    setValidationError(null);
    setIsValidating(true);
    try {
      const runtimeApiUrl = currentConversation?.apiUrl || getApiUrl();
      await configureApiSettings(runtimeApiUrl, undefined, adapterName);
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

  useFocusTrap(configDialogRef, { enabled: showConfig, onEscape: () => setShowConfig(false) });

  return (
    <>
      {/* API Configuration Modal */}
      {showConfig && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
          <div
            ref={configDialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="select-agent-title"
            tabIndex={-1}
            className="w-full max-w-md rounded-lg border border-gray-200 bg-white p-6 shadow-lg dark:border-[#444654] dark:bg-[#202123]"
          >
            <h2 id="select-agent-title" className="mb-4 text-lg font-medium text-[#353740] dark:text-[#ececf1]">
              Select an Agent
            </h2>
            <div className="space-y-5">
              <AdapterSelector
                selectedAdapter={selectedAdapter || currentConversation?.adapterName || null}
                onAdapterChange={handleAdapterSelection}
                disabled={isValidating}
                variant="prominent"
                showDescriptions
                showLabel={false}
              />
              {validationError && (
                <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-600/40 dark:bg-red-900/30 dark:text-red-200">
                  {validationError}
                </div>
              )}
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setValidationError(null);
                    setShowConfig(false);
                  }}
                  className="rounded-md border border-transparent px-4 py-2 text-sm text-gray-600 hover:border-gray-300 hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-50 dark:text-[#d1d5db] dark:hover:text-white"
                    disabled={isValidating}
                  >
                    Cancel
                  </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="flex h-full md:h-[calc(100%-2rem)] md:mt-4 w-full md:w-72 flex-col border-r border-b border-gray-200 md:border-l md:border-t md:rounded-2xl md:overflow-hidden bg-transparent dark:border-[#595a66]">
        <div className="bg-transparent px-4 pb-4 pt-4 shadow-none dark:border-[#4a4b54]">
          <div className="flex w-full justify-center">
            <GitHubStatsBanner className="w-full max-w-[220px] items-center text-center" />
          </div>
          <div className="mt-8 space-y-3 pb-3">
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
                Delete Conversations
              </button>
            )}
          </div>
          <div className="mt-4 space-y-3">
            {validationError && !showConfig && (
              <p className="text-xs text-red-600 dark:text-red-400">{validationError}</p>
            )}
          </div>
          <div className="border-t border-gray-200 pt-4 mt-4 dark:border-[#4a4b54]">
            <div className="relative flex items-center">
              <Search className="pointer-events-none absolute left-3 h-4 w-4 text-gray-400" />
              <input
                type="text"
                aria-label="Search conversations"
                placeholder="Search Conversations"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full rounded-md border border-gray-300 bg-white py-2 pl-9 pr-3 text-sm text-[#353740] placeholder-gray-400 shadow-inner focus:border-gray-400 focus:outline-none dark:border-[#4a4b54] dark:bg-[#343541] dark:text-[#ececf1] dark:shadow-none"
              />
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto bg-transparent px-3 py-3">
          {visibleConversations.length === 0 ? (
            <div className="rounded-xl border border-dashed border-gray-300 bg-white/90 p-6 text-center text-sm text-gray-500 shadow-sm dark:border-[#4a4b54] dark:bg-[#252830] dark:text-[#bfc2cd] dark:shadow-none">
              <MessageSquare className="mx-auto mb-3 h-6 w-6 text-gray-400 dark:text-[#6b6f7a]" />
              <p>
                {searchQuery ? 'No conversations found' : 'No conversations yet'}
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {visibleConversations.map((conversation) => {
                const agentLabel = getConversationAgentLabel(conversation);
                return (
                  <div
                    key={conversation.id}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        handleSelectConversation(conversation.id);
                      }
                    }}
                    onClick={() => handleSelectConversation(conversation.id)}
                    className={`group flex w-full cursor-pointer items-start rounded-xl border text-left transition shadow-sm ${sizeStyles.cardGap} ${sizeStyles.cardPadding} ${sizeStyles.cardText} dark:shadow-none ${
                      currentConversationId === conversation.id
                        ? 'border-[#343541] bg-white dark:border-[#6b6f7a] dark:bg-[#2c2f36]'
                        : 'border-gray-100 bg-white hover:border-gray-300 hover:bg-gray-50 dark:border-transparent dark:bg-[#252830] dark:hover:border-[#4a4b54] dark:hover:bg-[#2f323c]'
                    } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/70 dark:focus-visible:ring-blue-400/70`}
                    aria-current={currentConversationId === conversation.id ? 'true' : undefined}
                    aria-label={`Open conversation: ${conversation.title}`}
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
                          <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
                            <button
                              onClick={(e) => handleEditStart(e, conversation)}
                              className={`rounded-full text-gray-500 hover:bg-gray-200 hover:text-[#353740] dark:text-[#bfc2cd] dark:hover:bg-[#3c3f4a] ${sizeStyles.actionButton}`}
                              title="Rename conversation"
                              aria-label={`Rename conversation: ${conversation.title}`}
                            >
                              <Edit2 className={sizeStyles.actionIcon} />
                            </button>
                            <button
                              onClick={(e) => handleDeleteConversation(e, conversation)}
                              className={`rounded-full text-red-500 hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-900/30 ${sizeStyles.actionButton}`}
                              title="Delete conversation"
                              aria-label={`Delete conversation: ${conversation.title}`}
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
        message={`Are you sure you want to delete all ${totalConversations} ${conversationLabel}? This will clear all conversation history.`}
        confirmText="Clear All"
        cancelText="Cancel"
        type="danger"
        isLoading={clearAllConfirmation.isDeleting}
      />
    </>
  );
}
