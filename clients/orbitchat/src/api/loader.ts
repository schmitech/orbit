/**
 * API loader — all requests go through the Express proxy with X-Adapter-Name headers.
 */

import { debugLog } from '../utils/debug';
import { getAccessToken } from '../auth/tokenStore';

// Type definitions for the API
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

export interface ConversationHistoryMessage {
  message_id?: string | null;
  role: string;
  content: string;
  timestamp: string | number | Date | null;
  metadata?: Record<string, unknown>;
}

export interface ConversationHistoryResponse {
  session_id: string;
  messages: ConversationHistoryMessage[];
  count: number;
}

export interface ApiClient {
  streamChat(
    message: string,
    stream?: boolean,
    fileIds?: string[],
    threadId?: string,
    audioInput?: string,
    audioFormat?: string,
    language?: string,
    returnAudio?: boolean,
    ttsVoice?: string,
    sourceLanguage?: string,
    targetLanguage?: string
  ): AsyncGenerator<StreamResponse>;
  createThread?(messageId: string, sessionId: string): Promise<{
    thread_id: string;
    thread_session_id: string;
    parent_message_id: string;
    parent_session_id: string;
    adapter_name: string;
    created_at: string;
    expires_at: string;
  }>;
  getThreadInfo?(threadId: string): Promise<{
    thread_id: string;
    thread_session_id: string;
    parent_message_id: string;
    parent_session_id: string;
    adapter_name: string;
    created_at: string;
    expires_at: string;
  }>;
  deleteThread?(threadId: string): Promise<{ status: string; message: string; thread_id: string }>;
  clearConversationHistory?(sessionId?: string): Promise<{
    status: string;
    message: string;
    session_id: string;
    deleted_count: number;
    timestamp: string;
  }>;
  deleteConversationWithFiles?(sessionId?: string, fileIds?: string[]): Promise<{
    status: string;
    message: string;
    session_id: string;
    deleted_messages: number;
    deleted_files: number;
    file_deletion_errors: string[] | null;
    timestamp: string;
  }>;
  getSessionId(): string | null;
  uploadFile?(file: File): Promise<{
    file_id: string;
    filename: string;
    mime_type: string;
    file_size: number;
    status: string;
    chunk_count: number;
    message: string;
  }>;
  listFiles?(): Promise<Array<{
    file_id: string;
    filename: string;
    mime_type: string;
    file_size: number;
    upload_timestamp: string;
    processing_status: string;
    chunk_count: number;
    storage_type: string;
  }>>;
  getFileInfo?(fileId: string): Promise<{
    file_id: string;
    filename: string;
    mime_type: string;
    file_size: number;
    upload_timestamp: string;
    processing_status: string;
    chunk_count: number;
    storage_type: string;
  }>;
  queryFile?(fileId: string, query: string, maxResults?: number): Promise<{
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
  }>;
  deleteFile?(fileId: string): Promise<{ message: string; file_id: string }>;
  validateApiKey?(): Promise<{
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
  }>;
  getAdapterInfo?(): Promise<{
    client_name: string;
    adapter_name: string;
    model: string | null;
    isFileSupported?: boolean;
    notes?: string | null;
  }>;
  getConversationHistory?(sessionId?: string, limit?: number): Promise<ConversationHistoryResponse>;
  stopChat?(sessionId: string, requestId: string): Promise<boolean>;
}

export interface ApiFunctions {
  configureApi: (apiUrl: string, sessionId?: string | null, adapterName?: string | null) => void;
  streamChat: (
    message: string,
    stream?: boolean,
    fileIds?: string[],
    threadId?: string,
    audioInput?: string,
    audioFormat?: string,
    language?: string,
    returnAudio?: boolean,
    ttsVoice?: string,
    sourceLanguage?: string,
    targetLanguage?: string
  ) => AsyncGenerator<StreamResponse>;
  ApiClient: new (config: { apiUrl: string; sessionId?: string | null; adapterName?: string | null }) => ApiClient;
  stopChat?: (sessionId: string, requestId: string) => Promise<boolean>;
}

async function buildHeaders(extra: Record<string, string> = {}): Promise<Record<string, string>> {
  const headers = { ...extra };
  const token = await getAccessToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

// Cache for loaded API
let apiCache: ApiFunctions | null = null;

/**
 * Create API functions that route through the Express proxy
 */
function createProxyApi(): ApiFunctions {
  let sessionId: string | null = null;
  let adapterName: string | null = null;

  const configureApi = (_apiUrl: string, sessId?: string | null, adapter?: string | null) => {
    sessionId = sessId || null;
    adapterName = adapter || null;
  };

  const createProxyClient = (): ApiClient => {
    if (!adapterName) {
      throw new Error('Adapter name is required');
    }

    return {
      async *streamChat(
        message: string,
        stream?: boolean,
        fileIds?: string[],
        threadId?: string,
        audioInput?: string,
        audioFormat?: string,
        language?: string,
        returnAudio?: boolean,
        ttsVoice?: string,
        sourceLanguage?: string,
        targetLanguage?: string
      ): AsyncGenerator<StreamResponse> {
        const requestBody: Record<string, unknown> = {
          messages: [{ role: 'user', content: message }],
          stream: stream !== false,
        };
        if (fileIds && fileIds.length > 0) {
          requestBody.file_ids = fileIds;
        }
        if (threadId) {
          requestBody.thread_id = threadId;
        }
        if (audioInput) requestBody.audio_input = audioInput;
        if (audioFormat) requestBody.audio_format = audioFormat;
        if (language) requestBody.language = language;
        if (returnAudio !== undefined) requestBody.return_audio = returnAudio;
        if (ttsVoice) requestBody.tts_voice = ttsVoice;
        if (sourceLanguage) requestBody.source_language = sourceLanguage;
        if (targetLanguage) requestBody.target_language = targetLanguage;

        const response = await fetch('/api/v1/chat', {
          method: 'POST',
          headers: await buildHeaders({
            'Content-Type': 'application/json',
            'X-Adapter-Name': adapterName!,
            ...(sessionId ? { 'X-Session-ID': sessionId } : {}),
          }),
          body: JSON.stringify(requestBody),
        });

        if (!response.ok) {
          throw new Error(`API request failed: ${response.status} ${response.statusText}`);
        }

        if (response.headers.get('content-type')?.includes('text/event-stream')) {
          const reader = response.body?.getReader();
          const decoder = new TextDecoder();
          let buffer = '';

          if (!reader) {
            throw new Error('Response body is not readable');
          }

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
              if (line.startsWith('data: ')) {
                try {
                  const data = JSON.parse(line.substring(6));

                  if (data.request_id && !data.response && !data.done) {
                    yield {
                      text: '',
                      done: false,
                      request_id: data.request_id
                    };
                    continue;
                  }

                  const responseData: StreamResponse = {
                    text: data.text || data.content || data.message || data.response || '',
                    done: data.done || false,
                    audio: data.audio,
                    audioFormat: data.audio_format || data.audioFormat,
                    audio_chunk: data.audio_chunk,
                    chunk_index: data.chunk_index,
                    threading: data.threading
                  };

                  yield responseData;
                } catch {
                  // Skip invalid JSON
                }
              }
            }
          }

          // Parse remaining buffer
          if (buffer.trim()) {
            const lines = buffer.split('\n');
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                try {
                  const data = JSON.parse(line.substring(6));

                  if (data.request_id && !data.response && !data.done) {
                    yield {
                      text: '',
                      done: false,
                      request_id: data.request_id
                    };
                    continue;
                  }

                  const responseData: StreamResponse = {
                    text: data.text || data.content || data.message || data.response || '',
                    done: data.done || false,
                    audio: data.audio,
                    audioFormat: data.audio_format || data.audioFormat,
                    audio_chunk: data.audio_chunk,
                    chunk_index: data.chunk_index,
                    threading: data.threading
                  };
                  yield responseData;
                } catch {
                  // Skip invalid JSON
                }
              }
            }
          }
        } else {
          // Non-streaming response
          const data = await response.json();
          yield { text: data.message || data.response || '', done: true };
        }
      },

      async createThread(messageId: string, sessId: string) {
        const response = await fetch('/api/threads', {
          method: 'POST',
          headers: await buildHeaders({
            'Content-Type': 'application/json',
            'X-Adapter-Name': adapterName!,
            'X-Session-ID': sessId,
          }),
          body: JSON.stringify({ message_id: messageId, session_id: sessId }),
        });
        if (!response.ok) throw new Error(`Failed to create thread: ${response.statusText}`);
        return response.json();
      },

      async getThreadInfo(threadId: string) {
        const response = await fetch(`/api/threads/${threadId}`, {
          headers: await buildHeaders({
            'X-Adapter-Name': adapterName!,
          }),
        });
        if (!response.ok) throw new Error(`Failed to get thread info: ${response.statusText}`);
        return response.json();
      },

      async deleteThread(threadId: string) {
        const response = await fetch(`/api/threads/${threadId}`, {
          method: 'DELETE',
          headers: await buildHeaders({
            'X-Adapter-Name': adapterName!,
          }),
        });
        if (!response.ok) throw new Error(`Failed to delete thread: ${response.statusText}`);
        return response.json();
      },

      async clearConversationHistory(sessId?: string) {
        const response = await fetch(`/api/admin/chat-history/${sessId || sessionId}`, {
          method: 'DELETE',
          headers: await buildHeaders({
            'X-Adapter-Name': adapterName!,
          }),
        });
        if (!response.ok) throw new Error(`Failed to clear history: ${response.statusText}`);
        return response.json();
      },

      async getConversationHistory(sessId?: string, limit?: number) {
        const targetSession = sessId || sessionId;
        if (!targetSession) {
          throw new Error('No session ID available for conversation history');
        }
        const limitParam =
          typeof limit === 'number' && Number.isFinite(limit) && limit > 0
            ? `?limit=${Math.floor(limit)}`
            : '';
        const response = await fetch(`/api/admin/chat-history/${targetSession}${limitParam}`, {
          headers: await buildHeaders({
            'X-Adapter-Name': adapterName!,
          }),
        });
        if (!response.ok) throw new Error(`Failed to load history: ${response.statusText}`);
        return response.json();
      },

      async deleteConversationWithFiles(sessId?: string, fileIds?: string[]) {
        const targetSession = sessId || sessionId;
        const fileIdsParam = fileIds && fileIds.length > 0 ? `?file_ids=${fileIds.join(',')}` : '';
        const response = await fetch(`/api/admin/conversations/${targetSession}${fileIdsParam}`, {
          method: 'DELETE',
          headers: await buildHeaders({
            'X-Adapter-Name': adapterName!,
          }),
        });
        if (!response.ok) throw new Error(`Failed to delete conversation: ${response.statusText}`);
        return response.json();
      },

      getSessionId: () => sessionId,

      async uploadFile(file: File) {
        const formData = new FormData();
        formData.append('file', file);
        const response = await fetch('/api/files/upload', {
          method: 'POST',
          headers: await buildHeaders({
            'X-Adapter-Name': adapterName!,
          }),
          body: formData,
        });
        if (!response.ok) throw new Error(`Failed to upload file: ${response.statusText}`);
        return response.json();
      },

      async listFiles() {
        const response = await fetch('/api/files', {
          headers: await buildHeaders({
            'X-Adapter-Name': adapterName!,
          }),
        });
        if (!response.ok) throw new Error(`Failed to list files: ${response.statusText}`);
        const data = await response.json();
        return Array.isArray(data) ? data : (data.files || []);
      },

      async getFileInfo(fileId: string) {
        const response = await fetch(`/api/files/${fileId}`, {
          headers: await buildHeaders({
            'X-Adapter-Name': adapterName!,
          }),
        });
        if (!response.ok) throw new Error(`Failed to get file info: ${response.statusText}`);
        return response.json();
      },

      async queryFile(fileId: string, query: string, maxResults?: number) {
        const response = await fetch(`/api/files/${fileId}/query`, {
          method: 'POST',
          headers: await buildHeaders({
            'Content-Type': 'application/json',
            'X-Adapter-Name': adapterName!,
          }),
          body: JSON.stringify({ query, max_results: maxResults }),
        });
        if (!response.ok) throw new Error(`Failed to query file: ${response.statusText}`);
        return response.json();
      },

      async deleteFile(fileId: string) {
        const response = await fetch(`/api/files/${fileId}`, {
          method: 'DELETE',
          headers: await buildHeaders({
            'X-Adapter-Name': adapterName!,
          }),
        });
        if (!response.ok) throw new Error(`Failed to delete file: ${response.statusText}`);
        return response.json();
      },

      async validateApiKey() {
        const response = await fetch(`/api/admin/api-keys/${adapterName}/status`, {
          headers: await buildHeaders({
            'X-Adapter-Name': adapterName!,
          }),
        });
        if (!response.ok) throw new Error(`Failed to validate API key: ${response.statusText}`);
        return response.json();
      },

      async getAdapterInfo() {
        const adapterInfoPath = '/api/admin/adapters/info';
        const parseRetryAfterMs = (retryAfterHeader: string | null): number => {
          if (!retryAfterHeader) return 0;

          const asSeconds = Number(retryAfterHeader);
          if (Number.isFinite(asSeconds) && asSeconds > 0) {
            return Math.min(asSeconds * 1000, 30000);
          }

          const asDateMs = Date.parse(retryAfterHeader);
          if (!Number.isNaN(asDateMs)) {
            const delayMs = asDateMs - Date.now();
            if (delayMs > 0) {
              return Math.min(delayMs, 30000);
            }
          }

          return 0;
        };
        const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
        const requestInfo = async () => fetch(adapterInfoPath, {
          headers: await buildHeaders({
            'X-Adapter-Name': adapterName!,
          }),
        });

        let response = await requestInfo();
        if (response.status === 429) {
          const retryAfterMs = parseRetryAfterMs(response.headers.get('Retry-After'));
          if (retryAfterMs > 0) {
            await sleep(retryAfterMs);
            response = await requestInfo();
          }
        }

        if (!response.ok) {
          const errorText = await response.text();
          const statusLabel = `${response.status} ${response.statusText}`.trim();
          const friendlyMessage =
            response.status === 401
              ? `Adapter info request was unauthorized for '${adapterName}'. Verify the adapter exists and you have access.`
              : `Failed to load adapter info (${statusLabel}) for '${adapterName}'.`;

          console.warn('[ProxyApi] Adapter info request failed', {
            adapter: adapterName,
            status: response.status,
            statusText: response.statusText,
            details: errorText || undefined
          });

          throw new Error(friendlyMessage);
        }
        return response.json();
      },

      async stopChat(sessId: string, requestId: string): Promise<boolean> {
        const response = await fetch('/api/v1/chat/stop', {
          method: 'POST',
          headers: await buildHeaders({
            'Content-Type': 'application/json',
            'X-Adapter-Name': adapterName!,
          }),
          body: JSON.stringify({ session_id: sessId, request_id: requestId }),
        });
        if (!response.ok) {
          console.warn(`[ProxyApi] stopChat failed: ${response.status} ${response.statusText}`);
          return false;
        }
        const result = await response.json();
        return result.status === 'cancelled';
      },
    };
  };

  return {
    configureApi,
    streamChat: async function* (
      message: string,
      stream?: boolean,
      fileIds?: string[],
      threadId?: string,
      audioInput?: string,
      audioFormat?: string,
      language?: string,
      returnAudio?: boolean,
      ttsVoice?: string,
      sourceLanguage?: string,
      targetLanguage?: string
    ): AsyncGenerator<StreamResponse> {
      const client = createProxyClient();
      yield* client.streamChat(
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
        targetLanguage
      );
    },
    stopChat: async (sessionId: string, requestId: string): Promise<boolean> => {
      const client = createProxyClient();
      return client.stopChat!(sessionId, requestId);
    },
    ApiClient: class ProxyApiClient implements ApiClient {
      private client: ApiClient;

      constructor(config: { apiUrl: string; sessionId?: string | null; adapterName?: string | null }) {
        adapterName = config.adapterName || null;
        sessionId = config.sessionId || null;
        this.client = createProxyClient();
      }

      async *streamChat(...args: Parameters<ApiClient['streamChat']>): AsyncGenerator<StreamResponse> {
        yield* this.client.streamChat(...args);
      }

      get createThread() { return this.client.createThread?.bind(this.client); }
      get getThreadInfo() { return this.client.getThreadInfo?.bind(this.client); }
      get deleteThread() { return this.client.deleteThread?.bind(this.client); }
      get clearConversationHistory() { return this.client.clearConversationHistory?.bind(this.client); }
      get getConversationHistory() { return this.client.getConversationHistory?.bind(this.client); }
      get deleteConversationWithFiles() { return this.client.deleteConversationWithFiles?.bind(this.client); }
      get getSessionId() { return this.client.getSessionId?.bind(this.client); }
      get uploadFile() { return this.client.uploadFile?.bind(this.client); }
      get listFiles() { return this.client.listFiles?.bind(this.client); }
      get getFileInfo() { return this.client.getFileInfo?.bind(this.client); }
      get queryFile() { return this.client.queryFile?.bind(this.client); }
      get deleteFile() { return this.client.deleteFile?.bind(this.client); }
      get validateApiKey() { return this.client.validateApiKey?.bind(this.client); }
      get getAdapterInfo() { return this.client.getAdapterInfo?.bind(this.client); }
      get stopChat() { return this.client.stopChat?.bind(this.client); }
    },
  };
}

/**
 * Load the API (always uses the Express proxy)
 */
export async function loadApi(): Promise<ApiFunctions> {
  if (apiCache) {
    return apiCache;
  }

  debugLog('Loading API via Express proxy');
  apiCache = createProxyApi();
  debugLog('API loaded successfully');

  return apiCache;
}

/**
 * Get the loaded API functions
 */
export async function getApi(): Promise<ApiFunctions> {
  return await loadApi();
}

/**
 * Clear the API cache (useful for testing)
 */
export function clearApiCache(): void {
  apiCache = null;
}
