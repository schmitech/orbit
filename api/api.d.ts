export interface StreamResponse {
    text?: string;
    content?: string;
    done?: boolean;
    type?: string;
}
export declare const configureApi: (apiUrl: string) => void;
export declare function streamChat(message: string, voiceEnabled: boolean): AsyncGenerator<StreamResponse>;
