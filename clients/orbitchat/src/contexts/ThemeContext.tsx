import React, { createContext, useContext, useEffect, useState } from 'react';
import { ThemeConfig } from '../types';

interface ThemeContextType {
  theme: ThemeConfig;
  updateTheme: (updates: Partial<ThemeConfig>) => void;
  isDark: boolean;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<ThemeConfig>(() => {
    const saved = localStorage.getItem('chat-theme');
    if (saved) {
      const parsed = JSON.parse(saved) as Partial<ThemeConfig>;
      return {
        mode: parsed.mode || 'system',
        highContrast: !!parsed.highContrast
      };
    }
    return {
      mode: 'system',
      highContrast: false
    };
  });

  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const applyTheme = () => {
      let dark = false;
      
      if (theme.mode === 'dark') {
        dark = true;
      } else if (theme.mode === 'light') {
        dark = false;
      } else {
        // System preference
        const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        dark = systemPrefersDark;
      }
      
      setIsDark(dark);
      
      const root = document.documentElement;
      
      // Apply dark mode
      if (dark) {
        root.classList.add('dark');
      } else {
        root.classList.remove('dark');
      }
      
      // Apply high contrast
      if (theme.highContrast) {
        root.classList.add('high-contrast');
      } else {
        root.classList.remove('high-contrast');
      }
      
      // Keep a single consistent app font scale; users can use browser zoom if needed.
      root.classList.remove('text-sm', 'text-lg');
      root.classList.add('text-base');
    };

    applyTheme();
    
    // Listen for system theme changes only if mode is 'system'
    if (theme.mode === 'system') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      const handleSystemThemeChange = () => {
        applyTheme();
      };
      mediaQuery.addEventListener('change', handleSystemThemeChange);
      
      return () => mediaQuery.removeEventListener('change', handleSystemThemeChange);
    }
  }, [theme]);

  // Save theme to localStorage whenever it changes
  useEffect(() => {
    localStorage.setItem('chat-theme', JSON.stringify(theme));
  }, [theme]);

  const updateTheme = (updates: Partial<ThemeConfig>) => {
    setTheme(prev => ({ ...prev, ...updates }));
  };

  return (
    <ThemeContext.Provider value={{ theme, updateTheme, isDark }}>
      {children}
    </ThemeContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider');
  }
  return context;
}
