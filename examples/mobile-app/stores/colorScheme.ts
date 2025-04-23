import { create } from 'zustand';

interface ColorSchemeStore {
  isDarkMode: boolean;
  toggleColorScheme: () => void;
}

export const useColorScheme = create<ColorSchemeStore>((set) => ({
  isDarkMode: false,
  toggleColorScheme: () => set((state) => ({ isDarkMode: !state.isDarkMode })),
}));