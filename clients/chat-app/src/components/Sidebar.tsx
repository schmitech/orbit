import React, { useState } from 'react';
import { Plus, Search, MessageSquare, MoreHorizontal, Trash2, Edit2, Settings } from 'lucide-react';
import { useChatStore } from '../stores/chatStore';
import { Conversation } from '../types';
import { ConfirmationModal } from './ConfirmationModal';

interface SidebarProps {
  onOpenSettings: () => void;
}

export function Sidebar({ onOpenSettings }: SidebarProps) {
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
  }>({
    isOpen: false,
    conversationId: '',
    conversationTitle: ''
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
      conversationTitle: conversation.title
    });
  };

  const confirmDelete = () => {
    deleteConversation(deleteConfirmation.conversationId);
    setDeleteConfirmation({
      isOpen: false,
      conversationId: '',
      conversationTitle: ''
    });
  };

  const cancelDelete = () => {
    setDeleteConfirmation({
      isOpen: false,
      conversationId: '',
      conversationTitle: ''
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
      <div className="w-64 bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700 flex flex-col h-full">
        {/* Header */}
        <div className="p-3 border-b border-gray-200 dark:border-gray-700">
          <button
            onClick={handleNewChat}
            className="w-full flex items-center justify-center gap-3 px-4 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors font-medium"
          >
            <Plus className="w-5 h-5" />
            New Chat
          </button>
        </div>

        {/* Search */}
        <div className="p-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
            <input
              type="text"
              placeholder="Search conversations..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400"
            />
          </div>
        </div>

        {/* Conversations List */}
        <div className="flex-1 overflow-y-auto px-2">
          {filteredConversations.length === 0 ? (
            <div className="p-4 text-center text-gray-500 dark:text-gray-400 text-sm">
              {searchQuery ? 'No conversations found' : 'No conversations yet'}
            </div>
          ) : (
            <div className="space-y-1">
              {filteredConversations.map((conversation) => (
                <div
                  key={conversation.id}
                  onClick={() => selectConversation(conversation.id)}
                  className={`group flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-colors ${
                    currentConversationId === conversation.id
                      ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-900 dark:text-blue-100'
                      : 'hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300'
                  }`}
                >
                  <MessageSquare className="w-4 h-4 flex-shrink-0" />
                  
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
                      className="flex-1 bg-transparent border-none outline-none text-sm"
                      autoFocus
                    />
                  ) : (
                    <span className="flex-1 text-sm truncate">
                      {conversation.title}
                    </span>
                  )}

                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={(e) => handleEditStart(e, conversation)}
                      className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-colors"
                      title="Edit title"
                    >
                      <Edit2 className="w-3 h-3" />
                    </button>
                    <button
                      onClick={(e) => handleDeleteConversation(e, conversation)}
                      className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-colors text-red-600 dark:text-red-400"
                      title="Delete conversation"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-200 dark:border-gray-700">
          <button
            onClick={onOpenSettings}
            className="w-full flex items-center gap-3 px-4 py-3 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
          >
            <Settings className="w-5 h-5" />
            Settings
          </button>
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      <ConfirmationModal
        isOpen={deleteConfirmation.isOpen}
        onClose={cancelDelete}
        onConfirm={confirmDelete}
        title="Delete Conversation"
        message={`Are you sure you want to delete "${deleteConfirmation.conversationTitle}"? This action cannot be undone and all messages in this conversation will be permanently lost.`}
        confirmText="Delete"
        cancelText="Cancel"
        type="danger"
      />
    </>
  );
}