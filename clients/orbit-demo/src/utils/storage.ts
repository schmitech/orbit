import { Conversation } from '../types';

const STORAGE_KEY = 'orbit-demo-conversations';

export function saveConversations(conversations: Conversation[]): void {
  const serialized = JSON.stringify(conversations);
  localStorage.setItem(STORAGE_KEY, serialized);
}

export function loadConversations(): Conversation[] {
  const data = localStorage.getItem(STORAGE_KEY);
  if (!data) return [];

  const parsed = JSON.parse(data) as Conversation[];
  return parsed.map((conv) => ({
    ...conv,
    createdAt: new Date(conv.createdAt),
    updatedAt: new Date(conv.updatedAt),
    messages: conv.messages.map((msg) => ({
      ...msg,
      timestamp: new Date(msg.timestamp),
    })),
  }));
}
