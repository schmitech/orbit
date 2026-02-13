import { create } from 'zustand';
import { loadTheme, saveTheme } from '../utils/storage';

type ThemeMode = 'light' | 'dark' | 'system';

interface ThemeState {
  mode: ThemeMode;
  loaded: boolean;
  hydrate: () => Promise<void>;
  setThemeMode: (mode: ThemeMode) => void;
}

export const useThemeStore = create<ThemeState>((set) => ({
  mode: 'system',
  loaded: false,

  hydrate: async () => {
    const savedMode = await loadTheme();
    set({ mode: savedMode, loaded: true });
  },

  setThemeMode: (newMode: ThemeMode) => {
    set({ mode: newMode });
    saveTheme(newMode);
  },
}));
