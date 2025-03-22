import { create } from 'zustand';
import { streamChat, configureApi } from 'chatbot-api';
import { getApiUrl } from '../index';

export type MessageRole = 'user' | 'assistant' | 'system';

export interface Message {
  role: MessageRole;
  content: string;
}

interface ChatState {
  messages: Message[];
  isLoading: boolean;
  error: string | null;
  voiceEnabled: boolean;
  toggleVoice: () => void;
  sendMessage: (content: string) => Promise<void>;
  appendToLastMessage: (content: string) => void;
  clearMessages: () => void;
}

// Ensure the API is configured whenever the store is imported
function ensureApiConfigured() {
  try {
    if (typeof window !== 'undefined' && window.CHATBOT_API_URL) {
      configureApi(window.CHATBOT_API_URL);
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
  error: null,
  voiceEnabled: false,
  
  toggleVoice: () => set(state => ({ voiceEnabled: !state.voiceEnabled })),
  
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
        // Use the streamChat function from chatbot-api with the voiceEnabled state
        for await (const chunk of streamChat(content, get().voiceEnabled)) {
          if (chunk.text) {
            // Append the text to the last message
            get().appendToLastMessage(chunk.text);
            receivedAnyText = true;
          }
          
          // Handle audio content separately - don't append it to the text
          // The audio handling should be done in the UI component
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
  }
}));