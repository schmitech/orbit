import { create } from 'zustand';
import { Message } from './types';

interface ChatState {
  messages: Message[];
  isLoading: boolean;
  language: string;
  setLanguage: (language: string) => void;
  supportedLanguages: Array<{ value: string; label: string }>;
  addMessage: (message: Message) => void;
  setIsLoading: (loading: boolean) => void;
  appendToLastMessage: (content: string) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
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
  setIsLoading: (loading: boolean) => set({ isLoading: loading }),
  appendToLastMessage: (content: string) =>
    set((state) => {
      const messages = [...state.messages];
      if (messages.length > 0) {
        const lastMessage = messages[messages.length - 1];
        messages[messages.length - 1] = {
          ...lastMessage,
          content: lastMessage.content + content,
        };
      }
      return { messages };
    }),
  clearMessages: () => set({ messages: [] }),
}));