// Connection pooling agents are Node.js-only; not used in React Native
const httpAgent: any = null;
const httpsAgent: any = null;

// Define the StreamResponse interface
export interface StreamResponse {
  text: string;
  done: boolean;
  request_id?: string;  // Request ID from first chunk for cancellation
  audio?: string;  // Optional base64-encoded audio data (TTS response) - full audio
  audioFormat?: string;  // Audio format (mp3, wav, etc.)
  audio_chunk?: string;  // Optional streaming audio chunk (base64-encoded)
  chunk_index?: number;  // Index of the audio chunk for ordering
  threading?: {  // Optional threading metadata
    supports_threading: boolean;
    message_id: string;
    session_id: string;
  };
}

// The server now returns this directly for non-streaming chat
export interface ChatResponse {
  response: string;
  sources?: any[];
  audio?: string;  // Optional base64-encoded audio data (TTS response)
  audio_format?: string;  // Audio format (mp3, wav, etc.)
}

// Thread-related interfaces
export interface ThreadInfo {
  thread_id: string;
  thread_session_id: string;
  parent_message_id: string;
  parent_session_id: string;
  adapter_name: string;
  created_at: string;
  expires_at: string;
}

// The request body for the /v1/chat endpoint
interface ChatRequest {
  messages: Array<{ role: string; content: string; }>;
  stream: boolean;
  file_ids?: string[];  // Optional list of file IDs for file context
  thread_id?: string;  // Optional thread ID for follow-up questions
  audio_input?: string;  // Optional base64-encoded audio data for STT
  audio_format?: string;  // Optional audio format (mp3, wav, etc.)
  language?: string;  // Optional language code for STT (e.g., "en-US")
  return_audio?: boolean;  // Whether to return audio response (TTS)
  tts_voice?: string;  // Voice for TTS (e.g., "alloy", "echo" for OpenAI)
  source_language?: string;  // Source language for translation
  target_language?: string;  // Target language for translation
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

// API key status interface
export interface ApiKeyStatus {
  exists: boolean;
  active: boolean;
  adapter_name?: string | null;
  client_name?: string | null;
  created_at?: string | number | null;
  system_prompt?: {
    id: string;
    exists: boolean;
  } | null;
  message?: string;
}

// Adapter information interface
export interface AdapterInfo {
  client_name: string;
  adapter_name: string;
  model: string | null;
  isFileSupported?: boolean;
  notes?: string | null;
}

export interface ConversationHistoryMessage {
  message_id?: string | null;
  role: string;
  content: string;
  timestamp: string | number | Date | null;
  metadata?: Record<string, any>;
}

export interface ConversationHistoryResponse {
  session_id: string;
  messages: ConversationHistoryMessage[];
  count: number;
}

// Autocomplete interfaces
export interface AutocompleteSuggestion {
  text: string;
}

export interface AutocompleteResponse {
  suggestions: AutocompleteSuggestion[];
  query: string;
}

interface ApiClientConfig {
  apiUrl: string;
  apiKey?: string | null;
  sessionId?: string | null;
  adapterName?: string | null;
  useMiddleware?: boolean;
  middlewareBaseUrl?: string | null;
}

export class ApiClient {
  private readonly apiUrl: string;
  private readonly apiKey: string | null;
  private readonly adapterName: string | null;
  private readonly middlewareBaseUrl: string;
  private readonly middlewareMode: boolean;
  private sessionId: string | null; // Session ID can be mutable

  constructor(config: ApiClientConfig) {
    if (!config.apiUrl || typeof config.apiUrl !== 'string') {
      throw new Error('API URL must be a valid string');
    }
    if (config.apiKey !== undefined && config.apiKey !== null && typeof config.apiKey !== 'string') {
      throw new Error('API key must be a valid string or null');
    }
    if (config.sessionId !== undefined && config.sessionId !== null && typeof config.sessionId !== 'string') {
      throw new Error('Session ID must be a valid string or null');
    }
    if (config.adapterName !== undefined && config.adapterName !== null && typeof config.adapterName !== 'string') {
      throw new Error('Adapter name must be a valid string or null');
    }
    if (config.middlewareBaseUrl !== undefined && config.middlewareBaseUrl !== null && typeof config.middlewareBaseUrl !== 'string') {
      throw new Error('Middleware base URL must be a valid string or null');
    }
    
    this.apiUrl = config.apiUrl;
    this.apiKey = config.apiKey ?? null;
    this.sessionId = config.sessionId ?? null;
    const adapter = typeof config.adapterName === 'string' ? config.adapterName.trim() : '';
    this.adapterName = adapter && adapter.length > 0 ? adapter : null;
    const baseUrl = typeof config.middlewareBaseUrl === 'string' ? config.middlewareBaseUrl.trim() : '';
    this.middlewareBaseUrl = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl;
    const middlewareRequested = config.useMiddleware ?? (!this.apiKey && !!this.adapterName);
    this.middlewareMode = Boolean(this.adapterName && middlewareRequested);
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

  /**
   * Validate that the API key exists and is active.
   *
   * @returns Promise resolving to API key status information
   * @throws Error if API key is not provided, invalid, inactive, or validation fails
   */
  public async validateApiKey(): Promise<ApiKeyStatus> {
    if (!this.apiKey) {
      throw new Error('API key is required for validation');
    }

    try {
      const response = await fetch(`${this.apiUrl}/admin/api-keys/${this.apiKey}/status`, {
        ...this.getFetchOptions({
          method: 'GET'
        })
      }).catch((fetchError: any) => {
        // Catch network errors before they bubble up
        if (fetchError.name === 'TypeError' && fetchError.message.includes('Failed to fetch')) {
          throw new Error('Could not connect to the server. Please check if the server is running.');
        }
        throw fetchError;
      });

      if (!response.ok) {
        // Read error response body
        let errorText = '';
        try {
          errorText = await response.text();
        } catch {
          // If we can't read the body, fall back to status code
          errorText = `HTTP ${response.status}`;
        }

        let errorDetail: string;
        let friendlyMessage: string;

        try {
          const errorJson = JSON.parse(errorText);
          errorDetail = errorJson.detail || errorJson.message || errorText;
        } catch {
          // If parsing fails, use the error text or status code
          errorDetail = errorText || `HTTP ${response.status}`;
        }

        // Generate user-friendly error messages based on HTTP status code
        switch (response.status) {
          case 401:
            friendlyMessage = 'API key is invalid or expired';
            break;
          case 403:
            friendlyMessage = 'Access denied: API key does not have required permissions';
            break;
          case 404:
            friendlyMessage = 'API key not found';
            break;
          case 503:
            friendlyMessage = 'API key management is not available in inference-only mode';
            break;
          default:
            friendlyMessage = `Failed to validate API key: ${errorDetail}`;
            break;
        }

        // Throw error - will be logged in catch block to avoid duplicates
        throw new Error(friendlyMessage);
      }

      const status: ApiKeyStatus = await response.json();

      // Check if the key exists
      if (!status.exists) {
        const friendlyMessage = 'API key does not exist';
        // Throw error - will be logged in catch block to avoid duplicates
        throw new Error(friendlyMessage);
      }

      // Check if the key is active
      if (!status.active) {
        const friendlyMessage = 'API key is inactive';
        // Throw error - will be logged in catch block to avoid duplicates
        throw new Error(friendlyMessage);
      }

      return status;
    } catch (error: any) {
      // Extract user-friendly error message
      let friendlyMessage: string;

      if (error instanceof Error && error.message) {
        // If it's already a user-friendly Error from above, use it directly
        if (error.message.includes('API key') ||
            error.message.includes('Access denied') ||
            error.message.includes('invalid') ||
            error.message.includes('expired') ||
            error.message.includes('inactive') ||
            error.message.includes('not found') ||
            error.message.includes('Could not connect')) {
          friendlyMessage = error.message;
        } else {
          friendlyMessage = `API key validation failed: ${error.message}`;
        }
      } else if (error.name === 'TypeError' && error.message?.includes('Failed to fetch')) {
        friendlyMessage = 'Could not connect to the server. Please check if the server is running.';
      } else {
        friendlyMessage = 'API key validation failed. Please check your API key and try again.';
      }

      // Only log warning if it's not a network error (those are already logged by browser)
      // For validation errors, we log once with a friendly message
      // Note: Browser will still log HTTP errors (401, 404, etc.) - this is unavoidable
      console.warn(`[ApiClient] ${friendlyMessage}`);

      // Throw the friendly error message
      throw new Error(friendlyMessage);
    }
  }

  /**
   * Get adapter information for the current API key.
   *
   * Returns information about the adapter and model being used by the API key.
   * This is useful for displaying configuration details to users.
   *
   * @returns Promise resolving to adapter information
   * @throws Error if API key is not provided, invalid, disabled, or request fails
   */
  public async getAdapterInfo(): Promise<AdapterInfo> {
    if (!this.apiKey) {
      throw new Error('API key is required to get adapter information');
    }

    try {
      const response = await fetch(`${this.apiUrl}/admin/adapters/info`, {
        ...this.getFetchOptions({
          method: 'GET'
        })
      }).catch((fetchError: any) => {
        // Catch network errors before they bubble up
        if (fetchError.name === 'TypeError' && fetchError.message.includes('Failed to fetch')) {
          throw new Error('Could not connect to the server. Please check if the server is running.');
        }
        throw fetchError;
      });

      if (!response.ok) {
        // Read error response body
        let errorText = '';
        try {
          errorText = await response.text();
        } catch {
          // If we can't read the body, fall back to status code
          errorText = `HTTP ${response.status}`;
        }

        let errorDetail: string;
        let friendlyMessage: string;

        try {
          const errorJson = JSON.parse(errorText);
          errorDetail = errorJson.detail || errorJson.message || errorText;
        } catch {
          // If parsing fails, use the error text or status code
          errorDetail = errorText || `HTTP ${response.status}`;
        }

        // Generate user-friendly error messages based on HTTP status code
        switch (response.status) {
          case 401:
            friendlyMessage = 'API key is invalid, disabled, or has no associated adapter';
            break;
          case 404:
            friendlyMessage = 'Adapter configuration not found';
            break;
          case 503:
            friendlyMessage = 'Service is not available';
            break;
          default:
            friendlyMessage = `Failed to get adapter info: ${errorDetail}`;
            break;
        }

        // Throw error - will be logged in catch block to avoid duplicates
        throw new Error(friendlyMessage);
      }

      const adapterInfo: AdapterInfo = await response.json();
      return adapterInfo;
    } catch (error: any) {
      // Extract user-friendly error message
      let friendlyMessage: string;

      if (error instanceof Error && error.message) {
        // If it's already a user-friendly Error from above, use it directly
        if (error.message.includes('API key') ||
            error.message.includes('Adapter') ||
            error.message.includes('invalid') ||
            error.message.includes('disabled') ||
            error.message.includes('not found') ||
            error.message.includes('Could not connect')) {
          friendlyMessage = error.message;
        } else {
          friendlyMessage = `Failed to get adapter info: ${error.message}`;
        }
      } else if (error.name === 'TypeError' && error.message?.includes('Failed to fetch')) {
        friendlyMessage = 'Could not connect to the server. Please check if the server is running.';
      } else {
        friendlyMessage = 'Failed to get adapter information. Please try again.';
      }

      console.warn(`[ApiClient] ${friendlyMessage}`);

      // Throw the friendly error message
      throw new Error(friendlyMessage);
    }
  }

  /**
   * Get autocomplete suggestions based on query prefix.
   *
   * Returns query suggestions based on nl_examples from intent adapter templates.
   * This is useful for helping users discover available queries.
   *
   * @param query - The query prefix (minimum 3 characters)
   * @param limit - Maximum number of suggestions (default: 5)
   * @returns Promise resolving to autocomplete suggestions
   */
  public async getAutocompleteSuggestions(
    query: string,
    limit: number = 5
  ): Promise<AutocompleteResponse> {
    if (query.length < 3) {
      return { suggestions: [], query };
    }

    const useMiddleware = this.middlewareMode && !!this.adapterName;

    if (!useMiddleware && !this.apiKey) {
      return { suggestions: [], query };
    }

    try {
      const params = new URLSearchParams();
      params.set('q', query);
      params.set('limit', String(limit));

      let requestUrl: string;
      let requestOptions: RequestInit;

      if (useMiddleware) {
        if (!this.middlewareBaseUrl && typeof window === 'undefined') {
          throw new Error('middlewareBaseUrl must be set when using middleware outside the browser environment.');
        }

        const base = this.middlewareBaseUrl
          ? this.middlewareBaseUrl
          : '';
        const endpoint = '/api/v1/autocomplete';
        requestUrl = `${base}${endpoint}?${params.toString()}`;

        const headers: Record<string, string> = {
          'X-Adapter-Name': this.adapterName as string,
          'X-Request-ID': Date.now().toString(36) + Math.random().toString(36).substring(2),
        };

        if (this.sessionId) {
          headers['X-Session-ID'] = this.sessionId;
        }

        requestOptions = {
          method: 'GET',
          headers
        };
      } else {
        const url = new URL(`${this.apiUrl}/v1/autocomplete`);
        url.searchParams.set('q', query);
        url.searchParams.set('limit', String(limit));
        requestUrl = url.toString();

        requestOptions = {
          ...this.getFetchOptions({
            method: 'GET'
          })
        };
      }

      const response = await fetch(requestUrl, requestOptions);

      if (!response.ok) {
        // Non-critical - return empty suggestions rather than throw
        console.warn('[ApiClient] Autocomplete request failed:', response.status);
        return { suggestions: [], query };
      }

      return await response.json();
    } catch (error: any) {
      // Autocomplete failures should not block the user
      console.warn('[ApiClient] Autocomplete error:', error.message);
      return { suggestions: [], query };
    }
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
  private createChatRequest(
    message: string, 
    stream: boolean = true, 
    fileIds?: string[],
    threadId?: string,
    audioInput?: string,
    audioFormat?: string,
    language?: string,
    returnAudio?: boolean,
    ttsVoice?: string,
    sourceLanguage?: string,
    targetLanguage?: string
  ): ChatRequest {
    const request: ChatRequest = {
      messages: [
        { role: "user", content: message }
      ],
      stream
    };
    if (fileIds && fileIds.length > 0) {
      request.file_ids = fileIds;
    }
    if (threadId) {
      request.thread_id = threadId;
    }
    if (audioInput) {
      request.audio_input = audioInput;
    }
    if (audioFormat) {
      request.audio_format = audioFormat;
    }
    if (language) {
      request.language = language;
    }
    if (returnAudio !== undefined) {
      request.return_audio = returnAudio;
    }
    if (ttsVoice) {
      request.tts_voice = ttsVoice;
    }
    if (sourceLanguage) {
      request.source_language = sourceLanguage;
    }
    if (targetLanguage) {
      request.target_language = targetLanguage;
    }
    return request;
  }

  public async *streamChat(
    message: string,
    stream: boolean = true,
    fileIds?: string[],
    threadId?: string,
    audioInput?: string,
    audioFormat?: string,
    language?: string,
    returnAudio?: boolean,
    ttsVoice?: string,
    sourceLanguage?: string,
    targetLanguage?: string,
    abortSignal?: AbortSignal
  ): AsyncGenerator<StreamResponse> {
    try {
      // SSE line parser shared by both ReadableStream and XHR paths
      function* parseSSELines(
        lines: string[],
        state: { hasReceivedContent: boolean }
      ): Generator<StreamResponse> {
        for (const rawLine of lines) {
          const line = rawLine.trim();
          if (!line) continue;

          if (line.startsWith('data: ')) {
            const jsonText = line.slice(6).trim();

            if (!jsonText || jsonText === '[DONE]') {
              yield { text: '', done: true };
              return;
            }

            try {
              const data = JSON.parse(jsonText);

              if (data.error) {
                const errorMessage = data.error?.message || data.error || 'Unknown server error';
                throw new Error(`Server error: ${errorMessage}`);
              }

              if (data.request_id && !data.response && !data.done) {
                yield { text: '', done: false, request_id: data.request_id };
                continue;
              }

              if (data.done === true) {
                state.hasReceivedContent = true;
                yield {
                  text: '', done: true,
                  audio: data.audio,
                  audioFormat: data.audio_format || data.audioFormat,
                  threading: data.threading
                };
                return;
              }

              const responseText = data.response || '';

              if (data.audio_chunk !== undefined) {
                yield {
                  text: '', done: false,
                  audio_chunk: data.audio_chunk,
                  audioFormat: data.audioFormat || data.audio_format || 'opus',
                  chunk_index: data.chunk_index ?? 0
                };
              }

              if (responseText || data.audio) {
                state.hasReceivedContent = true;
                yield {
                  text: responseText,
                  done: data.done || false,
                  audio: data.audio,
                  audioFormat: data.audio_format || data.audioFormat,
                  threading: data.threading
                };
              }
            } catch (parseError: any) {
              if (parseError?.message?.startsWith('Server error:')) {
                throw parseError;
              }
              console.warn('[ApiClient] Parse error:', parseError?.message);
            }
          } else {
            state.hasReceivedContent = true;
            yield { text: line, done: false };
          }
        }
      }

      // React Native: always use XHR for streaming (fetch ReadableStream is unreliable in RN).
      // XHR provides progressive responseText access for real-time streaming.
      {
        const chatRequest = this.createChatRequest(
          message, stream, fileIds, threadId,
          audioInput, audioFormat, language,
          returnAudio, ttsVoice, sourceLanguage, targetLanguage
        );
        const apiUrl = this.apiUrl;
        const apiKey = this.apiKey;
        const sessionId = this.sessionId;
        const adapterName = this.adapterName;

        // Use a callback-driven XHR to yield chunks as they arrive
        const chunks: StreamResponse[] = [];
        let resolveNext: (() => void) | null = null;
        let xhrDone = false;
        let xhrError: Error | null = null;
        let lastProcessedIndex = 0;
        let sseBuffer = '';
        const state = { hasReceivedContent: false };

        const xhr = new XMLHttpRequest();
        xhr.open('POST', `${apiUrl}/v1/chat`);
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.setRequestHeader('Accept', 'text/event-stream');
        if (apiKey) xhr.setRequestHeader('x-api-key', apiKey);
        if (sessionId) xhr.setRequestHeader('X-Session-ID', sessionId);
        if (adapterName) xhr.setRequestHeader('X-Adapter-Name', adapterName);

        if (abortSignal) {
          abortSignal.addEventListener('abort', () => xhr.abort());
        }

        const processNewText = () => {
          const newText = xhr.responseText.slice(lastProcessedIndex);
          lastProcessedIndex = xhr.responseText.length;
          sseBuffer += newText;

          let lineStartIndex = 0;
          let newlineIndex;
          const lines: string[] = [];

          while ((newlineIndex = sseBuffer.indexOf('\n', lineStartIndex)) !== -1) {
            lines.push(sseBuffer.slice(lineStartIndex, newlineIndex));
            lineStartIndex = newlineIndex + 1;
          }
          sseBuffer = sseBuffer.slice(lineStartIndex);

          for (const parsed of parseSSELines(lines, state)) {
            chunks.push(parsed);
          }
          if (resolveNext) {
            resolveNext();
            resolveNext = null;
          }
        };

        xhr.onprogress = processNewText;
        xhr.onload = () => { processNewText(); xhrDone = true; if (resolveNext) { resolveNext(); resolveNext = null; } };
        xhr.onerror = () => { xhrError = new Error('Network error'); if (resolveNext) { resolveNext(); resolveNext = null; } };
        xhr.onabort = () => { xhrError = new Error('Stream cancelled by user'); if (resolveNext) { resolveNext(); resolveNext = null; } };
        xhr.send(JSON.stringify(chatRequest));

        let chunkIndex = 0;
        while (true) {
          while (chunkIndex < chunks.length) {
            const chunk = chunks[chunkIndex++];
            yield chunk;
            if (chunk.done) return;
          }

          if (xhrError) throw xhrError;
          if (xhrDone && chunkIndex >= chunks.length) break;

          // Wait for more data
          await new Promise<void>(resolve => { resolveNext = resolve; });
        }

        if (state.hasReceivedContent) {
          yield { text: '', done: true };
        }
      }
      
    } catch (error: any) {
      if (error.name === 'AbortError') {
        // Check if this was user-initiated or timeout
        if (abortSignal?.aborted) {
          throw new Error('Stream cancelled by user');
        }
        throw new Error('Connection timed out. Please check if the server is running.');
      } else if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
        throw new Error('Could not connect to the server. Please check if the server is running.');
      } else {
        throw error;
      }
    }
  }

  /**
   * Stop an active streaming request.
   *
   * @param sessionId - The session identifier
   * @param requestId - The request identifier (from first stream chunk)
   * @returns Promise resolving to true if stream was cancelled, false otherwise
   */
  public async stopChat(sessionId: string, requestId: string): Promise<boolean> {
    try {
      const response = await fetch(`${this.apiUrl}/v1/chat/stop`, {
        ...this.getFetchOptions({
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            session_id: sessionId,
            request_id: requestId
          }),
        }),
      });

      if (!response.ok) {
        console.warn('[ApiClient] Failed to stop stream:', response.status);
        return false;
      }

      const result = await response.json();
      return result.status === 'cancelled';
    } catch (error) {
      console.error('[ApiClient] Error stopping stream:', error);
      return false;
    }
  }

  public async getConversationHistory(
    sessionId?: string,
    limit?: number
  ): Promise<ConversationHistoryResponse> {
    /**
     * Retrieve persisted conversation history for a session.
     *
     * @param sessionId - Optional session ID to fetch. If not provided, uses current session.
     * @param limit - Optional maximum number of messages to return
     * @returns Promise resolving to conversation history payload
     */
    const targetSessionId = sessionId || this.sessionId;

    if (!targetSessionId) {
      throw new Error('No session ID provided and no current session available');
    }

    const headers: Record<string, string> = {};
    if (this.apiKey) {
      headers['X-API-Key'] = this.apiKey;
    }

    try {
      const url = new URL(`${this.apiUrl}/admin/chat-history/${targetSessionId}`);
      if (typeof limit === 'number' && Number.isFinite(limit) && limit > 0) {
        url.searchParams.set('limit', String(Math.floor(limit)));
      }

      const response = await fetch(url.toString(), {
        ...this.getFetchOptions({
          method: 'GET',
          headers
        })
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Failed to fetch conversation history: ${response.status} ${errorText}`);
      }

      const result = await response.json();
      const messages = Array.isArray(result?.messages) ? result.messages : [];
      const count = typeof result?.count === 'number' ? result.count : messages.length;

      return {
        session_id: result?.session_id || targetSessionId,
        messages,
        count
      };
    } catch (error: any) {
      if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
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
   * Create a conversation thread from a parent message.
   *
   * @param messageId - ID of the parent message
   * @param sessionId - Session ID of the parent conversation
   * @returns Promise resolving to thread information
   * @throws Error if the operation fails
   */
  public async createThread(messageId: string, sessionId: string): Promise<ThreadInfo> {
    if (!this.apiKey) {
      throw new Error('API key is required for creating threads');
    }

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-API-Key': this.apiKey
    };

    try {
      const response = await fetch(`${this.apiUrl}/api/threads`, {
        ...this.getFetchOptions({
          method: 'POST',
          headers,
          body: JSON.stringify({
            message_id: messageId,
            session_id: sessionId
          })
        })
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Failed to create thread: ${response.status} ${errorText}`);
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
   * Get thread information by thread ID.
   *
   * @param threadId - Thread identifier
   * @returns Promise resolving to thread information
   * @throws Error if the operation fails
   */
  public async getThreadInfo(threadId: string): Promise<ThreadInfo> {
    if (!this.apiKey) {
      throw new Error('API key is required for getting thread info');
    }

    const headers: Record<string, string> = {
      'X-API-Key': this.apiKey
    };

    try {
      const response = await fetch(`${this.apiUrl}/api/threads/${threadId}`, {
        ...this.getFetchOptions({
          method: 'GET',
          headers
        })
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Failed to get thread info: ${response.status} ${errorText}`);
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
   * Delete a thread and its associated dataset.
   *
   * @param threadId - Thread identifier
   * @returns Promise resolving to deletion result
   * @throws Error if the operation fails
   */
  public async deleteThread(threadId: string): Promise<{ status: string; message: string; thread_id: string }> {
    if (!this.apiKey) {
      throw new Error('API key is required for deleting threads');
    }

    const headers: Record<string, string> = {
      'X-API-Key': this.apiKey
    };

    try {
      const response = await fetch(`${this.apiUrl}/api/threads/${threadId}`, {
        ...this.getFetchOptions({
          method: 'DELETE',
          headers
        })
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Failed to delete thread: ${response.status} ${errorText}`);
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
        let friendlyMessage: string;
        try {
          const errorJson = JSON.parse(errorText);
          friendlyMessage = errorJson.detail || errorJson.message || `Failed to delete file (HTTP ${response.status})`;
        } catch {
          friendlyMessage = `Failed to delete file (HTTP ${response.status})`;
        }
        console.warn(`[ApiClient] ${friendlyMessage}`);
        throw new Error(friendlyMessage);
      }

      const result = await response.json();
      return result;
    } catch (error: any) {
      // Extract user-friendly error message
      let friendlyMessage: string;
      
      if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
        friendlyMessage = 'Could not connect to the server. Please check if the server is running.';
      } else if (error.message && !error.message.includes('Failed to delete file')) {
        // Use existing message if it's already user-friendly
        friendlyMessage = error.message;
      } else {
        friendlyMessage = `Failed to delete file. Please try again.`;
      }
      
      console.warn(`[ApiClient] ${friendlyMessage}`);
      throw new Error(friendlyMessage);
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
  fileIds?: string[],
  threadId?: string,
  audioInput?: string,
  audioFormat?: string,
  language?: string,
  returnAudio?: boolean,
  ttsVoice?: string,
  sourceLanguage?: string,
  targetLanguage?: string,
  abortSignal?: AbortSignal
): AsyncGenerator<StreamResponse> {
  if (!defaultClient) {
    throw new Error('API not configured. Please call configureApi() with your server URL before using any API functions.');
  }

  yield* defaultClient.streamChat(
    message,
    stream,
    fileIds,
    threadId,
    audioInput,
    audioFormat,
    language,
    returnAudio,
    ttsVoice,
    sourceLanguage,
    targetLanguage,
    abortSignal
  );
}

/**
 * Stop an active chat stream (legacy function).
 *
 * @param sessionId - Session ID of the stream to stop
 * @param requestId - Request ID of the stream to stop
 * @returns Promise resolving to true if cancelled, false if not found
 */
export async function stopChat(sessionId: string, requestId: string): Promise<boolean> {
  if (!defaultClient) {
    throw new Error('API not configured. Please call configureApi() with your server URL before using any API functions.');
  }

  return defaultClient.stopChat(sessionId, requestId);
}
