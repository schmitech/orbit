import { create } from 'zustand';
import { streamChat, configureApi } from '@schmitech/chatbot-api';
import { getApiUrl, getApiKey } from '../index';
import { getOrCreateSessionId, setSessionId } from '../utils/sessionManager';
import { CHAT_CONSTANTS } from '../shared/styles';

export type MessageRole = 'user' | 'assistant' | 'system';

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
}

interface ChatState {
  messages: Message[];
  isLoading: boolean;
  error: string | null;
  sessionId: string;
  sendMessage: (content: string) => Promise<void>;
  appendToLastMessage: (content: string) => void;
  clearMessages: () => void;
  getSessionId: () => string;
}

// Initialize API configuration
let apiConfigured = false;

function ensureApiConfigured(): boolean {
  if (apiConfigured) {
    return true;
  }

  try {
    if (typeof window !== 'undefined') {
      let apiUrl: string | undefined;
      let apiKey: string | undefined;
      let sessionId: string;

      // Try to get API URL and key from various sources
      if (window.CHATBOT_API_URL && window.CHATBOT_API_KEY) {
        apiUrl = window.CHATBOT_API_URL;
        apiKey = window.CHATBOT_API_KEY;
      } else if (getApiUrl && getApiKey) {
        try {
          apiUrl = getApiUrl();
          apiKey = getApiKey();
        } catch (err) {
          // Silently fail and continue
        }
      }

      if (!apiUrl || !apiKey) {
        console.warn('API URL or API Key not configured');
        return false;
      }

      // Handle session ID
      if (window.CHATBOT_SESSION_ID) {
        // If server provided a session ID, use it and persist it
        sessionId = window.CHATBOT_SESSION_ID;
        setSessionId(sessionId);
      } else {
        // Otherwise, get or create a persistent session ID
        sessionId = getOrCreateSessionId();
      }

      configureApi(apiUrl, apiKey, sessionId);
      apiConfigured = true;
      return true;
    }
  } catch (err) {
    console.error('Failed to configure API:', err);
  }
  return false;
}

// Helper function to generate unique IDs
function generateMessageId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // Fallback for environments without crypto.randomUUID
  return `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isLoading: false,
  error: null,
  sessionId: getOrCreateSessionId(),
  
  getSessionId: () => {
    return get().sessionId;
  },
  
  sendMessage: async (content: string) => {
    try {
      // Guardrail: Truncate if content is too long
      const maxLen = CHAT_CONSTANTS.MAX_SUGGESTED_QUESTION_QUERY_LENGTH;
      let safeContent = content;
      if (content.length > maxLen) {
        safeContent = content.substring(0, maxLen);
      }
      // Ensure API is configured before sending message
      if (!ensureApiConfigured()) {
        throw new Error('API not properly configured');
      }
      // Add user message
      set(state => ({
        messages: [...state.messages, { id: generateMessageId(), role: 'user', content: safeContent }],
        isLoading: true,
        error: null
      }));
      // Add empty assistant message that will be filled as the stream comes in
      set(state => ({
        messages: [...state.messages, { id: generateMessageId(), role: 'assistant', content: '' }],
      }));
      let receivedAnyText = false;
      try {
        // Use the streamChat function from chatbot-api
        for await (const chunk of streamChat(safeContent)) {
          if (chunk.text) {
            // Append the text to the last message
            get().appendToLastMessage(chunk.text);
            receivedAnyText = true;
          }
        }
        // If we didn't receive any text, show an error message
        if (!receivedAnyText) {
          get().appendToLastMessage('No response received from the server. Please try again later.');
        }
      } catch (error) {
        console.error('Chat API error:', error);
        get().appendToLastMessage('Sorry, there was an error processing your request.');
      }
      // Set loading to false when done
      set({ isLoading: false });
    } catch (error) {
      console.error('Chat store error:', error);
      set(state => ({
        isLoading: false,
        error: `Failed to send message: ${error instanceof Error ? error.message : 'Unknown error'}`
      }));
    }
  },
  
  appendToLastMessage: (content: string) => {
    set(state => {
      const messages = [...state.messages];
      const lastMessage = messages[messages.length - 1];
      
      if (lastMessage && lastMessage.role === 'assistant') {
        messages[messages.length - 1] = {
          ...lastMessage,
          content: lastMessage.content + content
        };
      }
      
      return { messages };
    });
  },
  
  clearMessages: () => {
    set({ messages: [] });
    // Note: We're NOT clearing the session here, just the messages
    // If you want to start a completely new session, you would also call:
    // clearSession();
    // apiConfigured = false;
    // ensureApiConfigured();
  }
}));