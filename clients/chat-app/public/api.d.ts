export interface StreamResponse {
    text: string;
    done: boolean;
}
export interface ChatResponse {
    response: string;
    sources?: any[];
}
export interface FileUploadResponse {
    file_id: string;
    filename: string;
    mime_type: string;
    file_size: number;
    status: string;
    chunk_count: number;
    message: string;
}
export interface FileInfo {
    file_id: string;
    filename: string;
    mime_type: string;
    file_size: number;
    upload_timestamp: string;
    processing_status: string;
    chunk_count: number;
    storage_type: string;
}
export interface FileQueryRequest {
    query: string;
    max_results?: number;
}
export interface FileQueryResponse {
    file_id: string;
    filename: string;
    results: Array<{
        content: string;
        metadata: {
            chunk_id: string;
            file_id: string;
            chunk_index: number;
            confidence: number;
        };
    }>;
}
export declare class ApiClient {
    private readonly apiUrl;
    private readonly apiKey;
    private sessionId;
    constructor(config: {
        apiUrl: string;
        apiKey?: string | null;
        sessionId?: string | null;
    });
    setSessionId(sessionId: string | null): void;
    getSessionId(): string | null;
    private getFetchOptions;
    private createChatRequest;
    streamChat(message: string, stream?: boolean, fileIds?: string[]): AsyncGenerator<StreamResponse>;
    clearConversationHistory(sessionId?: string): Promise<{
        status: string;
        message: string;
        session_id: string;
        deleted_count: number;
        timestamp: string;
    }>;
    /**
     * Upload a file for processing and indexing.
     *
     * @param file - The file to upload
     * @returns Promise resolving to upload response with file_id
     * @throws Error if upload fails
     */
    uploadFile(file: File): Promise<FileUploadResponse>;
    /**
     * List all files for the current API key.
     *
     * @returns Promise resolving to list of file information
     * @throws Error if request fails
     */
    listFiles(): Promise<FileInfo[]>;
    /**
     * Get information about a specific file.
     *
     * @param fileId - The file ID
     * @returns Promise resolving to file information
     * @throws Error if file not found or request fails
     */
    getFileInfo(fileId: string): Promise<FileInfo>;
    /**
     * Query a specific file using semantic search.
     *
     * @param fileId - The file ID
     * @param query - The search query
     * @param maxResults - Maximum number of results (default: 10)
     * @returns Promise resolving to query results
     * @throws Error if query fails
     */
    queryFile(fileId: string, query: string, maxResults?: number): Promise<FileQueryResponse>;
    /**
     * Delete a specific file.
     *
     * @param fileId - The file ID
     * @returns Promise resolving to deletion result
     * @throws Error if deletion fails
     */
    deleteFile(fileId: string): Promise<{
        message: string;
        file_id: string;
    }>;
}
export declare const configureApi: (apiUrl: string, apiKey?: string | null, sessionId?: string | null) => void;
export declare function streamChat(message: string, stream?: boolean, fileIds?: string[]): AsyncGenerator<StreamResponse>;
