import { create, StateCreator } from 'zustand';
import { streamChat, configureApi } from '@schmitech/chatbot-api';

export type MessageRole = 'user' | 'assistant' | 'system';

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  createdAt?: Date;
}

interface ChatState {
  messages: Message[];
  isLoading: boolean;
  error: string | null;
  sessionId: string;
  apiConfigured: boolean;
  apiUrl?: string;
  apiKey?: string;
  sendMessage: (content: string) => Promise<void>;
  appendToLastMessage: (content: string) => void;
  clearMessages: () => void;
  configureChat: (apiUrl: string, apiKey?: string) => void;
  getSessionId: () => string;
  newSession: () => void;
}

// Generate a unique session ID if none provided
const generateSessionId = (): string => {
  return 'session_' + Date.now().toString(36) + Math.random().toString(36).substring(2);
};

// Generate a unique message ID
const generateMessageId = (): string => {
  return 'msg_' + Date.now().toString(36) + Math.random().toString(36).substring(2);
};

// Generate initial session ID at module load time
let CURRENT_SESSION_ID = generateSessionId();

const createChatStore: StateCreator<ChatState> = (set, get) => ({
  messages: [],
  isLoading: false,
  error: null,
  sessionId: CURRENT_SESSION_ID,
  apiConfigured: false,
  apiUrl: undefined,
  apiKey: undefined,
  
  configureChat: (apiUrl: string, apiKey?: string) => {
    try {
      // Use the current session ID
      configureApi(apiUrl, apiKey || null, CURRENT_SESSION_ID);
      set({ 
        apiConfigured: true, 
        sessionId: CURRENT_SESSION_ID,
        apiUrl,
        apiKey,
        error: null 
      });
      console.log('Chat configured with session ID:', CURRENT_SESSION_ID);
    } catch (error) {
      console.error('Failed to configure chat API:', error);
      set({ 
        apiConfigured: false, 
        error: `Failed to configure API: ${error instanceof Error ? error.message : 'Unknown error'}` 
      });
    }
  },
  
  getSessionId: () => {
    return CURRENT_SESSION_ID;
  },
  
  newSession: () => {
    // Generate a new session ID
    CURRENT_SESSION_ID = generateSessionId();
    
    // Get current API configuration
    const state = get();
    
    // Clear messages and reset state
    set({ 
      messages: [], 
      error: null, 
      sessionId: CURRENT_SESSION_ID,
      isLoading: false
    });
    
    // Reconfigure API with new session ID if API was previously configured
    if (state.apiConfigured && state.apiUrl) {
      try {
        configureApi(state.apiUrl, state.apiKey || null, CURRENT_SESSION_ID);
        set({ apiConfigured: true });
        console.log('New session created and API reconfigured:', CURRENT_SESSION_ID);
      } catch (error) {
        console.error('Failed to reconfigure API with new session:', error);
        set({ 
          apiConfigured: false,
          error: 'Failed to reconfigure API with new session'
        });
      }
    } else {
      console.log('New session created:', CURRENT_SESSION_ID);
    }
  },
  
  sendMessage: async (content: string) => {
    try {
      const state = get();
      
      if (!state.apiConfigured) {
        throw new Error('API not configured. Please call configureChat() first.');
      }
      
      // Add user message
      const userMessage: Message = {
        id: generateMessageId(),
        role: 'user',
        content,
        createdAt: new Date()
      };
      
      set((state: ChatState) => ({
        messages: [...state.messages, userMessage],
        isLoading: true,
        error: null
      }));
      
      // Add empty assistant message that will be filled as the stream comes in
      const assistantMessage: Message = {
        id: generateMessageId(),
        role: 'assistant', 
        content: '',
        createdAt: new Date()
      };
      
      set((state: ChatState) => ({
        messages: [...state.messages, assistantMessage],
      }));
      
      let receivedAnyText = false;
      
      try {
        // Use the streamChat function from the API (session ID is already configured)
        for await (const chunk of streamChat(content, true)) {
          if (chunk.text) {
            get().appendToLastMessage(chunk.text);
            receivedAnyText = true;
          }
          
          // If the chunk indicates completion, break the loop
          if (chunk.done) {
            break;
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
      set((state: ChatState) => ({
        isLoading: false,
        error: `Failed to send message: ${error instanceof Error ? error.message : 'Unknown error'}`
      }));
    }
  },
  
  appendToLastMessage: (content: string) => {
    set((state: ChatState) => {
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
    set({ messages: [], error: null });
  }
});

export const useChatStore = create<ChatState>(createChatStore); 