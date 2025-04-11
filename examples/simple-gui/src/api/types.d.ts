declare module 'api-local' {
    export function streamChat(message: string): AsyncGenerator<{ text?: string; content?: string; done?: boolean; type?: string }>;
    export function configureApi(apiUrl: string, apiKey?: string): void;
} 