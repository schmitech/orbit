import { create } from 'zustand';
import { streamChat, configureApi } from '@schmitech/chatbot-api';
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

// Extended chat state for the store
interface ExtendedChatState extends ChatState {
  sessionId: string;
  createConversation: () => string;
  selectConversation: (id: string) => void;
  deleteConversation: (id: string) => void;
  sendMessage: (content: string) => Promise<void>;
  appendToLastMessage: (content: string) => void;
  regenerateResponse: (messageId: string) => Promise<void>;
  updateConversationTitle: (id: string, title: string) => void;
  clearError: () => void;
  configureApiSettings: (apiUrl: string, apiKey?: string, sessionId?: string) => void;
  getSessionId: () => string;
  cleanupStreamingMessages: () => void;
}

// API configuration state
let apiConfigured = false;
let currentApiUrl = '';

function ensureApiConfigured(): boolean {
  if (apiConfigured && currentApiUrl) {
    return true;
  }

  // Check localStorage first, then environment variables
  const apiUrl = localStorage.getItem('chat-api-url') || 
                import.meta.env.VITE_API_URL || 
                (window as any).CHATBOT_API_URL ||
                'http://localhost:3000';

  const sessionId = getOrCreateSessionId();
  configureApi(apiUrl, '', sessionId);
  currentApiUrl = apiUrl;
  apiConfigured = true;
  return true;
}

export const useChatStore = create<ExtendedChatState>((set, get) => ({
  conversations: [],
  currentConversationId: null,
  isLoading: false,
  error: null,
  sessionId: getOrCreateSessionId(),

  getSessionId: () => get().sessionId,

  configureApiSettings: (apiUrl: string, apiKey?: string, sessionId?: string) => {
    const actualSessionId = sessionId || getOrCreateSessionId();
    if (sessionId) {
      setSessionId(sessionId);
      set({ sessionId: actualSessionId });
    }
    
    // Configure the API with the provided URL and key
    configureApi(apiUrl, apiKey || '', actualSessionId);
    currentApiUrl = apiUrl;
    apiConfigured = true;

    // Save settings to localStorage
    localStorage.setItem('chat-api-url', apiUrl);
    if (apiKey) {
      localStorage.setItem('chat-api-key', apiKey);
    }
  },

  createConversation: () => {
    const id = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const sessionId = get().sessionId;
    const newConversation: Conversation = {
      id,
      sessionId,
      title: 'New Chat',
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date()
    };

    set((state: ExtendedChatState) => ({
      conversations: [newConversation, ...state.conversations],
      currentConversationId: id
    }));

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

  selectConversation: (id: string) => {
    set({ currentConversationId: id });
    
    // Save to localStorage
    setTimeout(() => {
      const currentState = get();
      localStorage.setItem('chat-state', JSON.stringify({
        conversations: currentState.conversations,
        currentConversationId: currentState.currentConversationId
      }));
    }, 0);
  },

  deleteConversation: (id: string) => {
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
      if (!ensureApiConfigured()) {
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
        // Stream the response using chatbot-api
        for await (const chunk of streamChat(content)) {
          if (chunk.text) {
            get().appendToLastMessage(chunk.text);
            receivedAnyText = true;
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

      if (!ensureApiConfigured()) {
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
        for await (const chunk of streamChat(userMessage.content)) {
          if (chunk.text) {
            get().appendToLastMessage(chunk.text);
            receivedAnyText = true;
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
  const sessionId = getOrCreateSessionId();
  
  // Configure API with saved or default values
  configureApi(savedApiUrl, '', sessionId);
  currentApiUrl = savedApiUrl;
  apiConfigured = true;

  // Then initialize the rest of the store
  const saved = localStorage.getItem('chat-state');
  if (saved) {
    try {
      const parsedState = JSON.parse(saved);
      // Restore Date objects and clean up any streaming messages
      parsedState.conversations = parsedState.conversations.map((conv: any) => ({
        ...conv,
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
      
      useChatStore.setState({
        conversations: parsedState.conversations || [],
        currentConversationId: parsedState.currentConversationId || null
      });
      
      // Clean up any residual streaming messages after initialization
      setTimeout(() => {
        useChatStore.getState().cleanupStreamingMessages();
      }, 100);
    } catch (error) {
      console.error('Failed to load chat state:', error);
    }
  }
};

// Initialize store on import
if (typeof window !== 'undefined') {
  initializeStore();
} 