import { create } from 'zustand';
import { getApi } from '../api/loader';
import { Message, Conversation, ChatState } from '../types';

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
  sendMessage: (content: string) => Promise<void>;
  appendToLastMessage: (content: string) => void;
  regenerateResponse: (messageId: string) => Promise<void>;
  updateConversationTitle: (id: string, title: string) => void;
  clearError: () => void;
  configureApiSettings: (apiUrl: string, apiKey?: string, sessionId?: string) => Promise<void>;
  getSessionId: () => string;
  cleanupStreamingMessages: () => void;
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
    set((state: ExtendedChatState) => ({
      conversations: [newConversation, ...state.conversations],
      currentConversationId: id,
      sessionId: newSessionId
    }));

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
    
    console.log(`🗑️ Deleting conversation ${id}:`, {
      conversationId: id,
      sessionId: conversation?.sessionId,
      title: conversation?.title,
      messageCount: conversation?.messages.length
    });
    
    // If conversation has a session ID, clear it from the server
    if (conversation?.sessionId) {
      try {
        const api = await getApi();
        const apiClient = new api.ApiClient({
          apiUrl: localStorage.getItem('chat-api-url') || 'http://localhost:3000',
          apiKey: localStorage.getItem('chat-api-key') || 'orbit-123456789',
          sessionId: conversation.sessionId
        });
        
        console.log(`🔧 Calling clearConversationHistory for session: ${conversation.sessionId}`);
        if (apiClient.clearConversationHistory) {
          const result = await apiClient.clearConversationHistory(conversation.sessionId);
          console.log(`✅ Cleared conversation history for session: ${conversation.sessionId}`, result);
        } else {
          console.warn(`⚠️ clearConversationHistory method not available on API client`);
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

  sendMessage: async (content: string) => {
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

      // Add user message and assistant streaming message in a single atomic update
      const userMessage: Message = {
        id: generateUniqueMessageId('user'),
        content,
        role: 'user',
        timestamp: new Date()
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
        // Load the API and stream the response
        const api = await getApi();
        for await (const response of api.streamChat(content)) {
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

        // If no text received, show error
        if (!receivedAnyText) {
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
      set(state => ({
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
        const api = await getApi();
        for await (const response of api.streamChat(userMessage.content)) {
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
      console.log('📋 Loaded conversations:', parsedState.conversations.map((conv: any) => ({
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