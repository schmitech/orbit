export interface StreamResponse {
    text: string;
    done: boolean;
}
export interface ChatResponse {
    response: string;
}
interface MCPResponse {
    jsonrpc: "2.0";
    id: string;
    result?: {
        type?: "start" | "chunk" | "complete";
        chunk?: {
            content: string;
        };
        output?: {
            messages: Array<{
                role: string;
                content: string;
            }>;
        };
    };
    error?: {
        code: number;
        message: string;
    };
}
export declare const configureApi: (apiUrl: string, apiKey?: string | null, sessionId?: string | null) => void;
export declare function streamChat(message: string, stream?: boolean): AsyncGenerator<StreamResponse>;
export declare function sendToolsRequest(tools: Array<{
    name: string;
    parameters: Record<string, any>;
}>): Promise<MCPResponse>;
export {};
