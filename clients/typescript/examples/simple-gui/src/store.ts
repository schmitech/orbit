import { create } from 'zustand';
import { Message, StreamResponse } from './types';
import { streamChat, configureApi } from '../../../api/api';

interface ChatState {
  messages: Message[];
  isLoading: boolean;
  language: string;
  error: string | null;
  setLanguage: (language: string) => void;
  supportedLanguages: Array<{ value: string; label: string }>;
  sendMessage: (content: string) => Promise<void>;
  appendToLastMessage: (content: string) => void;
  clearMessages: () => void;
}

// Add global types declaration for window properties
declare global {
  interface Window {
    CHATBOT_API_URL?: string;
    CHATBOT_API_KEY?: string;
  }
}

// Function to generate a UUID v4
function generateUUID(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

// Function to get or create session ID
function getSessionId(): string {
  const storageKey = 'orbit_session_id';
  let sessionId = sessionStorage.getItem(storageKey);
  
  if (!sessionId) {
    sessionId = generateUUID();
    sessionStorage.setItem(storageKey, sessionId);
  }
  
  return sessionId;
}

// Ensure the API is configured whenever the store is imported
function ensureApiConfigured() {
  try {
    // Use the same environment variables as in App.tsx
    const apiEndpoint = import.meta.env.VITE_API_ENDPOINT;
    const apiKey = import.meta.env.VITE_API_KEY;
    
    if (apiEndpoint && apiKey) {
      configureApi(apiEndpoint, apiKey, getSessionId());
      return true;
    }
  } catch (err) {
    console.error('Failed to configure API:', err);
  }
  return false;
}

// Try to configure the API
ensureApiConfigured();

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isLoading: false,
  language: 'en',
  error: null,
  setLanguage: (language) => set({ language }),
  supportedLanguages: [
    { value: 'en', label: 'English' },
    { value: 'fr', label: 'Français' },
    { value: 'es', label: 'Español' }
  ],
  
  sendMessage: async (content: string) => {
    try {
      // Ensure API is configured before sending message
      if (!ensureApiConfigured()) {
        throw new Error('API URL not configured');
      }
      
      // Add user message
      set(state => ({
        messages: [...state.messages, { role: 'user', content }],
        isLoading: true,
        error: null
      }));
      
      // Add empty assistant message that will be filled as the stream comes in
      set(state => ({
        messages: [...state.messages, { role: 'assistant', content: '' }],
      }));
      
      let receivedAnyText = false;
      
      try {
        // Use the streamChat function from chatbot-api
        // The API only accepts 1-2 parameters (message and stream flag)
        for await (const chunk of streamChat(content, false)) {
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
  
  appendToLastMessage: (content: string) =>
    set((state) => {
      const messages = [...state.messages];
      const lastMessage = messages[messages.length - 1];
      
      if (lastMessage && lastMessage.role === 'assistant') {
        messages[messages.length - 1] = {
          ...lastMessage,
          content: lastMessage.content + content,
        };
      }
      
      return { messages };
    }),
    
  clearMessages: () => set({ messages: [], error: null }),
}));