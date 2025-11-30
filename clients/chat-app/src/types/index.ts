export interface FileAttachment {
  file_id: string;
  filename: string;
  mime_type: string;
  file_size: number;
  upload_timestamp?: string;
  processing_status?: string;
  chunk_count?: number;
}

export interface ThreadInfo {
  thread_id: string;
  thread_session_id: string;
  parent_message_id: string;
  parent_session_id: string;
  adapter_name: string;
  created_at: string;
  expires_at: string;
}

export interface Message {
  id: string;
  content: string;
  role: 'user' | 'assistant';
  timestamp: Date;
  isStreaming?: boolean;
  attachments?: FileAttachment[];
  audio?: string;  // Optional base64-encoded audio data (TTS response) - full audio
  audioFormat?: string;  // Audio format (mp3, wav, etc.)
  threadInfo?: ThreadInfo;
  supportsThreading?: boolean;
  databaseMessageId?: string;  // Database message ID from server (used for thread creation)
  threadId?: string; // Thread identifier when message belongs to a thread
  parentMessageId?: string; // Parent message ID when message belongs to a thread
  isThreadMessage?: boolean; // Marks messages that should be rendered as thread replies
}

export interface AdapterInfo {
  client_name: string;
  adapter_name: string;
  model: string | null;
  isFileSupported?: boolean;
}

export interface AudioSettings {
  enabled: boolean;
  ttsVoice?: string;  // Voice for TTS: 'alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer' (OpenAI)
  language?: string;  // Language code: 'en-US', 'es-ES', 'fr-FR', etc.
  audioFormat?: string;  // Audio format: 'mp3', 'wav', 'opus', etc.
  autoPlay?: boolean;  // Auto-play TTS responses
}

export interface Conversation {
  id: string;
  sessionId: string; // Unique session ID for MongoDB storage - each conversation gets its own session
  title: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
  attachedFiles?: FileAttachment[];  // Files attached to this conversation
  apiKey?: string; // API key associated with this conversation (when middleware is disabled)
  adapterName?: string; // Adapter name associated with this conversation (when middleware is enabled)
  apiUrl?: string; // API URL associated with this conversation
  adapterInfo?: AdapterInfo; // Adapter information (client_name, model)
  audioSettings?: AudioSettings; // Audio configuration for this conversation
  currentThreadId?: string; // Current thread ID if in thread mode
  currentThreadSessionId?: string; // Current thread session ID if in thread mode
}

export interface ChatState {
  conversations: Conversation[];
  currentConversationId: string | null;
  isLoading: boolean;
  error: string | null;
}

export interface ThemeConfig {
  mode: 'light' | 'dark' | 'system';
  highContrast: boolean;
  fontSize: 'small' | 'medium' | 'large';
}

export interface Settings {
  theme: ThemeConfig;
  autoSend: boolean;
  voiceEnabled: boolean;
  soundEnabled: boolean;
}
