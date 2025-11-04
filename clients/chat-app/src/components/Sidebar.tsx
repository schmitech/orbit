import React, { useState } from 'react';
import { Plus, Search, MessageSquare, Trash2, Edit2 } from 'lucide-react';
import { useChatStore } from '../stores/chatStore';
import { Conversation } from '../types';
import { ConfirmationModal } from './ConfirmationModal';
import { FileList } from './FileList';
import { debugWarn, debugError } from '../utils/debug';

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
      <div className="flex h-full w-72 flex-col border-r border-gray-200 bg-gray-50 dark:border-[#4a4b54] dark:bg-[#202123]">
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

        <div className="border-t border-gray-200 px-3 py-3 dark:border-[#4a4b54]">
          <FileList />
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
