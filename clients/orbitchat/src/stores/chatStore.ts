import { create, type StoreApi } from 'zustand';
import { getApi, ApiClient } from '../apiClient';
import { Message, Conversation, ChatState, FileAttachment, AdapterInfo } from '../types';
import { FileUploadService } from '../services/fileService';
import { debugLog, debugWarn, debugError, logError } from '../utils/debug';
import { AppConfig } from '../utils/config';
import { getApiUrl, resolveApiUrl, DEFAULT_API_URL, getIsAuthConfigured } from '../utils/runtimeConfig';
import { sanitizeMessageContent, truncateLongContent } from '../utils/contentValidation';
import { audioStreamManager } from '../utils/audioStreamManager';
import { revokeFileThumbnail } from '../utils/fileTypeVisuals';
import { getIsAuthenticated } from '../auth/authState';
import { useLoginPromptStore } from './loginPromptStore';
import {
  DEFAULT_ADAPTER,
  getInitialConversationAdapterId,
  buildDefaultConversation,
  DEFAULT_CONVERSATION_TITLE,
  normalizeStoredTitle,
  getOrCreateSessionId,
  setSessionId,
  generateUniqueMessageId,
  generateUniqueSessionId,
  countNonStreamingMessages,
  extractGeneratedFileIds,
  convertHistoryMessages,
  ensureUniqueMessageIds,
  haveSameMessages,
  getAudioSettings,
} from './chatStore.helpers';
export { debouncedSaveToLocalStorage } from './chatStore.persistence';
import { debouncedSaveToLocalStorage } from './chatStore.persistence';

// Streaming content buffer — batches rapid updates to prevent "Maximum update depth exceeded"
// errors when rendering complex content like mermaid diagrams (~30fps)
const STREAMING_BATCH_DELAY = 32; // ms
const streamingBuffer: Map<string, { content: string; timeoutId: ReturnType<typeof setTimeout> | null; messageId?: string }> = new Map();

// Stream control state for stop functionality
let activeAbortController: AbortController | null = null;
let activeRequestId: string | null = null;
let activeStreamSessionId: string | null = null;
let activeStreamConversationId: string | null = null;

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
    const targetMessageId = buffer.messageId;
    buffer.content = '';

    setState(state => ({
      conversations: state.conversations.map(conv => {
        if (conv.id !== conversationId) return conv;
        const messages = [...conv.messages];
        const targetIdx = targetMessageId
          ? messages.findIndex(m => m.id === targetMessageId)
          : messages.length - 1;
        const targetMessage = targetIdx !== -1 ? messages[targetIdx] : undefined;
        if (targetMessage && targetMessage.role === 'assistant' && targetMessage.isStreaming) {
          messages[targetIdx] = {
            ...targetMessage,
            content: targetMessage.content + contentToAppend,
          };
        }
        return { ...conv, messages, updatedAt: new Date() };
      }),
    }));
  }

  streamingBuffer.delete(conversationId);
};

// Updates the last assistant message in a conversation, used when stream delivers media/audio
const updateLastAssistantMessage = (
  state: ChatState,
  conversationId: string,
  updater: (msg: Message) => Partial<Message>,
  messageId?: string
): Partial<ChatState> => ({
  conversations: state.conversations.map(conv => {
    if (conv.id !== conversationId) return conv;
    const messages = [...conv.messages];
    // Target the specific streaming message by id when known — e.g. regenerating a
    // non-final turn leaves a different, already-completed message last in the array,
    // so "last message" would silently misattribute audio/image/video/document fields.
    const targetIdx = messageId
      ? messages.findIndex(m => m.id === messageId)
      : messages.length - 1;
    if (targetIdx !== -1 && messages[targetIdx]?.role === 'assistant') {
      messages[targetIdx] = { ...messages[targetIdx], ...updater(messages[targetIdx]) };
    }
    return { ...conv, messages, updatedAt: new Date() };
  }),
});

// API configuration state
let apiConfigured = false;
let currentApiUrl = '';

async function ensureApiConfigured(): Promise<boolean> {
  if (apiConfigured && currentApiUrl) return true;

  try {
    const api = await getApi();

    const storedApiUrl = localStorage.getItem('chat-api-url');
    if (storedApiUrl && storedApiUrl === DEFAULT_API_URL) {
      localStorage.removeItem('chat-api-url');
    }
    const apiUrl =
      storedApiUrl && storedApiUrl !== DEFAULT_API_URL ? storedApiUrl : getApiUrl();

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

// Extended chat state for the store
interface ExtendedChatState extends ChatState {
  sessionId: string;
  createConversation: () => string;
  selectConversation: (id: string) => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;
  deleteAllConversations: () => Promise<void>;
  deleteThread: (conversationId: string, parentMessageId: string, threadId: string) => Promise<void>;
  sendMessage: (content: string, fileIds?: string[], threadId?: string, model?: string, skill?: string) => Promise<void>;
  createThread: (messageId: string, sessionId: string) => Promise<void>;
  appendToLastMessage: (content: string, conversationId?: string, messageId?: string) => void;
  regenerateResponse: (messageId: string, model?: string) => Promise<void>;
  editMessageAndRegenerate: (messageId: string, newContent: string, model?: string) => Promise<void>;
  updateConversationTitle: (id: string, title: string) => void;
  clearError: () => void;
  configureApiSettings: (apiUrl: string, sessionId?: string, adapterName?: string) => Promise<void>;
  getSessionId: () => string;
  cleanupStreamingMessages: () => void;
  canCreateNewConversation: () => boolean;
  getConversationCount: () => number;
  addFileToConversation: (conversationId: string, file: FileAttachment) => void;
  removeFileFromConversation: (conversationId: string, fileId: string) => Promise<void>;
  loadConversationFiles: (conversationId: string) => Promise<void>;
  syncConversationFiles: (conversationId: string) => Promise<void>;
  syncConversationsWithBackend: () => Promise<void>;
  stopStreaming: () => Promise<void>;
  clearCurrentConversationAdapter: () => void;
  submitFeedback: (conversationMessageId: string, feedbackType: 'up' | 'down', comment?: string) => Promise<boolean>;
  loadFeedbackForConversation: (sessionId: string) => Promise<void>;
}


async function _runStreamIntoMessage(
  get: () => ExtendedChatState,
  set: StoreApi<ExtendedChatState>['setState'],
  assistantMessageId: string,
  conversationId: string,
  content: string,
  attachmentIds: string[],
  model: string | undefined,
  logLabel: 'regenerate' | 'edit-regenerate',
  regenerateOfMessageId?: string
): Promise<void> {
  let receivedAnyText = false;
  const abortController = new AbortController();
  activeAbortController = abortController;
  activeStreamConversationId = conversationId;
  activeRequestId = null;

  try {
    const currentConversation = get().conversations.find(conv => conv.id === conversationId);
    if (!currentConversation) throw new Error('Conversation not found');
    if (!currentConversation.adapterName) {
      throw new Error('Adapter not configured for this conversation. Please select an adapter first.');
    }

    activeStreamSessionId = currentConversation.sessionId;

    if (currentConversation.sessionId) {
      const api = await getApi();
      api.configureApi(
        resolveApiUrl(currentConversation.apiUrl),
        currentConversation.sessionId,
        currentConversation.adapterName
      );
    }

    const api = await getApi();
    const { returnAudio, ttsVoice, language } = getAudioSettings(currentConversation);

    for await (const response of api.streamChat(
      content,
      true,
      attachmentIds.length > 0 ? attachmentIds : undefined,
      undefined,
      undefined,
      undefined,
      language,
      returnAudio,
      ttsVoice,
      undefined,
      undefined,
      model,
      undefined,
      regenerateOfMessageId
    )) {
      if (response.request_id && !activeRequestId) {
        activeRequestId = response.request_id;
        debugLog(`[chatStore] >>> CAPTURED request_id for ${logLabel} stop: ${response.request_id}`);
      }

      if (response.text) {
        const sanitizedText = sanitizeMessageContent(response.text);
        if (sanitizedText) {
          get().appendToLastMessage(sanitizedText, conversationId, assistantMessageId);
          receivedAnyText = true;
        } else if (response.text.length > 100) {
          debugWarn('[chatStore] Filtered out potential base64 audio data from regenerated message content');
        }
      }

      if (response.audio && response.done) {
        set((state: ExtendedChatState) =>
          updateLastAssistantMessage(state, conversationId, () => ({
            audio: response.audio,
            audioFormat: response.audioFormat || 'mp3',
          }), assistantMessageId)
        );
      }

      if (response.image && response.done) {
        receivedAnyText = true;
        set((state: ExtendedChatState) =>
          updateLastAssistantMessage(state, conversationId, () => ({
            image: response.image,
            imageFormat: response.image_format || 'png',
            imageRevisedPrompt: response.image_revised_prompt,
            imageUrl: response.image_url,
          }), assistantMessageId)
        );
      }

      if ((response.video || response.video_url) && response.done) {
        receivedAnyText = true;
        set((state: ExtendedChatState) =>
          updateLastAssistantMessage(state, conversationId, () => ({
            video: response.video,
            videoFormat: response.video_format || 'mp4',
            videoRevisedPrompt: response.video_revised_prompt,
            videoUrl: response.video_url,
          }), assistantMessageId)
        );
      }

      if ((response.document || response.document_url) && response.done) {
        receivedAnyText = true;
        set((state: ExtendedChatState) =>
          updateLastAssistantMessage(state, conversationId, () => ({
            document: response.document,
            documentFormat: response.document_format || 'pdf',
            documentRevisedPrompt: response.document_revised_prompt,
            documentUrl: response.document_url,
          }), assistantMessageId)
        );
      }

      if (response.generated_audio_url && response.done) {
        receivedAnyText = true;
        set((state: ExtendedChatState) =>
          updateLastAssistantMessage(state, conversationId, () => ({
            generatedAudioFormat: response.generated_audio_format || 'mp3',
            generatedAudioRevisedPrompt: response.generated_audio_revised_prompt,
            generatedAudioUrl: response.generated_audio_url,
          }), assistantMessageId)
        );
      }

      if (response.done) {
        const threadingInfo = response.threading;
        if (threadingInfo?.supports_threading) {
          set((state: ExtendedChatState) => ({
            conversations: state.conversations.map(conv => {
              if (conv.id !== conversationId) return conv;
              return {
                ...conv,
                messages: conv.messages.map(msg =>
                  msg.id === assistantMessageId
                    ? { ...msg, supportsThreading: true, databaseMessageId: threadingInfo.message_id }
                    : msg
                ),
                updatedAt: new Date(),
              };
            }),
          }));
        }

        if (response.assistant_message_id) {
          set((state: ExtendedChatState) => ({
            conversations: state.conversations.map(conv => {
              if (conv.id !== conversationId) return conv;
              return {
                ...conv,
                messages: conv.messages.map(msg =>
                  msg.id === assistantMessageId && !msg.databaseMessageId
                    ? { ...msg, databaseMessageId: response.assistant_message_id }
                    : msg
                ),
                updatedAt: new Date(),
              };
            }),
          }));
        }

        if (response.model) {
          set((state: ExtendedChatState) =>
            updateLastAssistantMessage(state, conversationId, () => ({
              model: response.model,
            }), assistantMessageId)
          );
        }

        break;
      }
    }

    if (!receivedAnyText && !abortController.signal.aborted) {
      get().appendToLastMessage(
        'No response received from the server. Please try again later.',
        conversationId,
        assistantMessageId
      );
    }
  } catch (error) {
    const isAbortError =
      error instanceof Error &&
      (error.name === 'AbortError' ||
        error.message === 'Stream cancelled by user' ||
        error.message.includes('aborted'));

    if (isAbortError) {
      debugLog(`[chatStore] ${logLabel === 'edit-regenerate' ? 'Edit-regenerate' : 'Regeneration'} stream was cancelled by user`);
      receivedAnyText = true;
    } else {
      logError(`${logLabel === 'edit-regenerate' ? 'Edit-regenerate' : 'Regenerate'} API error:`, error);
      let errorMessage = 'Sorry, there was an error regenerating the response.';
      if (error instanceof Error) {
        if (error.message.startsWith('Server error:')) {
          errorMessage = error.message.substring('Server error: '.length);
        } else if (
          error.message.includes('Could not connect') ||
          error.message.includes('timed out')
        ) {
          errorMessage = error.message;
        }
      }
      get().appendToLastMessage(errorMessage, conversationId, assistantMessageId);
    }
  }

  activeAbortController = null;
  activeRequestId = null;
  activeStreamSessionId = null;
  activeStreamConversationId = null;

  flushStreamingBuffer(conversationId, set);

  set((state: ExtendedChatState) => {
    const updatedConversations = state.conversations.map(conv =>
      conv.id === conversationId
        ? {
            ...conv,
            messages: conv.messages.map(msg =>
              msg.id === assistantMessageId ? { ...msg, isStreaming: false } : msg
            ),
            updatedAt: new Date(),
          }
        : conv
    );
    const currentConv = updatedConversations.find(conv => conv.id === state.currentConversationId);
    return {
      conversations: updatedConversations,
      isLoading: currentConv
        ? currentConv.messages.some(msg => msg.role === 'assistant' && msg.isStreaming)
        : false,
    };
  });
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
    const actualSessionId = currentConversation?.sessionId || sessionId || getOrCreateSessionId();

    if (sessionId) setSessionId(sessionId);
    set({ sessionId: actualSessionId });

    try {
      const api = await getApi();

      if (!adapterName || !adapterName.trim()) {
        throw new Error('Adapter name is required');
      }

      api.configureApi(apiUrl, actualSessionId, adapterName);
      currentApiUrl = apiUrl;
      apiConfigured = true;

      let adapterInfo: AdapterInfo | undefined;
      try {
        const validationClient = new api.ApiClient({
          apiUrl,
          sessionId: null,
          adapterName,
        });
        if (typeof validationClient.getAdapterInfo === 'function') {
          adapterInfo = await validationClient.getAdapterInfo();
          debugLog('Adapter info loaded:', adapterInfo);
        }
      } catch (error) {
        debugWarn('Failed to load adapter info:', error);
      }

      if (currentConversation) {
        set(state => ({
          conversations: state.conversations.map(conv =>
            conv.id === currentConversation.id
              ? { ...conv, adapterName, apiUrl, adapterInfo, adapterLoadError: null, updatedAt: new Date() }
              : conv
          ),
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
              title: DEFAULT_CONVERSATION_TITLE,
              messages: [],
              createdAt: new Date(),
              updatedAt: new Date(),
              adapterName,
              apiUrl,
              adapterInfo,
              adapterLoadError: null,
            },
          ],
          currentConversationId: newId,
        }));
      }
    } catch (error) {
      debugError('Failed to configure API:', error);
      set({ isLoading: false });
      if (error instanceof Error) throw error;
      throw new Error('Failed to configure API settings');
    }

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
        const guestLimitMessage = `You've reached the guest limit of ${maxConversations} conversation${maxConversations === 1 ? '' : 's'}. Sign in to unlock more conversations, or delete conversations to start over.`;
        set({ error: guestLimitMessage });
        useLoginPromptStore.getState().openLoginPrompt(guestLimitMessage);
        throw new Error('Guest conversation limit reached');
      }
      const limitMessage = `Maximum of ${maxConversations} conversations reached. Please delete an existing conversation before starting a new one.`;
      set({ error: limitMessage });
      throw new Error(limitMessage);
    }

    const currentConversationHasContent =
      !!currentConversation &&
      (currentConversation.messages.length > 0 || (currentConversation.attachedFiles?.length || 0) > 0);

    if (currentConversation && !currentConversationHasContent) {
      const emptyMessage = 'Finish or delete the current conversation before starting a new one.';
      set({ error: emptyMessage });
      throw new Error(emptyMessage);
    }

    const id = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const newSessionId = generateUniqueSessionId();

    const newConversation: Conversation = {
      id,
      sessionId: newSessionId,
      title: DEFAULT_CONVERSATION_TITLE,
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date(),
      apiUrl: getApiUrl(),
      adapterName: getInitialConversationAdapterId(),
      adapterLoadError: null,
    };

    // Reset isLoading so the new conversation is immediately usable even if a previous stream
    // is still running in the background.
    set((state: ExtendedChatState) => ({
      conversations: [newConversation, ...state.conversations],
      currentConversationId: id,
      sessionId: newSessionId,
      isLoading: false,
    }));

    debouncedSaveToLocalStorage(get);
    return id;
  },

  selectConversation: async (id: string) => {
    const conversation = get().conversations.find(conv => conv.id === id);
    if (conversation) {
      const hasStreamingMessages = conversation.messages.some(
        msg => msg.role === 'assistant' && msg.isStreaming
      );
      set({
        currentConversationId: id,
        sessionId: conversation.sessionId,
        isLoading: hasStreamingMessages,
      });

      const conversationApiUrl = conversation.apiUrl || getApiUrl();
      const conversationAdapterName = conversation.adapterName;

      const isConfigured = await ensureApiConfigured();
      if (isConfigured && conversationAdapterName) {
        const api = await getApi();
        api.configureApi(conversationApiUrl, conversation.sessionId, conversationAdapterName);

        if (!conversation.adapterInfo) {
          try {
            const adapterClient = new api.ApiClient({
              apiUrl: conversationApiUrl,
              sessionId: null,
              adapterName: conversationAdapterName,
            });
            if (typeof adapterClient.getAdapterInfo === 'function') {
              const adapterInfo = await adapterClient.getAdapterInfo();
              debugLog('Adapter info loaded for conversation:', adapterInfo);
              set(state => ({
                conversations: state.conversations.map(conv =>
                  conv.id === id
                    ? { ...conv, adapterInfo, adapterLoadError: null, updatedAt: new Date() }
                    : conv
                ),
              }));
              debouncedSaveToLocalStorage(get);
            }
          } catch (error) {
            debugWarn('Failed to load adapter info for conversation:', error);
          }
        }
      }

      get().loadFeedbackForConversation(conversation.sessionId).catch(() => {});
    }

    debouncedSaveToLocalStorage(get);
  },

  deleteConversation: async (id: string) => {
    const state = get();
    const conversation = state.conversations.find(conv => conv.id === id);

    debugLog(`🗑️ Deleting conversation ${id}:`, {
      conversationId: id,
      sessionId: conversation?.sessionId,
      title: conversation?.title,
      messageCount: conversation?.messages.length,
      fileCount: conversation?.attachedFiles?.length || 0,
    });

    if (state.currentConversationId === id) {
      audioStreamManager.stop();
    }

    if (conversation) {
      const attachmentFileIds = (conversation.attachedFiles || []).map(f => f.file_id);
      const messageAttachmentFileIds = (conversation.messages || []).flatMap(
        m => (m.attachments || []).map(f => f.file_id)
      );
      [...attachmentFileIds, ...messageAttachmentFileIds].forEach(revokeFileThumbnail);
    }

    if (conversation?.sessionId) {
      try {
        const isConfigured = await ensureApiConfigured();
        if (!isConfigured) {
          logError('Failed to configure API for conversation deletion');
        } else {
          const conversationApiUrl = conversation.apiUrl || getApiUrl();
          const conversationAdapterName = conversation.adapterName;

          if (!conversationAdapterName) {
            debugWarn(`Skipping server deletion for conversation ${id}: adapter not configured`);
          } else {
            debugLog(`Using conversation's adapter for deletion: ${conversationAdapterName} (conversation: ${id})`);
          }

          const api = await getApi();
          const apiClient: ApiClient = new api.ApiClient({
            apiUrl: conversationApiUrl,
            sessionId: conversation.sessionId,
            adapterName: conversationAdapterName,
          });

          const uploadedFileIds = conversation.attachedFiles?.map(f => f.file_id) || [];
          const generatedFileIds = extractGeneratedFileIds(conversation.messages || []);
          const fileIds = [...uploadedFileIds, ...generatedFileIds];

          debugLog(`🔧 Calling deleteConversationWithFiles for session: ${conversation.sessionId}`);
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
      }
    } else {
      debugWarn(`⚠️ No session ID found for conversation ${id}, skipping server-side deletion`);
    }

    set((state: ExtendedChatState) => {
      const filtered = state.conversations.filter((c: Conversation) => c.id !== id);
      const newCurrentId =
        state.currentConversationId === id
          ? filtered[0]?.id || null
          : state.currentConversationId;

      if (filtered.length === 0) {
        const defaultConversationId = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        const defaultSessionId = generateUniqueSessionId();
        const defaultConversation = buildDefaultConversation(
          defaultConversationId,
          defaultSessionId,
          getApiUrl()
        );
        debouncedSaveToLocalStorage(get);
        return {
          conversations: [defaultConversation],
          currentConversationId: defaultConversationId,
          sessionId: defaultSessionId,
        };
      }

      debouncedSaveToLocalStorage(get);
      return { conversations: filtered, currentConversationId: newCurrentId };
    });
  },

  deleteAllConversations: async () => {
    const state = get();
    const conversationsToDelete = [...state.conversations];

    debugLog(`🗑️ Deleting all conversations (${conversationsToDelete.length} total)`);
    audioStreamManager.stop();

    const deletionTasks = conversationsToDelete.map(async conversation => {
      if (!conversation?.sessionId) return;
      try {
        const isConfigured = await ensureApiConfigured();
        if (!isConfigured) {
          logError('Failed to configure API for conversation deletion');
          return;
        }

        const conversationAdapterName = conversation.adapterName;
        if (!conversationAdapterName) {
          debugLog(`Skipping server deletion for conversation ${conversation.id}: adapter not configured`);
          return;
        }

        const api = await getApi();
        const apiClient: ApiClient = new api.ApiClient({
          apiUrl: resolveApiUrl(conversation.apiUrl),
          sessionId: conversation.sessionId,
          adapterName: conversationAdapterName,
        });

        const fileIds = [
          ...(conversation.attachedFiles?.map(f => f.file_id) || []),
          ...extractGeneratedFileIds(conversation.messages || []),
        ];

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

    const results = await Promise.allSettled(deletionTasks);
    const failures = results.filter(r => r.status === 'rejected');
    if (failures.length > 0) {
      logError(`Some conversations failed to delete from server: ${failures.length}`, failures);
    }

    const defaultConversationId = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const defaultSessionId = generateUniqueSessionId();
    const defaultConversation = buildDefaultConversation(defaultConversationId, defaultSessionId, getApiUrl());

    set({
      conversations: [defaultConversation],
      currentConversationId: defaultConversationId,
      sessionId: defaultSessionId,
    });
    debouncedSaveToLocalStorage(get);
  },

  deleteThread: async (conversationId: string, parentMessageId: string, threadId: string) => {
    const conversation = get().conversations.find(conv => conv.id === conversationId);
    if (!conversation) throw new Error('Conversation not found');
    if (!conversation.adapterName) throw new Error('Adapter not configured for this conversation');

    const parentMessage = conversation.messages.find(msg => msg.id === parentMessageId);
    if (!parentMessage?.threadInfo || parentMessage.threadInfo.thread_id !== threadId) {
      throw new Error('Thread not found for this message');
    }

    const conversationApiUrl = resolveApiUrl(conversation.apiUrl || getApiUrl());
    const api = await getApi();
    const apiClient = new api.ApiClient({
      apiUrl: conversationApiUrl,
      sessionId: conversation.sessionId,
      adapterName: conversation.adapterName,
    });

    const threadService = new (await import('../services/threadService')).ThreadService(apiClient);
    await threadService.deleteThread(threadId);

    set(state => ({
      conversations: state.conversations.map(conv => {
        if (conv.id !== conversationId) return conv;

        const messages = conv.messages
          .filter(msg => {
            if (!msg.isThreadMessage) return true;
            return !(msg.threadId === threadId || msg.parentMessageId === parentMessageId);
          })
          .map(msg => {
            if (msg.id !== parentMessageId) return msg;
            return { ...msg, threadInfo: undefined, supportsThreading: true };
          });

        const shouldResetThreadPointers =
          conv.currentThreadId === threadId ||
          conv.currentThreadSessionId === parentMessage.threadInfo?.thread_session_id;

        return {
          ...conv,
          messages,
          currentThreadId: shouldResetThreadPointers ? undefined : conv.currentThreadId,
          currentThreadSessionId: shouldResetThreadPointers ? undefined : conv.currentThreadSessionId,
          updatedAt: new Date(),
        };
      }),
    }));

    debouncedSaveToLocalStorage(get);
  },

  sendMessage: async (content: string, fileIds?: string[], threadId?: string, model?: string, skill?: string) => {
    let streamingConversationId: string | null = null;
    try {
      if (get().isLoading) {
        debugWarn('Another request is already in progress');
        return;
      }

      const isConfigured = await ensureApiConfigured();
      if (!isConfigured) {
        throw new Error('API not properly configured. Please configure API settings first.');
      }

      let conversationId = get().currentConversationId;
      if (!conversationId) {
        conversationId = get().createConversation();
      }

      const conversation = get().conversations.find(conv => conv.id === conversationId);
      if (!conversation) throw new Error('Conversation not found');

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
              const existingFile = conversation?.attachedFiles?.find(f => f.file_id === fileId);
              if (existingFile) return existingFile;
              return { file_id: fileId, filename: '', mime_type: '', file_size: 0 };
            })
            .filter((f): f is FileAttachment => f !== undefined)
        : [];

      if (fileAttachments.length > 0) {
        fileAttachments.forEach(file => {
          get().addFileToConversation(conversationId!, file);
        });
      }

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

      const nonStreamingMessages = countNonStreamingMessages(conversation.messages);
      const maxMessagesPerConversation = AppConfig.maxMessagesPerConversation;
      if (maxMessagesPerConversation !== null && nonStreamingMessages >= maxMessagesPerConversation) {
        if (getIsAuthConfigured() && !getIsAuthenticated()) {
          useLoginPromptStore.getState().openLoginPrompt(
            `You've reached the guest limit of ${maxMessagesPerConversation} messages per conversation. Sign in to send more messages, or delete conversations to start over.`
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
              `You've reached the guest limit of ${maxTotalMessages} total messages. Sign in to continue chatting, or delete conversations to start over.`
            );
          }
          debugWarn(`[chatStore] Workspace reached the total message limit (${maxTotalMessages}).`);
          set({ isLoading: false });
          return;
        }
      }

      const userMessage: Message = {
        id: generateUniqueMessageId('user'),
        content,
        role: 'user',
        timestamp: new Date(),
        attachments: fileAttachments.length > 0 ? fileAttachments : undefined,
      };

      const assistantMessageId = generateUniqueMessageId('assistant');
      const assistantMessage: Message = {
        id: assistantMessageId,
        content: '',
        role: 'assistant',
        timestamp: new Date(),
        isStreaming: true,
        model,
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
              msg.threadId === activeThreadId || msg.parentMessageId === threadParentMessage!.id;
            return matchesThread && !(msg.role === 'assistant' && msg.isStreaming);
          });
          if (existingThreadMessages.length >= maxMessagesPerThread) {
            if (getIsAuthConfigured() && !getIsAuthenticated()) {
              useLoginPromptStore.getState().openLoginPrompt(
                `You've reached the guest limit of ${maxMessagesPerThread} messages per thread. Sign in to continue this thread, or delete conversations to start over.`
              );
            }
            debugWarn(`[chatStore] Thread ${activeThreadId} reached the message limit (${maxMessagesPerThread}).`);
            set({ isLoading: false });
            return;
          }
        }
      }

      // Single atomic update: clean up any existing streaming messages, then add user + assistant
      set(state => {
        const currentConv = state.conversations.find(c => c.id === conversationId);
        const streamingMsgs = currentConv?.messages.filter(m => m.role === 'assistant' && m.isStreaming) || [];
        if (streamingMsgs.length > 0) {
          debugWarn(`Cleaning up ${streamingMsgs.length} existing streaming messages`);
        }

        return {
          conversations: state.conversations.map(conv => {
            if (conv.id !== conversationId) return conv;
            const existingMessages = conv.messages.filter(m => !(m.role === 'assistant' && m.isStreaming));
            return {
              ...conv,
              messages: [...existingMessages, userMessage, assistantMessage],
              updatedAt: new Date(),
              title:
                conv.messages.length === 0
                  ? content.slice(0, 50) + (content.length > 50 ? '...' : '')
                  : conv.title,
            };
          }),
          isLoading: true,
          error: null,
        };
      });

      streamingConversationId = conversationId;
      let receivedAnyText = false;

      audioStreamManager.reset();

      try {
        const currentConversation = get().conversations.find(conv => conv.id === streamingConversationId);
        if (!currentConversation) throw new Error('Conversation not found');
        if (!currentConversation.adapterName) {
          throw new Error('Adapter not configured for this conversation. Please select an adapter first.');
        }

        const conversationApiUrl = resolveApiUrl(currentConversation.apiUrl);
        const conversationAdapterName = currentConversation.adapterName;
        const activeSessionId = threadSessionId || currentConversation.sessionId;

        const api = await getApi();
        api.configureApi(conversationApiUrl, activeSessionId, conversationAdapterName);

        if (activeThreadId && activeSessionId !== currentConversation.sessionId) {
          debugLog(`[chatStore] Thread mode: using thread session ${activeSessionId} (original: ${currentConversation.sessionId})`);
        }

        const { returnAudio, ttsVoice, language, audioFormat } = getAudioSettings(currentConversation);
        debugLog(`[chatStore] Audio settings:`, { returnAudio, ttsVoice, language, audioFormat });

        const abortController = new AbortController();
        activeAbortController = abortController;
        activeStreamSessionId = activeSessionId;
        activeStreamConversationId = streamingConversationId;
        activeRequestId = null;

        for await (const response of api.streamChat(
          content,
          true,
          fileIds,
          activeThreadId || undefined,
          undefined,
          undefined,
          language,
          returnAudio,
          ttsVoice,
          undefined,
          undefined,
          model,
          skill
        )) {
          if (response.request_id && !activeRequestId) {
            activeRequestId = response.request_id;
            debugLog(`[chatStore] >>> CAPTURED request_id for stop: ${response.request_id}`);
          }

          if (response.audio_chunk) {
            audioStreamManager.addChunk({
              audio: response.audio_chunk,
              audioFormat: response.audioFormat || 'opus',
              chunkIndex: response.chunk_index ?? 0,
            });
          }

          if (response.text) {
            const sanitizedText = sanitizeMessageContent(response.text);
            if (sanitizedText) {
              get().appendToLastMessage(sanitizedText, streamingConversationId, assistantMessageId);
              receivedAnyText = true;
            } else if (response.text.length > 100) {
              debugWarn('[chatStore] Filtered out potential base64 audio data from message content');
            }
          }

          if (response.audio && response.done) {
            set(state =>
              updateLastAssistantMessage(state, streamingConversationId!, () => ({
                audio: response.audio,
                audioFormat: response.audioFormat || 'mp3',
              }), assistantMessageId)
            );
          }

          if (response.image && response.done) {
            receivedAnyText = true;
            set(state =>
              updateLastAssistantMessage(state, streamingConversationId!, () => ({
                image: response.image,
                imageFormat: response.image_format || 'png',
                imageRevisedPrompt: response.image_revised_prompt,
                imageUrl: response.image_url,
              }), assistantMessageId)
            );
          }

          if ((response.video || response.video_url) && response.done) {
            receivedAnyText = true;
            set(state =>
              updateLastAssistantMessage(state, streamingConversationId!, () => ({
                video: response.video,
                videoFormat: response.video_format || 'mp4',
                videoRevisedPrompt: response.video_revised_prompt,
                videoUrl: response.video_url,
              }), assistantMessageId)
            );
          }

          if ((response.document || response.document_url) && response.done) {
            receivedAnyText = true;
            set(state =>
              updateLastAssistantMessage(state, streamingConversationId!, () => ({
                document: response.document,
                documentFormat: response.document_format || 'pdf',
                documentRevisedPrompt: response.document_revised_prompt,
                documentUrl: response.document_url,
              }), assistantMessageId)
            );
          }

          if (response.generated_audio_url && response.done) {
            receivedAnyText = true;
            set(state =>
              updateLastAssistantMessage(state, streamingConversationId!, () => ({
                generatedAudioFormat: response.generated_audio_format || 'mp3',
                generatedAudioRevisedPrompt: response.generated_audio_revised_prompt,
                generatedAudioUrl: response.generated_audio_url,
              }), assistantMessageId)
            );
          }

          if (response.done) {
            debugLog(`[chatStore] Stream completed, receivedAnyText:`, receivedAnyText);

            const threadingInfo = response.threading;
            if (threadingInfo?.supports_threading) {
              set(state => ({
                conversations: state.conversations.map(conv => {
                  if (conv.id !== streamingConversationId) return conv;
                  return {
                    ...conv,
                    messages: conv.messages.map(msg =>
                      msg.id === assistantMessageId
                        ? { ...msg, supportsThreading: true, databaseMessageId: threadingInfo.message_id }
                        : msg
                    ),
                    updatedAt: new Date(),
                  };
                }),
              }));
            }

            if (response.assistant_message_id) {
              set(state => ({
                conversations: state.conversations.map(conv => {
                  if (conv.id !== streamingConversationId) return conv;
                  return {
                    ...conv,
                    messages: conv.messages.map(msg =>
                      msg.id === assistantMessageId && !msg.databaseMessageId
                        ? { ...msg, databaseMessageId: response.assistant_message_id }
                        : msg
                    ),
                    updatedAt: new Date(),
                  };
                }),
              }));
            }

            if (response.model) {
              set(state =>
                updateLastAssistantMessage(state, streamingConversationId!, () => ({
                  model: response.model,
                }), assistantMessageId)
              );
            }

            break;
          }
        }

        if (!receivedAnyText && !abortController.signal.aborted) {
          get().appendToLastMessage(
            'No response received from the server. Please try again later.',
            streamingConversationId,
            assistantMessageId
          );
        }
      } catch (error) {
        const isAbortError =
          error instanceof Error &&
          (error.name === 'AbortError' ||
            error.message === 'Stream cancelled by user' ||
            error.message.includes('aborted'));

        if (isAbortError) {
          debugLog('[chatStore] Stream was cancelled by user');
          receivedAnyText = true;
        } else {
          logError('Chat API error:', error);
          let errorMessage = 'Sorry, there was an error processing your request.';
          if (error instanceof Error) {
            if (error.message.startsWith('Server error:')) {
              errorMessage = error.message.substring('Server error: '.length);
            } else if (
              error.message.includes('Could not connect') ||
              error.message.includes('timed out')
            ) {
              errorMessage = error.message;
            }
          }
          get().appendToLastMessage(errorMessage, streamingConversationId, assistantMessageId);
        }
      }

      activeAbortController = null;
      activeRequestId = null;
      activeStreamSessionId = null;
      activeStreamConversationId = null;

      flushStreamingBuffer(streamingConversationId, set);

      set(state => {
        const updatedConversations = state.conversations.map(conv =>
          conv.id === streamingConversationId
            ? {
                ...conv,
                messages: conv.messages.map(msg =>
                  msg.id === assistantMessageId ? { ...msg, isStreaming: false } : msg
                ),
                updatedAt: new Date(),
              }
            : conv
        );
        const currentConv = updatedConversations.find(conv => conv.id === state.currentConversationId);
        return {
          conversations: updatedConversations,
          isLoading: currentConv
            ? currentConv.messages.some(msg => msg.role === 'assistant' && msg.isStreaming)
            : false,
        };
      });

      debouncedSaveToLocalStorage(get);
    } catch (error) {
      logError('Chat store error:', error);
      set(state => ({
        isLoading: false,
        ...(state.currentConversationId === streamingConversationId && {
          error: `Failed to send message: ${error instanceof Error ? error.message : 'Unknown error'}`,
        }),
      }));
    }
  },

  createThread: async (messageId: string, sessionId: string) => {
    try {
      const conversation = get().conversations.find(conv => conv.sessionId === sessionId);
      if (!conversation) throw new Error('Conversation not found for session');
      if (!conversation.adapterName) throw new Error('Adapter not configured for this conversation');

      const message = conversation.messages.find(msg => msg.id === messageId);
      if (!message) throw new Error('Message not found');

      const dbMessageId = message.databaseMessageId || messageId;
      const conversationApiUrl = resolveApiUrl(conversation.apiUrl || getApiUrl());

      const api = await getApi();
      const apiClient = new api.ApiClient({
        apiUrl: conversationApiUrl,
        sessionId,
        adapterName: conversation.adapterName,
      });

      const threadService = new (await import('../services/threadService')).ThreadService(apiClient);
      const threadInfo = await threadService.createThread(dbMessageId, sessionId);

      set(state => ({
        conversations: state.conversations.map(conv => {
          if (conv.sessionId !== sessionId) return conv;
          return {
            ...conv,
            messages: conv.messages.map(msg =>
              msg.id === messageId
                ? { ...msg, threadInfo, supportsThreading: true }
                : msg
            ),
            currentThreadId: undefined,
            currentThreadSessionId: undefined,
          };
        }),
      }));

      debugLog(`[chatStore] Created thread ${threadInfo.thread_id} for message ${messageId}`);
    } catch (error) {
      logError('Failed to create thread:', error);
      throw error;
    }
  },

  appendToLastMessage: (content: string, conversationId?: string, messageId?: string) => {
    const sanitizedContent = sanitizeMessageContent(content);
    if (!sanitizedContent && content) {
      debugWarn('[chatStore] Filtered out base64 audio data from message content');
      return;
    }

    const finalContent = truncateLongContent(sanitizedContent);
    const targetConversationId = conversationId || get().currentConversationId;
    if (!targetConversationId) return;

    const bufferKey = targetConversationId;
    const existing = streamingBuffer.get(bufferKey);

    if (existing) {
      existing.content += finalContent;
      existing.messageId = messageId;
      if (existing.timeoutId) clearTimeout(existing.timeoutId);
    } else {
      streamingBuffer.set(bufferKey, { content: finalContent, timeoutId: null, messageId });
    }

    const flushBuffer = () => {
      const buffer = streamingBuffer.get(bufferKey);
      if (!buffer || !buffer.content) return;

      const contentToAppend = buffer.content;
      const targetMessageId = buffer.messageId;
      buffer.content = '';
      buffer.timeoutId = null;

      set(state => ({
        conversations: state.conversations.map(conv => {
          if (conv.id !== targetConversationId) return conv;
          const messages = [...conv.messages];
          // Target the specific streaming message by id when known — "last message"
          // is wrong when regenerating a non-final turn (see updateLastAssistantMessage).
          const targetIdx = targetMessageId
            ? messages.findIndex(m => m.id === targetMessageId)
            : messages.length - 1;
          const targetMessage = targetIdx !== -1 ? messages[targetIdx] : undefined;
          if (targetMessage && targetMessage.role === 'assistant' && targetMessage.isStreaming) {
            messages[targetIdx] = {
              ...targetMessage,
              content: targetMessage.content + contentToAppend,
            };
          }
          return { ...conv, messages, updatedAt: new Date() };
        }),
      }));
    };

    const buffer = streamingBuffer.get(bufferKey)!;
    buffer.timeoutId = setTimeout(flushBuffer, STREAMING_BATCH_DELAY);
  },

  regenerateResponse: async (messageId: string, model?: string) => {
    let regeneratingConversationId: string | null = null;
    try {
      if (get().isLoading) {
        debugWarn('Another request is already in progress');
        return;
      }

      const isConfigured = await ensureApiConfigured();
      if (!isConfigured) throw new Error('API not properly configured');

      const state = get();
      const currentConv = state.conversations.find(c => c.id === state.currentConversationId);
      if (!currentConv) return;

      const messageIndex = currentConv.messages.findIndex(m => m.id === messageId);
      if (messageIndex === -1) return;

      const previousAssistantMessage = currentConv.messages[messageIndex];
      if (!previousAssistantMessage || previousAssistantMessage.role !== 'assistant') return;

      const userMessage = currentConv.messages[messageIndex - 1];
      if (!userMessage || userMessage.role !== 'user') return;

      const attachmentIds = (userMessage.attachments || [])
        .map(file => file.file_id)
        .filter((fileId): fileId is string => typeof fileId === 'string' && fileId.length > 0);

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
                    isStreaming: true,
                    model,
                    supportsThreading: previousAssistantMessage.supportsThreading,
                    databaseMessageId: previousAssistantMessage.databaseMessageId,
                    threadInfo: previousAssistantMessage.threadInfo,
                    threadId: previousAssistantMessage.threadId,
                    parentMessageId: previousAssistantMessage.parentMessageId,
                    isThreadMessage: previousAssistantMessage.isThreadMessage,
                  },
                  ...conv.messages.slice(messageIndex + 1),
                ],
                updatedAt: new Date(),
              }
            : conv
        ),
        isLoading: true,
        error: null,
      }));

      regeneratingConversationId = state.currentConversationId;
      if (!regeneratingConversationId) throw new Error('No conversation selected');

      await _runStreamIntoMessage(
        get,
        set,
        newAssistantMessageId,
        regeneratingConversationId,
        userMessage.content,
        attachmentIds,
        model,
        'regenerate',
        previousAssistantMessage.databaseMessageId
      );
    } catch (error) {
      logError('Regenerate error:', error);
      set(state => ({
        isLoading: false,
        ...(state.currentConversationId === regeneratingConversationId && {
          error: `Failed to regenerate response: ${error instanceof Error ? error.message : 'Unknown error'}`,
        }),
      }));
    }
  },

  editMessageAndRegenerate: async (messageId: string, newContent: string, model?: string) => {
    let editingConversationId: string | null = null;
    try {
      if (get().isLoading) {
        await get().stopStreaming();
        // Flush any buffered chunks from the cancelled stream before creating the
        // new assistant message — otherwise late appendToLastMessage calls can
        // corrupt the new regenerated bubble's content.
        const prevConvId = get().currentConversationId;
        if (prevConvId) flushStreamingBuffer(prevConvId, set);
      }

      // Capture state after any in-flight stream has stopped and buffer drained
      const state = get();
      const currentConv = state.conversations.find(c => c.id === state.currentConversationId);
      if (!currentConv) return;

      const messageIndex = currentConv.messages.findIndex(m => m.id === messageId);
      if (messageIndex === -1) return;

      const userMessage = currentConv.messages[messageIndex];
      if (userMessage.role !== 'user') return;

      const attachmentIds = (userMessage.attachments || [])
        .map(file => file.file_id)
        .filter((fileId): fileId is string => typeof fileId === 'string' && fileId.length > 0);

      const newAssistantMessageId = generateUniqueMessageId('assistant');

      // Preserve the previous assistant reply's databaseMessageId (if any) so the
      // server can overwrite that turn in place instead of storing a duplicate —
      // the server resolves and updates the paired (edited) user turn on its own.
      const previousAssistantMessage = currentConv.messages[messageIndex + 1];
      const hasAssistantReply = previousAssistantMessage?.role === 'assistant';
      // The edited user message and its (old) assistant reply occupy messageIndex and
      // messageIndex + 1 — everything after that must be preserved, or editing a
      // non-final turn silently truncates the rest of the conversation.
      const tailStartIndex = hasAssistantReply ? messageIndex + 2 : messageIndex + 1;

      set(state => ({
        conversations: state.conversations.map(conv =>
          conv.id === state.currentConversationId
            ? {
                ...conv,
                messages: [
                  ...conv.messages.slice(0, messageIndex),
                  { ...userMessage, content: newContent, updatedAt: new Date() },
                  {
                    id: newAssistantMessageId,
                    content: '',
                    role: 'assistant' as const,
                    timestamp: new Date(),
                    isStreaming: true,
                    model,
                    supportsThreading: hasAssistantReply ? previousAssistantMessage.supportsThreading : undefined,
                    databaseMessageId: hasAssistantReply ? previousAssistantMessage.databaseMessageId : undefined,
                    threadInfo: hasAssistantReply ? previousAssistantMessage.threadInfo : undefined,
                    threadId: hasAssistantReply ? previousAssistantMessage.threadId : undefined,
                    parentMessageId: hasAssistantReply ? previousAssistantMessage.parentMessageId : undefined,
                    isThreadMessage: hasAssistantReply ? previousAssistantMessage.isThreadMessage : undefined,
                  },
                  ...conv.messages.slice(tailStartIndex),
                ],
                updatedAt: new Date(),
              }
            : conv
        ),
        isLoading: true,
        error: null,
      }));

      editingConversationId = state.currentConversationId;
      if (!editingConversationId) throw new Error('No conversation selected');

      await _runStreamIntoMessage(
        get,
        set,
        newAssistantMessageId,
        editingConversationId,
        newContent,
        attachmentIds,
        model,
        'edit-regenerate',
        hasAssistantReply ? previousAssistantMessage.databaseMessageId : undefined
      );

      // Persist the edited branch so a reload doesn't revert to pre-edit messages
      debouncedSaveToLocalStorage(get);
    } catch (error) {
      logError('Edit & regenerate error:', error);
      set(state => ({
        isLoading: false,
        ...(state.currentConversationId === editingConversationId && {
          error: `Failed to regenerate response: ${error instanceof Error ? error.message : 'Unknown error'}`,
        }),
      }));
    }
  },

  updateConversationTitle: (id: string, title: string) => {
    set(state => ({
      conversations: state.conversations.map(conv =>
        conv.id === id ? { ...conv, title, updatedAt: new Date() } : conv
      ),
    }));
    debouncedSaveToLocalStorage(get);
  },

  clearError: () => set({ error: null }),

  cleanupStreamingMessages: () => {
    const activeConvId = activeStreamConversationId;
    set(state => {
      let hasActiveStream = false;
      const conversations = state.conversations.map(conv => {
        if (conv.id === activeConvId) {
          if (conv.messages.some(m => m.role === 'assistant' && m.isStreaming)) {
            hasActiveStream = true;
          }
          return conv;
        }
        const hasOrphaned = conv.messages.some(m => m.role === 'assistant' && m.isStreaming);
        if (!hasOrphaned) return conv;
        return {
          ...conv,
          messages: conv.messages.filter(m => !(m.role === 'assistant' && m.isStreaming)),
          updatedAt: new Date(),
        };
      });
      return { conversations, isLoading: hasActiveStream };
    });
  },

  canCreateNewConversation: () => {
    const state = get();
    const maxConversations = AppConfig.maxConversations;
    if (!state.currentConversationId) {
      return maxConversations === null || state.conversations.length < maxConversations;
    }
    const currentConversation = state.conversations.find(conv => conv.id === state.currentConversationId);
    const currentConversationHasContent =
      !!currentConversation &&
      (currentConversation.messages.length > 0 || (currentConversation.attachedFiles?.length || 0) > 0);
    if (currentConversationHasContent) {
      return maxConversations === null || state.conversations.length < maxConversations;
    }
    return false;
  },

  getConversationCount: () => get().conversations.length,

  addFileToConversation: (conversationId: string, file: FileAttachment) => {
    debugLog(`[chatStore] addFileToConversation called`, { conversationId, fileId: file.file_id, filename: file.filename });
    set(state => ({
      conversations: state.conversations.map(conv =>
        conv.id === conversationId
          ? {
              ...conv,
              attachedFiles: [
                ...(conv.attachedFiles || []).filter(f => f.file_id !== file.file_id),
                file,
              ],
              updatedAt: new Date(),
            }
          : conv
      ),
    }));
    debouncedSaveToLocalStorage(get);
  },

  removeFileFromConversation: async (conversationId: string, fileId: string) => {
    debugLog(`[chatStore] removeFileFromConversation called`, { conversationId, fileId });
    try {
      const conversation = get().conversations.find(conv => conv.id === conversationId);
      if (!conversation) throw new Error('Conversation not found');
      if (!conversation.adapterName) throw new Error('Adapter not configured for this conversation. Cannot delete file.');

      await FileUploadService.deleteFile(
        fileId,
        undefined,
        resolveApiUrl(conversation.apiUrl),
        conversation.adapterName
      );
      debugLog(`[chatStore] Successfully deleted file ${fileId} from server`);
    } catch (error: unknown) {
      if (
        error instanceof Error &&
        (error.message.includes('404') || error.message.includes('File not found'))
      ) {
        debugLog(`[chatStore] File ${fileId} was already deleted from server`);
      } else {
        debugError(`[chatStore] Failed to delete file ${fileId} from server:`, error);
      }
    }

    revokeFileThumbnail(fileId);

    set(state => ({
      conversations: state.conversations.map(conv =>
        conv.id === conversationId
          ? {
              ...conv,
              attachedFiles: (conv.attachedFiles || []).filter(f => f.file_id !== fileId),
              updatedAt: new Date(),
            }
          : conv
      ),
    }));
    debouncedSaveToLocalStorage(get);
  },

  loadConversationFiles: async (conversationId: string) => {
    try {
      const conversation = get().conversations.find(conv => conv.id === conversationId);
      if (!conversation) return;
      if (!conversation.adapterName) {
        debugLog(`Skipping file load for conversation ${conversationId}: adapter not configured`);
        return;
      }

      const existingFileIds = new Set((conversation.attachedFiles || []).map(f => f.file_id));
      if (existingFileIds.size === 0) {
        debugLog(`No files to sync for conversation ${conversationId}`);
        return;
      }

      const allFiles = await FileUploadService.listFiles(
        undefined,
        resolveApiUrl(conversation.apiUrl),
        conversation.adapterName
      );

      const serverFilesMap = new Map(
        allFiles.map(file => [
          file.file_id,
          {
            file_id: file.file_id,
            filename: file.filename,
            mime_type: file.mime_type,
            file_size: file.file_size,
            upload_timestamp: file.upload_timestamp,
            processing_status: file.processing_status,
            chunk_count: file.chunk_count,
          } as FileAttachment,
        ])
      );

      set(state => {
        const conv = state.conversations.find(c => c.id === conversationId);
        if (!conv) return state;

        const updatedFiles: FileAttachment[] = (conv.attachedFiles || [])
          .map(existingFile => serverFilesMap.get(existingFile.file_id) || existingFile)
          .filter(
            file =>
              serverFilesMap.has(file.file_id) ||
              !file.processing_status ||
              file.processing_status === 'processing'
          );

        return {
          conversations: state.conversations.map(c =>
            c.id === conversationId ? { ...c, attachedFiles: updatedFiles, updatedAt: new Date() } : c
          ),
        };
      });

      debouncedSaveToLocalStorage(get);
    } catch (error) {
      logError(`Failed to load files for conversation ${conversationId}:`, error);
    }
  },

  syncConversationFiles: async (conversationId: string) => {
    await get().loadConversationFiles(conversationId);
  },

  syncConversationsWithBackend: async () => {
    try {
      const state = get();
      if (state.conversations.length === 0) return;

      const api = await getApi();
      const limit =
        AppConfig.maxMessagesPerConversation !== null
          ? AppConfig.maxMessagesPerConversation || undefined
          : undefined;

      let historyEndpointUnsupported = false;

      const syncResults = await Promise.all(
        state.conversations.map(async conversation => {
          if (!conversation.sessionId) return null;
          if (!conversation.adapterName) {
            debugWarn(`[chatStore] Skipping backend sync for conversation ${conversation.id} - adapter not configured`);
            return null;
          }
          // Empty conversations (e.g. a freshly created one in single-adapter mode,
          // which gets an adapterName assigned immediately) never had their session
          // registered on the backend - fetching history for them 422s.
          if (conversation.messages.length === 0) return null;

          try {
            const apiClient = new api.ApiClient({
              apiUrl: resolveApiUrl(conversation.apiUrl),
              sessionId: conversation.sessionId,
              adapterName: conversation.adapterName,
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
              if (conversation.messages.length === 0) return null;
              return {
                id: conversation.id,
                sessionId: history?.session_id || conversation.sessionId,
                messages: [] as Message[],
                cleared: true,
                updatedAt: new Date(),
              };
            }

            const normalizedMessages = convertHistoryMessages(historyMessages, conversation.messages);

            // Thread messages live under a separate session on the backend — preserve them
            // from local state so a backend sync doesn't wipe them out.
            const threadMessages = conversation.messages.filter(m => m.isThreadMessage);
            const mergedMessages = ensureUniqueMessageIds(
              threadMessages.length > 0 ? [...normalizedMessages, ...threadMessages] : normalizedMessages
            );

            if (haveSameMessages(conversation.messages, mergedMessages)) return null;

            return {
              id: conversation.id,
              sessionId: history?.session_id || conversation.sessionId,
              messages: mergedMessages,
              cleared: false,
              updatedAt: normalizedMessages[normalizedMessages.length - 1]?.timestamp || new Date(),
            };
          } catch (error) {
            debugWarn(`[chatStore] Failed to sync session ${conversation.sessionId}:`, error);
            return null;
          }
        })
      );

      const updates = syncResults.filter(
        (result): result is { id: string; sessionId: string; messages: Message[]; cleared: boolean; updatedAt: Date } =>
          Boolean(result)
      );

      if (updates.length === 0) return;

      set(currentState => {
        const updateMap = new Map(updates.map(u => [u.id, u]));
        return {
          conversations: currentState.conversations.map(conv => {
            const update = updateMap.get(conv.id);
            if (!update) return conv;
            if (update.cleared) {
              return {
                ...conv,
                sessionId: update.sessionId || conv.sessionId,
                messages: [],
                attachedFiles: [],
                title: DEFAULT_CONVERSATION_TITLE,
                updatedAt: update.updatedAt,
                adapterLoadError: null,
              };
            }
            return {
              ...conv,
              sessionId: update.sessionId || conv.sessionId,
              messages: update.messages,
              updatedAt: update.updatedAt,
              adapterLoadError: null,
            };
          }),
          currentConversationId: currentState.currentConversationId,
        };
      });

      debouncedSaveToLocalStorage(get);
    } catch (error) {
      debugWarn('Failed to synchronize conversations with backend:', error);
    }
  },

  stopStreaming: async () => {
    if (!get().isLoading) {
      debugLog('[chatStore] stopStreaming called but not currently loading');
      return;
    }

    debugLog('[chatStore] Stopping stream...', {
      hasAbortController: !!activeAbortController,
      requestId: activeRequestId,
      sessionId: activeStreamSessionId,
    });

    if (activeAbortController) activeAbortController.abort();

    if (activeRequestId && activeStreamSessionId) {
      try {
        const api = await getApi();
        const cancelled = await api.stopChat?.(activeStreamSessionId, activeRequestId);
        debugLog(`[chatStore] Server-side cancellation result: ${cancelled}`);
      } catch (error) {
        debugWarn('[chatStore] Failed to cancel server-side stream:', error);
      }
    } else {
      debugWarn(`[chatStore] Cannot call stopChat - missing IDs: requestId=${activeRequestId}, sessionId=${activeStreamSessionId}`);
    }

    const targetConversationId = activeStreamConversationId || get().currentConversationId;
    if (targetConversationId) {
      set(state => ({
        conversations: state.conversations.map(conv => {
          if (conv.id !== targetConversationId) return conv;
          return {
            ...conv,
            messages: conv.messages.map(msg =>
              msg.isStreaming ? { ...msg, isStreaming: false } : msg
            ),
            updatedAt: new Date(),
          };
        }),
        isLoading: false,
      }));
    } else {
      set({ isLoading: false });
    }

    activeAbortController = null;
    activeRequestId = null;
    activeStreamSessionId = null;
    activeStreamConversationId = null;

    debugLog('[chatStore] Stream stopped successfully');
  },

  clearCurrentConversationAdapter: () => {
    const currentConversationId = get().currentConversationId;
    if (!currentConversationId) return;

    set(state => ({
      conversations: state.conversations.map(conv =>
        conv.id === currentConversationId
          ? { ...conv, adapterName: undefined, adapterInfo: undefined, adapterLoadError: null }
          : conv
      ),
    }));

    debouncedSaveToLocalStorage(get);
  },

  submitFeedback: async (conversationMessageId: string, feedbackType: 'up' | 'down', comment?: string) => {
    const state = get();
    const conversation = state.conversations.find(c => c.id === state.currentConversationId);
    if (!conversation) return false;

    const message = conversation.messages.find(m => m.id === conversationMessageId);
    if (!message?.databaseMessageId) {
      debugWarn('[chatStore] Cannot submit feedback: no databaseMessageId on message');
      return false;
    }
    if (!conversation.adapterName) return false;

    try {
      const api = await getApi();
      const apiClient = new api.ApiClient({
        apiUrl: resolveApiUrl(conversation.apiUrl || getApiUrl()),
        sessionId: conversation.sessionId,
        adapterName: conversation.adapterName,
      });

      const result = await apiClient.submitFeedback!(
        message.databaseMessageId,
        conversation.sessionId,
        feedbackType,
        comment
      );

      const newFeedbackType = result.feedback_type as 'up' | 'down' | null;
      const newComment = (result.comment ?? null) as string | null;
      set(s => ({
        conversations: s.conversations.map(conv => {
          if (conv.id !== state.currentConversationId) return conv;
          return {
            ...conv,
            messages: conv.messages.map(msg =>
              msg.id === conversationMessageId
                ? { ...msg, feedback: newFeedbackType, feedbackComment: newComment }
                : msg
            ),
            updatedAt: new Date(),
          };
        }),
      }));

      debouncedSaveToLocalStorage(get);
      return true;
    } catch (error) {
      debugError('[chatStore] Failed to submit feedback:', error);
      return false;
    }
  },

  loadFeedbackForConversation: async (sessionId: string) => {
    const state = get();
    const conversation = state.conversations.find(c => c.sessionId === sessionId);
    if (!conversation?.adapterName) return;

    try {
      const api = await getApi();
      const apiClient = new api.ApiClient({
        apiUrl: resolveApiUrl(conversation.apiUrl || getApiUrl()),
        sessionId: conversation.sessionId,
        adapterName: conversation.adapterName,
      });

      const sessionIds = new Set<string>([sessionId]);
      for (const msg of conversation.messages) {
        if (msg.threadInfo?.thread_session_id) {
          sessionIds.add(msg.threadInfo.thread_session_id);
        }
      }

      const feedbackResults = await Promise.all(
        Array.from(sessionIds).map(sid =>
          apiClient.getSessionFeedback!(sid).catch(() => ({ feedbacks: [] }))
        )
      );

      const feedbackMap = new Map<string, { feedbackType: 'up' | 'down'; comment: string | null }>();
      for (const result of feedbackResults) {
        if (result?.feedbacks) {
          for (const fb of result.feedbacks) {
            feedbackMap.set(fb.message_id, {
              feedbackType: fb.feedback_type as 'up' | 'down',
              comment: fb.comment ?? null,
            });
          }
        }
      }

      if (feedbackMap.size === 0) return;

      set(s => ({
        conversations: s.conversations.map(conv => {
          if (conv.sessionId !== sessionId) return conv;
          return {
            ...conv,
            messages: conv.messages.map(msg => {
              if (msg.databaseMessageId && feedbackMap.has(msg.databaseMessageId)) {
                const entry = feedbackMap.get(msg.databaseMessageId)!;
                return { ...msg, feedback: entry.feedbackType, feedbackComment: entry.comment };
              }
              return msg;
            }),
          };
        }),
      }));
    } catch (error) {
      debugError('[chatStore] Failed to load feedback:', error);
    }
  },
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

  const saved = localStorage.getItem('chat-state');
  const runtimeApiUrl = getApiUrl();
  const hasStoredApiOverride = Boolean(localStorage.getItem('chat-api-url'));
  let sessionId = getOrCreateSessionId();
  let hasExistingConversations = false;

  if (saved) {
    try {
      const parsedState = JSON.parse(saved) as PersistedChatState;
      const toDate = (value: string | number | Date | undefined): Date => {
        if (value instanceof Date) return value;
        const parsedDate = value ? new Date(value) : new Date();
        return Number.isNaN(parsedDate.getTime()) ? new Date() : parsedDate;
      };

      const storedConversations = Array.isArray(parsedState.conversations)
        ? parsedState.conversations
        : [];

      const normalizedConversations: Conversation[] = storedConversations.map(storedConversation => {
        const storedMessages = Array.isArray(storedConversation.messages)
          ? storedConversation.messages
          : [];
        const sanitizedMessages: Message[] = storedMessages
          .filter(msg => !(msg.role === 'assistant' && msg.isStreaming))
          .map(msg => ({ ...msg, timestamp: toDate(msg.timestamp), isStreaming: false }));
        const uniqueMessages = ensureUniqueMessageIds(sanitizedMessages);

        const normalized: Conversation = {
          id: storedConversation.id,
          sessionId: storedConversation.sessionId || generateUniqueSessionId(),
          title: normalizeStoredTitle(storedConversation.title),
          messages: uniqueMessages,
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

        // Empty placeholder conversations always follow the runtime config URL
        const isPlaceholderConversation = normalized.messages.length === 0 && !normalized.adapterName;
        return {
          ...normalized,
          apiUrl:
            isPlaceholderConversation && !hasStoredApiOverride
              ? runtimeApiUrl
              : resolveApiUrl(storedConversation.apiUrl),
        };
      });

      hasExistingConversations = normalizedConversations.length > 0;

      if (parsedState.currentConversationId && normalizedConversations.length > 0) {
        const current = normalizedConversations.find(c => c.id === parsedState.currentConversationId);
        if (current?.sessionId) sessionId = current.sessionId;
      }

      if (normalizedConversations.length === 0) {
        const defaultConversationId = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        const defaultSessionId = generateUniqueSessionId();
        const defaultConversation = buildDefaultConversation(defaultConversationId, defaultSessionId, getApiUrl());
        useChatStore.setState({
          conversations: [defaultConversation],
          currentConversationId: defaultConversationId,
          sessionId: defaultSessionId,
        });
        sessionId = defaultSessionId;
      } else {
        useChatStore.setState({
          conversations: normalizedConversations,
          currentConversationId: parsedState.currentConversationId || normalizedConversations[0]?.id || null,
          sessionId,
        });
        if (!parsedState.currentConversationId && normalizedConversations.length > 0) {
          useChatStore.setState({
            currentConversationId: normalizedConversations[0].id,
            sessionId: normalizedConversations[0].sessionId || sessionId,
          });
          sessionId = normalizedConversations[0].sessionId || sessionId;
        }
      }

      debugLog('📋 Loaded conversations:', useChatStore.getState().conversations.map(conv => ({
        id: conv.id,
        title: conv.title,
        sessionId: conv.sessionId,
        messageCount: conv.messages?.length || 0,
      })));

      setTimeout(() => useChatStore.getState().cleanupStreamingMessages(), 100);
    } catch (error) {
      logError('Failed to load chat state:', error);
      const defaultConversationId = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      const defaultSessionId = generateUniqueSessionId();
      const defaultConversation = buildDefaultConversation(defaultConversationId, defaultSessionId, getApiUrl());
      useChatStore.setState({
        conversations: [defaultConversation],
        currentConversationId: defaultConversationId,
        sessionId: defaultSessionId,
      });
      sessionId = defaultSessionId;
    }
  } else {
    const defaultConversationId = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const defaultSessionId = generateUniqueSessionId();
    const defaultConversation = buildDefaultConversation(defaultConversationId, defaultSessionId, getApiUrl());
    useChatStore.setState({
      conversations: [defaultConversation],
      currentConversationId: defaultConversationId,
      sessionId: defaultSessionId,
    });
    sessionId = defaultSessionId;
  }

  localStorage.removeItem('chat-api-key');

  const currentState = useChatStore.getState();
  const currentConversation = currentState.currentConversationId
    ? currentState.conversations.find(conv => conv.id === currentState.currentConversationId)
    : null;

  const apiUrlToUse =
    hasExistingConversations && currentConversation?.apiUrl ? currentConversation.apiUrl : getApiUrl();

  try {
    const api = await getApi();
    const existingAdapterName = currentConversation?.adapterName;

    if (!existingAdapterName) {
      debugLog('No adapter selected yet. Waiting for user selection before configuring API.');
    } else {
      api.configureApi(apiUrlToUse, sessionId, existingAdapterName);
      currentApiUrl = apiUrlToUse;
      apiConfigured = true;

      if (!currentConversation?.adapterInfo) {
        try {
          const validationClient = new api.ApiClient({
            apiUrl: apiUrlToUse,
            sessionId: null,
            adapterName: existingAdapterName,
          });
          if (typeof validationClient.getAdapterInfo === 'function') {
            const adapterInfo = await validationClient.getAdapterInfo();
            debugLog('Adapter info loaded for existing adapter:', adapterInfo);

            const stateAfterLoad = useChatStore.getState();
            if (stateAfterLoad.currentConversationId) {
              useChatStore.setState({
                conversations: stateAfterLoad.conversations.map(conv =>
                  conv.id === stateAfterLoad.currentConversationId
                    ? { ...conv, adapterInfo, adapterLoadError: null, updatedAt: new Date() }
                    : conv
                ),
              });
              setTimeout(() => {
                const updatedState = useChatStore.getState();
                localStorage.setItem(
                  'chat-state',
                  JSON.stringify({
                    conversations: updatedState.conversations,
                    currentConversationId: updatedState.currentConversationId,
                  })
                );
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

  try {
    await useChatStore.getState().syncConversationsWithBackend();
  } catch (syncError) {
    debugWarn('Conversation history sync skipped:', syncError);
  }
};

if (typeof window !== 'undefined') {
  initializeStore();
}
