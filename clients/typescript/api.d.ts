export interface StreamResponse {
    text: string;
    done: boolean;
}
export interface ChatResponse {
    response: string;
}
export declare const configureApi: (apiUrl: string, apiKey: string) => void;
export declare function streamChat(message: string, stream?: boolean): AsyncGenerator<StreamResponse>;
