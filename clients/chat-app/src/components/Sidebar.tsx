import React, { useState } from 'react';
import { Plus, Search, MessageSquare, MoreHorizontal, Trash2, Edit2 } from 'lucide-react';
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
    updateConversationTitle
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

  const handleNewChat = () => {
    createConversation();
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
      <div className="w-72 bg-gradient-to-br from-slate-50/95 via-white/90 to-blue-50/95 dark:from-slate-900/95 dark:via-slate-800/90 dark:to-slate-900/95 flex flex-col h-full relative backdrop-blur-md">
        {/* Subtle gradient overlay for depth */}
        <div className="absolute inset-0 bg-gradient-to-r from-transparent via-blue-50/20 to-transparent dark:from-transparent dark:via-blue-900/10 dark:to-transparent pointer-events-none"></div>
        
        {/* Subtle right border for separation */}
        <div className="absolute right-0 top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-slate-200/40 to-transparent dark:via-slate-700/40"></div>
        
        {/* Soft shadow transition */}
        <div className="absolute -right-4 top-0 bottom-0 w-8 bg-gradient-to-r from-transparent to-black/[0.02] dark:to-black/[0.05] pointer-events-none"></div>

        {/* Header */}
        <div className="p-6 pb-4 relative z-10">
          <button
            onClick={handleNewChat}
            className="w-full group flex items-center justify-center gap-3 px-6 py-4 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 dark:from-blue-500 dark:to-blue-600 dark:hover:from-blue-600 dark:hover:to-blue-700 text-white rounded-xl transition-all duration-200 font-medium text-sm shadow-lg hover:shadow-xl transform hover:-translate-y-0.5 backdrop-blur-sm"
          >
            <Plus className="w-5 h-5 group-hover:rotate-90 transition-transform duration-200" />
            New Conversation
          </button>
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
              className="w-full pl-12 pr-4 py-3 bg-white/60 dark:bg-slate-800/60 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 dark:focus:ring-blue-400/30 shadow-sm hover:shadow-md transition-all duration-200 placeholder-slate-400 dark:placeholder-slate-500 backdrop-blur-sm border border-slate-200/20 dark:border-slate-700/20"
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
                  className={`group flex items-center gap-3 p-4 rounded-xl cursor-pointer transition-all duration-200 backdrop-blur-sm border ${
                    currentConversationId === conversation.id
                      ? 'bg-gradient-to-r from-blue-50/80 to-indigo-50/80 dark:from-blue-900/40 dark:to-indigo-900/40 shadow-lg transform scale-[1.02] border-blue-200/30 dark:border-blue-700/30'
                      : 'hover:bg-gradient-to-r hover:from-slate-50/60 hover:to-slate-100/60 dark:hover:from-slate-800/60 dark:hover:to-slate-700/60 hover:shadow-md hover:transform hover:scale-[1.01] border-slate-200/20 dark:border-slate-700/20'
                  }`}
                >
                  <div className={`p-2 rounded-lg ${
                    currentConversationId === conversation.id
                      ? 'bg-blue-100/80 dark:bg-blue-800/60 text-blue-600 dark:text-blue-400'
                      : 'bg-slate-100/80 dark:bg-slate-700/60 text-slate-500 dark:text-slate-400 group-hover:bg-slate-200/80 dark:group-hover:bg-slate-600/60'
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