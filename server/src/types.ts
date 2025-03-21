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

export interface AppConfig {
  ollama: {
    base_url: string;
    temperature: number | string;
    top_p: number | string;
    top_k: number | string;
    repeat_penalty: number | string;
    num_predict: number | string;
    num_ctx: number | string;
    num_threads: number | string;
    model: string;
    embed_model: string;
  };
  vllm: {
    base_url: string;
    temperature: number | string;
    max_tokens: number | string;
    model: string;
    top_p: number | string;
    frequency_penalty: number | string;
    presence_penalty: number | string;
    best_of?: number | string;
    n?: number | string;
    logprobs?: number | string | null;
    echo?: boolean | string;
    stream?: boolean | string;
    guardrail_max_tokens?: number | string;
    guardrail_temperature?: number | string;
    guardrail_top_p?: number | string;
  };
  huggingface: {
    api_key: string;
    model: string;
  };
  chroma: {
    host: string;
    port: number | string;
    collection: string;
  };
  eleven_labs: {
    api_key: string;
    voice_id: string;
  };
  system: {
    prompt: string;
    guardrail_prompt: string;
  };
  general: {
    verbose: string;
  };
  elasticsearch: {
    enabled: boolean;
    node: string;
    index: string;
    auth: {
      username: string;
      password: string;
    }
  }
}