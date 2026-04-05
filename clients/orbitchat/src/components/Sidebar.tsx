import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Search, X, MessageSquare, Trash2, Edit2, Trash, Paperclip, Settings } from 'lucide-react';
import { useChatStore } from '../stores/chatStore';
import { Conversation } from '../types';
import { ConfirmationModal } from './ConfirmationModal';
import { debugError } from '../utils/debug';
import { getApiUrl, getHeaderNavLinks, getIsSingleAdapterMode } from '../utils/runtimeConfig';
import { AdapterSelector } from './AdapterSelector';
import { useFocusTrap } from '../hooks/useFocusTrap';
import { GitHubStatsBanner } from './GitHubStatsBanner';
import { AppFooter } from './AppFooter';

interface SidebarProps {
  onRequestClose?: () => void;
  onOpenSettings?: () => void;
}

const MAX_TITLE_LENGTH = 100;

// ---------------------------------------------------------------------------
// Time-group helpers
// ---------------------------------------------------------------------------

interface TimeGroup {
  label: string;
  conversations: Conversation[];
}

function getTimeGroupLabel(date: Date, now: Date): string {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(startOfToday);
  startOfYesterday.setDate(startOfYesterday.getDate() - 1);
  const startOfWeek = new Date(startOfToday);
  startOfWeek.setDate(startOfWeek.getDate() - startOfToday.getDay());
  const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);

  if (date >= startOfToday) return 'Today';
  if (date >= startOfYesterday) return 'Yesterday';
  if (date >= startOfWeek) return 'This Week';
  if (date >= startOfMonth) return 'This Month';
  return 'Earlier';
}

function groupConversationsByTime(conversations: Conversation[]): TimeGroup[] {
  const now = new Date();
  const order = ['Today', 'Yesterday', 'This Week', 'This Month', 'Earlier'];
  const map = new Map<string, Conversation[]>();

  for (const conv of conversations) {
    const label = getTimeGroupLabel(conv.updatedAt, now);
    const arr = map.get(label);
    if (arr) {
      arr.push(conv);
    } else {
      map.set(label, [conv]);
    }
  }

  return order.filter((l) => map.has(l)).map((label) => ({ label, conversations: map.get(label)! }));
}

// ---------------------------------------------------------------------------
// Sidebar Component
// ---------------------------------------------------------------------------

export function Sidebar({ onRequestClose, onOpenSettings }: SidebarProps) {
  const isSingleAdapterMode = getIsSingleAdapterMode();
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

  const currentConversation = conversations.find((conv) => conv.id === currentConversationId);
  const [searchQuery, setSearchQuery] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [deleteConfirmation, setDeleteConfirmation] = useState<{
    isOpen: boolean;
    conversationId: string;
    conversationTitle: string;
    isDeleting: boolean;
  }>({ isOpen: false, conversationId: '', conversationTitle: '', isDeleting: false });

  const [clearAllConfirmation, setClearAllConfirmation] = useState<{
    isOpen: boolean;
    isDeleting: boolean;
  }>({ isOpen: false, isDeleting: false });

  const [showConfig, setShowConfig] = useState(false);
  const [selectedAdapter, setSelectedAdapter] = useState<string | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const configDialogRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const canConfigureApi = !currentConversation || currentConversation.messages.length === 0;

  useEffect(() => {
    setSelectedAdapter(currentConversation?.adapterName ?? null);
  }, [currentConversation?.adapterName]);

  useEffect(() => {
    setValidationError(null);
  }, [currentConversationId]);

  // -----------------------------------------------------------------------
  // Conversation filtering & grouping
  // -----------------------------------------------------------------------

  const conversationsWithHistory = useMemo(
    () =>
      conversations.filter(
        (conv) => (conv.messages.length > 0 || (conv.attachedFiles?.length || 0) > 0) && !conv.adapterLoadError
      ),
    [conversations]
  );

  const filteredConversations = useMemo(() => {
    if (!searchQuery) return conversationsWithHistory;
    const q = searchQuery.toLowerCase();
    return conversationsWithHistory.filter(
      (conv) =>
        conv.title.toLowerCase().includes(q) ||
        conv.messages.some((msg) => msg.content.toLowerCase().includes(q)) ||
        (conv.attachedFiles || []).some((file) => file.filename.toLowerCase().includes(q))
    );
  }, [conversationsWithHistory, searchQuery]);

  const timeGroups = useMemo(() => groupConversationsByTime(filteredConversations), [filteredConversations]);

  const totalConversations = getConversationCount();
  const conversationLabel = totalConversations === 1 ? 'conversation' : 'conversations';
  const isSearching = searchQuery.length > 0;

  // -----------------------------------------------------------------------
  // Scroll to active conversation on mount
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (!currentConversationId || !listRef.current) return;
    const active = listRef.current.querySelector('[aria-current="true"]');
    if (active) {
      active.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }, [currentConversationId]);

  // -----------------------------------------------------------------------
  // Keyboard navigation (arrow keys through conversation list)
  // -----------------------------------------------------------------------

  const handleListKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
      e.preventDefault();
      const items = listRef.current?.querySelectorAll<HTMLElement>('[role="option"]');
      if (!items || items.length === 0) return;

      const focused = document.activeElement as HTMLElement;
      const idx = Array.from(items).indexOf(focused);
      let next: number;
      if (e.key === 'ArrowDown') {
        next = idx < items.length - 1 ? idx + 1 : 0;
      } else {
        next = idx > 0 ? idx - 1 : items.length - 1;
      }
      items[next].focus();
    },
    []
  );

  // -----------------------------------------------------------------------
  // Handlers
  // -----------------------------------------------------------------------

  const handleAdapterSelection = async (adapterName: string) => {
    if (!canConfigureApi || !adapterName) return;
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
      setValidationError(error instanceof Error ? error.message : 'Failed to configure adapter');
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
    setDeleteConfirmation({ isOpen: true, conversationId: conversation.id, conversationTitle: conversation.title, isDeleting: false });
  };

  const confirmDelete = async () => {
    setDeleteConfirmation((prev) => ({ ...prev, isDeleting: true }));
    try {
      await deleteConversation(deleteConfirmation.conversationId);
    } catch (error) {
      debugError('Failed to delete conversation:', error);
    }
    setDeleteConfirmation({ isOpen: false, conversationId: '', conversationTitle: '', isDeleting: false });
  };

  const cancelDelete = () => {
    setDeleteConfirmation({ isOpen: false, conversationId: '', conversationTitle: '', isDeleting: false });
  };

  const handleEditStart = (e: React.MouseEvent, conversation: Conversation) => {
    e.stopPropagation();
    setEditingId(conversation.id);
    setEditTitle(conversation.title.slice(0, MAX_TITLE_LENGTH));
  };

  const handleEditSubmit = (id: string) => {
    const sanitized = editTitle.slice(0, MAX_TITLE_LENGTH).trim();
    if (sanitized) updateConversationTitle(id, sanitized);
    setEditingId(null);
    setEditTitle('');
  };

  const handleEditCancel = () => {
    setEditingId(null);
    setEditTitle('');
  };

  const handleClearAll = () => {
    setClearAllConfirmation({ isOpen: true, isDeleting: false });
  };

  const confirmClearAll = async () => {
    setClearAllConfirmation((prev) => ({ ...prev, isDeleting: true }));
    try {
      await deleteAllConversations();
    } catch (error) {
      debugError('Failed to clear all conversations:', error);
    }
    setClearAllConfirmation({ isOpen: false, isDeleting: false });
  };

  const cancelClearAll = () => {
    setClearAllConfirmation({ isOpen: false, isDeleting: false });
  };

  // -----------------------------------------------------------------------
  // Formatting helpers
  // -----------------------------------------------------------------------

  const formatConversationTimestamp = (date: Date) => {
    const formattedDate = date.toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' });
    const formattedTime = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return `${formattedDate} \u00B7 ${formattedTime}`;
  };

  const getConversationAgentLabel = (conversation: Conversation): string | null => {
    if (conversation.adapterName?.trim()) return conversation.adapterName;
    if (conversation.adapterInfo?.adapter_name?.trim()) return conversation.adapterInfo.adapter_name;
    return null;
  };

  useFocusTrap(configDialogRef, { enabled: showConfig, onEscape: () => setShowConfig(false) });

  // -----------------------------------------------------------------------
  // Render: Conversation card
  // -----------------------------------------------------------------------

  const renderConversationCard = (conversation: Conversation) => {
    const isActive = currentConversationId === conversation.id;
    const agentLabel = getConversationAgentLabel(conversation);

    return (
      <div
        key={conversation.id}
        role="option"
        aria-selected={isActive}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            handleSelectConversation(conversation.id);
          }
        }}
        onClick={() => handleSelectConversation(conversation.id)}
        className={`group flex w-full cursor-pointer items-start rounded-xl border text-left transition-all duration-150 px-3 py-3 text-sm
          ${
            isActive
              ? 'border-sky-200 bg-sky-50/60 shadow-sm dark:border-sky-500/30 dark:bg-sky-950/25'
              : 'border-transparent bg-white hover:border-gray-200 hover:bg-gray-50/80 hover:shadow-sm dark:bg-[#252830] dark:hover:border-[#3d4050] dark:hover:bg-[#2c2f3a]'
          } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60 dark:focus-visible:ring-sky-400/50`}
        aria-current={isActive ? 'true' : undefined}
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
              e.stopPropagation();
            }}
            onBlur={() => handleEditSubmit(conversation.id)}
            maxLength={MAX_TITLE_LENGTH}
            className="flex-1 rounded-md border border-sky-300 bg-white px-2 py-1 text-sm text-[#353740] focus:outline-none focus:ring-2 focus:ring-sky-400/50 dark:border-sky-500/40 dark:bg-[#1a1b1e] dark:text-[#ececf1]"
            autoFocus
            aria-label="Edit conversation title"
          />
        ) : (
          <div className="flex-1 min-w-0 space-y-1.5">
            {/* Title row */}
            <div className="flex items-center gap-2 text-sm">
              <h3
                className="flex-1 truncate font-semibold text-sm leading-tight text-sky-900 dark:text-sky-300"
              >
                {conversation.title}
              </h3>
              <div className="flex items-center gap-0.5 opacity-100 md:opacity-0 transition-opacity duration-150 md:group-hover:opacity-100 group-focus-within:opacity-100">
                <button
                  onClick={(e) => handleEditStart(e, conversation)}
                  className="rounded-md p-1.5 text-gray-400 transition-colors hover:bg-gray-200/80 hover:text-gray-700 dark:text-[#8b8fa3] dark:hover:bg-[#3c3f4a] dark:hover:text-[#d4d7e2]"
                  aria-label={`Rename conversation: ${conversation.title}`}
                >
                  <Edit2 className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={(e) => handleDeleteConversation(e, conversation)}
                  className="rounded-md p-1.5 text-gray-400 transition-colors hover:bg-red-50 hover:text-red-600 dark:text-[#8b8fa3] dark:hover:bg-red-900/30 dark:hover:text-red-300"
                  aria-label={`Delete conversation: ${conversation.title}`}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>

            <div className="space-y-2 pt-0.5">
              <div className="flex items-center gap-1.5 text-[11px] text-gray-400 dark:text-[#9aa1bc]">
                <span className="min-w-0 flex-1 truncate text-[11px] leading-none">
                  {agentLabel || '\u00A0'}
                </span>
                <span className="inline-flex shrink-0 items-center gap-0.5 font-medium text-gray-400 dark:text-[#9aa1bc] leading-none">
                  <MessageSquare className="h-3.5 w-3.5" />
                  {conversation.messages.length}
                </span>
                {conversation.attachedFiles && conversation.attachedFiles.length > 0 && (
                  <span className="inline-flex shrink-0 items-center gap-0.5 font-medium text-gray-400 dark:text-[#9aa1bc] leading-none">
                    <Paperclip className="h-3.5 w-3.5" />
                    {conversation.attachedFiles.length}
                  </span>
                )}
              </div>

              <div className="text-[11px] text-gray-400 dark:text-[#9aa1bc]">
                <span className="block truncate tabular-nums leading-none">
                  {formatConversationTimestamp(conversation.updatedAt)}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <>
      {/* API Configuration Modal */}
      {!isSingleAdapterMode && showConfig && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm px-4">
          <div
            ref={configDialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="select-agent-title"
            tabIndex={-1}
            className="w-full max-w-md rounded-2xl border border-gray-200 bg-white p-6 shadow-2xl dark:border-[#3d4050] dark:bg-[#1a1b1e]"
          >
            <h2 id="select-agent-title" className="mb-4 text-lg font-semibold text-gray-900 dark:text-[#ececf1]">
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
                <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-600/40 dark:bg-red-900/30 dark:text-red-200">
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
                  className="rounded-lg px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:text-[#d1d5db] dark:hover:bg-[#2d2f39]"
                  disabled={isValidating}
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <nav
        aria-label="Conversation sidebar"
        className="flex h-full md:h-[calc(100%-2rem)] md:mt-4 w-full md:w-72 flex-col border-r border-b border-gray-200 md:border-l md:border-t md:rounded-2xl md:overflow-hidden bg-transparent dark:border-[#2d2f39]"
      >
        {/* Header area */}
        <div className="bg-transparent px-4 pb-4 pt-4 dark:border-[#2d2f39]">
          <div className="flex w-full justify-center">
            <GitHubStatsBanner className="w-full max-w-[220px] items-center text-center" />
          </div>

          {/* Action buttons */}
          <div className="mt-8 space-y-2 pb-3">
            <button
              onClick={onOpenSettings}
              disabled={!onOpenSettings}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-gray-200 px-3 py-2 text-sm font-medium text-gray-700 transition-all duration-150 hover:bg-gray-50 hover:border-gray-300 hover:shadow-sm disabled:cursor-not-allowed disabled:opacity-50 dark:border-[#3d4050] dark:text-[#d4d7e2] dark:hover:bg-[#2d2f39] dark:hover:border-[#4d5166] dark:disabled:hover:bg-transparent dark:disabled:hover:border-[#3d4050]"
            >
              <Settings className="h-4 w-4" />
              Settings
            </button>
            {conversations.length > 0 && conversations.some((conv) => conv.messages.length > 0) && (
              <button
                onClick={handleClearAll}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-red-200 px-3 py-2 text-sm font-medium text-red-600 transition-all duration-150 hover:bg-red-50 hover:border-red-300 hover:shadow-sm dark:border-red-500/25 dark:text-red-400 dark:hover:bg-red-950/20 dark:hover:border-red-500/40"
                title="Delete all conversations"
              >
                <Trash className="h-4 w-4" />
                Delete Conversations
              </button>
            )}
          </div>

          {/* Validation error (outside modal) */}
          {validationError && !showConfig && (
            <p role="alert" className="mt-2 text-xs text-red-600 dark:text-red-400">
              {validationError}
            </p>
          )}

          {/* Search */}
          <div className="border-t border-gray-200 pt-4 mt-4 dark:border-[#2d2f39]">
            <div className="relative overflow-hidden rounded-[1.75rem] border border-slate-200/85 bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(248,250,252,0.94))] shadow-[0_10px_28px_rgba(15,23,42,0.05)] transition-all duration-200 focus-within:border-sky-300/90 focus-within:shadow-[0_0_0_1px_rgba(125,211,252,0.55),0_10px_28px_rgba(15,23,42,0.05)] dark:border-white/10 dark:bg-[linear-gradient(180deg,rgba(37,39,49,0.95),rgba(29,31,39,0.92))] dark:shadow-[0_12px_30px_rgba(0,0,0,0.2)] dark:focus-within:border-sky-400/30 dark:focus-within:shadow-[0_0_0_1px_rgba(56,189,248,0.22),0_12px_30px_rgba(0,0,0,0.2)]">
              <div className="pointer-events-none absolute inset-0 rounded-[inherit] bg-[linear-gradient(180deg,rgba(255,255,255,0.45),rgba(255,255,255,0))] dark:bg-[linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0))]" />
              <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 dark:text-slate-500" />
              <input
                ref={searchInputRef}
                type="text"
                role="searchbox"
                aria-label="Search conversations"
                placeholder="Search Conversations"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="relative z-10 w-full bg-transparent py-3 pl-11 pr-11 text-sm font-medium text-slate-700 placeholder:font-normal placeholder:text-slate-400 focus:outline-none dark:text-slate-100 dark:placeholder:text-slate-500"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => {
                    setSearchQuery('');
                    searchInputRef.current?.focus();
                  }}
                  className="absolute right-3 top-1/2 z-10 inline-flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full border border-slate-200/80 bg-white/90 text-slate-400 transition-colors hover:border-slate-300 hover:text-slate-600 focus:outline-none focus:ring-2 focus:ring-sky-200 dark:border-white/10 dark:bg-white/5 dark:text-slate-500 dark:hover:border-white/20 dark:hover:text-slate-200 dark:focus:ring-sky-500/20"
                  aria-label="Clear search"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>

            {/* Search result count */}
            {isSearching && (
              <p aria-live="polite" className="mt-2 text-center text-[11px] tabular-nums text-gray-400 dark:text-[#6e7490]">
                {filteredConversations.length === 0
                  ? 'No results'
                  : `${filteredConversations.length} ${filteredConversations.length === 1 ? 'result' : 'results'}`}
              </p>
            )}
          </div>
        </div>

        {/* Conversation list */}
        <div
          ref={listRef}
          role="listbox"
          aria-label="Conversations"
          onKeyDown={handleListKeyDown}
          className="flex-1 overflow-y-auto bg-transparent px-3 py-2"
        >
          {filteredConversations.length === 0 ? (
            <div className="rounded-xl border border-dashed border-gray-200 bg-white/60 p-6 text-center dark:border-[#2d2f39] dark:bg-[#1e2028]">
              <MessageSquare className="mx-auto mb-3 h-7 w-7 text-gray-300 dark:text-[#4d5166]" />
              <p className="text-sm font-medium text-gray-500 dark:text-[#8b8fa3]">
                {isSearching ? 'No conversations match your search' : 'No conversations yet'}
              </p>
              {!isSearching && (
                <p className="mt-1.5 text-[12px] text-gray-400 dark:text-[#6e7490]">
                  Start a conversation to see it here
                </p>
              )}
            </div>
          ) : isSearching ? (
            // Flat list when searching (no time groups)
            <div className="space-y-1">
              {filteredConversations.map(renderConversationCard)}
            </div>
          ) : (
            // Grouped by time
            <div className="space-y-4">
              {timeGroups.map((group) => (
                <section key={group.label} aria-label={group.label}>
                  <h4 className="sticky top-0 z-10 mb-1 bg-transparent px-1 pb-1 pt-0.5 text-[11px] font-semibold uppercase tracking-wider text-gray-400 backdrop-blur-sm dark:text-[#6e7490]">
                    {group.label}
                  </h4>
                  <div className="space-y-1">
                    {group.conversations.map(renderConversationCard)}
                  </div>
                </section>
              ))}
            </div>
          )}
        </div>

        {/* Mobile nav links */}
        {(() => {
          const navLinks = getHeaderNavLinks();
          if (navLinks.length === 0) return null;
          return (
            <div className="shrink-0 border-t border-gray-200/80 px-4 py-3 md:hidden dark:border-[#2d2f39]">
              <nav aria-label="Header links">
                <ul className="flex flex-wrap gap-2">
                  {navLinks.map((link) => (
                    <li key={link.url}>
                      <a
                        href={link.url}
                        className="inline-flex items-center rounded-md px-2.5 py-1.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-100 dark:text-[#d1d5db] dark:hover:bg-[#2b2d39]"
                      >
                        {link.label}
                      </a>
                    </li>
                  ))}
                </ul>
              </nav>
            </div>
          );
        })()}

        {/* Footer */}
        <div className="shrink-0 border-t border-gray-200/80 dark:border-[#2d2f39]">
          <AppFooter placement="sidebar" compact />
        </div>
      </nav>

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
