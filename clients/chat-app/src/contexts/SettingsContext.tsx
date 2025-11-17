import React, { createContext, useContext, useEffect, useState } from 'react';

interface AppSettings {
  voiceEnabled: boolean;
  soundEnabled: boolean;
  autoSend: boolean;
}

interface SettingsContextType {
  settings: AppSettings;
  updateSettings: (updates: Partial<AppSettings>) => void;
}

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

const DEFAULT_SETTINGS: AppSettings = {
  voiceEnabled: false,
  soundEnabled: false,
  autoSend: false,
};

export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const [settings, setSettings] = useState<AppSettings>(() => {
    const saved = localStorage.getItem('chat-settings');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        // Ensure voiceEnabled is always false on app start (user can enable it manually)
        return { ...DEFAULT_SETTINGS, ...parsed, voiceEnabled: false };
      } catch (error) {
        // If parsing fails, use defaults
        return DEFAULT_SETTINGS;
      }
    }
    return DEFAULT_SETTINGS;
  });

  // Save settings to localStorage whenever they change
  useEffect(() => {
    localStorage.setItem('chat-settings', JSON.stringify(settings));
  }, [settings]);

  const updateSettings = (updates: Partial<AppSettings>) => {
    setSettings(prev => ({ ...prev, ...updates }));
  };

  return (
    <SettingsContext.Provider value={{ settings, updateSettings }}>
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings() {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error('useSettings must be used within SettingsProvider');
  }
  return context;
}

