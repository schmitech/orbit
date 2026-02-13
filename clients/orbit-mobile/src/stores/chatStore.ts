import { create } from 'zustand';
import { ChatState, Conversation, Message, AdapterInfo, AudioSettings } from '../types';
import { getApiClient } from '../api/client';
import type { StreamResponse } from '../api/client';
import { generateSessionId, generateMessageId } from '../utils/session';
import { saveConversations, loadConversations } from '../utils/storage';
import { STREAMING_BATCH_DELAY, MAX_TITLE_LENGTH } from '../config/constants';
import { getConfig } from '../config/env';
import { audioStreamManager } from '../utils/audioPlayer';

// Streaming content buffer for batching rapid updates (~30fps)
const streamingBuffer: Map<
  string,
  { content: string; timeoutId: ReturnType<typeof setTimeout> | null }
> = new Map();

// Stream control state
let activeAbortController: AbortController | null = null;
let activeRequestId: string | null = null;
let activeStreamSessionId: string | null = null;

const flushStreamingBuffer = (
  conversationId: string,
  setState: (fn: (state: ChatState) => Partial<ChatState>) => void
) => {
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
        const lastMessage = messages[messages.length - 1];

        if (lastMessage && lastMessage.role === 'assistant') {
          messages[messages.length - 1] = {
            ...lastMessage,
            content: lastMessage.content + contentToAppend,
          };
        }

        return { ...conv, messages, updatedAt: new Date() };
      }),
    }));
  }

  streamingBuffer.delete(conversationId);
};

interface ChatActions {
  // Hydration
  hydrate: () => Promise<void>;

  // Conversation management
  createConversation: () => string;
  deleteConversation: (id: string) => void;
  setCurrentConversation: (id: string | null) => void;
  clearAllConversations: () => void;

  // Audio
  toggleAudioForConversation: (conversationId: string) => void;
  updateAudioSettings: (conversationId: string, settings: Partial<AudioSettings>) => void;

  // Messaging
  sendMessage: (content: string) => Promise<void>;
  stopGeneration: () => Promise<void>;
  appendToLastMessage: (content: string, conversationId: string) => void;

  // API
  validateConnection: () => Promise<boolean>;
  fetchAdapterInfo: () => Promise<AdapterInfo | null>;

  // Error
  clearError: () => void;
}

export const useChatStore = create<ChatState & ChatActions>((set, get) => ({
  // Initial state
  conversations: [],
  currentConversationId: null,
  isLoading: false,
  error: null,

  hydrate: async () => {
    const conversations = await loadConversations();
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
      return {
        conversations: updated,
        currentConversationId: id,
      };
    });

    return id;
  },

  deleteConversation: (id: string) => {
    set((state) => {
      const updated = state.conversations.filter((c) => c.id !== id);
      saveConversations(updated);
      return {
        conversations: updated,
        currentConversationId:
          state.currentConversationId === id ? null : state.currentConversationId,
      };
    });
  },

  setCurrentConversation: (id: string | null) => {
    set({ currentConversationId: id });
  },

  clearAllConversations: () => {
    set({ conversations: [], currentConversationId: null });
    saveConversations([]);
  },

  clearError: () => set({ error: null }),

  toggleAudioForConversation: (conversationId: string) => {
    set((state) => {
      const conversations = state.conversations.map((conv) => {
        if (conv.id !== conversationId) return conv;
        const currentEnabled = conv.audioSettings?.enabled ?? false;
        return {
          ...conv,
          audioSettings: {
            ...conv.audioSettings,
            enabled: !currentEnabled,
            autoPlay: true,
          },
        };
      });
      saveConversations(conversations);
      return { conversations };
    });

    // Enable/disable audio playback manager
    const conv = get().conversations.find((c) => c.id === conversationId);
    if (conv?.audioSettings?.enabled) {
      audioStreamManager.enableAudio();
    } else {
      audioStreamManager.disableAudio();
    }
  },

  updateAudioSettings: (conversationId: string, settings: Partial<AudioSettings>) => {
    set((state) => {
      const conversations = state.conversations.map((conv) => {
        if (conv.id !== conversationId) return conv;
        return {
          ...conv,
          audioSettings: { ...conv.audioSettings, enabled: false, ...settings },
        };
      });
      saveConversations(conversations);
      return { conversations };
    });
  },

  appendToLastMessage: (content: string, conversationId: string) => {
    const bufferKey = conversationId;
    const existing = streamingBuffer.get(bufferKey);

    if (existing) {
      existing.content += content;
      if (existing.timeoutId) {
        clearTimeout(existing.timeoutId);
      }
    } else {
      streamingBuffer.set(bufferKey, { content, timeoutId: null });
    }

    const flushBuffer = () => {
      const buffer = streamingBuffer.get(bufferKey);
      if (!buffer || !buffer.content) return;

      const contentToAppend = buffer.content;
      buffer.content = '';
      buffer.timeoutId = null;

      set((state) => ({
        conversations: state.conversations.map((conv) => {
          if (conv.id !== conversationId) return conv;

          const messages = [...conv.messages];
          const lastMessage = messages[messages.length - 1];

          if (
            lastMessage &&
            lastMessage.role === 'assistant' &&
            lastMessage.isStreaming
          ) {
            messages[messages.length - 1] = {
              ...lastMessage,
              content: lastMessage.content + contentToAppend,
            };
          }

          return { ...conv, messages, updatedAt: new Date() };
        }),
      }));
    };

    const buffer = streamingBuffer.get(bufferKey)!;
    buffer.timeoutId = setTimeout(flushBuffer, STREAMING_BATCH_DELAY);
  },

  sendMessage: async (content: string) => {
    if (get().isLoading) return;

    let conversationId = get().currentConversationId;
    if (!conversationId) {
      conversationId = get().createConversation();
    }

    const conversation = get().conversations.find((c) => c.id === conversationId);
    if (!conversation) return;

    // Resolve audio settings
    const config = getConfig();
    const audioEnabled = config.enableAudioOutput && (conversation.audioSettings?.enabled ?? false);
    const ttsVoice = conversation.audioSettings?.ttsVoice;
    const language = conversation.audioSettings?.language || 'en-US';

    // Create user and assistant placeholder messages
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

    // Atomic update: add messages, set title, mark loading
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
              ? content.slice(0, MAX_TITLE_LENGTH) +
                (content.length > MAX_TITLE_LENGTH ? '...' : '')
              : conv.title,
        };
      }),
      isLoading: true,
      error: null,
    }));

    const streamingConversationId = conversationId;

    // Prepare audio manager if audio is enabled
    if (audioEnabled) {
      audioStreamManager.reset();
      await audioStreamManager.enableAudio();
    }

    try {
      const api = getApiClient();
      api.setSessionId(conversation.sessionId);

      const abortController = new AbortController();
      activeAbortController = abortController;
      activeStreamSessionId = conversation.sessionId;
      activeRequestId = null;

      let receivedAnyText = false;

      for await (const response of api.streamChat(
        content,
        true, // stream
        undefined, // fileIds
        undefined, // threadId
        undefined, // audioInput
        undefined, // audioFormat
        audioEnabled ? language : undefined, // language
        audioEnabled, // returnAudio
        audioEnabled ? ttsVoice : undefined, // ttsVoice
        undefined, // sourceLanguage
        undefined, // targetLanguage
        abortController.signal
      )) {
        // Capture request_id for cancellation
        if (response.request_id && !activeRequestId) {
          activeRequestId = response.request_id;
        }

        // Append text chunks via buffer
        if (response.text) {
          get().appendToLastMessage(response.text, streamingConversationId);
          receivedAnyText = true;
        }

        // Handle audio chunks for TTS playback
        if (response.audio_chunk && audioEnabled) {
          audioStreamManager.addChunk({
            audio: response.audio_chunk,
            audioFormat: response.audioFormat || 'opus',
            chunkIndex: response.chunk_index ?? 0,
          });
        }

        if (response.done) {
          break;
        }
      }

      if (!receivedAnyText && !abortController.signal.aborted) {
        get().appendToLastMessage(
          'No response received from the server. Please try again later.',
          streamingConversationId
        );
      }
    } catch (error: any) {
      const isAbortError =
        error?.name === 'AbortError' ||
        error?.message === 'Stream cancelled by user' ||
        error?.message?.includes('aborted');

      if (!isAbortError) {
        const errorMessage =
          error?.message || 'An error occurred. Please try again.';
        get().appendToLastMessage(
          `\n\nError: ${errorMessage}`,
          streamingConversationId
        );
        set({ error: errorMessage });
      }
    } finally {
      // Flush remaining buffer
      flushStreamingBuffer(streamingConversationId, set);

      // Mark streaming as complete and remove empty assistant messages
      set((state) => ({
        isLoading: false,
        conversations: state.conversations.map((conv) => {
          if (conv.id !== streamingConversationId) return conv;

          return {
            ...conv,
            messages: conv.messages
              .filter((msg) => {
                // Remove assistant messages that have no content (interrupted before any text arrived)
                if (msg.role === 'assistant' && msg.isStreaming && !msg.content.trim()) {
                  return false;
                }
                return true;
              })
              .map((msg) =>
                msg.isStreaming ? { ...msg, isStreaming: false } : msg
              ),
          };
        }),
      }));

      // Persist
      saveConversations(get().conversations);

      activeAbortController = null;
      activeRequestId = null;
      activeStreamSessionId = null;
    }
  },

  stopGeneration: async () => {
    if (activeAbortController) {
      activeAbortController.abort();
    }

    // Stop audio playback
    audioStreamManager.stop();

    if (activeStreamSessionId && activeRequestId) {
      try {
        const api = getApiClient();
        await api.stopChat(activeStreamSessionId, activeRequestId);
      } catch {
        // Silently fail - the abort already stopped the local stream
      }
    }
  },

  validateConnection: async () => {
    try {
      const api = getApiClient();
      await api.validateApiKey();
      return true;
    } catch {
      return false;
    }
  },

  fetchAdapterInfo: async () => {
    try {
      const api = getApiClient();
      const info = await api.getAdapterInfo();
      return info as AdapterInfo;
    } catch {
      return null;
    }
  },
}));
