export interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatStore {
  messages: Message[];
  isLoading: boolean;
  addMessage: (message: Message) => void;
  setIsLoading: (loading: boolean) => void;
  appendToLastMessage: (content: string) => void;
  clearMessages: () => void;
}

export interface StreamResponse {
  type: 'text' | 'audio';
  content: string;
}