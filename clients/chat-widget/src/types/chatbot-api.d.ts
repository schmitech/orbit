declare module '@schmitech/chatbot-api' {
  export interface ThreadingInfo {
    supports_threading?: boolean;
    message_id?: string;
    session_id?: string;
  }

  export interface StreamResponse {
    text?: string;
    response?: string;
    content?: string;
    done?: boolean;
    audio?: string;
    audioFormat?: string;
    audio_chunk?: string;
    audioChunk?: string;
    chunk_index?: number;
    type?: string;
    threading?: ThreadingInfo;
  }

  export function streamChat(
    message: string,
    stream?: boolean,
    fileIds?: string[],
    threadId?: string,
    audioInput?: string,
    audioFormat?: string,
    language?: string,
    returnAudio?: boolean,
    ttsVoice?: string,
    sourceLanguage?: string,
    targetLanguage?: string
  ): AsyncGenerator<StreamResponse>;
  
  export function configureApi(
    apiUrl: string,
    apiKey?: string | null,
    sessionId?: string | null
  ): void;
}
