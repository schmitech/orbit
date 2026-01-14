import { create } from 'zustand';
import { ApiClient, configureApi, streamChat } from '@schmitech/chatbot-api';
import { getApiUrl, getApiKey } from '../index';
import { getOrCreateSessionId, setSessionId } from '../utils/sessionManager';
import { CHAT_CONSTANTS } from '../shared/styles';
import { sanitizeMessageContent } from '../utils/contentFiltering';

export type MessageRole = 'user' | 'assistant' | 'system';

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
}

interface ChatState {
  messages: Message[];
  isLoading: boolean;
  error: string | null;
  sessionId: string;
  sendMessage: (content: string) => Promise<void>;
  appendToLastMessage: (content: string) => void;
  deleteConversation: () => Promise<void>;
  clearMessages: () => void;
  getSessionId: () => string;
}

// Track if API is configured
let isApiConfigured = false;
let configuredApiUrl: string | null = null;
let configuredApiKey: string | null = null;

function ensureApiConfigured(): boolean {
  if (isApiConfigured) {
    return true;
  }

  try {
    if (typeof window !== 'undefined') {
      let apiUrl: string | undefined;
      let apiKey: string | undefined;
      let sessionId: string;

      // Try to get API URL and key from various sources
      if (window.CHATBOT_API_URL && window.CHATBOT_API_KEY) {
        apiUrl = window.CHATBOT_API_URL;
        apiKey = window.CHATBOT_API_KEY;
      } else if (getApiUrl && getApiKey) {
        try {
          apiUrl = getApiUrl();
          apiKey = getApiKey();
        } catch (err) {
          // Silently fail and continue
        }
      }

      if (!apiUrl || !apiKey) {
        console.warn('API URL or API Key not configured');
        return false;
      }

      // Handle session ID
      if (window.CHATBOT_SESSION_ID) {
        // If server provided a session ID, use it and persist it
        sessionId = window.CHATBOT_SESSION_ID;
        setSessionId(sessionId);
      } else {
        // Otherwise, get or create a persistent session ID
        sessionId = getOrCreateSessionId();
      }

      configureApi(apiUrl, apiKey, sessionId);
      configuredApiUrl = apiUrl;
      configuredApiKey = apiKey;
      isApiConfigured = true;
      return true;
    }
  } catch (err) {
    console.error('Failed to configure API:', err);
  }
  return false;
}

function resolveApiCredentials(): { apiUrl: string; apiKey: string } | null {
  let apiUrl: string | null = configuredApiUrl;
  let apiKey: string | null = configuredApiKey;

  if (typeof window !== 'undefined') {
    apiUrl = apiUrl || window.CHATBOT_API_URL || null;
    apiKey = apiKey || window.CHATBOT_API_KEY || null;
  }

  if (!apiUrl) {
    try {
      apiUrl = getApiUrl();
    } catch {
      apiUrl = null;
    }
  }

  if (!apiKey) {
    try {
      apiKey = getApiKey();
    } catch {
      apiKey = null;
    }
  }

  if (apiUrl && apiKey) {
    return { apiUrl, apiKey };
  }

  return null;
}

function generateNewSessionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

// Helper function to generate unique IDs
function generateMessageId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // Fallback for environments without crypto.randomUUID
  return `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

const AUDIO_CHUNK_MIME_TYPE = 'audio/ogg; codecs=opus';
const hasCreateObjectURL =
  typeof URL !== 'undefined' &&
  typeof (URL as typeof URL).createObjectURL === 'function';
const canStreamAudio =
  typeof Audio !== 'undefined' &&
  typeof Blob !== 'undefined' &&
  typeof atob === 'function' &&
  hasCreateObjectURL;

const audioChunkQueue: string[] = [];
let isAudioPlaybackActive = false;

async function enqueueAudioChunk(base64Chunk: string): Promise<void> {
  if (!canStreamAudio) {
    return;
  }

  audioChunkQueue.push(base64Chunk);
  if (isAudioPlaybackActive) {
    return;
  }

  isAudioPlaybackActive = true;
  while (audioChunkQueue.length > 0) {
    const nextChunk = audioChunkQueue.shift();
    if (nextChunk) {
      await playAudioChunk(nextChunk);
    }
  }
  isAudioPlaybackActive = false;
}

function playAudioChunk(base64Chunk: string): Promise<void> {
  return new Promise((resolve) => {
    try {
      if (!canStreamAudio) {
        resolve();
        return;
      }

      const binaryString = atob(base64Chunk);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      const blob = new Blob([bytes], { type: AUDIO_CHUNK_MIME_TYPE });
      const objectUrl = URL.createObjectURL(blob);
      const audio = new Audio(objectUrl);

      const cleanup = () => {
        audio.src = '';
        URL.revokeObjectURL(objectUrl);
      };

      audio.addEventListener('ended', () => {
        cleanup();
        resolve();
      }, { once: true });

      audio.addEventListener('error', () => {
        cleanup();
        resolve();
      }, { once: true });

      const playPromise = audio.play();
      if (playPromise) {
        playPromise.catch(() => {
          cleanup();
          resolve();
        });
      }
    } catch (error) {
      console.error('Failed to play streaming audio chunk', error);
      resolve();
    }
  });
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isLoading: false,
  error: null,
  sessionId: getOrCreateSessionId(),
  
  getSessionId: () => {
    return get().sessionId;
  },
  
  sendMessage: async (content: string) => {
    try {
      // Guardrail: Truncate if content is too long
      const maxLen = CHAT_CONSTANTS.MAX_SUGGESTED_QUESTION_QUERY_LENGTH;
      let safeContent = content;
      if (content.length > maxLen) {
        safeContent = content.substring(0, maxLen);
      }
      // Ensure API is configured
      if (!ensureApiConfigured()) {
        throw new Error('API not properly configured');
      }
      // Add user message
      set(state => ({
        messages: [...state.messages, { id: generateMessageId(), role: 'user', content: safeContent }],
        isLoading: true,
        error: null
      }));
      // Add empty assistant message that will be filled as the stream comes in
      set(state => ({
        messages: [...state.messages, { id: generateMessageId(), role: 'assistant', content: '' }],
      }));
      let receivedAnyText = false;
      try {
        // Use the streamChat function
        for await (const chunk of streamChat(safeContent, true)) {
          const audioChunk = chunk.audio_chunk || chunk.audioChunk;
          if (audioChunk) {
            enqueueAudioChunk(audioChunk).catch(err => {
              console.error('Audio chunk playback failed', err);
            });
          }

          const chunkText = chunk.text ?? chunk.content ?? '';
          if (chunkText) {
            const sanitizedText = sanitizeMessageContent(chunkText);
            if (sanitizedText) {
              get().appendToLastMessage(sanitizedText);
              receivedAnyText = true;
            }
          }
        }
        // If we didn't receive any text, show an error message
        if (!receivedAnyText) {
          get().appendToLastMessage('No response received from the server. Please try again later.');
        }
      } catch (error) {
        console.error('Chat API error:', error);
        get().appendToLastMessage('Sorry, there was an error processing your request.');
      }
      // Set loading to false when done
      set({ isLoading: false });
    } catch (error) {
      console.error('Chat store error:', error);
      set(state => ({
        isLoading: false,
        error: `Failed to send message: ${error instanceof Error ? error.message : 'Unknown error'}`
      }));
    }
  },
  
  appendToLastMessage: (content: string) => {
    set(state => {
      const messages = [...state.messages];
      const lastMessage = messages[messages.length - 1];
      
      if (lastMessage && lastMessage.role === 'assistant') {
        messages[messages.length - 1] = {
          ...lastMessage,
          content: lastMessage.content + content
        };
      }
      
      return { messages };
    });
  },
  
  deleteConversation: async () => {
    const sessionId = get().sessionId || getOrCreateSessionId();

    const apiReady = ensureApiConfigured();
    if (!apiReady) {
      console.warn('API not fully configured. Attempting deletion with available credentials.');
    }

    const credentials = resolveApiCredentials();

    if (credentials) {
      try {
        const apiClient = new ApiClient({
          apiUrl: credentials.apiUrl,
          apiKey: credentials.apiKey,
          sessionId
        });

        if (typeof apiClient.deleteConversationWithFiles === 'function') {
          await apiClient.deleteConversationWithFiles(sessionId, []);
        } else {
          console.warn('deleteConversationWithFiles not available on ApiClient. Skipping server deletion.');
        }
      } catch (error) {
        console.error('Failed to delete conversation from server:', error);
      }
    } else {
      console.warn('Missing API credentials. Clearing local messages without server deletion.');
    }

    const newSessionId = generateNewSessionId();
    setSessionId(newSessionId);

    if (credentials) {
      try {
        configureApi(credentials.apiUrl, credentials.apiKey, newSessionId);
        configuredApiUrl = credentials.apiUrl;
        configuredApiKey = credentials.apiKey;
        isApiConfigured = true;
      } catch (error) {
        console.error('Failed to reconfigure API with new session ID:', error);
      }
    }

    set({
      messages: [],
      isLoading: false,
      sessionId: newSessionId,
      error: null
    });
  },
  
  clearMessages: () => {
    set({ messages: [] });
    // Note: We're NOT clearing the session here, just the messages
    // If you want to start a completely new session, you would also call:
    // clearSession();
    // apiClient = null;
    // ensureApiClient();
  }
}));
