export interface FileAttachment {
  file_id: string;
  filename: string;
  mime_type: string;
  file_size: number;
  upload_timestamp?: string;
  processing_status?: string;
  chunk_count?: number;
  error_message?: string;
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
  model?: string;  // Model used to generate this assistant response
  attachments?: FileAttachment[];
  audio?: string;  // Optional base64-encoded audio data (TTS response) - full audio
  audioFormat?: string;  // Audio format (mp3, wav, etc.)
  image?: string;  // Optional base64-encoded generated image
  imageFormat?: string;  // Image format (png, jpeg, webp)
  imageRevisedPrompt?: string;  // Provider-rewritten prompt (e.g. DALL-E 3)
  imageUrl?: string;  // Persistent server-side URL (survives page refresh)
  video?: string;  // Optional base64-encoded generated video
  videoFormat?: string;  // Video format (mp4)
  videoRevisedPrompt?: string;  // Provider-rewritten prompt
  videoUrl?: string;  // Persistent server-side URL (survives page refresh)
  document?: string;  // Optional base64-encoded generated document
  documentFormat?: string;  // Document format (pdf, docx, xlsx, pptx)
  documentRevisedPrompt?: string;  // Title / final prompt used
  documentUrl?: string;  // Persistent server-side URL (survives page refresh)
  generatedAudioFormat?: string;  // Generated (TTS-skill) audio format (mp3, wav, etc.)
  generatedAudioRevisedPrompt?: string;  // Text that was spoken
  generatedAudioUrl?: string;  // Persistent server-side URL (survives page refresh)
  threadInfo?: ThreadInfo;
  supportsThreading?: boolean;
  databaseMessageId?: string;  // Database message ID from server (used for thread creation and feedback)
  feedback?: 'up' | 'down' | null;  // Persisted feedback state
  feedbackComment?: string | null;  // Optional free-text comment accompanying the rating
  threadId?: string; // Thread identifier when message belongs to a thread
  parentMessageId?: string; // Parent message ID when message belongs to a thread
  isThreadMessage?: boolean; // Marks messages that should be rendered as thread replies
}

export interface AdapterInfo {
  client_name: string;
  adapter_name: string;
  model: string | null;
  isFileSupported?: boolean;
  supportsThreading?: boolean;
  supportsRealtimeVoice?: boolean;
  notes?: string | null;  // Description/notes about the adapter from API key record
}

export interface AllowedModel {
  name: string;      // Client-facing identifier (sent as "model" in request body)
  provider: string;  // Internal provider key
  model: string;     // Actual model name passed to the provider
}

export interface AdapterModelsResponse {
  adapter_name: string;
  has_restrictions: boolean;
  models: AllowedModel[];
}

export interface SkillInfo {
  name: string;
  description: string;
  adapter_name: string;
  enabled: boolean;
}

export interface AdapterSkillsResponse {
  adapter_name: string;
  available_skills: string[];
}

export interface AllModelsResponse {
  models: AllowedModel[];
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
  adapterName?: string; // Adapter name associated with this conversation
  apiUrl?: string; // API URL associated with this conversation
  adapterInfo?: AdapterInfo; // Adapter information (client_name, model)
  adapterLoadError?: string | null; // Adapter configuration error for middleware mode
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

export interface RealtimeVoiceState {
  status: 'idle' | 'connecting' | 'connected' | 'error';
  provider?: string;
  model?: string;
  transcript: string;
  error?: string;
}

export interface ThemeConfig {
  mode: 'light' | 'dark' | 'system';
  highContrast: boolean;
}

export interface Settings {
  theme: ThemeConfig;
  autoSend: boolean;
  voiceEnabled: boolean;
  soundEnabled: boolean;
}
