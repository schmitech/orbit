export interface Message {
  id: string;
  content: string;
  role: 'user' | 'assistant';
  timestamp: Date;
  isStreaming?: boolean;
  threadInfo?: ThreadInfo;
  supportsThreading?: boolean;
  databaseMessageId?: string;
  threadId?: string;
  parentMessageId?: string;
  isThreadMessage?: boolean;
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

export interface AdapterInfo {
  client_name: string;
  adapter_name: string;
  model: string | null;
  isFileSupported?: boolean;
  notes?: string | null;
}

export interface Conversation {
  id: string;
  sessionId: string;
  title: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
  adapterInfo?: AdapterInfo;
  audioEnabled?: boolean;
  currentThreadId?: string;
  currentThreadSessionId?: string;
}

export interface ChatState {
  conversations: Conversation[];
  currentConversationId: string | null;
  isLoading: boolean;
  error: string | null;
  attachedFileIds: string[];
}
