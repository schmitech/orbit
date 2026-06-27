import { ConversationHistoryMessage } from '../apiClient';
import { Message, Conversation } from '../types';
import { debugWarn } from '../utils/debug';
import {
  getConfiguredSingleAdapterId,
  getDefaultKey,
  getDefaultAdapterName,
  getApiUrl,
  getIsSingleAdapterMode,
  resolveApiUrl,
} from '../utils/runtimeConfig';

// Default adapter name from runtime configuration
export const DEFAULT_ADAPTER = getDefaultAdapterName() || getDefaultKey();

export const getInitialConversationAdapterId = (): string | undefined => {
  if (!getIsSingleAdapterMode()) {
    return undefined;
  }
  return getConfiguredSingleAdapterId() || undefined;
};

export const buildDefaultConversation = (
  conversationId: string,
  sessionId: string,
  apiUrl: string
): Conversation => ({
  id: conversationId,
  sessionId,
  title: 'New Chat',
  messages: [],
  createdAt: new Date(),
  updatedAt: new Date(),
  apiUrl,
  adapterName: getInitialConversationAdapterId(),
  adapterLoadError: null,
});

// Session management
export const getOrCreateSessionId = (): string => {
  const stored = localStorage.getItem('chatbot-session-id');
  if (stored) return stored;
  const newSessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  localStorage.setItem('chatbot-session-id', newSessionId);
  return newSessionId;
};

export const setSessionId = (sessionId: string): void => {
  localStorage.setItem('chatbot-session-id', sessionId);
};

// ID generation
let messageCounter = 0;

export const generateUniqueMessageId = (role: 'user' | 'assistant'): string => {
  const timestamp = Date.now();
  const counter = ++messageCounter;
  const random = Math.random().toString(36).substr(2, 9);
  return `msg_${timestamp}_${counter}_${random}_${role}`;
};

export const generateUniqueSessionId = (): string => {
  const timestamp = Date.now();
  const random = Math.random().toString(36).substr(2, 9);
  return `session_${timestamp}_${random}`;
};

export const ensureUniqueMessageIds = (messages: Message[]): Message[] => {
  const seen = new Set<string>();
  let changed = false;

  const normalized = messages.map(message => {
    if (!seen.has(message.id)) {
      seen.add(message.id);
      return message;
    }

    changed = true;
    const nextMessage = {
      ...message,
      id: generateUniqueMessageId(message.role),
    };
    seen.add(nextMessage.id);
    debugWarn(`[chatStore] Re-keyed duplicate message id ${message.id}`);
    return nextMessage;
  });

  return changed ? normalized : messages;
};

// Message counting / ID extraction
export const countNonStreamingMessages = (messages: Message[]): number =>
  messages.filter(m => !m.isThreadMessage && !(m.role === 'assistant' && m.isStreaming)).length;

export const extractGeneratedFileIds = (messages: Message[]): string[] => {
  const urls = messages.flatMap(message => [
    message.imageUrl,
    message.videoUrl,
    message.documentUrl,
  ]);
  return urls
    .map(url => url?.match(/\/api\/files\/([^/]+)\/content/)?.[1] ?? null)
    .filter((id): id is string => id !== null);
};

// Date helpers
export const toDateOrFallback = (
  value: string | number | Date | null | undefined,
  fallback?: Date
): Date => {
  if (value instanceof Date) return new Date(value);
  if (typeof value === 'number' && Number.isFinite(value)) {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) return parsed;
  }
  if (typeof value === 'string') {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) return parsed;
  }
  return fallback ? new Date(fallback) : new Date();
};

export const convertHistoryMessages = (
  historyMessages: ConversationHistoryMessage[],
  existingMessages: Message[]
): Message[] => {
  const existingByDbId = new Map<string, { message: Message; index: number }>();
  existingMessages.forEach((msg, index) => {
    if (msg.databaseMessageId) {
      existingByDbId.set(msg.databaseMessageId, { message: msg, index });
    }
  });
  const consumedIndices = new Set<number>();

  return historyMessages.map((historyMsg, historyIndex) => {
    const normalizedRole: 'user' | 'assistant' =
      historyMsg.role === 'user' ? 'user' : 'assistant';
    const dbId =
      typeof historyMsg.message_id === 'string' && historyMsg.message_id.length > 0
        ? historyMsg.message_id
        : undefined;

    let reusedMessage: Message | undefined;
    if (dbId && existingByDbId.has(dbId)) {
      const found = existingByDbId.get(dbId)!;
      reusedMessage = found.message;
      consumedIndices.add(found.index);
    } else {
      // Positional fallback: prefer same-index match if role matches, else scan forward.
      // Avoids greedy first-match pairing that misaligns when server history has insertions/deletions.
      const startIndex = historyIndex < existingMessages.length ? historyIndex : 0;
      if (!consumedIndices.has(startIndex) && existingMessages[startIndex]?.role === normalizedRole) {
        reusedMessage = existingMessages[startIndex];
        consumedIndices.add(startIndex);
      } else {
        for (let offset = 1; offset < existingMessages.length; offset++) {
          const i = (startIndex + offset) % existingMessages.length;
          if (consumedIndices.has(i)) continue;
          if (existingMessages[i].role === normalizedRole) {
            reusedMessage = existingMessages[i];
            consumedIndices.add(i);
            break;
          }
        }
      }
    }

    const timestamp = historyMsg.timestamp
      ? toDateOrFallback(historyMsg.timestamp, reusedMessage?.timestamp)
      : reusedMessage?.timestamp
      ? new Date(reusedMessage.timestamp)
      : new Date();

    const baseMessage: Message = reusedMessage
      ? { ...reusedMessage, content: historyMsg.content ?? reusedMessage.content, timestamp }
      : {
          id: dbId ? `srv_${dbId}` : generateUniqueMessageId(normalizedRole),
          content: historyMsg.content || '',
          role: normalizedRole,
          timestamp,
        };

    baseMessage.isStreaming = false;
    if (dbId) baseMessage.databaseMessageId = dbId;

    if (!baseMessage.supportsThreading && historyMsg.metadata && typeof historyMsg.metadata === 'object') {
      const metadata = historyMsg.metadata as Record<string, unknown>;
      const retrievedDocs = metadata?.retrieved_docs;
      if (Array.isArray(retrievedDocs) && retrievedDocs.length > 0) {
        baseMessage.supportsThreading = true;
      }
    }

    return baseMessage;
  });
};

export const haveSameMessages = (current: Message[], nextMessages: Message[]): boolean => {
  if (current.length !== nextMessages.length) return false;
  for (let i = 0; i < current.length; i++) {
    const existing = current[i];
    const incoming = nextMessages[i];
    if (existing.role !== incoming.role) return false;
    if (existing.content !== incoming.content) return false;
    if ((existing.databaseMessageId || null) !== (incoming.databaseMessageId || null)) return false;
    if (+existing.timestamp !== +incoming.timestamp) return false;
  }
  return true;
};

// Audio settings for a conversation (used by sendMessage and regenerateResponse)
export interface AudioSettings {
  returnAudio: boolean;
  ttsVoice: string | undefined;
  language: string;
  audioFormat: string | undefined;
}

export const getAudioSettings = (conversation: {
  adapterInfo?: { adapter_name?: string };
  audioSettings?: {
    enabled?: boolean;
    ttsVoice?: string;
    language?: string;
    audioFormat?: string;
  };
}): AudioSettings => {
  const isVoiceAdapter =
    conversation.adapterInfo?.adapter_name?.includes('voice') ||
    conversation.adapterInfo?.adapter_name?.includes('audio') ||
    conversation.adapterInfo?.adapter_name?.includes('multilingual');

  let globalVoiceEnabled = false;
  try {
    const saved = localStorage.getItem('chat-settings');
    if (saved) {
      const settings = JSON.parse(saved);
      globalVoiceEnabled = settings.voiceEnabled === true;
    }
  } catch {
    debugWarn('Failed to read global voice setting');
  }

  const audioSettings = conversation.audioSettings;
  return {
    returnAudio: audioSettings?.enabled ?? globalVoiceEnabled ?? !!isVoiceAdapter,
    ttsVoice: audioSettings?.ttsVoice || undefined,
    language: audioSettings?.language || 'en-US',
    audioFormat: audioSettings?.audioFormat,
  };
};

// Re-export resolveApiUrl so callers that imported it via chatStore.helpers don't need runtimeConfig
export { resolveApiUrl, getApiUrl };
