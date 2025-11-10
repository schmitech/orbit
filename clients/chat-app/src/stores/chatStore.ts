import { create } from 'zustand';
import { getApi, ApiClient } from '../api/loader';
import { Message, Conversation, ChatState, FileAttachment, AdapterInfo } from '../types';
import { FileUploadService } from '../services/fileService';
import { debugLog, debugWarn, debugError, logError } from '../utils/debug';
import { AppConfig } from '../utils/config';
import { getDefaultKey, getApiUrl } from '../utils/runtimeConfig';

// Default API key from runtime configuration
const DEFAULT_API_KEY = getDefaultKey();

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
  deleteAllConversations: () => Promise<void>;
  sendMessage: (content: string, fileIds?: string[]) => Promise<void>;
  appendToLastMessage: (content: string, conversationId?: string) => void;
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

    // Check localStorage first, then runtime configuration
    const apiUrl = localStorage.getItem('chat-api-url') || 
                  getApiUrl() || 
                  (window as any).CHATBOT_API_URL ||
                  'http://localhost:3000';

    const apiKey = localStorage.getItem('chat-api-key') || DEFAULT_API_KEY;
    const sessionId = getOrCreateSessionId();
    api.configureApi(apiUrl, apiKey, sessionId);
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
      // Load the API
      const api = await getApi();
      
      // Validate API key and fetch adapter info if provided
      let adapterInfo: AdapterInfo | undefined;
      if (apiKey && apiKey.trim()) {
        try {
          // Create a temporary client to validate the API key
          const validationClient = new api.ApiClient({
            apiUrl,
            apiKey,
            sessionId: null
          });
          
          // Check if validateApiKey method exists (for backward compatibility)
          if (typeof validationClient.validateApiKey === 'function') {
            debugLog('Validating API key before configuration...');
            const status = await validationClient.validateApiKey();
            debugLog('API key validation successful:', {
              exists: status.exists,
              active: status.active,
              adapter_name: status.adapter_name,
              client_name: status.client_name
            });
          } else {
            debugWarn('API key validation not available (validateApiKey method not found)');
            // Continue without validation if method doesn't exist (backward compatibility)
          }
          
          // Fetch adapter info right after validation using the same client
          // Include 'default-key' since it's a valid key in the backend
          if (typeof validationClient.getAdapterInfo === 'function') {
            try {
              adapterInfo = await validationClient.getAdapterInfo();
              debugLog('Adapter info loaded:', adapterInfo);
            } catch (error) {
              debugWarn('Failed to load adapter info:', error);
              // Don't fail configuration if adapter info fails to load
            }
          }
        } catch (validationError: any) {
          // api.ts already throws user-friendly error messages, so we can just re-throw them
          // This avoids duplicating error message logic and keeps the code DRY
          if (validationError instanceof Error) {
            throw validationError;
          }
          // Fallback for non-Error objects
          throw new Error(`API key validation failed: ${validationError?.message || 'Unknown error'}`);
        }
      }
      
      // If validation passed (or no API key provided), proceed with configuration
      api.configureApi(apiUrl, apiKey || '', actualSessionId);
      currentApiUrl = apiUrl;
      apiConfigured = true;
      
      // Store API key and URL in the current conversation
      // If no conversation exists, create one
      // Include 'default-key' since it's a valid key
      if (currentConversation && apiKey && apiKey.trim()) {
        // Update existing conversation with API key and adapter info
        set(state => ({
          conversations: state.conversations.map(conv =>
            conv.id === currentConversation.id
              ? {
                  ...conv,
                  apiKey: apiKey, // Always use the provided API key if it was validated
                  apiUrl: apiUrl,
                  adapterInfo: adapterInfo,
                  updatedAt: new Date()
                }
              : conv
          )
        }));
        
        // Save to localStorage immediately
        setTimeout(() => {
          const currentState = get();
          localStorage.setItem('chat-state', JSON.stringify({
            conversations: currentState.conversations,
            currentConversationId: currentState.currentConversationId
          }));
        }, 0);
      } else if (apiKey && apiKey.trim()) {
        // No conversation exists, create one with the configured API key
        const newId = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        const newSessionId = generateUniqueSessionId();
        const newConversation: Conversation = {
          id: newId,
          sessionId: newSessionId,
          title: 'New Chat',
          messages: [],
          createdAt: new Date(),
          updatedAt: new Date(),
          apiKey: apiKey,
          apiUrl: apiUrl,
          adapterInfo: adapterInfo
        };
        
        set(state => {
          let updatedConversations = [newConversation, ...state.conversations];
          
          // Enforce maximum conversations limit
          const maxConversations = AppConfig.maxConversations;
          if (maxConversations !== null && updatedConversations.length > maxConversations) {
            // Remove oldest conversations (keep the most recent ones)
            updatedConversations = updatedConversations.slice(0, maxConversations);
          }
          
          return {
            conversations: updatedConversations,
            currentConversationId: newId,
            sessionId: newSessionId
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
      }
    } catch (error) {
      debugError('Failed to configure API:', error);
      // Ensure isLoading is not stuck when validation fails
      // Don't set global loading state - this is just configuration, not message sending
      set({ isLoading: false });
      // Re-throw the error so it can be displayed to the user
      if (error instanceof Error) {
        throw error;
      }
      throw new Error('Failed to configure API settings');
    }

    // Save settings to localStorage only if configuration was successful
    localStorage.setItem('chat-api-url', apiUrl);
    if (apiKey) {
      localStorage.setItem('chat-api-key', apiKey);
    }
    
    // Ensure isLoading is false after successful configuration
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
    const newSessionId = generateUniqueSessionId(); // Create unique session for this conversation
    // New conversations default to the configured default key
    const defaultApiUrl = 'http://localhost:3000';
    const defaultApiKey = DEFAULT_API_KEY;
    const newConversation: Conversation = {
      id,
      sessionId: newSessionId,
      title: 'New Chat',
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date(),
      apiKey: defaultApiKey,
      apiUrl: defaultApiUrl
    };

    // Update state with new conversation and switch to its session
    set((state: ExtendedChatState) => {
      let updatedConversations = [newConversation, ...state.conversations];
      
      // Enforce maximum conversations limit
      const maxConversations = AppConfig.maxConversations;
      if (maxConversations !== null && updatedConversations.length > maxConversations) {
        // Remove oldest conversations (keep the most recent ones)
        updatedConversations = updatedConversations.slice(0, maxConversations);
      }
      
      return {
        conversations: updatedConversations,
        currentConversationId: id,
        sessionId: newSessionId
      };
    });

    // Reconfigure API with the new session ID and the default API key
    ensureApiConfigured().then(isConfigured => {
      if (isConfigured) {
        getApi().then(api => {
          api.configureApi(defaultApiUrl, defaultApiKey, newSessionId);
          
          // Load adapter info for the default key when creating a new conversation
          try {
            const validationClient = new api.ApiClient({
              apiUrl: defaultApiUrl,
              apiKey: defaultApiKey,
              sessionId: null
            });
            
            if (typeof validationClient.getAdapterInfo === 'function') {
              validationClient.getAdapterInfo().then(adapterInfo => {
                debugLog('✅ Adapter info loaded for default key in new conversation:', adapterInfo);
                const currentState = useChatStore.getState();
                useChatStore.setState({
                  conversations: currentState.conversations.map(conv =>
                    conv.id === id
                      ? { ...conv, adapterInfo: adapterInfo, updatedAt: new Date() }
                      : conv
                  )
                });
              }).catch((error) => {
                debugWarn('Failed to load adapter info for default key in new conversation:', error);
              });
            }
          } catch (error) {
            debugWarn('Failed to load adapter info for default key:', error);
          }
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
      
      // Use conversation's stored API key and URL (use default key if not configured, don't fall back to localStorage)
      const conversationApiUrl = conversation.apiUrl || 'http://localhost:3000';
      const conversationApiKey = conversation.apiKey || DEFAULT_API_KEY;
      
      // Reconfigure API with the conversation's session ID and API key
      const isConfigured = await ensureApiConfigured();
      if (isConfigured) {
        const api = await getApi();
        api.configureApi(conversationApiUrl, conversationApiKey, conversation.sessionId);
        
        // Load adapter info if not already loaded
        // Include 'default-key' since it's a valid key
        if (!conversation.adapterInfo) {
          try {
            const adapterClient = new api.ApiClient({
              apiUrl: conversationApiUrl,
              apiKey: conversationApiKey,
              sessionId: null
            });
            
            if (typeof adapterClient.getAdapterInfo === 'function') {
              const adapterInfo = await adapterClient.getAdapterInfo();
              debugLog('Adapter info loaded for conversation:', adapterInfo);
              
              // Update conversation with adapter info
              set(state => ({
                conversations: state.conversations.map(conv =>
                  conv.id === id
                    ? { ...conv, adapterInfo: adapterInfo, updatedAt: new Date() }
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
            }
          } catch (error) {
            debugWarn('Failed to load adapter info for conversation:', error);
            // Don't fail conversation selection if adapter info fails to load
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
    const conversation = get().conversations.find(conv => conv.id === id);

    debugLog(`🗑️ Deleting conversation ${id}:`, {
      conversationId: id,
      sessionId: conversation?.sessionId,
      title: conversation?.title,
      messageCount: conversation?.messages.length,
      fileCount: conversation?.attachedFiles?.length || 0
    });

    // If conversation has a session ID, delete conversation and files in one call
    if (conversation?.sessionId) {
      try {
        // Ensure API is properly configured first
        const isConfigured = await ensureApiConfigured();
        if (!isConfigured) {
          logError('Failed to configure API for conversation deletion');
          // Continue with local deletion even if API configuration fails
        } else {
          // Use conversation's stored API key and URL (don't fall back to localStorage)
          // This ensures each conversation uses its own API key for deletion
          const conversationApiUrl = conversation.apiUrl || 'http://localhost:3000';
          const conversationApiKey = conversation.apiKey || DEFAULT_API_KEY;
          
          debugLog(`🔑 Using conversation's API key for deletion: ${conversationApiKey.substring(0, 8)}... (conversation: ${id})`);
          
          // Create API client with the conversation's session ID and API key
          const api = await getApi();
          const apiClient: ApiClient = new api.ApiClient({
            apiUrl: conversationApiUrl,
            apiKey: conversationApiKey,
            sessionId: conversation.sessionId
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
      let newCurrentId = state.currentConversationId === id 
        ? (filtered[0]?.id || null) 
        : state.currentConversationId;

      // If all conversations are deleted, create a new default conversation
      if (filtered.length === 0) {
        const defaultConversationId = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        const defaultSessionId = generateUniqueSessionId();
        const defaultConversation: Conversation = {
          id: defaultConversationId,
          sessionId: defaultSessionId,
          title: 'New Chat',
          messages: [],
          createdAt: new Date(),
          updatedAt: new Date(),
          apiKey: DEFAULT_API_KEY,
          apiUrl: 'http://localhost:3000'
        };

        // Configure API with default key and validate it
        ensureApiConfigured().then(isConfigured => {
          if (isConfigured) {
            getApi().then(api => {
              api.configureApi('http://localhost:3000', DEFAULT_API_KEY, defaultSessionId);
              
              // Validate and load adapter info for default key
              try {
                const validationClient = new api.ApiClient({
                  apiUrl: 'http://localhost:3000',
                  apiKey: DEFAULT_API_KEY,
                  sessionId: null
                });
                
                if (typeof validationClient.validateApiKey === 'function') {
                  validationClient.validateApiKey().then(() => {
                    debugLog('✅ Default API key validated after creating new conversation');
                  }).catch(() => {
                    debugWarn('Failed to validate default API key');
                  });
                }
                
                if (typeof validationClient.getAdapterInfo === 'function') {
                  validationClient.getAdapterInfo().then(adapterInfo => {
                    debugLog('✅ Adapter info loaded for default key:', adapterInfo);
                    // Update the conversation with adapter info
                    const currentState = useChatStore.getState();
                    useChatStore.setState({
                      conversations: currentState.conversations.map(conv =>
                        conv.id === defaultConversationId
                          ? { ...conv, adapterInfo: adapterInfo, updatedAt: new Date() }
                          : conv
                      )
                    });
                  }).catch(() => {
                    debugWarn('Failed to load adapter info for default key');
                  });
                }
              } catch (error) {
                debugWarn('Failed to validate default API key:', error);
              }
            });
          }
        });

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

    // Delete all conversations from server
    for (const conversation of conversationsToDelete) {
      if (conversation?.sessionId) {
        try {
          const isConfigured = await ensureApiConfigured();
          if (!isConfigured) {
            logError('Failed to configure API for conversation deletion');
            continue;
          }

          const conversationApiUrl = conversation.apiUrl || 'http://localhost:3000';
          const conversationApiKey = conversation.apiKey || DEFAULT_API_KEY;
          
          const api = await getApi();
          const apiClient: ApiClient = new api.ApiClient({
            apiUrl: conversationApiUrl,
            apiKey: conversationApiKey,
            sessionId: conversation.sessionId
          });

          const fileIds = conversation?.attachedFiles?.map(f => f.file_id) || [];

          if (apiClient.deleteConversationWithFiles) {
            await apiClient.deleteConversationWithFiles(conversation.sessionId, fileIds);
            debugLog(`✅ Deleted conversation ${conversation.id} and files`);
          }
        } catch (error) {
          logError(`Failed to delete conversation ${conversation.id} from server:`, error);
          // Continue with other conversations even if one fails
        }
      }
    }

    // Create a new default conversation after deleting all
    const defaultConversationId = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const defaultSessionId = generateUniqueSessionId();
    const defaultConversation: Conversation = {
      id: defaultConversationId,
      sessionId: defaultSessionId,
      title: 'New Chat',
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date(),
      apiKey: DEFAULT_API_KEY,
      apiUrl: 'http://localhost:3000'
    };

    // Configure API with default key and validate it
    ensureApiConfigured().then(isConfigured => {
      if (isConfigured) {
        getApi().then(api => {
          api.configureApi('http://localhost:3000', DEFAULT_API_KEY, defaultSessionId);
          
          // Validate and load adapter info for default key
          try {
            const validationClient = new api.ApiClient({
              apiUrl: 'http://localhost:3000',
              apiKey: DEFAULT_API_KEY,
              sessionId: null
            });
            
            if (typeof validationClient.validateApiKey === 'function') {
              validationClient.validateApiKey().then(() => {
                debugLog('✅ Default API key validated after clearing all conversations');
              }).catch(() => {
                debugWarn('Failed to validate default API key');
              });
            }
            
            if (typeof validationClient.getAdapterInfo === 'function') {
              validationClient.getAdapterInfo().then(adapterInfo => {
                debugLog('✅ Adapter info loaded for default key:', adapterInfo);
                const currentState = useChatStore.getState();
                useChatStore.setState({
                  conversations: currentState.conversations.map(conv =>
                    conv.id === defaultConversationId
                      ? { ...conv, adapterInfo: adapterInfo, updatedAt: new Date() }
                      : conv
                  )
                });
              }).catch(() => {
                debugWarn('Failed to load adapter info for default key');
              });
            }
          } catch (error) {
            debugWarn('Failed to validate default API key:', error);
          }
        });
      }
    });

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

  sendMessage: async (content: string, fileIds?: string[]) => {
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

      // Check message limits before adding messages
      // We'll handle cleanup in the set() call below to ensure atomic updates

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
      let trimmedPerConversation = false;
      let trimmedTotalMessages = false;

      // Single atomic update for both messages with message limit cleanup
      set(state => {
        // Clean up any existing streaming messages first
        const currentConv = state.conversations.find(c => c.id === conversationId);
        const streamingMsgs = currentConv?.messages.filter(m => m.role === 'assistant' && m.isStreaming) || [];
        if (streamingMsgs.length > 0) {
          debugWarn(`Cleaning up ${streamingMsgs.length} existing streaming messages`);
        }

        // Apply message limit cleanup before adding new messages
        let updatedConversations = state.conversations.map(conv => {
          if (conv.id !== conversationId) {
            // For other conversations, check per-conversation limit
            const maxMessagesPerConversation = AppConfig.maxMessagesPerConversation;
            if (maxMessagesPerConversation !== null) {
              const nonStreamingMessages = conv.messages.filter(m => !(m.role === 'assistant' && m.isStreaming));
              if (nonStreamingMessages.length >= maxMessagesPerConversation) {
                trimmedPerConversation = true;
                // Remove oldest messages to make room (keep at least 1 message for context)
                const messagesToKeep = Math.max(1, maxMessagesPerConversation - 1);
                const filteredMessages = nonStreamingMessages.slice(-messagesToKeep);
                const streamingMessages = conv.messages.filter(m => m.role === 'assistant' && m.isStreaming);
                return {
                  ...conv,
                  messages: [...filteredMessages, ...streamingMessages]
                };
              }
            }
            return conv;
          }
          
          // For current conversation, prepare messages for new message addition
          const nonStreamingMessages = conv.messages.filter(m => !(m.role === 'assistant' && m.isStreaming));
          
          // Check per-conversation message limit
          const maxMessagesPerConversation = AppConfig.maxMessagesPerConversation;
          let messagesToAdd = nonStreamingMessages;
          if (maxMessagesPerConversation !== null && nonStreamingMessages.length >= maxMessagesPerConversation) {
            trimmedPerConversation = true;
            // Remove oldest messages to make room (keep at least 1 message for context)
            const messagesToKeep = Math.max(1, maxMessagesPerConversation - 1);
            messagesToAdd = nonStreamingMessages.slice(-messagesToKeep);
          }
          
          return {
            ...conv,
            messages: [
              ...messagesToAdd,
              userMessage,
              assistantMessage
            ],
            updatedAt: new Date(),
            title: conv.messages.length === 0 
              ? content.slice(0, 50) + (content.length > 50 ? '...' : '')
              : conv.title
          };
        });

        // Check total messages limit across all conversations
        const maxTotalMessages = AppConfig.maxTotalMessages;
        if (maxTotalMessages !== null) {
          const totalMessages = updatedConversations.reduce(
            (total, conv) => total + conv.messages.filter(m => !(m.role === 'assistant' && m.isStreaming)).length,
            0
          );
          
          if (totalMessages > maxTotalMessages) {
            trimmedTotalMessages = true;
            // Remove oldest messages from oldest conversations
            let remainingToRemove = totalMessages - maxTotalMessages;
            const sortedConversations = [...updatedConversations].sort((a, b) => 
              a.updatedAt.getTime() - b.updatedAt.getTime()
            );
            
            for (const conv of sortedConversations) {
              if (remainingToRemove <= 0) break;
              
              const nonStreamingMessages = conv.messages.filter(m => !(m.role === 'assistant' && m.isStreaming));
              if (nonStreamingMessages.length > 0) {
                const toRemove = Math.min(remainingToRemove, nonStreamingMessages.length);
                const streamingMessages = conv.messages.filter(m => m.role === 'assistant' && m.isStreaming);
                const updatedMessages = [
                  ...nonStreamingMessages.slice(toRemove),
                  ...streamingMessages
                ];
                
                const convIndex = updatedConversations.findIndex(c => c.id === conv.id);
                if (convIndex !== -1) {
                  updatedConversations[convIndex] = {
                    ...conv,
                    messages: updatedMessages
                  };
                }
                
                remainingToRemove -= toRemove;
              }
            }
          }
        }

        return {
          conversations: updatedConversations,
          isLoading: true,
          error: null
        };
      });

      if (trimmedPerConversation || trimmedTotalMessages) {
        const notices: string[] = [];
        if (trimmedPerConversation && AppConfig.maxMessagesPerConversation !== null) {
          notices.push(
            `Only the most recent ${AppConfig.maxMessagesPerConversation} messages are kept per conversation. Older messages in this chat were removed automatically.`
          );
        }
        if (trimmedTotalMessages && AppConfig.maxTotalMessages !== null) {
          notices.push(
            `There is a workspace limit of ${AppConfig.maxTotalMessages} total messages. Older conversations were trimmed to stay within that limit.`
          );
        }
        if (notices.length > 0) {
          set({ error: notices.join(' ') });
        }
      }

      // Store conversationId in a variable so we can use it even if user switches conversations
      const streamingConversationId = conversationId;
      let receivedAnyText = false;

      try {
      // Ensure API is configured with the current conversation's session ID and API key
      // Get fresh conversation state to ensure we have the latest API key
      const currentConversation = get().conversations.find(conv => conv.id === streamingConversationId);
      if (!currentConversation) {
        throw new Error('Conversation not found');
      }
      
      // Check if conversation has an API key configured
      if (!currentConversation.apiKey) {
        debugWarn(`[sendMessage] Conversation ${streamingConversationId} has no API key`);
        throw new Error('API key not configured for this conversation. Please configure API settings first.');
      }
      
      debugLog(`[sendMessage] Using API key for conversation ${streamingConversationId}: ${currentConversation.apiKey.substring(0, 8)}...`);
      
      if (currentConversation.sessionId) {
        // Use conversation's stored API key and URL
        const conversationApiUrl = currentConversation.apiUrl || 'http://localhost:3000';
        const conversationApiKey = currentConversation.apiKey;
        
        const api = await getApi();
        // Reconfigure API with the current conversation's session ID and API key to ensure consistency
        api.configureApi(
          conversationApiUrl,
          conversationApiKey,
          currentConversation.sessionId
        );
      }
        
        // Load the API and stream the response
        const api = await getApi();
        debugLog(`[chatStore] Starting streamChat with fileIds:`, fileIds);
        for await (const response of api.streamChat(content, true, fileIds)) {
          debugLog(`[chatStore] Received stream chunk:`, { text: response.text?.substring(0, 50), done: response.done });
          if (response.text) {
            // Always append to the conversation that initiated the stream, not the current one
            get().appendToLastMessage(response.text, streamingConversationId);
            receivedAnyText = true;
            // Add a small delay to slow down the streaming effect
            await new Promise(resolve => setTimeout(resolve, 30));
          }
          
          if (response.done) {
            debugLog(`[chatStore] Stream completed, receivedAnyText:`, receivedAnyText);
            break;
          }
        }

        // If no text received, show error
        if (!receivedAnyText) {
          debugWarn(`[chatStore] No text received from stream, showing error message`);
          get().appendToLastMessage('No response received from the server. Please try again later.', streamingConversationId);
        }
      } catch (error) {
        logError('Chat API error:', error);
        get().appendToLastMessage('Sorry, there was an error processing your request.', streamingConversationId);
      }

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

  appendToLastMessage: (content: string, conversationId?: string) => {
    set(state => {
      // Use provided conversationId or current conversation
      const targetConversationId = conversationId || state.currentConversationId;
      
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
              content: lastMessage.content + content
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
        
        // Check if conversation has an API key configured
        if (!currentConversation.apiKey) {
          throw new Error('API key not configured for this conversation. Please configure API settings first.');
        }
        
        if (currentConversation.sessionId) {
          // Use conversation's stored API key and URL
          const conversationApiUrl = currentConversation.apiUrl || 'http://localhost:3000';
          const conversationApiKey = currentConversation.apiKey;
          
          const api = await getApi();
          // Reconfigure API with the current conversation's session ID and API key to ensure consistency
          api.configureApi(
            conversationApiUrl,
            conversationApiKey,
            currentConversation.sessionId
          );
        }
        
        const api = await getApi();
        for await (const response of api.streamChat(userMessage.content, true, undefined)) {
          if (response.text) {
            // Always append to the conversation that initiated the regenerate, not the current one
            get().appendToLastMessage(response.text, regeneratingConversationId);
            receivedAnyText = true;
            // Add a small delay to slow down the streaming effect
            await new Promise(resolve => setTimeout(resolve, 30));
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
        get().appendToLastMessage('Sorry, there was an error regenerating the response.', regeneratingConversationId);
      }

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
      
      // Check if conversation has an API key configured
      if (!conversation.apiKey) {
        throw new Error('API key not configured for this conversation. Cannot delete file.');
      }
      
      // Use conversation's stored API key and URL
      const conversationApiKey = conversation.apiKey;
      const conversationApiUrl = conversation.apiUrl || 'http://localhost:3000';
      
      // Delete from server
      debugLog(`[chatStore] Calling FileUploadService.deleteFile for ${fileId}`);
      await FileUploadService.deleteFile(fileId, conversationApiKey, conversationApiUrl);
      debugLog(`[chatStore] Successfully deleted file ${fileId} from server`);
    } catch (error: any) {
      // If file was already deleted (404), that's fine - just log and continue
      if (error.message && (error.message.includes('404') || error.message.includes('File not found'))) {
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
      
      // Check if conversation has an API key configured
      if (!conversation.apiKey) {
        // Skip loading files if API key is not configured
        debugLog(`Skipping file load for conversation ${conversationId}: API key not configured`);
        return;
      }
      
      // Use conversation's stored API key and URL
      const conversationApiKey = conversation.apiKey;
      const conversationApiUrl = conversation.apiUrl || 'http://localhost:3000';
      
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
      
      // Get all files from server for this API key
      const allFiles = await FileUploadService.listFiles(conversationApiKey, conversationApiUrl);
      
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
  }
}));

// Initialize store from localStorage
const initializeStore = async () => {
  // Then initialize the rest of the store
  const saved = localStorage.getItem('chat-state');
  let sessionId = getOrCreateSessionId(); // Default session ID
  let hasExistingConversations = false;
  
  if (saved) {
    try {
      const parsedState = JSON.parse(saved);
      // Restore Date objects and clean up any streaming messages
      // For backward compatibility: initialize conversations without apiKey/apiUrl with 'default-key'
      parsedState.conversations = parsedState.conversations.map((conv: any) => ({
        ...conv,
        sessionId: conv.sessionId || generateUniqueSessionId(), // Generate sessionId for existing conversations if missing
        createdAt: new Date(conv.createdAt),
        updatedAt: new Date(conv.updatedAt),
        attachedFiles: conv.attachedFiles || [], // Ensure attachedFiles exists
        // Preserve existing API keys - only use default if missing (backward compatibility)
        // This ensures existing conversations maintain their associated API keys
        apiKey: conv.apiKey || DEFAULT_API_KEY,
        apiUrl: conv.apiUrl || 'http://localhost:3000',
        // Preserve adapterInfo if it exists
        adapterInfo: conv.adapterInfo || undefined,
        messages: conv.messages
          .filter((msg: any) => !(msg.role === 'assistant' && msg.isStreaming)) // Remove any streaming messages
          .map((msg: any) => ({
            ...msg,
            timestamp: new Date(msg.timestamp),
            isStreaming: false // Ensure no messages are marked as streaming
          }))
      }));
      
      // Check if we have existing conversations
      hasExistingConversations = parsedState.conversations && parsedState.conversations.length > 0;
      
      // If there's a current conversation, use its session ID
      if (parsedState.currentConversationId && parsedState.conversations) {
        const currentConversation = parsedState.conversations.find(
          (conv: any) => conv.id === parsedState.currentConversationId
        );
        if (currentConversation && currentConversation.sessionId) {
          sessionId = currentConversation.sessionId;
        }
      }
      
      // If conversations array is empty, create a default conversation with DEFAULT_API_KEY
      // Always use default-key when there are no conversations, regardless of localStorage
      if (!parsedState.conversations || parsedState.conversations.length === 0) {
        const defaultConversationId = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        const defaultSessionId = generateUniqueSessionId();
        const defaultConversation: Conversation = {
          id: defaultConversationId,
          sessionId: defaultSessionId,
          title: 'New Chat',
          messages: [],
          createdAt: new Date(),
          updatedAt: new Date(),
          apiKey: DEFAULT_API_KEY, // Always use default-key when no conversations exist
          apiUrl: 'http://localhost:3000'
        };
        
        useChatStore.setState({
          conversations: [defaultConversation],
          currentConversationId: defaultConversationId,
          sessionId: defaultSessionId
        });
        
        sessionId = defaultSessionId;
      } else {
        // Existing conversations - preserve their API keys
        useChatStore.setState({
          conversations: parsedState.conversations || [],
          currentConversationId: parsedState.currentConversationId || parsedState.conversations[0]?.id || null,
          sessionId: sessionId
        });
        
        // If no current conversation is set, use the first one
        if (!parsedState.currentConversationId && parsedState.conversations.length > 0) {
          useChatStore.setState({
            currentConversationId: parsedState.conversations[0].id,
            sessionId: parsedState.conversations[0].sessionId || sessionId
          });
          sessionId = parsedState.conversations[0].sessionId || sessionId;
        }
      }
      
      // Debug: Log loaded conversations and their session IDs
      const loadedConversations = useChatStore.getState().conversations;
      debugLog('📋 Loaded conversations:', loadedConversations.map((conv: any) => ({
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
      const defaultConversation: Conversation = {
        id: defaultConversationId,
        sessionId: defaultSessionId,
        title: 'New Chat',
        messages: [],
        createdAt: new Date(),
        updatedAt: new Date(),
        apiKey: DEFAULT_API_KEY,
        apiUrl: 'http://localhost:3000'
      };
      
      useChatStore.setState({
        conversations: [defaultConversation],
        currentConversationId: defaultConversationId,
        sessionId: defaultSessionId
      });
      
      sessionId = defaultSessionId;
    }
  } else {
    // No saved state - create a default conversation with DEFAULT_API_KEY
    // Always use default-key when there are no conversations, regardless of localStorage
    const defaultConversationId = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const defaultSessionId = generateUniqueSessionId();
    const defaultConversation: Conversation = {
      id: defaultConversationId,
      sessionId: defaultSessionId,
      title: 'New Chat',
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date(),
      apiKey: DEFAULT_API_KEY, // Always use default-key when no conversations exist
      apiUrl: 'http://localhost:3000'
    };
    
    useChatStore.setState({
      conversations: [defaultConversation],
      currentConversationId: defaultConversationId,
      sessionId: defaultSessionId
    });
    
    sessionId = defaultSessionId;
  }
  
  // Determine which API key/URL to use for API configuration
  // If there are no existing conversations, always use DEFAULT_API_KEY
  // If there are existing conversations, use the current conversation's API key or default
  const currentState = useChatStore.getState();
  const currentConversation = currentState.currentConversationId
    ? currentState.conversations.find(conv => conv.id === currentState.currentConversationId)
    : null;
  
  // Use current conversation's API key if available and we have existing conversations
  // But if there are no conversations at all, always use default-key
  // This ensures new installations always start with default-key
  const apiKeyToUse = (hasExistingConversations && currentConversation?.apiKey)
    ? currentConversation.apiKey
    : DEFAULT_API_KEY;
  const apiUrlToUse = (hasExistingConversations && currentConversation?.apiUrl)
    ? currentConversation.apiUrl
    : 'http://localhost:3000';
  
  // Auto-configure API with the determined key and validate it
  try {
    const api = await getApi();
    api.configureApi(apiUrlToUse, apiKeyToUse, sessionId);
    currentApiUrl = apiUrlToUse;
    apiConfigured = true;
    
    // Validate and load adapter info for the default key on startup
    // Only validate default key if we're using it (no existing conversations or no conversation key)
    if (apiKeyToUse === DEFAULT_API_KEY) {
      try {
        const validationClient = new api.ApiClient({
          apiUrl: apiUrlToUse,
          apiKey: apiKeyToUse,
          sessionId: null
        });
        
        // Validate the API key
        if (typeof validationClient.validateApiKey === 'function') {
          await validationClient.validateApiKey();
          debugLog('✅ Default API key validated on startup');
        }
        
        // Load adapter info
        if (typeof validationClient.getAdapterInfo === 'function') {
          const adapterInfo = await validationClient.getAdapterInfo();
          debugLog('✅ Adapter info loaded for default key:', adapterInfo);
          
          // Update the current conversation with adapter info
          const currentState = useChatStore.getState();
          if (currentState.currentConversationId) {
            useChatStore.setState({
              conversations: currentState.conversations.map(conv =>
                conv.id === currentState.currentConversationId
                  ? { ...conv, adapterInfo: adapterInfo, updatedAt: new Date() }
                  : conv
              )
            });
          }
        }
      } catch (error) {
        debugWarn('Failed to validate default API key on startup:', error);
        // Don't fail initialization if validation fails
      }
    }
  } catch (error) {
    logError('Failed to initialize API:', error);
  }
};

// Initialize store on import
if (typeof window !== 'undefined') {
  initializeStore();
} 
