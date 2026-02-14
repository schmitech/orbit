export const STREAMING_BATCH_DELAY = 12; // lower latency while keeping update batching

export const MAX_TITLE_LENGTH = 100;

export const MAX_MESSAGE_LENGTH = 1000;

export const MAX_CONVERSATIONS = 100;

export const STORAGE_KEYS = {
  CONVERSATIONS: 'orbit_conversations',
  THEME: 'orbit_theme',
} as const;
