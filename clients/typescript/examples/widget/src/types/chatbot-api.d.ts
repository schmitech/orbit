declare module '@schmitech/chatbot-api' {
  export interface StreamResponse {
    text?: string;
    audioChunk?: string;
    type?: string;
    content?: string;
    done?: boolean;
  }

  export function streamChat(
    message: string,
    voiceEnabled: boolean
  ): AsyncGenerator<StreamResponse>;
  
  export function configureApi(apiUrl: string, apiKey: string, sessionId: string): void;
} 