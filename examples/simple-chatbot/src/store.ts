import { create } from 'zustand';
import { Message } from './types';

interface ChatState {
  messages: Message[];
  voiceEnabled: boolean;
  isLoading: boolean;
  language: string;
  setLanguage: (language: string) => void;
  supportedLanguages: Array<{ value: string; label: string }>;
  addMessage: (message: Message) => void;
  setVoiceEnabled: (enabled: boolean) => void;
  setIsLoading: (loading: boolean) => void;
  appendToLastMessage: (content: string) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  voiceEnabled: false,
  isLoading: false,
  language: 'en',
  setLanguage: (language) => set({ language }),
  supportedLanguages: [
    { value: 'en', label: 'English' },
    { value: 'fr', label: 'Français' },
    { value: 'es', label: 'Español' }
  ],
  addMessage: (message: Message) =>
    set((state) => ({ messages: [...state.messages, message] })),
  setVoiceEnabled: (enabled: boolean) => set({ voiceEnabled: enabled }),
  setIsLoading: (loading: boolean) => set({ isLoading: loading }),
  appendToLastMessage: (content: string) =>
    set((state) => {
      const messages = [...state.messages];
      if (messages.length > 0) {
        const lastMessage = messages[messages.length - 1];
        
        // Check if the content contains audio data markers and strip them out
        // This prevents audio data from being displayed in the message
        let cleanContent = content;
        if (content.includes('//')) {
          // Only keep the text part before the audio data marker
          cleanContent = content.split('//')[0];
        }
        
        messages[messages.length - 1] = {
          ...lastMessage,
          content: lastMessage.content + cleanContent,
        };
      }
      return { messages };
    }),
  clearMessages: () => set({ messages: [] }),
}));