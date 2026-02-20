import { create } from 'zustand';

interface LoginPromptState {
  showLoginPrompt: boolean;
  promptMessage: string;
  openLoginPrompt: (message: string) => void;
  closeLoginPrompt: () => void;
}

export const useLoginPromptStore = create<LoginPromptState>((set) => ({
  showLoginPrompt: false,
  promptMessage: '',
  openLoginPrompt: (message: string) => set({ showLoginPrompt: true, promptMessage: message }),
  closeLoginPrompt: () => set({ showLoginPrompt: false, promptMessage: '' }),
}));
