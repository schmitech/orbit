import { useState, useCallback, useEffect } from 'react';
import { useChatStore } from '../stores/chatStore';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import type { Message as MessageType } from '../types';

interface ChatViewProps {
  conversationId: string | null;
}

export function ChatView({ conversationId }: ChatViewProps) {
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [activeParentMessageId, setActiveParentMessageId] = useState<string | null>(null);

  const conversation = useChatStore((s) =>
    s.conversations.find((c) => c.id === conversationId)
  );
  const createThread = useChatStore((s) => s.createThread);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const setConversationAdapterInfo = useChatStore((s) => s.setConversationAdapterInfo);
  const fetchAdapterInfo = useChatStore((s) => s.fetchAdapterInfo);
  const toggleAudioForConversation = useChatStore((s) => s.toggleAudioForConversation);

  const handleReplyInThread = useCallback(
    async (message: MessageType) => {
      if (!conversation) return;
      let threadId = message.threadInfo?.thread_id;
      if (!threadId && message.supportsThreading) {
        try {
          const info = await createThread(message.id, conversation.sessionId);
          threadId = info.thread_id;
        } catch {
          return;
        }
      }
      if (threadId) {
        setActiveThreadId(threadId);
        setActiveParentMessageId(message.id);
      }
    },
    [conversation, createThread]
  );

  const handleSend = useCallback(
    (content: string, fileIds: string[], audioInput?: string) => {
      sendMessage(content, {
        fileIds: fileIds.length > 0 ? fileIds : undefined,
        threadId: activeThreadId ?? undefined,
        parentMessageId: activeParentMessageId ?? undefined,
        audioInput,
      });
      setActiveThreadId(null);
      setActiveParentMessageId(null);
    },
    [sendMessage, activeThreadId, activeParentMessageId]
  );

  const handleClearThread = useCallback(() => {
    setActiveThreadId(null);
    setActiveParentMessageId(null);
  }, []);

  useEffect(() => {
    if (!conversation?.id || conversation.adapterInfo) return;
    let cancelled = false;
    (async () => {
      const info = await fetchAdapterInfo();
      if (!cancelled && info) setConversationAdapterInfo(conversation.id, info);
    })();
    return () => {
      cancelled = true;
    };
  }, [conversation?.id, conversation?.adapterInfo, fetchAdapterInfo, setConversationAdapterInfo]);

  if (!conversationId) {
    return (
      <div className="chat-empty">
        <p>Select a conversation or create a new chat.</p>
      </div>
    );
  }

  if (!conversation) {
    return (
      <div className="chat-empty">
        <p>Conversation not found.</p>
      </div>
    );
  }

  const adapterInfo = conversation.adapterInfo;

  return (
    <main className="chat-view" aria-label="Chat">
      <header className="chat-header">
        <div className="chat-header-info">
          <span className="chat-title">{conversation.title}</span>
          {adapterInfo && (
            <span className="chat-adapter">
              {adapterInfo.adapter_name}
              {adapterInfo.model ? ` · ${adapterInfo.model}` : ''}
            </span>
          )}
        </div>
        <div className="chat-header-actions">
          <button
            type="button"
            className={`btn-audio-toggle ${conversation.audioEnabled ? 'on' : ''}`}
            onClick={() => toggleAudioForConversation(conversation.id)}
            title={conversation.audioEnabled ? 'Disable audio' : 'Enable audio (TTS)'}
            aria-label={conversation.audioEnabled ? 'Disable audio (TTS)' : 'Enable audio (TTS)'}
            aria-pressed={conversation.audioEnabled}
          >
            <span aria-hidden="true">🔊</span>
          </button>
        </div>
      </header>
      {activeThreadId && (
        <div className="thread-banner">
          Replying in thread
          <button type="button" className="btn-clear-thread" onClick={handleClearThread}>
            Cancel
          </button>
        </div>
      )}
      <div className="chat-messages">
        {conversation.messages.length === 0 ? (
          <div className="chat-empty-state">
            <p>Send a message to start. You can attach files, use voice, or enable TTS.</p>
            {!adapterInfo && (
              <p className="chat-empty-hint">Loading adapter info…</p>
            )}
          </div>
        ) : (
          <MessageList
            messages={conversation.messages}
            onReplyInThread={handleReplyInThread}
          />
        )}
      </div>
      <MessageInput
        onSend={handleSend}
        disabled={conversation.messages.length === 0 && !adapterInfo}
        activeThreadId={activeThreadId}
        onClearThread={handleClearThread}
      />
    </main>
  );
}
