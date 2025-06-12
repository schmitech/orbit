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
    return saved ? JSON.parse(saved) : {
      mode: 'system',
      highContrast: false,
      fontSize: 'medium'
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
        dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
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
      
      // Apply font size
      root.classList.remove('text-sm', 'text-base', 'text-lg');
      switch (theme.fontSize) {
        case 'small':
          root.classList.add('text-sm');
          break;
        case 'large':
          root.classList.add('text-lg');
          break;
        default:
          root.classList.add('text-base');
      }
    };

    applyTheme();
    
    // Listen for system theme changes only if mode is 'system'
    if (theme.mode === 'system') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      mediaQuery.addEventListener('change', applyTheme);
      
      return () => mediaQuery.removeEventListener('change', applyTheme);
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

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider');
  }
  return context;
}