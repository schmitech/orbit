// For Node.js environments, we can use http.Agent for connection pooling
let httpAgent: any = null;
let httpsAgent: any = null;

// Initialize agents for connection pooling in Node.js environments
if (typeof window === 'undefined') {
  // Lazy load to avoid including 'http' in browser bundles
  Promise.all([
    import('http').catch(() => null),
    import('https').catch(() => null)
  ]).then(([http, https]) => {
    if (http?.default?.Agent) {
      httpAgent = new http.default.Agent({ keepAlive: true });
    } else if (http?.Agent) {
      httpAgent = new http.Agent({ keepAlive: true });
    }
    
    if (https?.default?.Agent) {
      httpsAgent = new https.default.Agent({ keepAlive: true });
    } else if (https?.Agent) {
      httpsAgent = new https.Agent({ keepAlive: true });
    }
  }).catch(err => {
    // Silently fail - connection pooling is optional
    console.warn('Failed to initialize HTTP agents:', err.message);
  });
}

// Define the StreamResponse interface
export interface StreamResponse {
  text: string;
  done: boolean;
}

// The server now returns this directly for non-streaming chat
export interface ChatResponse {
  response: string;
  sources?: any[];
}

// The request body for the /v1/chat endpoint
interface ChatRequest {
  messages: Array<{ role: string; content: string; }>;
  stream: boolean;
  file_ids?: string[];  // Optional list of file IDs for file context
}

// File-related interfaces
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

export class ApiClient {
  private readonly apiUrl: string;
  private readonly apiKey: string | null;
  private sessionId: string | null; // Session ID can be mutable

  constructor(config: { apiUrl: string; apiKey?: string | null; sessionId?: string | null }) {
    if (!config.apiUrl || typeof config.apiUrl !== 'string') {
      throw new Error('API URL must be a valid string');
    }
    if (config.apiKey !== undefined && config.apiKey !== null && typeof config.apiKey !== 'string') {
      throw new Error('API key must be a valid string or null');
    }
    if (config.sessionId !== undefined && config.sessionId !== null && typeof config.sessionId !== 'string') {
      throw new Error('Session ID must be a valid string or null');
    }
    
    this.apiUrl = config.apiUrl;
    this.apiKey = config.apiKey ?? null;
    this.sessionId = config.sessionId ?? null;
  }

  public setSessionId(sessionId: string | null): void {
    if (sessionId !== null && typeof sessionId !== 'string') {
      throw new Error('Session ID must be a valid string or null');
    }
    this.sessionId = sessionId;
  }

  public getSessionId(): string | null {
    return this.sessionId;
  }

  // Helper to get fetch options with connection pooling if available
  private getFetchOptions(options: RequestInit = {}): RequestInit {
    const baseOptions: RequestInit = {};
    
    // Environment-specific options
    if (typeof window === 'undefined') {
      // Node.js: Use connection pooling agent
      const isHttps = this.apiUrl.startsWith('https:');
      const agent = isHttps ? httpsAgent : httpAgent;
      if (agent) {
        (baseOptions as any).agent = agent;
      }
    } else {
      // Browser: Use keep-alive header
      baseOptions.headers = { 'Connection': 'keep-alive' };
    }

    // Common headers
    const headers: Record<string, string> = {
      'X-Request-ID': Date.now().toString(36) + Math.random().toString(36).substring(2),
    };

    // Merge base options headers (for browser keep-alive)
    if (baseOptions.headers) {
      Object.assign(headers, baseOptions.headers);
    }

    // Merge original request headers (but don't overwrite API key)
    if (options.headers) {
      const incomingHeaders = options.headers as Record<string, string>;
      for (const [key, value] of Object.entries(incomingHeaders)) {
        // Don't overwrite X-API-Key if we have one
        if (key.toLowerCase() !== 'x-api-key' || !this.apiKey) {
          headers[key] = value;
        }
      }
    }

    if (this.apiKey) {
      headers['X-API-Key'] = this.apiKey;
    }

    if (this.sessionId) {
      headers['X-Session-ID'] = this.sessionId;
    }

    return {
      ...options,
      ...baseOptions,
      headers,
    };
  }

  // Create Chat request
  private createChatRequest(message: string, stream: boolean = true, fileIds?: string[]): ChatRequest {
    const request: ChatRequest = {
      messages: [
        { role: "user", content: message }
      ],
      stream
    };
    if (fileIds && fileIds.length > 0) {
      request.file_ids = fileIds;
    }
    return request;
  }

  public async *streamChat(
    message: string,
    stream: boolean = true,
    fileIds?: string[]
  ): AsyncGenerator<StreamResponse> {
    try {
      // Add timeout to the fetch request
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 60000); // 60 second timeout

      const response = await fetch(`${this.apiUrl}/v1/chat`, {
        ...this.getFetchOptions({
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Accept': stream ? 'text/event-stream' : 'application/json'
          },
          body: JSON.stringify(this.createChatRequest(message, stream, fileIds)),
        }),
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Network response was not ok: ${response.status} ${errorText}`);
      }

      if (!stream) {
        // Handle non-streaming response
        const data = await response.json() as ChatResponse;
        if (data.response) {
          yield {
            text: data.response,
            done: true
          };
        }
        return;
      }
      
      const reader = response.body?.getReader();
      if (!reader) throw new Error('No reader available');

      const decoder = new TextDecoder();
      let buffer = '';
      let hasReceivedContent = false;

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            break;
          }

          const chunk = decoder.decode(value, { stream: true });
          buffer += chunk;
          
          // Process complete lines immediately as they arrive
          let lineStartIndex = 0;
          let newlineIndex;
          
          while ((newlineIndex = buffer.indexOf('\n', lineStartIndex)) !== -1) {
            const line = buffer.slice(lineStartIndex, newlineIndex).trim();
            lineStartIndex = newlineIndex + 1;
            
            if (line && line.startsWith('data: ')) {
              const jsonText = line.slice(6).trim();
              
              if (!jsonText || jsonText === '[DONE]') {
                yield { text: '', done: true };
                return;
              }

              try {
                const data = JSON.parse(jsonText);
                
                if (data.error) {
                  console.error(`[ApiClient] Server error:`, data.error);
                  throw new Error(`Server Error: ${data.error.message}`);
                }
                
                if (data.response) {
                  hasReceivedContent = true;
                  yield { text: data.response, done: data.done || false };
                }

                if (data.done) {
                    yield { text: '', done: true };
                    return;
                }
                
              } catch (parseError) {
                console.warn('[ApiClient] Error parsing JSON chunk:', parseError, 'Chunk:', jsonText);
              }
            } else if (line) {
                // Handle raw text chunks that are not in SSE format
                hasReceivedContent = true;
                yield { text: line, done: false };
            }
          }
          
          buffer = buffer.slice(lineStartIndex);
          
          if (buffer.length > 1000000) { // 1MB limit
            console.warn('Buffer too large, truncating...');
            buffer = buffer.slice(-500000); // Keep last 500KB
          }
        }
        
        if (hasReceivedContent) {
          yield { text: '', done: true };
        }
        
      } finally {
        reader.releaseLock();
      }
      
    } catch (error: any) {
      if (error.name === 'AbortError') {
        throw new Error('Connection timed out. Please check if the server is running.');
      } else if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
        throw new Error('Could not connect to the server. Please check if the server is running.');
      } else {
        throw error;
      }
    }
  }

  public async clearConversationHistory(sessionId?: string): Promise<{
    status: string;
    message: string;
    session_id: string;
    deleted_count: number;
    timestamp: string;
  }> {
    /**
     * Clear conversation history for a session.
     *
     * @param sessionId - Optional session ID to clear. If not provided, uses current session.
     * @returns Promise resolving to operation result
     * @throws Error if the operation fails
     */
    const targetSessionId = sessionId || this.sessionId;

    if (!targetSessionId) {
      throw new Error('No session ID provided and no current session available');
    }

    if (!this.apiKey) {
      throw new Error('API key is required for clearing conversation history');
    }

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-Session-ID': targetSessionId,
      'X-API-Key': this.apiKey
    };

    try {
      const response = await fetch(`${this.apiUrl}/admin/chat-history/${targetSessionId}`, {
        ...this.getFetchOptions({
          method: 'DELETE',
          headers
        })
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Failed to clear conversation history: ${response.status} ${errorText}`);
      }

      const result = await response.json();
      return result;

    } catch (error: any) {
      if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
        throw new Error('Could not connect to the server. Please check if the server is running.');
      } else {
        throw error;
      }
    }
  }

  public async deleteConversationWithFiles(sessionId?: string, fileIds?: string[]): Promise<{
    status: string;
    message: string;
    session_id: string;
    deleted_messages: number;
    deleted_files: number;
    file_deletion_errors: string[] | null;
    timestamp: string;
  }> {
    /**
     * Delete a conversation and all associated files.
     *
     * This method performs a complete conversation deletion:
     * - Deletes each file provided in fileIds (metadata, content, and vector store chunks)
     * - Clears conversation history
     *
     * File tracking is managed by the frontend (localStorage). The backend is stateless
     * and requires fileIds to be provided explicitly.
     *
     * @param sessionId - Optional session ID to delete. If not provided, uses current session.
     * @param fileIds - Optional list of file IDs to delete (from conversation's attachedFiles)
     * @returns Promise resolving to deletion result with counts
     * @throws Error if the operation fails
     */
    const targetSessionId = sessionId || this.sessionId;

    if (!targetSessionId) {
      throw new Error('No session ID provided and no current session available');
    }

    if (!this.apiKey) {
      throw new Error('API key is required for deleting conversation');
    }

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-Session-ID': targetSessionId,
      'X-API-Key': this.apiKey
    };

    // Build URL with file_ids query parameter
    const fileIdsParam = fileIds && fileIds.length > 0 ? `?file_ids=${fileIds.join(',')}` : '';
    const url = `${this.apiUrl}/admin/conversations/${targetSessionId}${fileIdsParam}`;

    try {
      const response = await fetch(url, {
        ...this.getFetchOptions({
          method: 'DELETE',
          headers
        })
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Failed to delete conversation: ${response.status} ${errorText}`);
      }

      const result = await response.json();
      return result;

    } catch (error: any) {
      if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
        throw new Error('Could not connect to the server. Please check if the server is running.');
      } else {
        throw error;
      }
    }
  }

  /**
   * Upload a file for processing and indexing.
   *
   * @param file - The file to upload
   * @returns Promise resolving to upload response with file_id
   * @throws Error if upload fails
   */
  public async uploadFile(file: File): Promise<FileUploadResponse> {
    if (!this.apiKey) {
      throw new Error('API key is required for file upload');
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${this.apiUrl}/api/files/upload`, {
        ...this.getFetchOptions({
          method: 'POST',
          body: formData
        })
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Failed to upload file: ${response.status} ${errorText}`);
      }

      return await response.json();
    } catch (error: any) {
      if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
        throw new Error('Could not connect to the server. Please check if the server is running.');
      } else {
        throw error;
      }
    }
  }

  /**
   * List all files for the current API key.
   * 
   * @returns Promise resolving to list of file information
   * @throws Error if request fails
   */
  public async listFiles(): Promise<FileInfo[]> {
    if (!this.apiKey) {
      throw new Error('API key is required for listing files');
    }

    try {
      const response = await fetch(`${this.apiUrl}/api/files`, {
        ...this.getFetchOptions({
          method: 'GET'
        })
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Failed to list files: ${response.status} ${errorText}`);
      }

      return await response.json();
    } catch (error: any) {
      if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
        throw new Error('Could not connect to the server. Please check if the server is running.');
      } else {
        throw error;
      }
    }
  }

  /**
   * Get information about a specific file.
   * 
   * @param fileId - The file ID
   * @returns Promise resolving to file information
   * @throws Error if file not found or request fails
   */
  public async getFileInfo(fileId: string): Promise<FileInfo> {
    if (!this.apiKey) {
      throw new Error('API key is required for getting file info');
    }

    try {
      const response = await fetch(`${this.apiUrl}/api/files/${fileId}`, {
        ...this.getFetchOptions({
          method: 'GET'
        })
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Failed to get file info: ${response.status} ${errorText}`);
      }

      return await response.json();
    } catch (error: any) {
      if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
        throw new Error('Could not connect to the server. Please check if the server is running.');
      } else {
        throw error;
      }
    }
  }

  /**
   * Query a specific file using semantic search.
   * 
   * @param fileId - The file ID
   * @param query - The search query
   * @param maxResults - Maximum number of results (default: 10)
   * @returns Promise resolving to query results
   * @throws Error if query fails
   */
  public async queryFile(fileId: string, query: string, maxResults: number = 10): Promise<FileQueryResponse> {
    if (!this.apiKey) {
      throw new Error('API key is required for querying files');
    }

    try {
      const response = await fetch(`${this.apiUrl}/api/files/${fileId}/query`, {
        ...this.getFetchOptions({
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ query, max_results: maxResults })
        })
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Failed to query file: ${response.status} ${errorText}`);
      }

      return await response.json();
    } catch (error: any) {
      if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
        throw new Error('Could not connect to the server. Please check if the server is running.');
      } else {
        throw error;
      }
    }
  }

  /**
   * Delete a specific file.
   * 
   * @param fileId - The file ID
   * @returns Promise resolving to deletion result
   * @throws Error if deletion fails
   */
  public async deleteFile(fileId: string): Promise<{ message: string; file_id: string }> {
    if (!this.apiKey) {
      throw new Error('API key is required for deleting files');
    }

    const url = `${this.apiUrl}/api/files/${fileId}`;
    const fetchOptions = this.getFetchOptions({
      method: 'DELETE'
    });

    try {
      const response = await fetch(url, fetchOptions);

      if (!response.ok) {
        const errorText = await response.text();
        console.error(`[ApiClient] Delete failed: ${response.status}`, errorText);
        throw new Error(`Failed to delete file: ${response.status} ${errorText}`);
      }

      const result = await response.json();
      return result;
    } catch (error: any) {
      console.error(`[ApiClient] Delete error for file ${fileId}:`, error);
      if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
        throw new Error('Could not connect to the server. Please check if the server is running.');
      } else {
        throw error;
      }
    }
  }
}

// Legacy compatibility functions - these create a default client instance
// These are kept for backward compatibility but should be deprecated in favor of the class-based approach

let defaultClient: ApiClient | null = null;

// Configure the API with a custom URL, API key (optional), and session ID (optional)
export const configureApi = (apiUrl: string, apiKey: string | null = null, sessionId: string | null = null): void => {
  defaultClient = new ApiClient({ apiUrl, apiKey, sessionId });
}

// Legacy streamChat function that uses the default client
export async function* streamChat(
  message: string,
  stream: boolean = true,
  fileIds?: string[]
): AsyncGenerator<StreamResponse> {
  if (!defaultClient) {
    throw new Error('API not configured. Please call configureApi() with your server URL before using any API functions.');
  }
  
  yield* defaultClient.streamChat(message, stream, fileIds);
}

