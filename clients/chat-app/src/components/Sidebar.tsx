import React, { useState } from 'react';
import { Plus, Search, MessageSquare, Trash2, Edit2 } from 'lucide-react';
import { useChatStore } from '../stores/chatStore';
import { Conversation } from '../types';
import { ConfirmationModal } from './ConfirmationModal';

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

  const handleNewChat = () => {
    try {
      createConversation();
    } catch (error) {
      console.warn('Cannot create new conversation:', error instanceof Error ? error.message : 'Unknown error');
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
      console.error('Failed to delete conversation:', error);
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
      <div className="w-80 bg-white/80 dark:bg-[#050b16]/80 border-r border-white/60 dark:border-slate-800/70 backdrop-blur-[24px] flex flex-col h-full relative shadow-[0_0_60px_rgba(15,23,42,0.12)]">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(37,99,235,0.12),_transparent_70%)] dark:bg-[radial-gradient(circle_at_top,_rgba(56,189,248,0.18),_transparent_75%)]" />
        <div className="pointer-events-none absolute inset-y-0 right-0 w-px bg-white/60 dark:bg-slate-800/70" />

        {/* Header */}
        <div className="p-6 pb-4 relative z-10">
          <button
            onClick={handleNewChat}
            disabled={!canStartNew}
            className={`w-full group flex items-center justify-center gap-3 px-6 py-4 rounded-xl transition-all duration-200 font-medium text-sm border ${
              canStartNew
                ? 'border-slate-200/70 dark:border-slate-700/70 bg-white/80 dark:bg-slate-900/60 text-slate-900 dark:text-white shadow-[0_18px_48px_rgba(15,23,42,0.12)] hover:-translate-y-0.5 hover:shadow-[0_26px_70px_rgba(37,99,235,0.22)]'
                : 'border-slate-200/60 dark:border-slate-700/60 bg-transparent text-slate-400 dark:text-slate-500 cursor-not-allowed'
            }`}
            title={
              canStartNew
                ? 'Start a new conversation'
                : getConversationCount() >= 10
                  ? 'Maximum 10 conversations reached. Delete a conversation to create a new one.'
                  : 'Current conversation is empty. Send a message first to create a new conversation.'
            }
          >
            <Plus className={`w-5 h-5 transition-transform duration-200 ${
              canStartNew ? 'group-hover:rotate-90' : ''
            }`} />
            New Conversation
          </button>
          
          {/* Conversation count indicator */}
          <div className="mt-3 text-center">
            <span className="text-xs text-slate-500 dark:text-slate-400">
              {getConversationCount()}/10 conversations
            </span>
          </div>
        </div>

        {/* Search */}
        <div className="px-6 pb-4 relative z-10">
          <div className="relative">
            <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 text-slate-400 w-5 h-5" />
            <input
              type="text"
              placeholder="Search conversations..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-12 pr-4 py-3 bg-white/80 dark:bg-slate-900/60 rounded-xl text-sm border border-slate-200/70 dark:border-slate-700/60 placeholder-slate-400 dark:placeholder-slate-500 shadow-[0_14px_40px_rgba(15,23,42,0.12)] focus:outline-none focus:ring-2 focus:ring-blue-500/40 dark:focus:ring-cyan-400/30"
            />
          </div>
        </div>

        {/* Conversations List */}
        <div className="flex-1 overflow-y-auto px-4 pb-4 relative z-10">
          {filteredConversations.length === 0 ? (
            <div className="p-8 text-center">
              <MessageSquare className="w-12 h-12 mx-auto mb-4 text-slate-300 dark:text-slate-600" />
              <p className="text-slate-500 dark:text-slate-400 text-sm font-medium">
                {searchQuery ? 'No conversations found' : 'No conversations yet'}
              </p>
              <p className="text-slate-400 dark:text-slate-500 text-xs mt-2">
                {searchQuery ? 'Try a different search term' : 'Start a new conversation to begin'}
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {filteredConversations.map((conversation) => (
                <div
                  key={conversation.id}
                  onClick={async () => await selectConversation(conversation.id)}
                  className={`group flex items-center gap-3 p-4 rounded-xl cursor-pointer transition-all duration-200 border ${
                    currentConversationId === conversation.id
                      ? 'border-blue-500/30 bg-blue-500/10 dark:bg-blue-500/10 shadow-[0_18px_48px_rgba(37,99,235,0.22)]'
                      : 'border-transparent hover:border-slate-200/70 dark:hover:border-slate-700/60 hover:bg-white/80 dark:hover:bg-slate-800/50'
                  }`}
                >
                  <div className={`p-2 rounded-lg ${
                    currentConversationId === conversation.id
                      ? 'bg-blue-500/20 text-blue-700 dark:text-blue-300'
                      : 'bg-slate-200/40 dark:bg-slate-800/60 text-slate-500 dark:text-slate-400 group-hover:text-slate-700 dark:group-hover:text-slate-200'
                  }`}>
                    <MessageSquare className="w-4 h-4" />
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
                      className="flex-1 bg-transparent border-none outline-none text-sm font-medium text-slate-700 dark:text-slate-300"
                      autoFocus
                    />
                  ) : (
                    <div className="flex-1 min-w-0">
                      <h3 className={`text-sm font-medium truncate ${
                        currentConversationId === conversation.id
                          ? 'text-slate-900 dark:text-slate-100'
                          : 'text-slate-700 dark:text-slate-300'
                      }`}>
                        {conversation.title}
                      </h3>
                      <p className="text-xs text-slate-500 dark:text-slate-400 truncate mt-0.5">
                        {conversation.messages.length} messages
                      </p>
                    </div>
                  )}

                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                    <button
                      onClick={(e) => handleEditStart(e, conversation)}
                      className="p-2 hover:bg-slate-200/60 dark:hover:bg-slate-600/60 rounded-lg transition-colors duration-200 backdrop-blur-sm"
                      title="Edit title"
                    >
                      <Edit2 className="w-4 h-4 text-slate-500 dark:text-slate-400" />
                    </button>
                    <button
                      onClick={(e) => handleDeleteConversation(e, conversation)}
                      className="p-2 hover:bg-red-50/60 dark:hover:bg-red-900/30 rounded-lg transition-colors duration-200 text-red-500 dark:text-red-400 backdrop-blur-sm"
                      title="Delete conversation"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
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
        message={`Are you sure you want to delete "${deleteConfirmation.conversationTitle}"? This will clear the conversation history from both the server and your local storage. This action cannot be undone.`}
        confirmText="Delete"
        cancelText="Cancel"
        type="danger"
        isLoading={deleteConfirmation.isDeleting}
      />
    </>
  );
}
