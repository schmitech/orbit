export interface FileAttachment {
  file_id: string;
  filename: string;
  mime_type: string;
  file_size: number;
  upload_timestamp?: string;
  processing_status?: string;
  chunk_count?: number;
}

export interface Message {
  id: string;
  content: string;
  role: 'user' | 'assistant';
  timestamp: Date;
  isStreaming?: boolean;
  attachments?: FileAttachment[];
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