export interface StreamResponse {
    text: string;
    done: boolean;
}
export interface ChatResponse {
    response: string;
    audio: string | null;
}
export declare const configureApi: (apiUrl: string) => void;
export declare function streamChat(message: string, voiceEnabled: boolean, stream?: boolean): AsyncGenerator<StreamResponse>;
