import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Search, X, Trash2, Edit2, Trash, PanelLeftClose } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useChatStore } from '../stores/chatStore';
import { Conversation } from '../types';
import { ConfirmationModal } from './ConfirmationModal';
import { debugError } from '../utils/debug';
import { getApiUrl, getHeaderNavLinks, getIsSingleAdapterMode } from '../utils/runtimeConfig';
import { AdapterSelector } from './AdapterSelector';
import { useFocusTrap } from '../hooks/useFocusTrap';
import { AppFooter } from './AppFooter';

interface SidebarProps {
  onRequestClose?: () => void;
  onToggleDesktopSidebar?: () => void;
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

  if (date >= startOfToday) return 'today';
  if (date >= startOfYesterday) return 'yesterday';
  if (date >= startOfWeek) return 'thisWeek';
  if (date >= startOfMonth) return 'thisMonth';
  return 'earlier';
}

function groupConversationsByTime(conversations: Conversation[]): TimeGroup[] {
  const now = new Date();
  const order = ['today', 'yesterday', 'thisWeek', 'thisMonth', 'earlier'];
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

export function Sidebar({ onRequestClose, onToggleDesktopSidebar }: SidebarProps) {
  const { t } = useTranslation();
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
  const [selectedAdapter, setSelectedAdapter] = useState<{ conversationId: string | null; adapterName: string } | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [validationError, setValidationError] = useState<{ conversationId: string | null; message: string } | null>(null);
  const configDialogRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const canConfigureApi = !currentConversation || currentConversation.messages.length === 0;

  const selectedAdapterName =
    selectedAdapter?.conversationId === currentConversationId
      ? selectedAdapter.adapterName
      : currentConversation?.adapterName ?? null;
  const validationErrorMessage =
    validationError?.conversationId === currentConversationId ? validationError.message : null;

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
        (conv.title || t('chatInterface.newChatTitle')).toLowerCase().includes(q) ||
        conv.messages.some((msg) => msg.content.toLowerCase().includes(q)) ||
        (conv.attachedFiles || []).some((file) => file.filename.toLowerCase().includes(q))
    );
  }, [conversationsWithHistory, searchQuery, t]);

  const timeGroups = useMemo(() => groupConversationsByTime(filteredConversations), [filteredConversations]);

  const totalConversations = getConversationCount();
  const isSearching = searchQuery.length > 0;
  const hasSearchableConversations = conversationsWithHistory.length > 0;

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
    setSelectedAdapter({ conversationId: currentConversationId ?? null, adapterName });
    setValidationError(null);
    setIsValidating(true);
    try {
      const runtimeApiUrl = currentConversation?.apiUrl || getApiUrl();
      await configureApiSettings(runtimeApiUrl, undefined, adapterName);
      clearError();
      setShowConfig(false);
    } catch (error) {
      debugError('Failed to configure adapter:', error);
      setValidationError({
        conversationId: currentConversationId ?? null,
        message: error instanceof Error ? error.message : t('sidebar.adapterConfigureFailed')
      });
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
      conversationTitle: conversation.title || t('chatInterface.newChatTitle'),
      isDeleting: false,
    });
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
    setEditTitle((conversation.title || t('chatInterface.newChatTitle')).slice(0, MAX_TITLE_LENGTH));
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
    const displayTitle = conversation.title || t('chatInterface.newChatTitle');

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
        className={`group relative flex w-full cursor-pointer items-center rounded-lg px-3 py-2 text-left text-sm transition-colors duration-100
          ${
            isActive
              ? 'bg-slate-100 dark:bg-[#2a2b36]'
              : 'hover:bg-slate-100/70 dark:hover:bg-[#25262f]'
          } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/50 dark:focus-visible:ring-sky-400/40`}
        aria-current={isActive ? 'true' : undefined}
        aria-label={t('sidebar.conversationCard.openAriaLabel', { title: displayTitle })}
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
            className="flex-1 rounded border border-sky-300 bg-white px-2 py-0.5 text-sm text-[#353740] focus:outline-none focus:ring-2 focus:ring-sky-400/50 dark:border-sky-500/40 dark:bg-[#1a1b1e] dark:text-[#ececf1]"
            autoFocus
            aria-label={t('sidebar.conversationCard.editInputAriaLabel')}
          />
        ) : (
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <div className="flex min-w-0 items-center gap-1">
              <h3 className={`flex-1 truncate text-sm leading-snug ${isActive ? 'font-medium text-slate-900 dark:text-[#ececf1]' : 'font-normal text-slate-700 dark:text-[#c5c8d6]'}`}>
                {displayTitle}
              </h3>
              {/* Actions: hidden until hover/focus, then fade in */}
              <div className="ml-1 flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity duration-100 group-hover:opacity-100 group-focus-within:opacity-100">
                <button
                  onClick={(e) => handleEditStart(e, conversation)}
                  className="rounded p-1 text-slate-400 transition-colors hover:bg-slate-200/80 hover:text-slate-600 dark:text-[#6b6f7a] dark:hover:bg-[#3c3f4a] dark:hover:text-[#c5c8d6]"
                  aria-label={t('sidebar.conversationCard.editAriaLabel', { title: displayTitle })}
                >
                  <Edit2 className="h-3 w-3" />
                </button>
                <button
                  onClick={(e) => handleDeleteConversation(e, conversation)}
                  className="rounded p-1 text-slate-400 transition-colors hover:bg-red-100/80 hover:text-red-600 dark:text-[#6b6f7a] dark:hover:bg-red-900/30 dark:hover:text-red-400"
                  aria-label={t('sidebar.conversationCard.deleteAriaLabel', { title: displayTitle })}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            </div>
            {agentLabel && (
              <span className="truncate text-[11px] leading-none text-slate-400 dark:text-[#6b6f7a]">
                {agentLabel}
              </span>
            )}
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
              {t('sidebar.selectAgent.title')}
            </h2>
            <div className="space-y-5">
              <AdapterSelector
                selectedAdapter={selectedAdapterName}
                onAdapterChange={handleAdapterSelection}
                disabled={isValidating}
                variant="prominent"
                showDescriptions
                showLabel={false}
              />
              {validationErrorMessage && (
                <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-600/40 dark:bg-red-900/30 dark:text-red-200">
                  {validationErrorMessage}
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
                  {t('common.cancel')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <nav
        aria-label={t('sidebar.navAriaLabel')}
        className="flex h-full md:h-[calc(100%-2rem)] md:mt-4 w-full md:w-72 flex-col border-r border-b border-gray-200 md:border-l md:border-t md:rounded-2xl md:overflow-hidden bg-transparent dark:border-[#2d2f39]"
      >
        {/* Header area */}
        <div className="bg-transparent px-4 pb-4 pt-4 dark:border-[#2d2f39]">
          {/* Action row: delete button + collapse toggle share the same row */}
          <div className="flex items-center gap-2 pb-3">
            {conversations.length > 0 && conversations.some((conv) => conv.messages.length > 0) && (
              <button
                onClick={handleClearAll}
                className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-red-200 px-3 py-2 text-sm font-medium text-red-600 transition-all duration-150 hover:bg-red-50 hover:border-red-300 hover:shadow-sm dark:border-red-500/25 dark:text-red-400 dark:hover:bg-red-950/20 dark:hover:border-red-500/40"
                title={t('sidebar.deleteAllConversations.title')}
              >
                <Trash className="h-4 w-4" />
                {t('sidebar.deleteAllConversations.button')}
              </button>
            )}
            {onToggleDesktopSidebar && (
              <button
                type="button"
                onClick={onToggleDesktopSidebar}
                className="ml-auto hidden shrink-0 md:inline-flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200/80 bg-white text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:border-[#333645] dark:bg-[#161616] dark:text-[#d1d5db] dark:hover:border-[#43465a] dark:hover:bg-[#202020] dark:hover:text-white"
                aria-label={t('sidebar.collapse.ariaLabel')}
                title={t('sidebar.collapse.title')}
              >
                <PanelLeftClose className="h-4 w-4" />
              </button>
            )}
          </div>

          {/* Validation error (outside modal) */}
          {validationErrorMessage && !showConfig && (
            <p role="alert" className="mt-2 text-xs text-red-600 dark:text-red-400">
              {validationErrorMessage}
            </p>
          )}

          {/* Search */}
          {hasSearchableConversations && (
          <div className="border-t border-gray-200 pt-4 mt-4 dark:border-[#2d2f39]">
            <div className="relative overflow-hidden rounded-[1.75rem] border border-slate-200/85 bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(248,250,252,0.94))] shadow-[0_10px_28px_rgba(15,23,42,0.05)] transition-all duration-200 focus-within:border-sky-300/90 focus-within:shadow-[0_0_0_1px_rgba(125,211,252,0.55),0_10px_28px_rgba(15,23,42,0.05)] dark:border-white/10 dark:bg-[linear-gradient(180deg,rgba(37,39,49,0.95),rgba(29,31,39,0.92))] dark:shadow-[0_12px_30px_rgba(0,0,0,0.2)] dark:focus-within:border-sky-400/30 dark:focus-within:shadow-[0_0_0_1px_rgba(56,189,248,0.22),0_12px_30px_rgba(0,0,0,0.2)]">
              <div className="pointer-events-none absolute inset-0 rounded-[inherit] bg-[linear-gradient(180deg,rgba(255,255,255,0.45),rgba(255,255,255,0))] dark:bg-[linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0))]" />
              <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 dark:text-slate-500" />
              <input
                ref={searchInputRef}
                type="text"
                role="searchbox"
                aria-label={t('sidebar.search.ariaLabel')}
                placeholder={t('sidebar.search.placeholder')}
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
                  aria-label={t('sidebar.search.clearAriaLabel')}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>

            {/* Search result count */}
            {isSearching && (
              <p aria-live="polite" className="mt-2 text-center text-[11px] tabular-nums text-gray-400 dark:text-[#6e7490]">
                {filteredConversations.length === 0
                  ? t('sidebar.resultsNone')
                  : t('sidebar.results', { count: filteredConversations.length })}
              </p>
            )}
          </div>
          )}
        </div>

        {/* Conversation list */}
        <div
          ref={listRef}
          role="listbox"
          aria-label={t('sidebar.conversations.ariaLabel')}
          onKeyDown={handleListKeyDown}
          className="flex-1 overflow-y-auto bg-transparent px-3 py-2"
        >
          {filteredConversations.length === 0 ? null : isSearching ? (
            // Flat list when searching (no time groups)
            <div className="space-y-1">
              {filteredConversations.map(renderConversationCard)}
            </div>
          ) : (
            // Grouped by time
            <div className="space-y-4">
              {timeGroups.map((group) => (
                <section key={group.label} aria-label={t(`sidebar.timeGroups.${group.label}`)}>
                  <h4 className="sticky top-0 z-10 mb-1 bg-transparent px-1 pb-1 pt-0.5 text-[11px] font-semibold uppercase tracking-wider text-gray-400 backdrop-blur-sm dark:text-[#6e7490]">
                    {t(`sidebar.timeGroups.${group.label}`)}
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
              <nav aria-label={t('appHeader.navLinksAriaLabel')}>
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
        title={t('sidebar.deleteConfirm.title')}
        message={t('sidebar.deleteConfirm.message', { title: deleteConfirmation.conversationTitle })}
        confirmText={t('sidebar.deleteConfirm.confirmText')}
        cancelText={t('common.cancel')}
        type="danger"
        isLoading={deleteConfirmation.isDeleting}
      />

      {/* Clear All Conversations Confirmation Modal */}
      <ConfirmationModal
        isOpen={clearAllConfirmation.isOpen}
        onClose={cancelClearAll}
        onConfirm={confirmClearAll}
        title={t('sidebar.clearAllConfirm.title')}
        message={t('sidebar.clearAllConfirm.message', { count: totalConversations })}
        confirmText={t('sidebar.clearAllConfirm.confirmText')}
        cancelText={t('common.cancel')}
        type="danger"
        isLoading={clearAllConfirmation.isDeleting}
      />
    </>
  );
}
