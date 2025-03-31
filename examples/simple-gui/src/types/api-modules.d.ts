// Declaration for direct path
declare module '../../api/dist/api.mjs' {
  export interface StreamResponse {
    text?: string;
    content?: string;
    done?: boolean;
    type?: string;
  }

  export function streamChat(
    message: string,
    voiceEnabled: boolean
  ): AsyncGenerator<StreamResponse>;
  
  export function configureApi(apiUrl: string): void;
}

// Declaration for alias
declare module 'api-local' {
  export interface StreamResponse {
    text?: string;
    content?: string;
    done?: boolean;
    type?: string;
  }

  export function streamChat(
    message: string,
    voiceEnabled: boolean
  ): AsyncGenerator<StreamResponse>;
  
  export function configureApi(apiUrl: string): void;
} 