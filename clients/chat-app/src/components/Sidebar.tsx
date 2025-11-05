import React, { useState } from 'react';
import { Plus, Search, MessageSquare, Trash2, Edit2 } from 'lucide-react';
import { useChatStore } from '../stores/chatStore';
import { Conversation } from '../types';
import { ConfirmationModal } from './ConfirmationModal';
import { debugWarn, debugError } from '../utils/debug';
import { useGitHubStats } from '../hooks/useGitHubStats';

interface SidebarProps {}

export function Sidebar({}: SidebarProps) {
    const {
    conversations,
    currentConversationId,
    createConversation,
    selectConversation,
    deleteConversation,
    updateConversationTitle,
    canCreateNewConversation,
    getConversationCount
  } = useChatStore();
  
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

  const filteredConversations = conversations.filter(conv =>
    conv.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    conv.messages.some(msg => 
      msg.content.toLowerCase().includes(searchQuery.toLowerCase())
    )
  );

  const canStartNew = canCreateNewConversation();

  // GitHub stats for ORBIT project info
  const githubStats = useGitHubStats(
    import.meta.env.VITE_GITHUB_OWNER || 'schmitech',
    import.meta.env.VITE_GITHUB_REPO || 'orbit'
  );

  const handleNewChat = () => {
    try {
      createConversation();
    } catch (error) {
      debugWarn('Cannot create new conversation:', error instanceof Error ? error.message : 'Unknown error');
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
    setEditTitle(conversation.title);
  };

  const handleEditSubmit = (id: string) => {
    if (editTitle.trim()) {
      updateConversationTitle(id, editTitle.trim());
    }
    setEditingId(null);
    setEditTitle('');
  };

  const handleEditCancel = () => {
    setEditingId(null);
    setEditTitle('');
  };

  return (
    <>
      <div className="flex h-full w-72 flex-col border-r border-b border-gray-200 bg-gray-50 dark:border-[#4a4b54] dark:bg-[#202123]">
        <div className="border-b border-gray-200 p-4 dark:border-[#4a4b54]">
          <button
            onClick={handleNewChat}
            disabled={!canStartNew}
            className={`flex w-full items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium ${
              canStartNew
                ? 'bg-[#343541] text-white hover:bg-[#2c2f36] dark:bg-[#565869] dark:hover:bg-[#6b6f7a]'
                : 'cursor-not-allowed bg-gray-200 text-gray-500 dark:bg-[#3c3f4a] dark:text-[#6b6f7a]'
            }`}
            title={
              canStartNew
                ? 'Start a new conversation'
                : getConversationCount() >= 10
                  ? 'Maximum 10 conversations reached. Delete a conversation to create a new one.'
                  : 'Current conversation is empty. Send a message first to create a new conversation.'
            }
          >
            <Plus className="h-4 w-4" />
            New Conversation
          </button>
          
          <div className="mt-3 text-center">
            <span className="text-xs text-gray-500 dark:text-[#bfc2cd]">
              {getConversationCount()}/10 conversations
            </span>
          </div>
        </div>

        <div className="border-b border-gray-200 px-4 py-3 dark:border-[#4a4b54]">
          <div className="relative flex items-center">
            <Search className="pointer-events-none absolute left-3 h-4 w-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search conversations"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-md border border-gray-300 bg-white py-2 pl-9 pr-3 text-sm text-[#353740] placeholder-gray-400 focus:border-gray-400 focus:outline-none dark:border-[#4a4b54] dark:bg-[#343541] dark:text-[#ececf1]"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-3">
          {filteredConversations.length === 0 ? (
            <div className="rounded-md border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500 dark:border-[#4a4b54] dark:text-[#bfc2cd]">
              <MessageSquare className="mx-auto mb-3 h-6 w-6 text-gray-400 dark:text-[#6b6f7a]" />
              <p>
                {searchQuery ? 'No conversations found' : 'No conversations yet'}
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {filteredConversations.map((conversation) => (
                <div
                  key={conversation.id}
                  onClick={async () => await selectConversation(conversation.id)}
                  className={`group flex cursor-pointer items-center gap-3 rounded-md border px-3 py-3 text-left ${
                    currentConversationId === conversation.id
                      ? 'border-[#343541] bg-white dark:border-[#6b6f7a] dark:bg-[#343541]'
                      : 'border-transparent bg-gray-100 hover:border-gray-300 hover:bg-white dark:bg-[#2c2f36] dark:hover:border-[#4a4b54] dark:hover:bg-[#343541]'
                  }`}
                >
                  <div
                    className={`rounded-md p-2 ${
                    currentConversationId === conversation.id
                      ? 'bg-[#f0f0f5] text-[#353740] dark:bg-[#3c3f4a] dark:text-[#ececf1]'
                      : 'bg-white text-gray-500 dark:bg-[#3c3f4a] dark:text-[#bfc2cd]'
                  }`}
                  >
                    <MessageSquare className="h-4 w-4" />
                  </div>
                  
                  {editingId === conversation.id ? (
                    <input
                      type="text"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleEditSubmit(conversation.id);
                        if (e.key === 'Escape') handleEditCancel();
                      }}
                      onBlur={() => handleEditSubmit(conversation.id)}
                      className="flex-1 border-none bg-transparent text-sm text-[#353740] focus:outline-none dark:text-[#ececf1]"
                      autoFocus
                    />
                  ) : (
                    <div className="flex-1 min-w-0">
                      <h3 className={`truncate text-sm font-medium ${
                        currentConversationId === conversation.id
                          ? 'text-[#353740] dark:text-[#ececf1]'
                          : 'text-gray-700 dark:text-[#ececf1]'
                      }`}>
                        {conversation.title}
                      </h3>
                      <p className="mt-1 truncate text-xs text-gray-500 dark:text-[#bfc2cd]">
                        {conversation.messages.length} messages
                        {conversation.attachedFiles && conversation.attachedFiles.length > 0 && (
                          <span className="ml-2">
                            · {conversation.attachedFiles.length} file{conversation.attachedFiles.length !== 1 ? 's' : ''}
                          </span>
                        )}
                      </p>
                    </div>
                  )}

                  <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                    <button
                      onClick={(e) => handleEditStart(e, conversation)}
                      className="rounded p-2 text-gray-500 hover:bg-gray-200 hover:text-[#353740] dark:text-[#bfc2cd] dark:hover:bg-[#3c3f4a]"
                      title="Edit title"
                    >
                      <Edit2 className="h-4 w-4" />
                    </button>
                    <button
                      onClick={(e) => handleDeleteConversation(e, conversation)}
                      className="rounded p-2 text-red-500 hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-900/30"
                      title="Delete conversation"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ORBIT Project Information */}
        <div className="border-t border-gray-200 p-4 dark:border-[#4a4b54]">
          <div className="text-center">
            <div className="flex items-center justify-center gap-2 mb-3">
              <svg className="w-5 h-5 text-gray-600 dark:text-[#bfc2cd]" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
              </svg>
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
              href={`https://github.com/${import.meta.env.VITE_GITHUB_OWNER || 'schmitech'}/${import.meta.env.VITE_GITHUB_REPO || 'orbit'}`}
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
      </div>

      {/* Delete Confirmation Modal */}
      <ConfirmationModal
        isOpen={deleteConfirmation.isOpen}
        onClose={cancelDelete}
        onConfirm={confirmDelete}
        title="Delete Conversation"
        message={`Are you sure you want to delete "${deleteConfirmation.conversationTitle}"? This will clear the conversation history from both the server and your local storage. This action cannot be undone.`}
        confirmText="Delete"
        cancelText="Cancel"
        type="danger"
        isLoading={deleteConfirmation.isDeleting}
      />
    </>
  );
}
