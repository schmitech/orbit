export interface FileAttachment {
  file_id: string;
  filename: string;
  mime_type: string;
  file_size: number;
  upload_timestamp?: string;
  processing_status?: string;
  chunk_count?: number;
}

export interface StreamingAudioChunk {
  audio: string;  // Base64-encoded audio chunk
  audioFormat: string;  // Audio format (mp3, wav, opus, etc.)
  chunkIndex: number;  // Index of the chunk for ordering
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
  streamingAudioChunks?: StreamingAudioChunk[];  // Streaming audio chunks for incremental playback
  streamingAudioFormat?: string;  // Format for streaming audio chunks
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
  apiKey?: string; // API key associated with this conversation
  apiUrl?: string; // API URL associated with this conversation
  adapterInfo?: AdapterInfo; // Adapter information (client_name, model)
  audioSettings?: AudioSettings; // Audio configuration for this conversation
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