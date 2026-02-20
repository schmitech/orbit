import { useState } from 'react';
import { useChatStore } from '../stores/chatStore';

interface SidebarProps {
  onOpenConfig: () => void;
}

export function Sidebar({ onOpenConfig }: SidebarProps) {
  const {
    conversations,
    currentConversationId,
    createConversation,
    deleteConversation,
    setCurrentConversation,
  } = useChatStore();
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const handleDeleteClick = (e: React.MouseEvent, convId: string) => {
    e.stopPropagation();
    setDeleteConfirmId(convId);
  };

  const handleConfirmDelete = () => {
    if (deleteConfirmId) {
      deleteConversation(deleteConfirmId);
      setDeleteConfirmId(null);
    }
  };

  const handleCancelDelete = () => {
    setDeleteConfirmId(null);
  };

  return (
    <aside className="sidebar" aria-label="Conversations">
      <div className="sidebar-header">
        <button type="button" className="btn-new-chat" onClick={() => createConversation()}>
          New chat
        </button>
        <button type="button" className="btn-configure" onClick={onOpenConfig} title="Configure connection">
          Configure
        </button>
      </div>
      <ul className="conversation-list">
        {conversations.map((conv) => (
          <li key={conv.id} className="conversation-item">
            <button
              type="button"
              className={`conversation-btn ${currentConversationId === conv.id ? 'active' : ''}`}
              onClick={() => setCurrentConversation(conv.id)}
              aria-current={currentConversationId === conv.id ? 'true' : undefined}
            >
              <span className="conversation-title">{conv.title}</span>
            </button>
            {deleteConfirmId === conv.id ? (
              <span className="conversation-delete-confirm">
                <button
                  type="button"
                  className="btn-delete-confirm-yes"
                  onClick={handleConfirmDelete}
                  aria-label="Confirm delete"
                >
                  Delete
                </button>
                <button
                  type="button"
                  className="btn-delete-confirm-no"
                  onClick={handleCancelDelete}
                  aria-label="Cancel"
                >
                  Cancel
                </button>
              </span>
            ) : (
              <button
                type="button"
                className="btn-delete"
                onClick={(e) => handleDeleteClick(e, conv.id)}
                title="Delete conversation"
                aria-label={`Delete conversation "${conv.title}"`}
              >
                <span aria-hidden="true">×</span>
              </button>
            )}
          </li>
        ))}
      </ul>
    </aside>
  );
}
