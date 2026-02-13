import AsyncStorage from '@react-native-async-storage/async-storage';
import { STORAGE_KEYS } from '../config/constants';
import { Conversation } from '../types';

export async function saveConversations(conversations: Conversation[]): Promise<void> {
  const serialized = JSON.stringify(conversations);
  await AsyncStorage.setItem(STORAGE_KEYS.CONVERSATIONS, serialized);
}

export async function loadConversations(): Promise<Conversation[]> {
  const data = await AsyncStorage.getItem(STORAGE_KEYS.CONVERSATIONS);
  if (!data) return [];

  const parsed = JSON.parse(data) as Conversation[];
  return parsed.map(conv => ({
    ...conv,
    createdAt: new Date(conv.createdAt),
    updatedAt: new Date(conv.updatedAt),
    messages: conv.messages.map(msg => ({
      ...msg,
      timestamp: new Date(msg.timestamp),
    })),
  }));
}

export async function loadTheme(): Promise<'light' | 'dark' | 'system'> {
  const theme = await AsyncStorage.getItem(STORAGE_KEYS.THEME);
  if (theme === 'light' || theme === 'dark' || theme === 'system') return theme;
  return 'system';
}

export async function saveTheme(theme: 'light' | 'dark' | 'system'): Promise<void> {
  await AsyncStorage.setItem(STORAGE_KEYS.THEME, theme);
}
