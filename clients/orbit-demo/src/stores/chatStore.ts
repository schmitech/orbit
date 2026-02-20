import { create } from 'zustand';
import {
  ChatState,
  Conversation,
  Message,
  AdapterInfo,
  ThreadInfo,
} from '../types';
import { getApiClient } from '../api/client';
import type { StreamResponse } from '@schmitech/chatbot-api';
import { generateSessionId, generateMessageId } from '../utils/session';
import { saveConversations, loadConversations } from '../utils/storage';
import { STREAMING_BATCH_DELAY, MAX_TITLE_LENGTH } from '../config/constants';
import {
  playAudioChunk,
  playFullAudio,
  stopAudio,
  setAudioEnabled,
} from '../utils/audio';

const streamingBuffer: Map<
  string,
  { content: string; timeoutId: ReturnType<typeof setTimeout> | null }
> = new Map();

let activeAbortController: AbortController | null = null;
let activeRequestId: string | null = null;
let activeStreamSessionId: string | null = null;

function flushStreamingBuffer(
  conversationId: string,
  setState: (fn: (state: ChatState) => Partial<ChatState>) => void
): void {
  const buffer = streamingBuffer.get(conversationId);
  if (!buffer) return;
  if (buffer.timeoutId) {
    clearTimeout(buffer.timeoutId);
    buffer.timeoutId = null;
  }
  if (buffer.content) {
    const contentToAppend = buffer.content;
    buffer.content = '';
    setState((state) => ({
      conversations: state.conversations.map((conv) => {
        if (conv.id !== conversationId) return conv;
        const messages = [...conv.messages];
        const last = messages[messages.length - 1];
        if (last?.role === 'assistant') {
          messages[messages.length - 1] = {
            ...last,
            content: last.content + contentToAppend,
          };
        }
        return { ...conv, messages, updatedAt: new Date() };
      }),
    }));
  }
  streamingBuffer.delete(conversationId);
}

interface ChatActions {
  hydrate: () => void;
  createConversation: () => string;
  deleteConversation: (id: string) => void;
  setCurrentConversation: (id: string | null) => void;
  clearAllConversations: () => void;
  setConversationAdapterInfo: (conversationId: string, adapterInfo: AdapterInfo) => void;
  toggleAudioForConversation: (conversationId: string) => void;
  sendMessage: (
    content: string,
    options?: {
      fileIds?: string[];
      threadId?: string;
      parentMessageId?: string;
      audioInput?: string;
      audioFormat?: string;
    }
  ) => Promise<void>;
  createThread: (messageId: string, sessionId: string) => Promise<ThreadInfo>;
  sendThreadMessage: (threadId: string, parentMessageId: string, content: string) => Promise<void>;
  stopGeneration: () => Promise<void>;
  appendToLastMessage: (content: string, conversationId: string) => void;
  validateConnection: () => Promise<boolean>;
  fetchAdapterInfo: () => Promise<AdapterInfo | null>;
  clearError: () => void;
  setAttachedFileIds: (ids: string[]) => void;
  addAttachedFileIds: (ids: string[]) => void;
  clearAttachedFileIds: () => void;
}

export const useChatStore = create<ChatState & ChatActions>((set, get) => ({
  conversations: [],
  currentConversationId: null,
  isLoading: false,
  error: null,
  attachedFileIds: [],

  hydrate: () => {
    const conversations = loadConversations();
    set({ conversations });
  },

  createConversation: () => {
    const id = generateMessageId('conv');
    const sessionId = generateSessionId();
    const conversation: Conversation = {
      id,
      sessionId,
      title: 'New Chat',
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date(),
    };
    set((state) => {
      const updated = [conversation, ...state.conversations];
      saveConversations(updated);
      return { conversations: updated, currentConversationId: id };
    });
    return id;
  },

  deleteConversation: (id: string) => {
    const conversation = get().conversations.find((c) => c.id === id);
    set((state) => {
      const updated = state.conversations.filter((c) => c.id !== id);
      saveConversations(updated);
      return {
        conversations: updated,
        currentConversationId: state.currentConversationId === id ? null : state.currentConversationId,
      };
    });
    if (conversation?.sessionId) {
      const api = getApiClient();
      if (api) {
        api.setSessionId(conversation.sessionId);
        api.deleteConversationWithFiles(conversation.sessionId).catch(() => {});
      }
    }
  },

  setCurrentConversation: (id: string | null) => {
    set({ currentConversationId: id });
  },

  clearAllConversations: () => {
    const conversations = get().conversations;
    set({ conversations: [], currentConversationId: null });
    saveConversations([]);
    const api = getApiClient();
    if (api) {
      for (const conv of conversations) {
        if (conv.sessionId) {
          api.setSessionId(conv.sessionId);
          api.deleteConversationWithFiles(conv.sessionId).catch(() => {});
        }
      }
    }
  },

  setConversationAdapterInfo: (conversationId: string, adapterInfo: AdapterInfo) => {
    set((state) => {
      const conversations = state.conversations.map((conv) =>
        conv.id === conversationId ? { ...conv, adapterInfo } : conv
      );
      saveConversations(conversations);
      return { conversations };
    });
  },

  clearError: () => set({ error: null }),

  toggleAudioForConversation: (conversationId: string) => {
    set((state) => {
      const conversations = state.conversations.map((conv) => {
        if (conv.id !== conversationId) return conv;
        const next = !(conv.audioEnabled ?? false);
        return { ...conv, audioEnabled: next };
      });
      saveConversations(conversations);
      return { conversations };
    });
    const conv = get().conversations.find((c) => c.id === conversationId);
    setAudioEnabled(conv?.audioEnabled ?? false);
  },

  setAttachedFileIds: (ids: string[]) => set({ attachedFileIds: ids }),
  addAttachedFileIds: (ids: string[]) =>
    set((s) => ({ attachedFileIds: [...s.attachedFileIds, ...ids] })),
  clearAttachedFileIds: () => set({ attachedFileIds: [] }),

  appendToLastMessage: (content: string, conversationId: string) => {
    const bufferKey = conversationId;
    const existing = streamingBuffer.get(bufferKey);
    const isFirstChunk = !existing;
    if (existing) {
      existing.content += content;
      if (existing.timeoutId) clearTimeout(existing.timeoutId);
    } else {
      streamingBuffer.set(bufferKey, { content, timeoutId: null });
    }
    const flushBuffer = () => {
      const buffer = streamingBuffer.get(bufferKey);
      if (!buffer?.content) return;
      const contentToAppend = buffer.content;
      buffer.content = '';
      buffer.timeoutId = null;
      set((state) => ({
        conversations: state.conversations.map((conv) => {
          if (conv.id !== conversationId) return conv;
          const messages = [...conv.messages];
          const last = messages[messages.length - 1];
          if (last?.role === 'assistant' && last.isStreaming) {
            messages[messages.length - 1] = { ...last, content: last.content + contentToAppend };
          }
          return { ...conv, messages, updatedAt: new Date() };
        }),
      }));
    };
    if (isFirstChunk) {
      flushBuffer();
      return;
    }
    const buf = streamingBuffer.get(bufferKey)!;
    buf.timeoutId = setTimeout(flushBuffer, STREAMING_BATCH_DELAY);
  },

  sendMessage: async (content, options = {}) => {
    const { fileIds = [], threadId, parentMessageId, audioInput, audioFormat } = options;
    const api = getApiClient();
    if (!api) {
      set({ error: 'Not connected. Configure Orbit URL and API key.' });
      return;
    }
    if (get().isLoading) return;

    let conversationId = get().currentConversationId;
    if (!conversationId) {
      conversationId = get().createConversation();
    }
    let conversation = get().conversations.find((c) => c.id === conversationId);
    if (!conversation) return;

    if (!conversation.adapterInfo) {
      const adapterInfo = await get().fetchAdapterInfo();
      if (adapterInfo) get().setConversationAdapterInfo(conversationId, adapterInfo);
    }
    conversation = get().conversations.find((c) => c.id === conversationId);
    if (!conversation) return;

    const audioEnabled = conversation.audioEnabled ?? false;
    const activeThreadId = threadId ?? null;
    let threadParentMessage: Message | undefined;
    let threadSessionId: string | null = null;
    if (activeThreadId) {
      threadParentMessage = conversation.messages.find(
        (msg) => msg.threadInfo?.thread_id === activeThreadId
      );
      if (!threadParentMessage) {
        set({ error: 'Thread not found. Start a thread from the message first.' });
        return;
      }
      threadSessionId = threadParentMessage.threadInfo?.thread_session_id ?? null;
    }

    const userMessage: Message = {
      id: generateMessageId('user'),
      content,
      role: 'user',
      timestamp: new Date(),
    };
    const assistantMessage: Message = {
      id: generateMessageId('assistant'),
      content: '',
      role: 'assistant',
      timestamp: new Date(),
      isStreaming: true,
    };
    const parentId = threadParentMessage?.id ?? parentMessageId;
    if (activeThreadId && parentId) {
      userMessage.isThreadMessage = true;
      userMessage.threadId = activeThreadId;
      userMessage.parentMessageId = parentId;
      assistantMessage.isThreadMessage = true;
      assistantMessage.threadId = activeThreadId;
      assistantMessage.parentMessageId = parentId;
    }

    set((state) => ({
      conversations: state.conversations.map((conv) => {
        if (conv.id !== conversationId) return conv;
        const existingMessages = conv.messages.filter(
          (m) => !(m.role === 'assistant' && m.isStreaming && m.content === '')
        );
        return {
          ...conv,
          messages: [...existingMessages, userMessage, assistantMessage],
          updatedAt: new Date(),
          title:
            conv.messages.length === 0
              ? content.slice(0, MAX_TITLE_LENGTH) + (content.length > MAX_TITLE_LENGTH ? '...' : '')
              : conv.title,
        };
      }),
      isLoading: true,
      error: null,
      attachedFileIds: [],
    }));

    const streamingConversationId = conversationId;
    if (audioEnabled) {
      stopAudio();
      setAudioEnabled(true);
    }

    try {
      const requestSessionId = threadSessionId ?? conversation.sessionId;
      api.setSessionId(requestSessionId);
      const abortController = new AbortController();
      activeAbortController = abortController;
      activeStreamSessionId = requestSessionId;
      activeRequestId = null;
      let receivedAnyText = false;

      const stream = api.streamChat(
        content,
        true,
        fileIds.length > 0 ? fileIds : undefined,
        activeThreadId ?? undefined,
        audioInput,
        audioFormat ?? 'webm',
        audioEnabled || audioInput ? 'en-US' : undefined,
        audioEnabled,
        undefined,
        undefined,
        undefined,
        abortController.signal
      );

      for await (const response of stream) {
        const resp = response as StreamResponse;
        if (resp.request_id && !activeRequestId) activeRequestId = resp.request_id;
        if (resp.text) {
          get().appendToLastMessage(resp.text, streamingConversationId);
          receivedAnyText = true;
        }
        if (resp.audio_chunk && audioEnabled) {
          playAudioChunk(resp.audio_chunk, resp.audioFormat ?? 'webm');
        }
        if (resp.audio && resp.done && audioEnabled) {
          playFullAudio(resp.audio, resp.audioFormat ?? 'mp3');
        }
        if (resp.done && resp.threading?.supports_threading) {
          const th = resp.threading;
          set((state) => ({
            conversations: state.conversations.map((conv) => {
              if (conv.id !== streamingConversationId) return conv;
              return {
                ...conv,
                messages: conv.messages.map((msg) =>
                  msg.id === assistantMessage.id
                    ? { ...msg, supportsThreading: true, databaseMessageId: th.message_id }
                    : msg
                ),
                updatedAt: new Date(),
              };
            }),
          }));
        }
        if (resp.done) break;
      }

      if (!receivedAnyText && !abortController.signal.aborted) {
        get().appendToLastMessage(
          'No response received from the server. Please try again.',
          streamingConversationId
        );
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      const isAbort =
        err instanceof Error &&
        (err.name === 'AbortError' || message.includes('aborted') || message.includes('cancel'));
      if (!isAbort) {
        get().appendToLastMessage(`\n\nError: ${message}`, streamingConversationId);
        set({ error: message });
      }
    } finally {
      flushStreamingBuffer(streamingConversationId, set);
      set((state) => ({
        isLoading: false,
        conversations: state.conversations.map((conv) => {
          if (conv.id !== streamingConversationId) return conv;
          return {
            ...conv,
            messages: conv.messages
              .filter((m) => {
                if (m.role === 'assistant' && m.isStreaming && !m.content.trim()) return false;
                return true;
              })
              .map((m) => (m.isStreaming ? { ...m, isStreaming: false } : m)),
          };
        }),
      }));
      saveConversations(get().conversations);
      activeAbortController = null;
      activeRequestId = null;
      activeStreamSessionId = null;
    }
  },

  createThread: async (messageId: string, sessionId: string) => {
    const conversation = get().conversations.find((c) => c.sessionId === sessionId);
    if (!conversation) throw new Error('Conversation not found');
    const message = conversation.messages.find((m) => m.id === messageId);
    if (!message) throw new Error('Message not found');
    const api = getApiClient();
    if (!api) throw new Error('Not connected');
    const dbMessageId = message.databaseMessageId ?? messageId;
    const threadInfo: ThreadInfo = await api.createThread(dbMessageId, sessionId);
    set((state) => ({
      conversations: state.conversations.map((conv) => {
        if (conv.sessionId !== sessionId) return conv;
        return {
          ...conv,
          messages: conv.messages.map((msg) =>
            msg.id === messageId ? { ...msg, threadInfo, supportsThreading: true } : msg
          ),
          updatedAt: new Date(),
        };
      }),
    }));
    saveConversations(get().conversations);
    return threadInfo;
  },

  sendThreadMessage: async (threadId: string, parentMessageId: string, content: string) => {
    await get().sendMessage(content, { threadId, parentMessageId });
  },

  stopGeneration: async () => {
    stopAudio();
    if (activeAbortController) activeAbortController.abort();
    if (activeStreamSessionId && activeRequestId) {
      const api = getApiClient();
      if (api) {
        api.stopChat(activeStreamSessionId, activeRequestId).catch(() => {});
      }
    }
  },

  validateConnection: async () => {
    const api = getApiClient();
    if (!api) return false;
    try {
      await api.validateApiKey();
      return true;
    } catch {
      return false;
    }
  },

  fetchAdapterInfo: async () => {
    const api = getApiClient();
    if (!api) return null;
    try {
      const info = await api.getAdapterInfo();
      return info as AdapterInfo;
    } catch {
      return null;
    }
  },
}));
