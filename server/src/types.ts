export interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatStore {
  messages: Message[];
  voiceEnabled: boolean;
  isLoading: boolean;
  addMessage: (message: Message) => void;
  setVoiceEnabled: (enabled: boolean) => void;
  setIsLoading: (loading: boolean) => void;
  appendToLastMessage: (content: string) => void;
  clearMessages: () => void;
}

export interface StreamResponse {
  type: 'text' | 'audio';
  content: string;
  isFinal?: boolean;
}