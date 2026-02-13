export interface Message {
  id: string;
  content: string;
  role: 'user' | 'assistant';
  timestamp: Date;
  isStreaming?: boolean;
}

export interface AdapterInfo {
  client_name: string;
  adapter_name: string;
  model: string | null;
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
}

export interface ChatState {
  conversations: Conversation[];
  currentConversationId: string | null;
  isLoading: boolean;
  error: string | null;
}
