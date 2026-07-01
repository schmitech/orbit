import React, { createContext, useContext, useEffect, useState } from 'react';
import i18n from '../i18n';
import { getActiveLanguages, getDefaultLanguage } from '../utils/runtimeConfig';
import { SUPPORTED_LANGUAGES, isSupportedLanguage, type SupportedLanguage } from '../utils/languages';

interface LanguageContextType {
  currentLanguage: SupportedLanguage;
  activeLanguages: SupportedLanguage[];
  setLanguage: (lang: SupportedLanguage) => void;
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

const STORAGE_KEY = 'orbit-chat-language';

function resolveActiveLanguages(): SupportedLanguage[] {
  const configured = getActiveLanguages().filter(isSupportedLanguage);
  return configured.length > 0 ? configured : ['en'];
}

function resolveInitialLanguage(activeLanguages: SupportedLanguage[]): SupportedLanguage {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored && isSupportedLanguage(stored) && activeLanguages.includes(stored)) {
    return stored;
  }

  const browserLanguages = [...(navigator.languages || []), navigator.language].filter(Boolean);
  for (const browserLanguage of browserLanguages) {
    const base = browserLanguage.split('-')[0].toLowerCase();
    if (isSupportedLanguage(base) && activeLanguages.includes(base)) {
      return base;
    }
  }

  const configuredDefault = getDefaultLanguage();
  if (isSupportedLanguage(configuredDefault) && activeLanguages.includes(configuredDefault)) {
    return configuredDefault;
  }

  return activeLanguages[0] ?? 'en';
}

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [activeLanguages] = useState<SupportedLanguage[]>(() => resolveActiveLanguages());
  const [currentLanguage, setCurrentLanguage] = useState<SupportedLanguage>(() =>
    resolveInitialLanguage(activeLanguages)
  );

  useEffect(() => {
    void i18n.changeLanguage(currentLanguage);
  }, [currentLanguage]);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, currentLanguage);
  }, [currentLanguage]);

  const setLanguage = (lang: SupportedLanguage) => {
    if (!SUPPORTED_LANGUAGES.includes(lang)) return;
    setCurrentLanguage(lang);
  };

  return (
    <LanguageContext.Provider value={{ currentLanguage, activeLanguages, setLanguage }}>
      {children}
    </LanguageContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error('useLanguage must be used within LanguageProvider');
  }
  return context;
}
