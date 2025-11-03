import { create } from 'zustand';
import { getApi, ApiClient } from '../api/loader';
import { Message, Conversation, ChatState, FileAttachment } from '../types';
import { FileUploadService } from '../services/fileService';

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

// Extended chat state for the store
interface ExtendedChatState extends ChatState {
  sessionId: string;
  createConversation: () => string;
  selectConversation: (id: string) => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;
  sendMessage: (content: string, fileIds?: string[]) => Promise<void>;
  appendToLastMessage: (content: string) => void;
  regenerateResponse: (messageId: string) => Promise<void>;
  updateConversationTitle: (id: string, title: string) => void;
  clearError: () => void;
  configureApiSettings: (apiUrl: string, apiKey?: string, sessionId?: string) => Promise<void>;
  getSessionId: () => string;
  cleanupStreamingMessages: () => void;
  canCreateNewConversation: () => boolean;
  getConversationCount: () => number;
  // File management methods
  addFileToConversation: (conversationId: string, file: FileAttachment) => void;
  removeFileFromConversation: (conversationId: string, fileId: string) => Promise<void>;
  loadConversationFiles: (conversationId: string) => Promise<void>;
  syncConversationFiles: (conversationId: string) => Promise<void>;
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

    // Check localStorage first, then environment variables
    const apiUrl = localStorage.getItem('chat-api-url') || 
                  import.meta.env.VITE_API_URL || 
                  (window as any).CHATBOT_API_URL ||
                  'http://localhost:3000';

    const apiKey = localStorage.getItem('chat-api-key') || 'orbit-123456789';
    const sessionId = getOrCreateSessionId();
    api.configureApi(apiUrl, apiKey, sessionId);
    currentApiUrl = apiUrl;
    apiConfigured = true;
    return true;
  } catch (error) {
    console.error('Failed to configure API:', error);
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

  configureApiSettings: async (apiUrl: string, apiKey?: string, sessionId?: string) => {
    const state = get();
    const currentConversation = state.conversations.find(conv => conv.id === state.currentConversationId);
    
    // Use the conversation's session ID if available, otherwise use the provided sessionId or generate one
    const actualSessionId = currentConversation?.sessionId || sessionId || getOrCreateSessionId();
    
    if (sessionId) {
      setSessionId(sessionId);
    }
    set({ sessionId: actualSessionId });
    
    try {
      // Load the API and configure it
      const api = await getApi();
      api.configureApi(apiUrl, apiKey || '', actualSessionId);
      currentApiUrl = apiUrl;
      apiConfigured = true;
    } catch (error) {
      console.error('Failed to configure API:', error);
      throw new Error('Failed to configure API settings');
    }

    // Save settings to localStorage
    localStorage.setItem('chat-api-url', apiUrl);
    if (apiKey) {
      localStorage.setItem('chat-api-key', apiKey);
    }
  },

  createConversation: () => {
    const state = get();
    
    // Check if we can create a new conversation
    if (!state.canCreateNewConversation()) {
      throw new Error('Cannot create new conversation: current conversation is empty or maximum conversations reached');
    }

    const id = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const newSessionId = generateUniqueSessionId(); // Create unique session for this conversation
    const newConversation: Conversation = {
      id,
      sessionId: newSessionId,
      title: 'New Chat',
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date()
    };

    // Update state with new conversation and switch to its session
    set((state: ExtendedChatState) => {
      let updatedConversations = [newConversation, ...state.conversations];
      
      // Enforce maximum 10 conversations limit
      if (updatedConversations.length > 10) {
        // Remove oldest conversations (keep the most recent 10)
        updatedConversations = updatedConversations.slice(0, 10);
      }
      
      return {
        conversations: updatedConversations,
        currentConversationId: id,
        sessionId: newSessionId
      };
    });

    // Reconfigure API with the new session ID
    ensureApiConfigured().then(isConfigured => {
      if (isConfigured) {
        const apiUrl = localStorage.getItem('chat-api-url') || 'http://localhost:3000';
        const apiKey = localStorage.getItem('chat-api-key') || 'orbit-123456789';
        getApi().then(api => {
          api.configureApi(apiUrl, apiKey, newSessionId);
        });
      }
    });

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
      // Switch to the conversation's session ID
      set({ 
        currentConversationId: id,
        sessionId: conversation.sessionId
      });
      
      // Reconfigure API with the conversation's session ID
      const isConfigured = await ensureApiConfigured();
      if (isConfigured) {
        const apiUrl = localStorage.getItem('chat-api-url') || 'http://localhost:3000';
        const apiKey = localStorage.getItem('chat-api-key') || 'orbit-123456789';
        const api = await getApi();
        api.configureApi(apiUrl, apiKey, conversation.sessionId);
      }

      // Sync files for this conversation
      await get().syncConversationFiles(id);
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
    const conversation = get().conversations.find(conv => conv.id === id);

    const debugMode = (import.meta.env as any).VITE_CONSOLE_DEBUG === 'true';
    if (debugMode) {
      console.log(`🗑️ Deleting conversation ${id}:`, {
        conversationId: id,
        sessionId: conversation?.sessionId,
        title: conversation?.title,
        messageCount: conversation?.messages.length,
        fileCount: conversation?.attachedFiles?.length || 0
      });
    }

    // If conversation has a session ID, delete conversation and files in one call
    if (conversation?.sessionId) {
      try {
        // Ensure API is properly configured first
        const isConfigured = await ensureApiConfigured();
        if (!isConfigured) {
          console.error('Failed to configure API for conversation deletion');
          // Continue with local deletion even if API configuration fails
        } else {
          // Create API client with the conversation's session ID
          const api = await getApi();
          const apiClient: ApiClient = new api.ApiClient({
            apiUrl: localStorage.getItem('chat-api-url') || 'http://localhost:3000',
            apiKey: localStorage.getItem('chat-api-key') || 'orbit-123456789',
            sessionId: conversation.sessionId
          });

          // Extract file IDs from attached files
          const fileIds = conversation?.attachedFiles?.map(f => f.file_id) || [];

          if (debugMode) {
            console.log(`🔧 Calling deleteConversationWithFiles for session: ${conversation.sessionId}`);
            console.log(`🔧 File IDs to delete: ${fileIds.join(', ') || 'none'}`);
          }

          // Delete conversation and all associated files in one call
          if (apiClient.deleteConversationWithFiles) {
            const result = await apiClient.deleteConversationWithFiles(conversation.sessionId, fileIds);
            if (debugMode) {
              console.log(`✅ Deleted conversation and files for session: ${conversation.sessionId}`, result);
              console.log(`   - Deleted ${result.deleted_messages} messages`);
              console.log(`   - Deleted ${result.deleted_files} files`);
              if (result.file_deletion_errors && result.file_deletion_errors.length > 0) {
                console.warn(`   - Errors deleting files: ${result.file_deletion_errors.join(', ')}`);
              }
            }
          } else {
            if (debugMode) {
              console.warn(`⚠️ deleteConversationWithFiles method not available on API client`);
            }
          }
        }
      } catch (error) {
        console.error('Failed to clear conversation history from server:', error);
        // Continue with local deletion even if server clear fails
      }
    } else {
      console.warn(`⚠️ No session ID found for conversation ${id}, skipping server-side deletion`);
    }

    set((state: ExtendedChatState) => {
      const filtered = state.conversations.filter((c: Conversation) => c.id !== id);
      const newCurrentId = state.currentConversationId === id 
        ? (filtered[0]?.id || null) 
        : state.currentConversationId;

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

  sendMessage: async (content: string, fileIds?: string[]) => {
    try {
      // Prevent multiple simultaneous requests
      if (get().isLoading) {
        console.warn('Another request is already in progress');
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

      // Single atomic update for both messages
      set(state => {
        // Clean up any existing streaming messages first
        const currentConv = state.conversations.find(c => c.id === conversationId);
        const streamingMsgs = currentConv?.messages.filter(m => m.role === 'assistant' && m.isStreaming) || [];
        if (streamingMsgs.length > 0) {
          console.warn(`Cleaning up ${streamingMsgs.length} existing streaming messages`);
        }

        return {
          conversations: state.conversations.map(conv =>
            conv.id === conversationId
              ? {
                  ...conv,
                  messages: [
                    // Keep all non-streaming messages
                    ...conv.messages.filter(m => !(m.role === 'assistant' && m.isStreaming)),
                    // Add user message
                    userMessage,
                    // Add new streaming assistant message
                    assistantMessage
                  ],
                  updatedAt: new Date(),
                  title: conv.messages.length === 0 
                    ? content.slice(0, 50) + (content.length > 50 ? '...' : '')
                    : conv.title
                }
              : conv
          ),
          isLoading: true,
          error: null
        };
      });

      let receivedAnyText = false;

      try {
        // Ensure API is configured with the current conversation's session ID
        const currentConversation = get().conversations.find(conv => conv.id === conversationId);
        if (currentConversation?.sessionId) {
          const api = await getApi();
          // Reconfigure API with the current conversation's session ID to ensure consistency
          api.configureApi(
            localStorage.getItem('chat-api-url') || 'http://localhost:3000',
            localStorage.getItem('chat-api-key') || 'orbit-123456789',
            currentConversation.sessionId
          );
        }
        
        // Load the API and stream the response
        const api = await getApi();
        console.log(`[chatStore] Starting streamChat with fileIds:`, fileIds);
        for await (const response of api.streamChat(content, true, fileIds)) {
          console.log(`[chatStore] Received stream chunk:`, { text: response.text?.substring(0, 50), done: response.done });
          if (response.text) {
            get().appendToLastMessage(response.text);
            receivedAnyText = true;
            // Add a small delay to slow down the streaming effect
            await new Promise(resolve => setTimeout(resolve, 30));
          }
          
          if (response.done) {
            console.log(`[chatStore] Stream completed, receivedAnyText:`, receivedAnyText);
            break;
          }
        }

        // If no text received, show error
        if (!receivedAnyText) {
          console.warn(`[chatStore] No text received from stream, showing error message`);
          get().appendToLastMessage('No response received from the server. Please try again later.');
        }
      } catch (error) {
        console.error('Chat API error:', error);
        get().appendToLastMessage('Sorry, there was an error processing your request.');
      }

      // Mark message as no longer streaming and stop loading
      set(state => ({
        conversations: state.conversations.map(conv =>
          conv.id === conversationId
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
        ),
        isLoading: false
      }));

      // Save to localStorage
      setTimeout(() => {
        const currentState = get();
        localStorage.setItem('chat-state', JSON.stringify({
          conversations: currentState.conversations,
          currentConversationId: currentState.currentConversationId
        }));
      }, 0);

    } catch (error) {
      console.error('Chat store error:', error);
      set(() => ({
        isLoading: false,
        error: `Failed to send message: ${error instanceof Error ? error.message : 'Unknown error'}`
      }));
    }
  },

  appendToLastMessage: (content: string) => {
    set(state => ({
      conversations: state.conversations.map(conv => {
        if (conv.id !== state.currentConversationId) return conv;
        
        const messages = [...conv.messages];
        const lastMessage = messages[messages.length - 1];
        
        // Only append to streaming assistant messages
        if (lastMessage && lastMessage.role === 'assistant' && lastMessage.isStreaming) {
          messages[messages.length - 1] = {
            ...lastMessage,
            content: lastMessage.content + content
          };
        }
        
        return {
          ...conv,
          messages,
          updatedAt: new Date()
        };
      })
    }));
  },

  regenerateResponse: async (messageId: string) => {
    try {
      // Prevent multiple simultaneous requests
      if (get().isLoading) {
        console.warn('Another request is already in progress');
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

      let receivedAnyText = false;

      try {
        // Ensure API is configured with the current conversation's session ID
        const currentConversation = get().conversations.find(conv => conv.id === state.currentConversationId);
        if (currentConversation?.sessionId) {
          const api = await getApi();
          // Reconfigure API with the current conversation's session ID to ensure consistency
          api.configureApi(
            localStorage.getItem('chat-api-url') || 'http://localhost:3000',
            localStorage.getItem('chat-api-key') || 'orbit-123456789',
            currentConversation.sessionId
          );
        }
        
        const api = await getApi();
        for await (const response of api.streamChat(userMessage.content, true, undefined)) {
          if (response.text) {
            get().appendToLastMessage(response.text);
            receivedAnyText = true;
            // Add a small delay to slow down the streaming effect
            await new Promise(resolve => setTimeout(resolve, 30));
          }
          
          if (response.done) {
            break;
          }
        }

        if (!receivedAnyText) {
          get().appendToLastMessage('No response received from the server. Please try again later.');
        }
      } catch (error) {
        console.error('Regenerate API error:', error);
        get().appendToLastMessage('Sorry, there was an error regenerating the response.');
      }

      // Mark as no longer streaming
      set(state => ({
        conversations: state.conversations.map(conv =>
          conv.id === state.currentConversationId
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
        ),
        isLoading: false
      }));

    } catch (error) {
      console.error('Regenerate error:', error);
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
    set(state => ({
      conversations: state.conversations.map(conv => ({
        ...conv,
        messages: conv.messages.filter(msg => !(msg.role === 'assistant' && msg.isStreaming))
      })),
      isLoading: false
    }));
  },

  // Check if a new conversation can be created
  canCreateNewConversation: () => {
    const state = get();
    
    // If no current conversation, allow creation
    if (!state.currentConversationId) {
      return state.conversations.length < 10;
    }
    
    // Find current conversation
    const currentConversation = state.conversations.find(conv => conv.id === state.currentConversationId);
    
    // If current conversation has messages, allow creation (if under limit)
    if (currentConversation && currentConversation.messages.length > 0) {
      return state.conversations.length < 10;
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
    console.log(`[chatStore] addFileToConversation called`, { conversationId, fileId: file.file_id, filename: file.filename });
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
      console.log(`[chatStore] Updated conversation ${conversationId}`, {
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
    console.log(`[chatStore] removeFileFromConversation called`, {
      conversationId,
      fileId
    });
    try {
      // Delete from server
      console.log(`[chatStore] Calling FileUploadService.deleteFile for ${fileId}`);
      await FileUploadService.deleteFile(fileId);
      console.log(`[chatStore] Successfully deleted file ${fileId} from server`);
    } catch (error: any) {
      // If file was already deleted (404), that's fine - just log and continue
      if (error.message && (error.message.includes('404') || error.message.includes('File not found'))) {
        console.log(`[chatStore] File ${fileId} was already deleted from server`);
      } else {
        console.error(`[chatStore] Failed to delete file ${fileId} from server:`, error);
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
      const files = await FileUploadService.listFiles();
      
      // Convert to FileAttachment format and update conversation
      const fileAttachments: FileAttachment[] = files.map(file => ({
        file_id: file.file_id,
        filename: file.filename,
        mime_type: file.mime_type,
        file_size: file.file_size,
        upload_timestamp: file.upload_timestamp,
        processing_status: file.processing_status,
        chunk_count: file.chunk_count
      }));

      // Update conversation with loaded files (merge with existing, avoid duplicates, update statuses)
      set(state => {
        const conversation = state.conversations.find(conv => conv.id === conversationId);
        if (!conversation) return state;

        // Create a map of server files for quick lookup
        const serverFilesMap = new Map(
          fileAttachments.map(file => [file.file_id, file])
        );

        // Merge: update existing files with server status, add new server files
        const mergedFiles: FileAttachment[] = [
          // Update existing files with server status if available
          ...(conversation.attachedFiles || []).map(existingFile => {
            const serverFile = serverFilesMap.get(existingFile.file_id);
            // Use server file if available (has latest status), otherwise keep existing
            return serverFile || existingFile;
          }),
          // Add new files from server that aren't in conversation yet
          ...fileAttachments.filter(
            serverFile => !(conversation.attachedFiles || []).some(
              existingFile => existingFile.file_id === serverFile.file_id
            )
          )
        ];

        return {
          conversations: state.conversations.map(conv =>
            conv.id === conversationId
              ? {
                  ...conv,
                  attachedFiles: mergedFiles,
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
      console.error(`Failed to load files for conversation ${conversationId}:`, error);
      // Don't throw - allow conversation to load even if file loading fails
    }
  },

  // Sync files when switching conversations
  syncConversationFiles: async (conversationId: string) => {
    await get().loadConversationFiles(conversationId);
  }
}));

// Initialize store from localStorage
const initializeStore = () => {
  // Initialize API configuration first
  const savedApiUrl = localStorage.getItem('chat-api-url') || 'http://localhost:3000';
  const savedApiKey = localStorage.getItem('chat-api-key') || 'orbit-123456789';
  
  // Then initialize the rest of the store
  const saved = localStorage.getItem('chat-state');
  let sessionId = getOrCreateSessionId(); // Default session ID
  
  if (saved) {
    try {
      const parsedState = JSON.parse(saved);
      // Restore Date objects and clean up any streaming messages
      parsedState.conversations = parsedState.conversations.map((conv: any) => ({
        ...conv,
        sessionId: conv.sessionId || generateUniqueSessionId(), // Generate sessionId for existing conversations if missing
        createdAt: new Date(conv.createdAt),
        updatedAt: new Date(conv.updatedAt),
        attachedFiles: conv.attachedFiles || [], // Ensure attachedFiles exists
        messages: conv.messages
          .filter((msg: any) => !(msg.role === 'assistant' && msg.isStreaming)) // Remove any streaming messages
          .map((msg: any) => ({
            ...msg,
            timestamp: new Date(msg.timestamp),
            isStreaming: false // Ensure no messages are marked as streaming
          }))
      }));
      
      // If there's a current conversation, use its session ID
      if (parsedState.currentConversationId && parsedState.conversations) {
        const currentConversation = parsedState.conversations.find(
          (conv: any) => conv.id === parsedState.currentConversationId
        );
        if (currentConversation && currentConversation.sessionId) {
          sessionId = currentConversation.sessionId;
        }
      }
      
      useChatStore.setState({
        conversations: parsedState.conversations || [],
        currentConversationId: parsedState.currentConversationId || null,
        sessionId: sessionId
      });
      
      // Debug: Log loaded conversations and their session IDs
      const debugMode = (import.meta.env as any).VITE_CONSOLE_DEBUG === 'true';
      if (debugMode) {
        console.log('📋 Loaded conversations:', parsedState.conversations.map((conv: any) => ({
          id: conv.id,
          title: conv.title,
          sessionId: conv.sessionId,
          messageCount: conv.messages?.length || 0
        })));
      }
      
      // Clean up any residual streaming messages after initialization
      setTimeout(() => {
        useChatStore.getState().cleanupStreamingMessages();
      }, 100);
    } catch (error) {
      console.error('Failed to load chat state:', error);
    }
  }
  
  // Configure API with saved or default values and the appropriate session ID
  getApi().then(api => {
    api.configureApi(savedApiUrl, savedApiKey, sessionId);
    currentApiUrl = savedApiUrl;
    apiConfigured = true;
  }).catch(error => {
    console.error('Failed to initialize API:', error);
  });
};

// Initialize store on import
if (typeof window !== 'undefined') {
  initializeStore();
} 