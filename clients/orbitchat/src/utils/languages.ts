export const SUPPORTED_LANGUAGES = ['de', 'en', 'es', 'fr', 'ja', 'pt', 'zh'] as const;

export type SupportedLanguage = typeof SUPPORTED_LANGUAGES[number];

export const LANGUAGE_LABELS: Record<SupportedLanguage, string> = {
  de: 'Deutsch',
  en: 'English',
  es: 'Español',
  fr: 'Français',
  ja: '日本語',
  pt: 'Português',
  zh: '中文',
};

export function isSupportedLanguage(value: string): value is SupportedLanguage {
  return (SUPPORTED_LANGUAGES as readonly string[]).includes(value);
}
