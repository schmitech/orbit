import React, { createContext, useContext, useReducer, useEffect } from 'react';
import { ChatState, Conversation, Message } from '../types';
import { debugLog, debugError } from '../utils/debug';

interface ChatContextType extends ChatState {
  createConversation: () => string;
  selectConversation: (id: string) => void;
  deleteConversation: (id: string) => void;
  sendMessage: (content: string) => void;
  regenerateResponse: (messageId: string) => void;
  updateConversationTitle: (id: string, title: string) => void;
  clearError: () => void;
  getCurrentSessionId: () => string | null;
  syncConversationFromBackend: (conversationId: string) => Promise<void>; // Sync frontend with backend
}

type ChatAction =
  | { type: 'CREATE_CONVERSATION'; id: string; sessionId: string }
  | { type: 'SELECT_CONVERSATION'; id: string }
  | { type: 'DELETE_CONVERSATION'; id: string }
  | { type: 'ADD_MESSAGE'; conversationId: string; message: Message }
  | { type: 'UPDATE_MESSAGE'; conversationId: string; messageId: string; content: string }
  | { type: 'SET_LOADING'; loading: boolean }
  | { type: 'SET_ERROR'; error: string | null }
  | { type: 'UPDATE_TITLE'; id: string; title: string }
  | { type: 'LOAD_STATE'; state: ChatState }
  | { type: 'SYNC_CONVERSATION'; conversationId: string; messages: Message[] };

const ChatContext = createContext<ChatContextType | undefined>(undefined);

type StoredMessage = Omit<Message, 'timestamp'> & {
  timestamp: string | number | Date;
};

type StoredConversation = Omit<Conversation, 'createdAt' | 'updatedAt' | 'messages'> & {
  createdAt: string | number | Date;
  updatedAt: string | number | Date;
  messages: StoredMessage[];
};

type PersistedChatState = Omit<ChatState, 'conversations'> & {
  conversations: StoredConversation[];
};

function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case 'LOAD_STATE':
      return action.state;
      
    case 'CREATE_CONVERSATION': {
      const newConversation: Conversation = {
        id: action.id,
        sessionId: action.sessionId,
        title: 'New Chat',
        messages: [],
        createdAt: new Date(),
        updatedAt: new Date()
      };
      return {
        ...state,
        conversations: [newConversation, ...state.conversations],
        currentConversationId: action.id
      };
    }
      
    case 'SELECT_CONVERSATION':
      return {
        ...state,
        currentConversationId: action.id
      };
      
    case 'DELETE_CONVERSATION': {
      const filtered = state.conversations.filter(c => c.id !== action.id);
      return {
        ...state,
        conversations: filtered,
        currentConversationId: state.currentConversationId === action.id 
          ? (filtered[0]?.id || null) 
          : state.currentConversationId
      };
    }
      
    case 'ADD_MESSAGE':
      return {
        ...state,
        conversations: state.conversations.map(conv =>
          conv.id === action.conversationId
            ? {
                ...conv,
                messages: [...conv.messages, action.message],
                updatedAt: new Date(),
                title: conv.messages.length === 0 
                  ? action.message.content.slice(0, 50) + (action.message.content.length > 50 ? '...' : '')
                  : conv.title
              }
            : conv
        )
      };
      
    case 'UPDATE_MESSAGE':
      return {
        ...state,
        conversations: state.conversations.map(conv =>
          conv.id === action.conversationId
            ? {
                ...conv,
                messages: conv.messages.map(msg =>
                  msg.id === action.messageId
                    ? { ...msg, content: action.content, isStreaming: false }
                    : msg
                ),
                updatedAt: new Date()
              }
            : conv
        )
      };
      
    case 'SET_LOADING':
      return { ...state, isLoading: action.loading };
      
    case 'SET_ERROR':
      return { ...state, error: action.error };
      
    case 'UPDATE_TITLE':
      return {
        ...state,
        conversations: state.conversations.map(conv =>
          conv.id === action.id
            ? { ...conv, title: action.title, updatedAt: new Date() }
            : conv
        )
      };
      
    case 'SYNC_CONVERSATION':
      return {
        ...state,
        conversations: state.conversations.map(conv =>
          conv.id === action.conversationId
            ? { ...conv, messages: action.messages, updatedAt: new Date() }
            : conv
        )
      };
      
    default:
      return state;
  }
}

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(chatReducer, {
    conversations: [],
    currentConversationId: null,
    isLoading: false,
    error: null
  });

  // Load state from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem('chat-state');
    if (saved) {
      try {
        const parsedState = JSON.parse(saved) as PersistedChatState;
        // Restore Date objects and ensure sessionId exists for backward compatibility
        const normalizedConversations: Conversation[] = parsedState.conversations.map((conv) => ({
          ...conv,
          sessionId: conv.sessionId || `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          createdAt: new Date(conv.createdAt),
          updatedAt: new Date(conv.updatedAt),
          messages: conv.messages.map((msg) => ({
            ...msg,
            timestamp: new Date(msg.timestamp)
          }))
        }));
        dispatch({
          type: 'LOAD_STATE',
          state: {
            ...parsedState,
            conversations: normalizedConversations
          }
        });
      } catch (error) {
        debugError('Failed to load chat state:', error);
      }
    }
  }, []);

  // Save state to localStorage whenever it changes
  useEffect(() => {
    localStorage.setItem('chat-state', JSON.stringify(state));
  }, [state]);

  const createConversation = (): string => {
    const id = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    dispatch({ type: 'CREATE_CONVERSATION', id, sessionId });
    return id;
  };

  const selectConversation = (id: string) => {
    dispatch({ type: 'SELECT_CONVERSATION', id });
  };

  const deleteConversation = (id: string) => {
    dispatch({ type: 'DELETE_CONVERSATION', id });
  };

  const sendMessage = async (content: string) => {
    // ARCHITECTURE NOTE:
    // - Frontend: Manages message display for UI/UX purposes only
    // - Backend: Handles all persistent storage in MongoDB using session ID
    // - We send only the current message; backend retrieves full context from MongoDB
    
    let conversationId = state.currentConversationId;
    
    // Create a new conversation if none exists
    if (!conversationId) {
      conversationId = createConversation();
    }

    // Get the current conversation to access its sessionId
    const currentConversation = state.conversations.find(c => c.id === conversationId);
    if (!currentConversation) {
      dispatch({ type: 'SET_ERROR', error: 'Current conversation not found' });
      return;
    }

    const userMessage: Message = {
      id: `msg_${Date.now()}_user`,
      content,
      role: 'user',
      timestamp: new Date()
    };

    dispatch({ 
      type: 'ADD_MESSAGE', 
      conversationId, 
      message: userMessage 
    });

    // Set loading state
    dispatch({ type: 'SET_LOADING', loading: true });

    // Simulate AI response
    const assistantMessageId = `msg_${Date.now()}_assistant`;
    const assistantMessage: Message = {
      id: assistantMessageId,
      content: '',
      role: 'assistant',
      timestamp: new Date(),
      isStreaming: true
    };

    dispatch({ 
      type: 'ADD_MESSAGE', 
      conversationId, 
      message: assistantMessage 
    });

    try {
      debugLog(`Sending message to session: ${currentConversation.sessionId}`);
      
      // Make API call to backend with session ID in header
      // NOTE: We only send the current user message, NOT the entire conversation history
      // The backend will retrieve conversation context from MongoDB using the session ID
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Session-ID': currentConversation.sessionId, // Backend uses this to retrieve/store in MongoDB
        },
        body: JSON.stringify({
          message: content // Only the current user message - backend handles history
        })
      });

      if (!response.ok) {
        throw new Error(`API request failed: ${response.status} ${response.statusText}`);
      }

      // Check if the response is a streaming response
      const reader = response.body?.getReader();
      if (reader) {
        // Handle streaming response
        const decoder = new TextDecoder();
        let fullContent = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          fullContent += chunk;

          // Update message with streaming content
          dispatch({
            type: 'UPDATE_MESSAGE',
            conversationId,
            messageId: assistantMessageId,
            content: fullContent
          });
        }
      } else {
        // Handle non-streaming response
        const data = await response.json();
        const assistantResponse = data.message || data.response || data.content || 'No response received';

        dispatch({
          type: 'UPDATE_MESSAGE',
          conversationId,
          messageId: assistantMessageId,
          content: assistantResponse
        });
      }
    } catch (error) {
      debugError('Error sending message:', error);
      dispatch({ 
        type: 'SET_ERROR', 
        error: error instanceof Error ? error.message : 'Failed to send message' 
      });
    } finally {
      dispatch({ type: 'SET_LOADING', loading: false });
    }
  };

  const regenerateResponse = async (messageId: string) => {
    // Implementation for regenerating AI responses
    debugLog('Regenerating response for:', messageId);
  };

  const updateConversationTitle = (id: string, title: string) => {
    dispatch({ type: 'UPDATE_TITLE', id, title });
  };

  const clearError = () => {
    dispatch({ type: 'SET_ERROR', error: null });
  };

  const getCurrentSessionId = (): string | null => {
    if (!state.currentConversationId) return null;
    const currentConversation = state.conversations.find(c => c.id === state.currentConversationId);
    return currentConversation?.sessionId || null;
  };

  // Optional: Function to sync frontend display with backend history
  // This can be called when switching conversations or on page refresh
  const syncConversationFromBackend = async (conversationId: string) => {
    const conversation = state.conversations.find(c => c.id === conversationId);
    if (!conversation) return;

    try {
      const response = await fetch(`/api/chat/history`, {
        method: 'GET',
        headers: {
          'X-Session-ID': conversation.sessionId,
        },
      });

      if (response.ok) {
        const data = await response.json();
        type BackendMessage = {
          timestamp: string | number | Date;
          role: Message['role'];
          content: string;
        };

        const backendMessages: BackendMessage[] = Array.isArray(data.messages)
          ? data.messages
          : [];
        
        // Update local conversation with backend messages
        // This ensures frontend display matches backend storage
        const updatedMessages = backendMessages.map((msg) => ({
          id: `msg_${msg.timestamp}_${msg.role}`,
          content: msg.content,
          role: msg.role,
          timestamp: new Date(msg.timestamp)
        }));

        // Update the conversation with synced messages
        dispatch({
          type: 'SYNC_CONVERSATION',
          conversationId,
          messages: updatedMessages
        });
      }
    } catch (error) {
      debugError('Failed to sync conversation from backend:', error);
    }
  };

  return (
    <ChatContext.Provider value={{
      ...state,
      createConversation,
      selectConversation,
      deleteConversation,
      sendMessage,
      regenerateResponse,
      updateConversationTitle,
      clearError,
      getCurrentSessionId,
      syncConversationFromBackend
    }}>
      {children}
    </ChatContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useChat() {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error('useChat must be used within ChatProvider');
  }
  return context;
}
