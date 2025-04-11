declare module 'chatbot-api' {
  export interface StreamResponse {
    text?: string;
    type?: string;
    content?: string;
    done?: boolean;
  }

  export function streamChat(
    message: string,
  ): AsyncGenerator<StreamResponse>;
  
  export function configureApi(apiUrl: string): void;
} 