import { create } from 'zustand';
import { ChatMessage, ChatbotConfig } from '../types/chatbot';

interface ChatStore {
  messages: ChatMessage[];
  isOpen: boolean;
  isTyping: boolean;
  config: ChatbotConfig;
  addMessage: (message: Omit<ChatMessage, 'id' | 'timestamp'>) => void;
  toggleChat: () => void;
  setConfig: (config: ChatbotConfig) => void;
}

const defaultConfig: ChatbotConfig = {
  theme: {
    primaryColor: '#007bff',
    size: 'medium',
  },
  messages: {
    greeting: 'Hi there! 👋 How can I assist you today?',
    title: 'Chat Support',
  },
  position: {
    bottom: 20,
    right: 20,
  },
  dimensions: {
    width: 350,
    height: 500,
  },
  api: {
    endpoint: 'http://localhost:3001',
  },
};

const fallbackResponses = [
  "I'm a demo bot. Here's what you said: ",
  "While the API server is not running, I'll echo your message: ",
  "API server is offline. Your message was: ",
];

export const useChatStore = create<ChatStore>((set, get) => ({
  messages: [],
  isOpen: false,
  isTyping: false,
  config: defaultConfig,
  addMessage: async (message) => {
    const newMessage = {
      id: Math.random().toString(36).substring(7),
      timestamp: new Date(),
      ...message,
    };

    set((state) => ({
      messages: [...state.messages, newMessage],
    }));

    // Only send user messages to the API
    if (message.sender === 'user') {
      try {
        set({ isTyping: true });
        
        // Wrap fetch in AbortController with timeout
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);

        const response = await fetch(`${get().config.api.endpoint}/chat`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ message: message.content }),
          signal: controller.signal,
        });

        clearTimeout(timeoutId);

        if (!response.ok) {
          throw new Error('Failed to get response from chatbot API');
        }

        const data = await response.json();
        
        set((state) => ({
          messages: [
            ...state.messages,
            {
              id: Math.random().toString(36).substring(7),
              content: data.response,
              sender: 'bot',
              timestamp: new Date(),
            },
          ],
          isTyping: false,
        }));
      } catch (error) {
        // Use fallback response when API is not available
        const randomResponse = fallbackResponses[Math.floor(Math.random() * fallbackResponses.length)];
        
        set((state) => ({
          messages: [
            ...state.messages,
            {
              id: Math.random().toString(36).substring(7),
              content: `${randomResponse}${message.content}`,
              sender: 'bot',
              timestamp: new Date(),
            },
          ],
          isTyping: false,
        }));
      }
    }
  },
  toggleChat: () => set((state) => ({ isOpen: !state.isOpen })),
  setConfig: (config) => {
    set((state) => {
      const newConfig = { ...state.config, ...config };
      
      // Add greeting message only if there are no messages yet
      if (state.messages.length === 0 && newConfig.messages?.greeting) {
        const greetingMessage = {
          id: Math.random().toString(36).substring(7),
          content: newConfig.messages.greeting,
          sender: 'bot' as const,
          timestamp: new Date(),
        };
        
        return {
          config: newConfig,
          messages: [greetingMessage],
        };
      }
      
      return { config: newConfig };
    });
  },
}));