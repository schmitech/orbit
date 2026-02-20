import { create } from 'zustand';
import { getApi, ApiClient, ConversationHistoryMessage } from '../api/loader';
import { Message, Conversation, ChatState, FileAttachment, AdapterInfo } from '../types';
import { FileUploadService } from '../services/fileService';
import { debugLog, debugWarn, debugError, logError } from '../utils/debug';
import { AppConfig } from '../utils/config';
import { getDefaultKey, getDefaultAdapterName, getApiUrl, resolveApiUrl, DEFAULT_API_URL, getIsAuthConfigured } from '../utils/runtimeConfig';
import { sanitizeMessageContent, truncateLongContent } from '../utils/contentValidation';
import { audioStreamManager } from '../utils/audioStreamManager';
import { getIsAuthenticated } from '../auth/authState';
import { useLoginPromptStore } from './loginPromptStore';

// Default adapter name from runtime configuration
// getDefaultAdapterName() resolves "default-key" to the first real adapter name from config
const DEFAULT_ADAPTER = getDefaultAdapterName() || getDefaultKey();

// Streaming content buffer for batching rapid updates
// This prevents "Maximum update depth exceeded" errors when rendering complex content like mermaid
const streamingBuffer: Map<string, { content: string; timeoutId: ReturnType<typeof setTimeout> | null }> = new Map();
const STREAMING_BATCH_DELAY = 32; // ms - batch updates within this window (~30fps)

// Stream control state for stop functionality
let activeAbortController: AbortController | null = null;
let activeRequestId: string | null = null;
let activeStreamSessionId: string | null = null;


const buildDefaultConversation = (conversationId: string, sessionId: string, apiUrl: string): Conversation => {
  return {
    id: conversationId,
    sessionId,
    title: 'New Chat',
    messages: [],
    createdAt: new Date(),
    updatedAt: new Date(),
    apiUrl,
    adapterName: undefined,
    adapterLoadError: null
  };
};

// Helper to flush streaming buffer immediately (called when streaming ends)
const flushStreamingBuffer = (conversationId: string, setState: (fn: (state: ChatState) => Partial<ChatState>) => void) => {
  const buffer = streamingBuffer.get(conversationId);
  if (!buffer) return;

  // Clear any pending timeout
  if (buffer.timeoutId) {
    clearTimeout(buffer.timeoutId);
    buffer.timeoutId = null;
  }

  // If there's content to flush, do it
  if (buffer.content) {
    const contentToAppend = buffer.content;
    buffer.content = '';

    setState(state => ({
      conversations: state.conversations.map(conv => {
        if (conv.id !== conversationId) return conv;

        const messages = [...conv.messages];
        const lastMessage = messages[messages.length - 1];

        if (lastMessage && lastMessage.role === 'assistant') {
          messages[messages.length - 1] = {
            ...lastMessage,
            content: lastMessage.content + contentToAppend
          };
        }

        return { ...conv, messages, updatedAt: new Date() };
      })
    }));
  }

  // Clean up buffer entry
  streamingBuffer.delete(conversationId);
};

// Session management utilities
const getOrCreateSessionId = (): string => {
  const stored = localStorage.getItem('chatbot-session-id');
  if (stored) return stored;
  
  const newSessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  localStorage.setItem('chatbot-session-id', newSessionId);
  return newSessionId;
};

const setSessionId = (sessionId: string): void => {
  localStorage.setItem('chatbot-session-id', sessionId);
};

// Counter to ensure unique IDs even if timestamps are identical
let messageCounter = 0;

// Generate unique message IDs
const generateUniqueMessageId = (role: 'user' | 'assistant'): string => {
  const timestamp = Date.now();
  const counter = ++messageCounter;
  const random = Math.random().toString(36).substr(2, 9);
  return `msg_${timestamp}_${counter}_${random}_${role}`;
};

// Generate unique session IDs for conversations
const generateUniqueSessionId = (): string => {
  const timestamp = Date.now();
  const random = Math.random().toString(36).substr(2, 9);
  return `session_${timestamp}_${random}`;
};

const countNonStreamingMessages = (messages: Message[]): number => {
  return messages.filter(m => !m.isThreadMessage && !(m.role === 'assistant' && m.isStreaming)).length;
};

const toDateOrFallback = (
  value: string | number | Date | null | undefined,
  fallback?: Date
): Date => {
  if (value instanceof Date) {
    return new Date(value);
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) {
      return parsed;
    }
  }
  if (typeof value === 'string') {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) {
      return parsed;
    }
  }
  return fallback ? new Date(fallback) : new Date();
};

const convertHistoryMessages = (
  historyMessages: ConversationHistoryMessage[],
  existingMessages: Message[]
): Message[] => {
  const existingByDbId = new Map<string, { message: Message; index: number }>();
  existingMessages.forEach((msg, index) => {
    if (msg.databaseMessageId) {
      existingByDbId.set(msg.databaseMessageId, { message: msg, index });
    }
  });
  const consumedIndices = new Set<number>();

  return historyMessages.map((historyMsg) => {
    const normalizedRole: 'user' | 'assistant' =
      historyMsg.role === 'user' ? 'user' : 'assistant';
    const dbId = typeof historyMsg.message_id === 'string' && historyMsg.message_id.length > 0
      ? historyMsg.message_id
      : undefined;

    let reusedMessage: Message | undefined;
    if (dbId && existingByDbId.has(dbId)) {
      const found = existingByDbId.get(dbId)!;
      reusedMessage = found.message;
      consumedIndices.add(found.index);
    } else {
      for (let i = 0; i < existingMessages.length; i++) {
        if (consumedIndices.has(i)) continue;
        if (existingMessages[i].role === normalizedRole) {
          reusedMessage = existingMessages[i];
          consumedIndices.add(i);
          break;
        }
      }
    }

    const timestamp = historyMsg.timestamp
      ? toDateOrFallback(historyMsg.timestamp, reusedMessage?.timestamp)
      : (reusedMessage?.timestamp ? new Date(reusedMessage.timestamp) : new Date());

    const baseMessage: Message = reusedMessage
      ? {
          ...reusedMessage,
          content: historyMsg.content ?? reusedMessage.content,
          timestamp
        }
      : {
          id: dbId ? `srv_${dbId}` : generateUniqueMessageId(normalizedRole),
          content: historyMsg.content || '',
          role: normalizedRole,
          timestamp
        };

    baseMessage.isStreaming = false;
    if (dbId) {
      baseMessage.databaseMessageId = dbId;
    }

    if (!baseMessage.supportsThreading && historyMsg.metadata && typeof historyMsg.metadata === 'object') {
      const metadata = historyMsg.metadata as Record<string, unknown>;
      const retrievedDocs = metadata?.retrieved_docs;
      if (Array.isArray(retrievedDocs) && retrievedDocs.length > 0) {
        baseMessage.supportsThreading = true;
      }
    }

    return baseMessage;
  });
};

const haveSameMessages = (current: Message[], nextMessages: Message[]): boolean => {
  if (current.length !== nextMessages.length) {
    return false;
  }

  for (let i = 0; i < current.length; i++) {
    const existing = current[i];
    const incoming = nextMessages[i];
    if (existing.role !== incoming.role) {
      return false;
    }
    if (existing.content !== incoming.content) {
      return false;
    }
    if ((existing.databaseMessageId || null) !== (incoming.databaseMessageId || null)) {
      return false;
    }
    if (+existing.timestamp !== +incoming.timestamp) {
      return false;
    }
  }

  return true;
};

// Extended chat state for the store
interface ExtendedChatState extends ChatState {
  sessionId: string;
  createConversation: () => string;
  selectConversation: (id: string) => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;
  deleteAllConversations: () => Promise<void>;
  sendMessage: (content: string, fileIds?: string[], threadId?: string) => Promise<void>;
  createThread: (messageId: string, sessionId: string) => Promise<void>;
  appendToLastMessage: (content: string, conversationId?: string) => void;
  regenerateResponse: (messageId: string) => Promise<void>;
  updateConversationTitle: (id: string, title: string) => void;
  clearError: () => void;
  configureApiSettings: (apiUrl: string, sessionId?: string, adapterName?: string) => Promise<void>;
  getSessionId: () => string;
  cleanupStreamingMessages: () => void;
  canCreateNewConversation: () => boolean;
  getConversationCount: () => number;
  // File management methods
  addFileToConversation: (conversationId: string, file: FileAttachment) => void;
  removeFileFromConversation: (conversationId: string, fileId: string) => Promise<void>;
  loadConversationFiles: (conversationId: string) => Promise<void>;
  syncConversationFiles: (conversationId: string) => Promise<void>;
  syncConversationsWithBackend: () => Promise<void>;
  stopStreaming: () => Promise<void>;
  clearCurrentConversationAdapter: () => void;
}

// API configuration state
let apiConfigured = false;
let currentApiUrl = '';

async function ensureApiConfigured(): Promise<boolean> {
  if (apiConfigured && currentApiUrl) {
    return true;
  }

  try {
    // Load the API dynamically
    const api = await getApi();

    const storedApiUrl = localStorage.getItem('chat-api-url');
    if (storedApiUrl && storedApiUrl === DEFAULT_API_URL) {
      localStorage.removeItem('chat-api-url');
    }
    const apiUrl = storedApiUrl && storedApiUrl !== DEFAULT_API_URL
      ? storedApiUrl
      : getApiUrl();

    const sessionId = getOrCreateSessionId();
    const adapterName = localStorage.getItem('chat-adapter-name') || DEFAULT_ADAPTER;
    api.configureApi(apiUrl, sessionId, adapterName);
    currentApiUrl = apiUrl;
    apiConfigured = true;
    return true;
  } catch (error) {
    logError('Failed to configure API:', error);
    return false;
  }
}

export const useChatStore = create<ExtendedChatState>((set, get) => ({
  conversations: [],
  currentConversationId: null,
  isLoading: false,
  error: null,
  sessionId: getOrCreateSessionId(),

  getSessionId: () => get().sessionId,

  configureApiSettings: async (apiUrl: string, sessionId?: string, adapterName?: string) => {
    const state = get();
    const currentConversation = state.conversations.find(conv => conv.id === state.currentConversationId);

    // Use the conversation's session ID if available, otherwise use the provided sessionId or generate one
    const actualSessionId = currentConversation?.sessionId || sessionId || getOrCreateSessionId();

    if (sessionId) {
      setSessionId(sessionId);
    }
    set({ sessionId: actualSessionId });

    try {
      const api = await getApi();

      if (!adapterName || !adapterName.trim()) {
        throw new Error('Adapter name is required');
      }

      api.configureApi(apiUrl, actualSessionId, adapterName);
      currentApiUrl = apiUrl;
      apiConfigured = true;

      // Load adapter info
      let adapterInfo: AdapterInfo | undefined;
      try {
        const validationClient = new api.ApiClient({
          apiUrl,
          sessionId: null,
          adapterName
        });

        if (typeof validationClient.getAdapterInfo === 'function') {
          adapterInfo = await validationClient.getAdapterInfo();
          debugLog('Adapter info loaded:', adapterInfo);
        }
      } catch (error) {
        debugWarn('Failed to load adapter info:', error);
      }

      // Store adapter name in conversation
      if (currentConversation) {
        set(state => ({
          conversations: state.conversations.map(conv =>
            conv.id === currentConversation.id
              ? {
                  ...conv,
                  adapterName: adapterName,
                  apiUrl: apiUrl,
                  adapterInfo: adapterInfo,
                  adapterLoadError: null,
                  updatedAt: new Date()
                }
              : conv
          )
        }));
      } else if (adapterName && adapterName.trim()) {
        const newId = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        const newSessionId = generateUniqueSessionId();
        set(state => ({
          conversations: [
            ...state.conversations,
            {
              id: newId,
              sessionId: newSessionId,
              title: 'New Conversation',
              messages: [],
              createdAt: new Date(),
              updatedAt: new Date(),
              adapterName: adapterName,
              apiUrl: apiUrl,
              adapterInfo: adapterInfo,
              adapterLoadError: null
            }
          ],
          currentConversationId: newId
        }));
      }
    } catch (error) {
      debugError('Failed to configure API:', error);
      set({ isLoading: false });
      if (error instanceof Error) {
        throw error;
      }
      throw new Error('Failed to configure API settings');
    }

    // Save adapter name to localStorage
    if (adapterName) {
      localStorage.setItem('chat-adapter-name', adapterName);
    } else {
      localStorage.removeItem('chat-adapter-name');
    }

    set({ isLoading: false });
  },

  createConversation: () => {
    const state = get();
    const maxConversations = AppConfig.maxConversations;
    const conversationCount = state.conversations.length;
    const currentConversation = state.currentConversationId
      ? state.conversations.find(conv => conv.id === state.currentConversationId)
      : null;
    
    if (maxConversations !== null && conversationCount >= maxConversations) {
      if (getIsAuthConfigured() && !getIsAuthenticated()) {
        useLoginPromptStore.getState().openLoginPrompt(
          `You've reached the guest limit of ${maxConversations} conversation${maxConversations === 1 ? '' : 's'}. Sign in to unlock more conversations.`
        );
        throw new Error('Guest conversation limit reached');
      }
      const limitMessage = `Maximum of ${maxConversations} conversations reached. Please delete an existing conversation before starting a new one.`;
      set({ error: limitMessage });
      throw new Error(limitMessage);
    }

    if (currentConversation && currentConversation.messages.length === 0) {
      const emptyMessage = 'Finish or delete the current conversation before starting a new one.';
      set({ error: emptyMessage });
      throw new Error(emptyMessage);
    }

    const id = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const newSessionId = generateUniqueSessionId();
    const defaultApiUrl = getApiUrl();

    const newConversation: Conversation = {
      id,
      sessionId: newSessionId,
      title: 'New Chat',
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date(),
      apiUrl: defaultApiUrl,
      adapterName: undefined,
      adapterLoadError: null
    };

    // Update state with new conversation and switch to its session
    set((state: ExtendedChatState) => ({
      conversations: [newConversation, ...state.conversations],
      currentConversationId: id,
      sessionId: newSessionId
    }));

    // Wait for adapter selection before configuring API
    debugLog('Waiting for the user to select an adapter for the new conversation.');

    // Save to localStorage
    setTimeout(() => {
      const currentState = get();
      localStorage.setItem('chat-state', JSON.stringify({
        conversations: currentState.conversations,
        currentConversationId: currentState.currentConversationId
      }));
    }, 0);

    return id;
  },

  selectConversation: async (id: string) => {
    const conversation = get().conversations.find(conv => conv.id === id);
    if (conversation) {
      // Check if this conversation has any streaming messages
      const hasStreamingMessages = conversation.messages.some(
        msg => msg.role === 'assistant' && msg.isStreaming
      );
      
      // Switch to the conversation's session ID
      set({ 
        currentConversationId: id,
        sessionId: conversation.sessionId,
        // Set isLoading based on whether the current conversation has streaming messages
        isLoading: hasStreamingMessages
      });
      
      // Use conversation's stored adapter and URL
      const conversationApiUrl = conversation.apiUrl || getApiUrl();
      const conversationAdapterName = conversation.adapterName;

      // Reconfigure API with the conversation's session ID and adapter
      const isConfigured = await ensureApiConfigured();
      if (isConfigured && conversationAdapterName) {
        const api = await getApi();
        api.configureApi(conversationApiUrl, conversation.sessionId, conversationAdapterName);

        // Load adapter info if not already loaded
        if (!conversation.adapterInfo) {
          try {
            const adapterClient = new api.ApiClient({
              apiUrl: conversationApiUrl,
              sessionId: null,
              adapterName: conversationAdapterName
            });

            if (typeof adapterClient.getAdapterInfo === 'function') {
              const adapterInfo = await adapterClient.getAdapterInfo();
              debugLog('Adapter info loaded for conversation:', adapterInfo);

              set(state => ({
                conversations: state.conversations.map(conv =>
                  conv.id === id
                    ? { ...conv, adapterInfo: adapterInfo, adapterLoadError: null, updatedAt: new Date() }
                    : conv
                )
              }));

              setTimeout(() => {
                const currentState = get();
                localStorage.setItem('chat-state', JSON.stringify({
                  conversations: currentState.conversations,
                  currentConversationId: currentState.currentConversationId
                }));
              }, 0);
            }
          } catch (error) {
            debugWarn('Failed to load adapter info for conversation:', error);
          }
        }
      }

      // Don't auto-sync files when switching conversations
      // Files are only loaded when explicitly uploaded to a conversation
      // This ensures full segregation - files from one conversation don't appear in others
      // await get().syncConversationFiles(id);
    }
    
    // Save to localStorage
    setTimeout(() => {
      const currentState = get();
      localStorage.setItem('chat-state', JSON.stringify({
        conversations: currentState.conversations,
        currentConversationId: currentState.currentConversationId
      }));
    }, 0);
  },

  deleteConversation: async (id: string) => {
    const state = get();
    const conversation = state.conversations.find(conv => conv.id === id);

    debugLog(`🗑️ Deleting conversation ${id}:`, {
      conversationId: id,
      sessionId: conversation?.sessionId,
      title: conversation?.title,
      messageCount: conversation?.messages.length,
      fileCount: conversation?.attachedFiles?.length || 0
    });

    // Stop audio playback if deleting the current conversation
    if (state.currentConversationId === id) {
      audioStreamManager.stop();
    }

    // If conversation has a session ID, delete conversation and files in one call
    if (conversation?.sessionId) {
      try {
        // Ensure API is properly configured first
        const isConfigured = await ensureApiConfigured();
        if (!isConfigured) {
          logError('Failed to configure API for conversation deletion');
          // Continue with local deletion even if API configuration fails
        } else {
          const conversationApiUrl = conversation.apiUrl || getApiUrl();
          const conversationAdapterName = conversation.adapterName;

          if (!conversationAdapterName) {
            debugWarn(`Skipping server deletion for conversation ${id}: adapter not configured`);
          } else {
            debugLog(`Using conversation's adapter for deletion: ${conversationAdapterName} (conversation: ${id})`);
          }

          // Create API client with the conversation's session ID and adapter
          const api = await getApi();
          const apiClient: ApiClient = new api.ApiClient({
            apiUrl: conversationApiUrl,
            sessionId: conversation.sessionId,
            adapterName: conversationAdapterName
          });

          // Extract file IDs from attached files
          const fileIds = conversation?.attachedFiles?.map(f => f.file_id) || [];

          debugLog(`🔧 Calling deleteConversationWithFiles for session: ${conversation.sessionId}`);
          debugLog(`🔧 File IDs to delete: ${fileIds.join(', ') || 'none'}`);

          // Delete conversation and all associated files in one call
          if (apiClient.deleteConversationWithFiles) {
            const result = await apiClient.deleteConversationWithFiles(conversation.sessionId, fileIds);
            debugLog(`✅ Deleted conversation and files for session: ${conversation.sessionId}`, result);
            debugLog(`   - Deleted ${result.deleted_messages} messages`);
            debugLog(`   - Deleted ${result.deleted_files} files`);
            if (result.file_deletion_errors && result.file_deletion_errors.length > 0) {
              debugWarn(`   - Errors deleting files: ${result.file_deletion_errors.join(', ')}`);
            }
          } else {
            debugWarn(`⚠️ deleteConversationWithFiles method not available on API client`);
          }
        }
      } catch (error) {
        logError('Failed to clear conversation history from server:', error);
        // Continue with local deletion even if server clear fails
      }
    } else {
      debugWarn(`⚠️ No session ID found for conversation ${id}, skipping server-side deletion`);
    }

    set((state: ExtendedChatState) => {
      const filtered = state.conversations.filter((c: Conversation) => c.id !== id);
      const newCurrentId = state.currentConversationId === id 
        ? (filtered[0]?.id || null) 
        : state.currentConversationId;

      // If all conversations are deleted, create a new default conversation
      if (filtered.length === 0) {
        const defaultConversationId = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        const defaultSessionId = generateUniqueSessionId();
        const defaultApiUrl = getApiUrl();
        const defaultConversation: Conversation = {
          id: defaultConversationId,
          sessionId: defaultSessionId,
          title: 'New Chat',
          messages: [],
          createdAt: new Date(),
          updatedAt: new Date(),
          apiUrl: defaultApiUrl,
          adapterName: undefined,
          adapterLoadError: null
        };

        debugLog('Waiting for user to select an adapter after deleting all conversations.');

        // Save to localStorage
        setTimeout(() => {
          localStorage.setItem('chat-state', JSON.stringify({
            conversations: [defaultConversation],
            currentConversationId: defaultConversationId
          }));
        }, 0);

        return {
          conversations: [defaultConversation],
          currentConversationId: defaultConversationId,
          sessionId: defaultSessionId
        };
      }

      // Save to localStorage
      setTimeout(() => {
        localStorage.setItem('chat-state', JSON.stringify({
          conversations: filtered,
          currentConversationId: newCurrentId
        }));
      }, 0);

      return {
        conversations: filtered,
        currentConversationId: newCurrentId
      };
    });
  },

  deleteAllConversations: async () => {
    const state = get();
    const conversationsToDelete = [...state.conversations];

    debugLog(`🗑️ Deleting all conversations (${conversationsToDelete.length} total)`);

    // Stop any ongoing audio playback when clearing all conversations
    audioStreamManager.stop();

    // Delete all conversations from server in the background
    const deletionTasks = conversationsToDelete.map(async (conversation) => {
      if (!conversation?.sessionId) {
        return;
      }
      try {
        const isConfigured = await ensureApiConfigured();
        if (!isConfigured) {
          logError('Failed to configure API for conversation deletion');
          return;
        }

        const conversationApiUrl = resolveApiUrl(conversation.apiUrl);
        const conversationAdapterName = conversation.adapterName;

        if (!conversationAdapterName) {
          debugLog(`Skipping server deletion for conversation ${conversation.id}: adapter not configured`);
          return;
        }

        const api = await getApi();
        const apiClient: ApiClient = new api.ApiClient({
          apiUrl: conversationApiUrl,
          sessionId: conversation.sessionId,
          adapterName: conversationAdapterName
        });

        const fileIds = conversation?.attachedFiles?.map(f => f.file_id) || [];

        if (apiClient.deleteConversationWithFiles) {
          await apiClient.deleteConversationWithFiles(conversation.sessionId, fileIds);
          debugLog(`✅ Deleted conversation ${conversation.id} and files`);
        } else {
          debugWarn(`deleteConversationWithFiles not available for conversation ${conversation.id}`);
        }
      } catch (error) {
        logError(`Failed to delete conversation ${conversation.id} from server:`, error);
      }
    });

    Promise.allSettled(deletionTasks).then(results => {
      const failures = results.filter(result => result.status === 'rejected');
      if (failures.length > 0) {
        logError(`Some conversations failed to delete from server: ${failures.length}`, failures);
      }
    });

    // Create a new default conversation after deleting all
    const defaultConversationId = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const defaultSessionId = generateUniqueSessionId();
    const defaultApiUrl = getApiUrl();
    const defaultConversation: Conversation = {
      id: defaultConversationId,
      sessionId: defaultSessionId,
      title: 'New Chat',
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date(),
      apiUrl: defaultApiUrl,
      adapterLoadError: null
    };

    debugLog('Default conversation will wait for adapter selection.');

    // Update state with empty conversations array and new default conversation
    set({
      conversations: [defaultConversation],
      currentConversationId: defaultConversationId,
      sessionId: defaultSessionId
    });
    // Save to localStorage
    setTimeout(() => {
      localStorage.setItem('chat-state', JSON.stringify({
        conversations: [defaultConversation],
        currentConversationId: defaultConversationId
      }));
    }, 0);
  },

  sendMessage: async (content: string, fileIds?: string[], threadId?: string) => {
    try {
      // Prevent multiple simultaneous requests
      if (get().isLoading) {
        debugWarn('Another request is already in progress');
        return;
      }

      // Ensure API is configured
      const isConfigured = await ensureApiConfigured();
      if (!isConfigured) {
        throw new Error('API not properly configured. Please configure API settings first.');
      }

      let conversationId = get().currentConversationId;
      
      // Create a new conversation if none exists
      if (!conversationId) {
        conversationId = get().createConversation();
      }

      // Get file attachments for the message from conversation's attachedFiles
      const conversation = get().conversations.find(conv => conv.id === conversationId);
      if (!conversation) {
        throw new Error('Conversation not found');
      }

      // Enforce guest conversation-count gate even for restored/local persisted state.
      const maxConversations = AppConfig.maxConversations;
      if (
        getIsAuthConfigured() &&
        !getIsAuthenticated() &&
        maxConversations !== null &&
        get().conversations.length > maxConversations
      ) {
        useLoginPromptStore.getState().openLoginPrompt(
          `You've reached the guest limit of ${maxConversations} conversation${maxConversations === 1 ? '' : 's'}. Sign in to continue chatting.`
        );
        set({ isLoading: false });
        return;
      }

      const fileAttachments: FileAttachment[] = fileIds
        ? fileIds
            .map(fileId => {
              // Try to find in conversation's attachedFiles first
              const existingFile = conversation?.attachedFiles?.find(f => f.file_id === fileId);
              if (existingFile) {
                return existingFile;
              }
              // Fallback: create minimal attachment
              return {
                file_id: fileId,
                filename: '',
                mime_type: '',
                file_size: 0
              };
            })
            .filter((f): f is FileAttachment => f !== undefined)
        : [];

      // If fileIds were provided, ensure they're added to conversation's attachedFiles
      if (fileAttachments.length > 0) {
        fileAttachments.forEach(file => {
          get().addFileToConversation(conversationId, file);
        });
      }

      // Resolve thread context if a threadId was provided
      const activeThreadId = threadId || null;
      let threadParentMessage: Message | undefined;
      let threadSessionId: string | null = null;

      if (activeThreadId) {
        threadParentMessage = conversation.messages.find(
          msg => msg.threadInfo?.thread_id === activeThreadId
        );

        if (!threadParentMessage) {
          throw new Error('Thread metadata not found. Please recreate the thread from this message.');
        }

        threadSessionId = threadParentMessage.threadInfo?.thread_session_id || null;
        if (!threadSessionId) {
          throw new Error('Thread session is missing. Please recreate the thread from this message.');
        }
      }

      // Enforce message limits before creating new entries
      const nonStreamingMessages = countNonStreamingMessages(conversation.messages);
      const maxMessagesPerConversation = AppConfig.maxMessagesPerConversation;
      if (maxMessagesPerConversation !== null && nonStreamingMessages >= maxMessagesPerConversation) {
        if (getIsAuthConfigured() && !getIsAuthenticated()) {
          useLoginPromptStore.getState().openLoginPrompt(
            `You've reached the guest limit of ${maxMessagesPerConversation} messages per conversation. Sign in to send more messages.`
          );
        }
        debugWarn(`[chatStore] Conversation ${conversationId} reached the message limit (${maxMessagesPerConversation}).`);
        set({ isLoading: false });
        return;
      }

      const maxTotalMessages = AppConfig.maxTotalMessages;
      if (maxTotalMessages !== null) {
        const totalMessages = get().conversations.reduce(
          (total, conv) => total + countNonStreamingMessages(conv.messages),
          0
        );
        if (totalMessages >= maxTotalMessages) {
          if (getIsAuthConfigured() && !getIsAuthenticated()) {
            useLoginPromptStore.getState().openLoginPrompt(
              `You've reached the guest limit of ${maxTotalMessages} total messages. Sign in to continue chatting.`
            );
          }
          debugWarn(`[chatStore] Workspace reached the total message limit (${maxTotalMessages}).`);
          set({ isLoading: false });
          return;
        }
      }

      // Add user message and assistant streaming message in a single atomic update
      // Store file attachments with the message if provided
      const userMessage: Message = {
        id: generateUniqueMessageId('user'),
        content,
        role: 'user',
        timestamp: new Date(),
        attachments: fileAttachments.length > 0 ? fileAttachments : undefined
      };

      const assistantMessageId = generateUniqueMessageId('assistant');
      const assistantMessage: Message = {
        id: assistantMessageId,
        content: '',
        role: 'assistant',
        timestamp: new Date(),
        isStreaming: true
      };

      if (activeThreadId && threadParentMessage) {
        userMessage.isThreadMessage = true;
        userMessage.threadId = activeThreadId;
        userMessage.parentMessageId = threadParentMessage.id;

        assistantMessage.isThreadMessage = true;
        assistantMessage.threadId = activeThreadId;
        assistantMessage.parentMessageId = threadParentMessage.id;

        const maxMessagesPerThread = AppConfig.maxMessagesPerThread;
        if (maxMessagesPerThread !== null) {
          const existingThreadMessages = conversation.messages.filter(msg => {
            if (!msg.isThreadMessage) return false;
            const matchesThread =
              msg.threadId === activeThreadId ||
              msg.parentMessageId === threadParentMessage.id;
            return matchesThread && !(msg.role === 'assistant' && msg.isStreaming);
          });
          if (existingThreadMessages.length >= maxMessagesPerThread) {
            if (getIsAuthConfigured() && !getIsAuthenticated()) {
              useLoginPromptStore.getState().openLoginPrompt(
                `You've reached the guest limit of ${maxMessagesPerThread} messages per thread. Sign in to continue this thread.`
              );
            }
            debugWarn(`[chatStore] Thread ${activeThreadId} reached the message limit (${maxMessagesPerThread}).`);
            set({ isLoading: false });
            return;
          }
        }
      }

      // Single atomic update for both messages
      set(state => {
        // Clean up any existing streaming messages first
        const currentConv = state.conversations.find(c => c.id === conversationId);
        const streamingMsgs = currentConv?.messages.filter(m => m.role === 'assistant' && m.isStreaming) || [];
        if (streamingMsgs.length > 0) {
          debugWarn(`Cleaning up ${streamingMsgs.length} existing streaming messages`);
        }

        const updatedConversations = state.conversations.map(conv => {
          if (conv.id !== conversationId) {
            return {
              ...conv,
              messages: conv.messages
            };
          }

          const existingMessages = conv.messages.filter(m => !(m.role === 'assistant' && m.isStreaming));
          return {
            ...conv,
            messages: [
              ...existingMessages,
              userMessage,
              assistantMessage
            ],
            updatedAt: new Date(),
            title: conv.messages.length === 0 
              ? content.slice(0, 50) + (content.length > 50 ? '...' : '')
              : conv.title
          };
        });

        return {
          conversations: updatedConversations,
          isLoading: true,
          error: null
        };
      });

      // Store conversationId in a variable so we can use it even if user switches conversations
      const streamingConversationId = conversationId;
      let receivedAnyText = false;

      // Reset audio stream manager for new response
      audioStreamManager.reset();

      try {
      // Ensure API is configured with the current conversation's session ID and API key
      // Get fresh conversation state to ensure we have the latest API key
      const currentConversation = get().conversations.find(conv => conv.id === streamingConversationId);
      if (!currentConversation) {
        throw new Error('Conversation not found');
      }
      
      // Check if conversation has adapter configured
      if (!currentConversation.adapterName) {
        debugWarn(`[sendMessage] Conversation ${streamingConversationId} has no adapter name`);
        throw new Error('Adapter not configured for this conversation. Please select an adapter first.');
      }
      debugLog(`[sendMessage] Using adapter for conversation ${streamingConversationId}: ${currentConversation.adapterName}`);

      // Use conversation's stored adapter and URL
      const conversationApiUrl = resolveApiUrl(currentConversation.apiUrl);
      const conversationAdapterName = currentConversation.adapterName;

      // Determine if we're in thread mode and use appropriate session ID
      const activeThreadId = threadId || null;
      const activeSessionId = threadSessionId || currentConversation.sessionId;

      const api = await getApi();
      api.configureApi(
        conversationApiUrl,
        activeSessionId,
        conversationAdapterName
      );
      
      if (activeThreadId && activeSessionId !== currentConversation.sessionId) {
        debugLog(`[chatStore] Thread mode: using thread session ${activeSessionId} (original: ${currentConversation.sessionId})`);
      }
        
      debugLog(`[chatStore] Starting streamChat with fileIds:`, fileIds);

        // Extract audio parameters from conversation or use defaults
        const conversation = get().conversations.find(conv => conv.id === streamingConversationId);

        // Determine if audio should be returned based on adapter name or explicit settings
        const isVoiceAdapter = conversation?.adapterInfo?.adapter_name?.includes('voice') ||
                               conversation?.adapterInfo?.adapter_name?.includes('audio') ||
                               conversation?.adapterInfo?.adapter_name?.includes('multilingual');

        // Get global voice setting from localStorage
        const getGlobalVoiceEnabled = (): boolean => {
          try {
            const saved = localStorage.getItem('chat-settings');
            if (saved) {
              const settings = JSON.parse(saved);
              return settings.voiceEnabled === true;
            }
          } catch (error) {
            debugWarn('Failed to read global voice setting:', error);
          }
          return false;
        };

        // Get audio settings with fallbacks: conversation-specific > global setting > adapter detection
        const audioSettings = conversation?.audioSettings;
        const globalVoiceEnabled = getGlobalVoiceEnabled();
        const returnAudio = audioSettings?.enabled ?? globalVoiceEnabled ?? isVoiceAdapter;
        const ttsVoice = audioSettings?.ttsVoice || undefined; // Let backend use adapter/config defaults
        const language = audioSettings?.language || 'en-US';
        const audioFormat = audioSettings?.audioFormat;

        debugLog(`[chatStore] Audio settings:`, {
          returnAudio,
          ttsVoice,
          language,
          audioFormat,
          isVoiceAdapter,
          adapterName: conversation?.adapterInfo?.adapter_name
        });

        // activeThreadId and activeSessionId are already determined above
        // Use them for the streamChat call

        // Set up abort controller for stop functionality
        const abortController = new AbortController();
        activeAbortController = abortController;
        activeStreamSessionId = activeSessionId;
        activeRequestId = null; // Will be set when we receive the first chunk

        for await (const response of api.streamChat(
          content,
          true,
          fileIds,
          activeThreadId || undefined, // threadId for follow-up questions
          undefined, // audioInput - for STT (to be implemented)
          undefined, // audioFormat for input
          language,
          returnAudio,
          ttsVoice,
          undefined, // sourceLanguage
          undefined // targetLanguage
        )) {
          // Capture request_id from server's first chunk (for stop functionality)
          if (response.request_id && !activeRequestId) {
            activeRequestId = response.request_id;
            debugLog(`[chatStore] >>> CAPTURED request_id for stop: ${response.request_id}, session=${activeStreamSessionId}`);
          }
          debugLog(`[chatStore] Received stream chunk:`, {
            text: response.text?.substring(0, 50),
            done: response.done,
            request_id: response.request_id,  // Debug: show if request_id is present
            hasAudio: !!response.audio,
            hasAudioChunk: !!response.audio_chunk,
            audioFormat: response.audioFormat,
            audioLength: response.audio?.length,
            chunkIndex: response.chunk_index
          });
          
          // Handle streaming audio chunks
          if (response.audio_chunk) {
            debugLog(`[chatStore] Received audio chunk:`, {
              chunk_index: response.chunk_index,
              audioFormat: response.audioFormat,
              audioLength: response.audio_chunk?.length
            });

            // Immediately queue chunk for real-time playback
            const chunkIndex = response.chunk_index ?? 0;
            audioStreamManager.addChunk({
              audio: response.audio_chunk,
              audioFormat: response.audioFormat || 'opus',
              chunkIndex: chunkIndex
            });

          }
          
          if (response.text) {
            // Sanitize text to remove any base64 audio data that might have leaked into content
            const sanitizedText = sanitizeMessageContent(response.text);
            if (sanitizedText) {
              // Always append to the conversation that initiated the stream, not the current one
              get().appendToLastMessage(sanitizedText, streamingConversationId);
              receivedAnyText = true;
              // Text appears immediately as chunks arrive from server
            } else if (response.text.length > 100) {
              // If text was filtered out but was long, log a warning
              debugWarn('[chatStore] Filtered out potential base64 audio data from message content');
            }
          }
          
          // Handle final audio response if present (fallback for non-streaming audio)
          if (response.audio && response.done) {
            set(state => ({
              conversations: state.conversations.map(conv => {
                if (conv.id !== streamingConversationId) return conv;
                
                const messages = [...conv.messages];
                const lastMessage = messages[messages.length - 1];
                
                // Update the last assistant message with audio data
                if (lastMessage && lastMessage.role === 'assistant') {
                  messages[messages.length - 1] = {
                    ...lastMessage,
                    audio: response.audio,
                    audioFormat: response.audioFormat || 'mp3'
                  };
                }
                
                return {
                  ...conv,
                  messages,
                  updatedAt: new Date()
                };
              })
            }));
          }
          
          if (response.done) {
            debugLog(`[chatStore] Stream completed, receivedAnyText:`, receivedAnyText);
            debugLog(`[chatStore] Done chunk received:`, { 
              hasThreading: !!response.threading,
              threading: response.threading,
              assistantMessageId 
            });
            
            // Check for threading metadata in the response
            const threadingInfo = response.threading;
            if (threadingInfo && threadingInfo.supports_threading) {
              // Update the assistant message with threading support and database message ID
              set(state => ({
                conversations: state.conversations.map(conv => {
                  if (conv.id !== streamingConversationId) return conv;
                  
                  return {
                    ...conv,
                    messages: conv.messages.map(msg =>
                      msg.id === assistantMessageId
                        ? { 
                            ...msg, 
                            supportsThreading: true,
                            databaseMessageId: threadingInfo.message_id  // Store database message ID
                          }
                        : msg
                    ),
                    updatedAt: new Date()
                  };
                })
              }));
              
              debugLog(`[chatStore] Message ${assistantMessageId} marked as supporting threading`, {
                message_id: threadingInfo.message_id,
                session_id: threadingInfo.session_id,
                databaseMessageId: threadingInfo.message_id
              });
            }
            
            break;
          }
        }

        // If no text received and not cancelled by user, show error
        if (!receivedAnyText && !abortController.signal.aborted) {
          debugWarn(`[chatStore] No text received from stream, showing error message`);
          get().appendToLastMessage('No response received from the server. Please try again later.', streamingConversationId);
        } else if (!receivedAnyText && abortController.signal.aborted) {
          debugLog('[chatStore] Stream cancelled before text received - not showing error');
        }
      } catch (error) {
        // Check if this was a user-initiated abort
        const isAbortError = error instanceof Error && (
          error.name === 'AbortError' ||
          error.message === 'Stream cancelled by user' ||
          error.message.includes('aborted')
        );

        if (isAbortError) {
          debugLog('[chatStore] Stream was cancelled by user');
          // Don't show error message for user-initiated cancellation
          // Mark as received to avoid "no text received" warning
          receivedAnyText = true;
        } else {
          logError('Chat API error:', error);
          // Extract meaningful error message for the user
          let errorMessage = 'Sorry, there was an error processing your request.';
          if (error instanceof Error) {
            // Handle moderation/server errors - show the actual message
            if (error.message.startsWith('Server error:')) {
              // Extract the message after "Server error: "
              errorMessage = error.message.substring('Server error: '.length);
            } else if (error.message.includes('Could not connect') || error.message.includes('timed out')) {
              errorMessage = error.message;
            }
          }
          get().appendToLastMessage(errorMessage, streamingConversationId);
        }
      }

      // Clean up stream control state
      activeAbortController = null;
      activeRequestId = null;
      activeStreamSessionId = null;

      // Flush any remaining buffered content before marking streaming as complete
      flushStreamingBuffer(streamingConversationId, set);

      // Mark message as no longer streaming and stop loading
      // Use the conversation that initiated the stream, not the current one
      set(state => {
        // Update the streaming conversation's messages
        const updatedConversations = state.conversations.map(conv =>
          conv.id === streamingConversationId
            ? {
                ...conv,
                messages: conv.messages.map(msg =>
                  msg.id === assistantMessageId
                    ? { ...msg, isStreaming: false }
                    : msg
                ),
                updatedAt: new Date()
              }
            : conv
        );
        
        // Check if the current conversation has any streaming messages AFTER the update
        const currentConv = updatedConversations.find(conv => conv.id === state.currentConversationId);
        const hasStreamingMessages = currentConv 
          ? currentConv.messages.some(msg => msg.role === 'assistant' && msg.isStreaming)
          : false;
        
        return {
          conversations: updatedConversations,
          isLoading: hasStreamingMessages
        };
      });

      // Save to localStorage
      setTimeout(() => {
        const currentState = get();
        localStorage.setItem('chat-state', JSON.stringify({
          conversations: currentState.conversations,
          currentConversationId: currentState.currentConversationId
        }));
      }, 0);

    } catch (error) {
      logError('Chat store error:', error);
      set(() => ({
        isLoading: false,
        error: `Failed to send message: ${error instanceof Error ? error.message : 'Unknown error'}`
      }));
    }
  },

  createThread: async (messageId: string, sessionId: string) => {
    try {
      // Get the conversation to use its API key/adapter and URL
      const conversation = get().conversations.find(conv => conv.sessionId === sessionId);
      if (!conversation) {
        throw new Error('Conversation not found for session');
      }
      
      if (!conversation.adapterName) {
        throw new Error('Adapter not configured for this conversation');
      }

      // Find the message to get its database message ID
      const message = conversation.messages.find(msg => msg.id === messageId);
      if (!message) {
        throw new Error('Message not found');
      }

      // Use database message ID if available, otherwise fall back to client message ID
      const dbMessageId = message.databaseMessageId || messageId;

      const conversationApiUrl = resolveApiUrl(conversation.apiUrl || getApiUrl());
      const conversationAdapterName = conversation.adapterName;

      const api = await getApi();
      const apiClient = new api.ApiClient({
        apiUrl: conversationApiUrl,
        sessionId: sessionId,
        adapterName: conversationAdapterName
      });

      const threadService = new (await import('../services/threadService')).ThreadService(apiClient);
      const threadInfo = await threadService.createThread(dbMessageId, sessionId);

      // Update the message with thread info
      set(state => ({
        conversations: state.conversations.map(conv => {
          if (conv.sessionId !== sessionId) return conv;
          
          return {
            ...conv,
            messages: conv.messages.map(msg => {
              if (msg.id === messageId) {
                return {
                  ...msg,
                  threadInfo: threadInfo,
                  supportsThreading: true
                };
              }
              return msg;
            }),
            currentThreadId: undefined,
            currentThreadSessionId: undefined
          };
        })
      }));

      debugLog(`[chatStore] Created thread ${threadInfo.thread_id} for message ${messageId}`);
    } catch (error) {
      logError('Failed to create thread:', error);
      throw error;
    }
  },

  appendToLastMessage: (content: string, conversationId?: string) => {
    // Sanitize content to prevent base64 audio data from being displayed
    const sanitizedContent = sanitizeMessageContent(content);
    if (!sanitizedContent && content) {
      // Content was filtered out - log warning but don't append
      debugWarn('[chatStore] Filtered out base64 audio data from message content');
      return;
    }

    // Truncate extremely long content to prevent UI issues
    const finalContent = truncateLongContent(sanitizedContent);

    // Get the target conversation ID
    const targetConversationId = conversationId || get().currentConversationId;
    if (!targetConversationId) return;

    // Batch rapid updates to prevent "Maximum update depth exceeded" errors
    // This is especially important for complex content like mermaid diagrams
    const bufferKey = targetConversationId;
    const existing = streamingBuffer.get(bufferKey);

    if (existing) {
      // Accumulate content in buffer
      existing.content += finalContent;
      // Clear existing timeout - we'll set a new one
      if (existing.timeoutId) {
        clearTimeout(existing.timeoutId);
      }
    } else {
      // Create new buffer entry
      streamingBuffer.set(bufferKey, { content: finalContent, timeoutId: null });
    }

    // Function to flush the buffer to state
    const flushBuffer = () => {
      const buffer = streamingBuffer.get(bufferKey);
      if (!buffer || !buffer.content) return;

      const contentToAppend = buffer.content;
      buffer.content = ''; // Clear buffer
      buffer.timeoutId = null;

      set(state => {
        return {
          conversations: state.conversations.map(conv => {
            // Update the conversation that's streaming, not just the current one
            if (conv.id !== targetConversationId) return conv;

            const messages = [...conv.messages];
            const lastMessage = messages[messages.length - 1];

            // Only append to streaming assistant messages
            if (lastMessage && lastMessage.role === 'assistant' && lastMessage.isStreaming) {
              messages[messages.length - 1] = {
                ...lastMessage,
                content: lastMessage.content + contentToAppend
              };
            }

            return {
              ...conv,
              messages,
              updatedAt: new Date()
            };
          })
        };
      });
    };

    // Set timeout to flush buffer
    const buffer = streamingBuffer.get(bufferKey)!;
    buffer.timeoutId = setTimeout(flushBuffer, STREAMING_BATCH_DELAY);
  },

  regenerateResponse: async (messageId: string) => {
    try {
      // Prevent multiple simultaneous requests
      if (get().isLoading) {
        debugWarn('Another request is already in progress');
        return;
      }

      const isConfigured = await ensureApiConfigured();
      if (!isConfigured) {
        throw new Error('API not properly configured');
      }

      const state = get();
      const currentConv = state.conversations.find(c => c.id === state.currentConversationId);
      if (!currentConv) return;

      const messageIndex = currentConv.messages.findIndex(m => m.id === messageId);
      if (messageIndex === -1) return;

      const userMessage = currentConv.messages[messageIndex - 1];
      if (!userMessage || userMessage.role !== 'user') return;
      const attachmentIds = (userMessage.attachments || [])
        .map(file => file.file_id)
        .filter((fileId): fileId is string => typeof fileId === 'string' && fileId.length > 0);

      // Remove the old assistant message and add a new streaming one
      const newAssistantMessageId = generateUniqueMessageId('assistant');
      set(state => ({
        conversations: state.conversations.map(conv =>
          conv.id === state.currentConversationId
            ? {
                ...conv,
                messages: [
                  ...conv.messages.slice(0, messageIndex),
                  {
                    id: newAssistantMessageId,
                    content: '',
                    role: 'assistant' as const,
                    timestamp: new Date(),
                    isStreaming: true
                  }
                ],
                updatedAt: new Date()
              }
            : conv
        ),
        isLoading: true,
        error: null
      }));

      // Store the conversation ID that's regenerating at the start
      const regeneratingConversationId = state.currentConversationId;
      if (!regeneratingConversationId) {
        throw new Error('No conversation selected');
      }
      let receivedAnyText = false;

      try {
        // Ensure API is configured with the current conversation's session ID and API key
        const currentConversation = get().conversations.find(conv => conv.id === regeneratingConversationId);
        if (!currentConversation) {
          throw new Error('Conversation not found');
        }
        
        if (!currentConversation.adapterName) {
          throw new Error('Adapter not configured for this conversation. Please select an adapter first.');
        }

        if (currentConversation.sessionId) {
          const conversationApiUrl = resolveApiUrl(currentConversation.apiUrl);
          const conversationAdapterName = currentConversation.adapterName;

          const api = await getApi();
          api.configureApi(
            conversationApiUrl,
            currentConversation.sessionId,
            conversationAdapterName
          );
        }
        
        const api = await getApi();

        // Extract audio parameters for regeneration (same as sendMessage)
        const regeneratingConv = get().conversations.find(conv => conv.id === regeneratingConversationId);
        const isVoiceAdapter = regeneratingConv?.adapterInfo?.adapter_name?.includes('voice') ||
                               regeneratingConv?.adapterInfo?.adapter_name?.includes('audio') ||
                               regeneratingConv?.adapterInfo?.adapter_name?.includes('multilingual');
        
        // Get global voice setting from localStorage
        const getGlobalVoiceEnabled = (): boolean => {
          try {
            const saved = localStorage.getItem('chat-settings');
            if (saved) {
              const settings = JSON.parse(saved);
              return settings.voiceEnabled === true;
            }
          } catch (error) {
            debugWarn('Failed to read global voice setting:', error);
          }
          return false;
        };
        
        const audioSettings = regeneratingConv?.audioSettings;
        const globalVoiceEnabled = getGlobalVoiceEnabled();
        const returnAudio = audioSettings?.enabled ?? globalVoiceEnabled ?? isVoiceAdapter;
        const ttsVoice = audioSettings?.ttsVoice || undefined; // Let backend use adapter/config defaults
        const language = audioSettings?.language || 'en-US';

        for await (const response of api.streamChat(
          userMessage.content,
          true,
          attachmentIds.length > 0 ? attachmentIds : undefined, // Preserve files from original question
          undefined, // threadId
          undefined, // audioInput
          undefined, // audioFormat for input
          language,
          returnAudio,
          ttsVoice
        )) {
          if (response.text) {
            // Sanitize text to remove any base64 audio data that might have leaked into content
            const sanitizedText = sanitizeMessageContent(response.text);
            if (sanitizedText) {
              // Always append to the conversation that initiated the regenerate, not the current one
              get().appendToLastMessage(sanitizedText, regeneratingConversationId);
              receivedAnyText = true;
              // Text appears immediately as chunks arrive from server
            } else if (response.text.length > 100) {
              // If text was filtered out but was long, log a warning
              debugWarn('[chatStore] Filtered out potential base64 audio data from regenerated message content');
            }
          }

          // Handle audio response if present
          if (response.audio && response.done) {
            set(state => ({
              conversations: state.conversations.map(conv => {
                if (conv.id !== regeneratingConversationId) return conv;

                const messages = [...conv.messages];
                const lastMessage = messages[messages.length - 1];

                // Update the last assistant message with audio data
                if (lastMessage && lastMessage.role === 'assistant') {
                  messages[messages.length - 1] = {
                    ...lastMessage,
                    audio: response.audio,
                    audioFormat: response.audioFormat || 'mp3'
                  };
                }

                return {
                  ...conv,
                  messages,
                  updatedAt: new Date()
                };
              })
            }));
          }

          if (response.done) {
            break;
          }
        }

        if (!receivedAnyText) {
          get().appendToLastMessage('No response received from the server. Please try again later.', regeneratingConversationId);
        }
      } catch (error) {
        logError('Regenerate API error:', error);
        // Extract meaningful error message for the user
        let errorMessage = 'Sorry, there was an error regenerating the response.';
        if (error instanceof Error) {
          // Handle moderation/server errors - show the actual message
          if (error.message.startsWith('Server error:')) {
            errorMessage = error.message.substring('Server error: '.length);
          } else if (error.message.includes('Could not connect') || error.message.includes('timed out')) {
            errorMessage = error.message;
          }
        }
        get().appendToLastMessage(errorMessage, regeneratingConversationId);
      }

      // Flush any remaining buffered content before marking streaming as complete
      flushStreamingBuffer(regeneratingConversationId, set);

      // Mark as no longer streaming
      // Use the conversation that initiated the regenerate
      set(state => {
        // Update the regenerating conversation's messages
        const updatedConversations = state.conversations.map(conv =>
          conv.id === regeneratingConversationId
            ? {
                ...conv,
                messages: conv.messages.map(msg =>
                  msg.id === newAssistantMessageId
                    ? { ...msg, isStreaming: false }
                    : msg
                ),
                updatedAt: new Date()
              }
            : conv
        );
        
        // Check if the current conversation has any streaming messages AFTER the update
        const currentConv = updatedConversations.find(conv => conv.id === state.currentConversationId);
        const hasStreamingMessages = currentConv 
          ? currentConv.messages.some(msg => msg.role === 'assistant' && msg.isStreaming)
          : false;
        
        return {
          conversations: updatedConversations,
          isLoading: hasStreamingMessages
        };
      });

    } catch (error) {
      logError('Regenerate error:', error);
      set({
        isLoading: false,
        error: `Failed to regenerate response: ${error instanceof Error ? error.message : 'Unknown error'}`
      });
    }
  },

  updateConversationTitle: (id: string, title: string) => {
    set(state => ({
      conversations: state.conversations.map(conv =>
        conv.id === id
          ? { ...conv, title, updatedAt: new Date() }
          : conv
      )
    }));

    // Save to localStorage
    setTimeout(() => {
      const currentState = get();
      localStorage.setItem('chat-state', JSON.stringify({
        conversations: currentState.conversations,
        currentConversationId: currentState.currentConversationId
      }));
    }, 0);
  },

  clearError: () => {
    set({ error: null });
  },

  // Utility function to clean up any orphaned streaming messages
  cleanupStreamingMessages: () => {
    // Only clean up streaming messages from conversations that are not the current one
    // This preserves streaming state when switching conversations
    set(state => ({
      conversations: state.conversations.map(conv => {
        // Keep streaming messages in the current conversation (they might be actively streaming)
        if (conv.id === state.currentConversationId) {
          return conv;
        }
        
        // Only clean up streaming messages from other conversations if they're truly orphaned
        // (e.g., if they're old and shouldn't be streaming anymore)
        // For now, we'll keep all streaming messages to preserve state
        return conv;
      }),
      // Only set isLoading to false if there are no active streaming operations
      isLoading: false
    }));
  },

  // Check if a new conversation can be created
  canCreateNewConversation: () => {
    const state = get();
    const maxConversations = AppConfig.maxConversations;
    
    // If no current conversation, allow creation (if under limit)
    if (!state.currentConversationId) {
      return maxConversations === null || state.conversations.length < maxConversations;
    }
    
    // Find current conversation
    const currentConversation = state.conversations.find(conv => conv.id === state.currentConversationId);
    
    // If current conversation has messages, allow creation (if under limit)
    if (currentConversation && currentConversation.messages.length > 0) {
      return maxConversations === null || state.conversations.length < maxConversations;
    }
    
    // If current conversation is empty, don't allow creation
    return false;
  },

  // Get current conversation count
  getConversationCount: () => {
    return get().conversations.length;
  },

  // Add file to conversation
  addFileToConversation: (conversationId: string, file: FileAttachment) => {
    debugLog(`[chatStore] addFileToConversation called`, { conversationId, fileId: file.file_id, filename: file.filename });
    set(state => {
      const updated = {
        conversations: state.conversations.map(conv =>
          conv.id === conversationId
            ? {
                ...conv,
                attachedFiles: [
                  ...(conv.attachedFiles || []).filter(f => f.file_id !== file.file_id),
                  file
                ],
                updatedAt: new Date()
              }
            : conv
        )
      };
      const conversation = updated.conversations.find(conv => conv.id === conversationId);
      debugLog(`[chatStore] Updated conversation ${conversationId}`, {
        hasConversation: !!conversation,
        attachedFilesCount: conversation?.attachedFiles?.length || 0,
        attachedFiles: conversation?.attachedFiles?.map(f => ({ file_id: f.file_id, filename: f.filename }))
      });
      return updated;
    });

    // Save to localStorage
    setTimeout(() => {
      const currentState = get();
      localStorage.setItem('chat-state', JSON.stringify({
        conversations: currentState.conversations,
        currentConversationId: currentState.currentConversationId
      }));
    }, 0);
  },

  // Remove file from conversation and delete from server
  removeFileFromConversation: async (conversationId: string, fileId: string) => {
    debugLog(`[chatStore] removeFileFromConversation called`, {
      conversationId,
      fileId
    });
    try {
      // Get the conversation to access its API key
      const conversation = get().conversations.find(conv => conv.id === conversationId);
      if (!conversation) {
        throw new Error('Conversation not found');
      }
      
      if (!conversation.adapterName) {
        throw new Error('Adapter not configured for this conversation. Cannot delete file.');
      }

      const conversationAdapterName = conversation.adapterName;
      const conversationApiUrl = resolveApiUrl(conversation.apiUrl);

      // Delete from server
      debugLog(`[chatStore] Calling FileUploadService.deleteFile for ${fileId}`);
      await FileUploadService.deleteFile(fileId, undefined, conversationApiUrl, conversationAdapterName);
      debugLog(`[chatStore] Successfully deleted file ${fileId} from server`);
    } catch (error: unknown) {
      // If file was already deleted (404), that's fine - just log and continue
      if (
        error instanceof Error &&
        (error.message.includes('404') || error.message.includes('File not found'))
      ) {
        debugLog(`[chatStore] File ${fileId} was already deleted from server`);
      } else {
        debugError(`[chatStore] Failed to delete file ${fileId} from server:`, error);
      }
      // Continue with local removal even if server deletion fails
    }

    // Remove from conversation locally
    set(state => ({
      conversations: state.conversations.map(conv =>
        conv.id === conversationId
          ? {
              ...conv,
              attachedFiles: (conv.attachedFiles || []).filter(f => f.file_id !== fileId),
              updatedAt: new Date()
            }
          : conv
      )
    }));

    // Save to localStorage
    setTimeout(() => {
      const currentState = get();
      localStorage.setItem('chat-state', JSON.stringify({
        conversations: currentState.conversations,
        currentConversationId: currentState.currentConversationId
      }));
    }, 0);
  },

  // Load files from server for a conversation
  loadConversationFiles: async (conversationId: string) => {
    try {
      // Get the conversation to access its API key
      const conversation = get().conversations.find(conv => conv.id === conversationId);
      if (!conversation) {
        return;
      }
      
      if (!conversation.adapterName) {
        debugLog(`Skipping file load for conversation ${conversationId}: adapter not configured`);
        return;
      }

      const conversationAdapterName = conversation.adapterName;
      const conversationApiUrl = resolveApiUrl(conversation.apiUrl);
      
      // Only load files that are already in the conversation's attachedFiles
      // This ensures full segregation - files uploaded in one conversation don't appear in others
      const existingFileIds = new Set(
        (conversation.attachedFiles || []).map(f => f.file_id)
      );
      
      if (existingFileIds.size === 0) {
        // No files to sync - skip loading
        debugLog(`No files to sync for conversation ${conversationId}`);
        return;
      }
      
      // Get all files from server for this adapter
      const allFiles = await FileUploadService.listFiles(undefined, conversationApiUrl, conversationAdapterName);
      
      // Convert to FileAttachment format
      const fileAttachments: FileAttachment[] = allFiles.map(file => ({
        file_id: file.file_id,
        filename: file.filename,
        mime_type: file.mime_type,
        file_size: file.file_size,
        upload_timestamp: file.upload_timestamp,
        processing_status: file.processing_status,
        chunk_count: file.chunk_count
      }));

      // Create a map of server files for quick lookup
      const serverFilesMap = new Map(
        fileAttachments.map(file => [file.file_id, file])
      );

      // Only update existing files with server status - don't add new files
      // This ensures files uploaded in one conversation don't appear in others
      set(state => {
        const conversation = state.conversations.find(conv => conv.id === conversationId);
        if (!conversation) return state;

        // Only update files that are already in the conversation's attachedFiles
        // Filter out any files that aren't in the server's response (may have been deleted)
        const updatedFiles: FileAttachment[] = (conversation.attachedFiles || [])
          .map(existingFile => {
            const serverFile = serverFilesMap.get(existingFile.file_id);
            // Use server file if available (has latest status), otherwise keep existing
            return serverFile || existingFile;
          })
          .filter(file => {
            // Only keep files that exist on the server or are still uploading (no status yet)
            // This filters out files that were deleted from the server
            return serverFilesMap.has(file.file_id) || !file.processing_status || file.processing_status === 'processing';
          });

        return {
          conversations: state.conversations.map(conv =>
            conv.id === conversationId
              ? {
                  ...conv,
                  attachedFiles: updatedFiles,
                  updatedAt: new Date()
                }
              : conv
          )
        };
      });

      // Save to localStorage
      setTimeout(() => {
        const currentState = get();
        localStorage.setItem('chat-state', JSON.stringify({
          conversations: currentState.conversations,
          currentConversationId: currentState.currentConversationId
        }));
      }, 0);
    } catch (error) {
      logError(`Failed to load files for conversation ${conversationId}:`, error);
      // Don't throw - allow conversation to load even if file loading fails
    }
  },

  // Sync files when switching conversations
  syncConversationFiles: async (conversationId: string) => {
    await get().loadConversationFiles(conversationId);
  },

  syncConversationsWithBackend: async () => {
    try {
      const state = get();
      if (state.conversations.length === 0) {
        return;
      }

      const api = await getApi();
      const limit = AppConfig.maxMessagesPerConversation !== null
        ? AppConfig.maxMessagesPerConversation || undefined
        : undefined;

      let historyEndpointUnsupported = false;

      const syncResults = await Promise.all(
        state.conversations.map(async (conversation) => {
          if (!conversation.sessionId) {
            return null;
          }

          if (!conversation.adapterName) {
            debugWarn(`[chatStore] Skipping backend sync for conversation ${conversation.id} - adapter not configured`);
            return null;
          }

          try {
            const apiClient = new api.ApiClient({
              apiUrl: resolveApiUrl(conversation.apiUrl),
              sessionId: conversation.sessionId,
              adapterName: conversation.adapterName
            });

            if (typeof apiClient.getConversationHistory !== 'function') {
              if (!historyEndpointUnsupported) {
                historyEndpointUnsupported = true;
                debugWarn('[chatStore] Conversation history endpoint not supported by current API client');
              }
              return null;
            }

            const history = await apiClient.getConversationHistory(conversation.sessionId, limit);
            const historyMessages = Array.isArray(history?.messages) ? history.messages : [];

            if (historyMessages.length === 0) {
              if (conversation.messages.length === 0) {
                return null;
              }
              return {
                id: conversation.id,
                sessionId: history?.session_id || conversation.sessionId,
                messages: [] as Message[],
                cleared: true,
                updatedAt: new Date()
              };
            }

            const normalizedMessages = convertHistoryMessages(historyMessages, conversation.messages);
            if (haveSameMessages(conversation.messages, normalizedMessages)) {
              return null;
            }

            return {
              id: conversation.id,
              sessionId: history?.session_id || conversation.sessionId,
              messages: normalizedMessages,
              cleared: false,
              updatedAt: normalizedMessages[normalizedMessages.length - 1]?.timestamp || new Date()
            };
          } catch (error) {
            debugWarn(`[chatStore] Failed to sync session ${conversation.sessionId}:`, error);
            return null;
          }
        })
      );

      const updates = syncResults.filter((result): result is {
        id: string;
        sessionId: string;
        messages: Message[];
        cleared: boolean;
        updatedAt: Date;
      } => Boolean(result));

      if (updates.length === 0) {
        return;
      }

      set(currentState => {
        const updateMap = new Map(updates.map(update => [update.id, update]));
        const updatedConversations = currentState.conversations.map(conv => {
          const update = updateMap.get(conv.id);
          if (!update) {
            return conv;
          }

          if (update.cleared) {
            return {
              ...conv,
              sessionId: update.sessionId || conv.sessionId,
              messages: [],
              attachedFiles: [],
              title: 'New Chat',
              updatedAt: update.updatedAt,
              adapterLoadError: null
            };
          }

          return {
            ...conv,
            sessionId: update.sessionId || conv.sessionId,
            messages: update.messages,
            updatedAt: update.updatedAt,
            adapterLoadError: null
          };
        });

        return {
          conversations: updatedConversations,
          currentConversationId: currentState.currentConversationId
        };
      });

      setTimeout(() => {
        const currentState = get();
        localStorage.setItem('chat-state', JSON.stringify({
          conversations: currentState.conversations,
          currentConversationId: currentState.currentConversationId
        }));
      }, 0);
    } catch (error) {
      debugWarn('Failed to synchronize conversations with backend:', error);
    }
  },

  stopStreaming: async () => {
    // Only proceed if we're currently loading/streaming
    if (!get().isLoading) {
      debugLog('[chatStore] stopStreaming called but not currently loading');
      return;
    }

    debugLog('[chatStore] Stopping stream...', {
      hasAbortController: !!activeAbortController,
      requestId: activeRequestId,
      sessionId: activeStreamSessionId
    });

    // Abort the local fetch request
    if (activeAbortController) {
      activeAbortController.abort();
    }

    // Cancel server-side stream if we have the required IDs
    if (activeRequestId && activeStreamSessionId) {
      try {
        debugLog(`[chatStore] Calling stopChat API: session=${activeStreamSessionId}, request=${activeRequestId}`);
        const api = await getApi();
        const cancelled = await api.stopChat?.(activeStreamSessionId, activeRequestId);
        debugLog(`[chatStore] Server-side cancellation result: ${cancelled}`);
      } catch (error) {
        debugWarn('[chatStore] Failed to cancel server-side stream:', error);
        // Don't throw - the local abort already stopped the stream from our perspective
      }
    } else {
      debugWarn(`[chatStore] Cannot call stopChat - missing IDs: requestId=${activeRequestId}, sessionId=${activeStreamSessionId}`);
    }

    // Mark the current streaming message as complete
    const currentConversationId = get().currentConversationId;
    if (currentConversationId) {
      set(state => ({
        conversations: state.conversations.map(conv => {
          if (conv.id !== currentConversationId) return conv;

          return {
            ...conv,
            messages: conv.messages.map(msg =>
              msg.isStreaming ? { ...msg, isStreaming: false } : msg
            ),
            updatedAt: new Date()
          };
        }),
        isLoading: false
      }));
    } else {
      set({ isLoading: false });
    }

    // Clear stream control state
    activeAbortController = null;
    activeRequestId = null;
    activeStreamSessionId = null;

    debugLog('[chatStore] Stream stopped successfully');
  },

  clearCurrentConversationAdapter: () => {
    const currentConversationId = get().currentConversationId;
    if (!currentConversationId) {
      return;
    }

    set(state => ({
      conversations: state.conversations.map(conv =>
        conv.id === currentConversationId
          ? {
              ...conv,
              adapterName: undefined,
              adapterInfo: undefined,
              adapterLoadError: null
            }
          : conv
      )
    }));

    setTimeout(() => {
      const currentState = get();
      localStorage.setItem('chat-state', JSON.stringify({
        conversations: currentState.conversations,
        currentConversationId: currentState.currentConversationId
      }));
    }, 0);
  }
}));

// Initialize store from localStorage
const initializeStore = async () => {
  type StoredMessage = Omit<Message, 'timestamp'> & {
    timestamp: string | number | Date;
    isStreaming?: boolean;
  };

  type StoredConversation = Omit<Conversation, 'createdAt' | 'updatedAt' | 'messages'> & {
    createdAt: string | number | Date;
    updatedAt: string | number | Date;
    messages?: StoredMessage[];
  };

  interface PersistedChatState {
    conversations?: StoredConversation[];
    currentConversationId?: string | null;
  }
  // Then initialize the rest of the store
  const saved = localStorage.getItem('chat-state');
  const runtimeApiUrl = getApiUrl();
  const hasStoredApiOverride = typeof window !== 'undefined'
    ? Boolean(localStorage.getItem('chat-api-url'))
    : false;
  let sessionId = getOrCreateSessionId(); // Default session ID
  let hasExistingConversations = false;
  
  if (saved) {
    try {
      const parsedState = JSON.parse(saved) as PersistedChatState;
      const toDate = (value: string | number | Date | undefined): Date => {
        if (value instanceof Date) {
          return value;
        }
        const parsedDate = value ? new Date(value) : new Date();
        return Number.isNaN(parsedDate.getTime()) ? new Date() : parsedDate;
      };
      // Restore Date objects, clean up streaming messages, strip legacy apiKey field
      const storedConversations = Array.isArray(parsedState.conversations) ? parsedState.conversations : [];
      const normalizedConversations: Conversation[] = storedConversations.map((storedConversation) => {
        const storedMessages = Array.isArray(storedConversation.messages) ? storedConversation.messages : [];
        const sanitizedMessages: Message[] = storedMessages
          .filter((msg) => !(msg.role === 'assistant' && msg.isStreaming))
          .map((msg) => ({
            ...msg,
            timestamp: toDate(msg.timestamp),
            isStreaming: false,
          }));

        const normalizedConversation: Conversation = {
          id: storedConversation.id,
          sessionId: storedConversation.sessionId || generateUniqueSessionId(),
          title: storedConversation.title || 'New Chat',
          messages: sanitizedMessages,
          createdAt: toDate(storedConversation.createdAt),
          updatedAt: toDate(storedConversation.updatedAt),
          attachedFiles: storedConversation.attachedFiles || [],
          adapterName: storedConversation.adapterName,
          apiUrl: storedConversation.apiUrl,
          adapterInfo: storedConversation.adapterInfo,
          adapterLoadError: storedConversation.adapterLoadError || null,
          audioSettings: storedConversation.audioSettings,
          currentThreadId: undefined,
          currentThreadSessionId: undefined,
        };

        // If the user hasn't configured a custom API URL yet, make sure empty placeholder
        // conversations always follow the runtime config that the CLI injected.
        const isPlaceholderConversation =
          normalizedConversation.messages.length === 0 &&
          !normalizedConversation.adapterName;

        const apiUrl = isPlaceholderConversation && !hasStoredApiOverride
          ? runtimeApiUrl
          : resolveApiUrl(storedConversation.apiUrl);

        return {
          ...normalizedConversation,
          apiUrl,
        };
      });
      
      // Check if we have existing conversations
      hasExistingConversations = normalizedConversations.length > 0;
      
      // If there's a current conversation, use its session ID
      if (parsedState.currentConversationId && normalizedConversations.length > 0) {
        const currentConversation = normalizedConversations.find(
          (conv) => conv.id === parsedState.currentConversationId
        );
        if (currentConversation && currentConversation.sessionId) {
          sessionId = currentConversation.sessionId;
        }
      }
      
      // If conversations array is empty, create a default conversation with DEFAULT_ADAPTER
      // Always use default-key when there are no conversations, regardless of localStorage
      if (normalizedConversations.length === 0) {
        const defaultConversationId = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        const defaultSessionId = generateUniqueSessionId();
        const defaultConversation = buildDefaultConversation(
          defaultConversationId,
          defaultSessionId,
          getApiUrl()
        );
        
        useChatStore.setState({
          conversations: [defaultConversation],
          currentConversationId: defaultConversationId,
          sessionId: defaultSessionId
        });
        
        sessionId = defaultSessionId;
      } else {
        // Existing conversations - preserve their API keys
        useChatStore.setState({
          conversations: normalizedConversations,
          currentConversationId: parsedState.currentConversationId || normalizedConversations[0]?.id || null,
          sessionId: sessionId
        });
        
        // If no current conversation is set, use the first one
        if (!parsedState.currentConversationId && normalizedConversations.length > 0) {
          useChatStore.setState({
            currentConversationId: normalizedConversations[0].id,
            sessionId: normalizedConversations[0].sessionId || sessionId
          });
          sessionId = normalizedConversations[0].sessionId || sessionId;
        }
      }
      
      // Debug: Log loaded conversations and their session IDs
      const loadedConversations = useChatStore.getState().conversations;
      debugLog('📋 Loaded conversations:', loadedConversations.map((conv) => ({
        id: conv.id,
        title: conv.title,
        sessionId: conv.sessionId,
        messageCount: conv.messages?.length || 0
      })));
      
      // Clean up any residual streaming messages after initialization
      setTimeout(() => {
        useChatStore.getState().cleanupStreamingMessages();
      }, 100);
    } catch (error) {
      logError('Failed to load chat state:', error);
      // If loading fails, create a default conversation
      const defaultConversationId = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      const defaultSessionId = generateUniqueSessionId();
      const defaultConversation = buildDefaultConversation(
        defaultConversationId,
        defaultSessionId,
        getApiUrl()
      );
      
      useChatStore.setState({
        conversations: [defaultConversation],
        currentConversationId: defaultConversationId,
        sessionId: defaultSessionId
      });
      
      sessionId = defaultSessionId;
    }
  } else {
    // No saved state - create a default conversation with DEFAULT_ADAPTER
    // Always use default-key when there are no conversations, regardless of localStorage
    const defaultConversationId = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const defaultSessionId = generateUniqueSessionId();
    const defaultConversation = buildDefaultConversation(
      defaultConversationId,
      defaultSessionId,
      getApiUrl()
    );
    
    useChatStore.setState({
      conversations: [defaultConversation],
      currentConversationId: defaultConversationId,
      sessionId: defaultSessionId
    });
    
    sessionId = defaultSessionId;
  }
  
  // One-time cleanup of legacy localStorage keys
  localStorage.removeItem('chat-api-key');

  // Determine which adapter/URL to use for API configuration
  const currentState = useChatStore.getState();
  const currentConversation = currentState.currentConversationId
    ? currentState.conversations.find(conv => conv.id === currentState.currentConversationId)
    : null;

  const apiUrlToUse = (hasExistingConversations && currentConversation?.apiUrl)
    ? currentConversation.apiUrl
    : getApiUrl();

  try {
    const api = await getApi();

    const existingAdapterName = currentConversation?.adapterName;
    if (!existingAdapterName) {
      debugLog('No adapter selected yet. Waiting for user selection before configuring API.');
    } else {
      api.configureApi(apiUrlToUse, sessionId, existingAdapterName);
      currentApiUrl = apiUrlToUse;
      apiConfigured = true;
      debugLog('Using existing adapter from conversation:', existingAdapterName);

      // Load adapter info if not already loaded
      if (!currentConversation?.adapterInfo) {
        try {
          const validationClient = new api.ApiClient({
            apiUrl: apiUrlToUse,
            sessionId: null,
            adapterName: existingAdapterName
          });

          if (typeof validationClient.getAdapterInfo === 'function') {
            const adapterInfo = await validationClient.getAdapterInfo();
            debugLog('Adapter info loaded for existing adapter:', adapterInfo);

            const stateAfterLoad = useChatStore.getState();
            if (stateAfterLoad.currentConversationId) {
              useChatStore.setState({
                conversations: stateAfterLoad.conversations.map(conv =>
                  conv.id === stateAfterLoad.currentConversationId
                    ? { ...conv, adapterInfo: adapterInfo, adapterLoadError: null, updatedAt: new Date() }
                    : conv
                )
              });

              setTimeout(() => {
                const updatedState = useChatStore.getState();
                localStorage.setItem('chat-state', JSON.stringify({
                  conversations: updatedState.conversations,
                  currentConversationId: updatedState.currentConversationId
                }));
              }, 0);
            }
          }
        } catch (error) {
          debugWarn('Failed to load adapter info for existing adapter:', error);
        }
      }
    }
  } catch (error) {
    logError('Failed to initialize API:', error);
  }

  // After initializing base state and API configuration, reconcile with backend history
  try {
    await useChatStore.getState().syncConversationsWithBackend();
  } catch (syncError) {
    debugWarn('Conversation history sync skipped:', syncError);
  }
};

// Initialize store on import
if (typeof window !== 'undefined') {
  initializeStore();
} 
