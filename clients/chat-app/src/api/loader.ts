/**
 * Dynamic API loader that can load either the npm package or local dist build
 * based on runtime configuration for testing before publishing
 */

import { getApiPackageVersion } from '../utils/version';
import { debugLog, debugError } from '../utils/debug';
import { getUseLocalApi, getLocalApiPath, getEnableApiMiddleware } from '../utils/runtimeConfig';

// Type definitions for the API
export interface StreamResponse {
  text: string;
  done: boolean;
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
  }>;
}

export interface ApiFunctions {
  configureApi: (apiUrl: string, apiKey?: string | null, sessionId?: string | null, adapterName?: string | null) => void;
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
  ApiClient: new (config: { apiUrl: string; apiKey?: string | null; sessionId?: string | null; adapterName?: string | null }) => ApiClient;
}

type LocalApiModule = {
  configureApi: ApiFunctions['configureApi'];
  streamChat: ApiFunctions['streamChat'];
  ApiClient: ApiFunctions['ApiClient'];
};

// Cache for loaded API
let apiCache: ApiFunctions | null = null;

// Middleware state
let middlewareAdapterName: string | null = null;
let middlewareApiUrl: string | null = null;

/**
 * Create middleware-aware API functions that route through proxy
 */
function createMiddlewareApi(baseApi: LocalApiModule): ApiFunctions {
  let sessionId: string | null = null;
  let adapterName: string | null = null;

  const configureApi = (apiUrl: string, apiKey?: string | null, sessId?: string | null, adapter?: string | null) => {
    sessionId = sessId || null;
    adapterName = adapter || null;
    middlewareAdapterName = adapterName;
    middlewareApiUrl = apiUrl;
    // In middleware mode, we don't configure the base API with the actual key
    // The proxy will handle it
  };

  const createMiddlewareClient = (): ApiClient => {
    if (!adapterName) {
      throw new Error('Adapter name is required when middleware is enabled');
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
        const response = await fetch('/api/proxy/v1/chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Adapter-Name': adapterName!,
            ...(sessionId ? { 'X-Session-ID': sessionId } : {}),
            ...(threadId ? { 'X-Thread-ID': threadId } : {}),
          },
          body: JSON.stringify({
            messages: [{ role: 'user', content: message }],
            stream: stream !== false,
            file_ids: fileIds,
            audio_input: audioInput,
            audio_format: audioFormat,
            language,
            return_audio: returnAudio,
            tts_voice: ttsVoice,
            source_language: sourceLanguage,
            target_language: targetLanguage,
          }),
        });

        if (!response.ok) {
          throw new Error(`API request failed: ${response.status} ${response.statusText}`);
        }

        if (response.headers.get('content-type')?.includes('text/event-stream')) {
          // Handle SSE streaming
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
                  
                  // Handle different response formats - check for text, content, message, or response fields
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
                } catch (e) {
                  // Skip invalid JSON
                }
              }
            }
          }
          
          // If we have remaining buffer, try to parse it
          if (buffer.trim()) {
            const lines = buffer.split('\n');
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                try {
                  const data = JSON.parse(line.substring(6));
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
                } catch (e) {
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
        const response = await fetch('/api/proxy/api/threads', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Adapter-Name': adapterName!,
            'X-Session-ID': sessId,
          },
          body: JSON.stringify({ message_id: messageId, session_id: sessId }),
        });
        if (!response.ok) throw new Error(`Failed to create thread: ${response.statusText}`);
        return response.json();
      },

      async getThreadInfo(threadId: string) {
        const response = await fetch(`/api/proxy/api/threads/${threadId}`, {
          headers: {
            'X-Adapter-Name': adapterName!,
          },
        });
        if (!response.ok) throw new Error(`Failed to get thread info: ${response.statusText}`);
        return response.json();
      },

      async deleteThread(threadId: string) {
        const response = await fetch(`/api/proxy/api/threads/${threadId}`, {
          method: 'DELETE',
          headers: {
            'X-Adapter-Name': adapterName!,
          },
        });
        if (!response.ok) throw new Error(`Failed to delete thread: ${response.statusText}`);
        return response.json();
      },

      async clearConversationHistory(sessId?: string) {
        const response = await fetch(`/api/proxy/admin/chat-history/${sessId || sessionId}`, {
          method: 'DELETE',
          headers: {
            'X-Adapter-Name': adapterName!,
          },
        });
        if (!response.ok) throw new Error(`Failed to clear history: ${response.statusText}`);
        return response.json();
      },

      async deleteConversationWithFiles(sessId?: string, fileIds?: string[]) {
        const response = await fetch(`/api/proxy/admin/conversations/${sessId || sessionId}`, {
          method: 'DELETE',
          headers: {
            'Content-Type': 'application/json',
            'X-Adapter-Name': adapterName!,
          },
          body: JSON.stringify({ file_ids: fileIds }),
        });
        if (!response.ok) throw new Error(`Failed to delete conversation: ${response.statusText}`);
        return response.json();
      },

      getSessionId: () => sessionId,

      async uploadFile(file: File) {
        const formData = new FormData();
        formData.append('file', file);
        const response = await fetch('/api/proxy/api/files/upload', {
          method: 'POST',
          headers: {
            'X-Adapter-Name': adapterName!,
          },
          body: formData,
        });
        if (!response.ok) throw new Error(`Failed to upload file: ${response.statusText}`);
        return response.json();
      },

      async listFiles() {
        const response = await fetch('/api/proxy/api/files', {
          headers: {
            'X-Adapter-Name': adapterName!,
          },
        });
        if (!response.ok) throw new Error(`Failed to list files: ${response.statusText}`);
        return response.json();
      },

      async getFileInfo(fileId: string) {
        const response = await fetch(`/api/proxy/api/files/${fileId}`, {
          headers: {
            'X-Adapter-Name': adapterName!,
          },
        });
        if (!response.ok) throw new Error(`Failed to get file info: ${response.statusText}`);
        return response.json();
      },

      async queryFile(fileId: string, query: string, maxResults?: number) {
        const response = await fetch(`/api/proxy/api/files/${fileId}/query`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Adapter-Name': adapterName!,
          },
          body: JSON.stringify({ query, max_results: maxResults }),
        });
        if (!response.ok) throw new Error(`Failed to query file: ${response.statusText}`);
        return response.json();
      },

      async deleteFile(fileId: string) {
        const response = await fetch(`/api/proxy/api/files/${fileId}`, {
          method: 'DELETE',
          headers: {
            'X-Adapter-Name': adapterName!,
          },
        });
        if (!response.ok) throw new Error(`Failed to delete file: ${response.statusText}`);
        return response.json();
      },

      async validateApiKey() {
        const response = await fetch(`/api/proxy/admin/api-keys/${adapterName}/status`, {
          headers: {
            'X-Adapter-Name': adapterName!,
          },
        });
        if (!response.ok) throw new Error(`Failed to validate API key: ${response.statusText}`);
        return response.json();
      },

      async getAdapterInfo() {
        const response = await fetch('/api/proxy/admin/api-keys/info', {
          headers: {
            'X-Adapter-Name': adapterName!,
          },
        });
        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`Failed to get adapter info: ${response.status} ${response.statusText} - ${errorText}`);
        }
        return response.json();
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
      const client = createMiddlewareClient();
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
    ApiClient: class MiddlewareApiClient implements ApiClient {
      private client: ApiClient;

      constructor(config: { apiUrl: string; apiKey?: string | null; sessionId?: string | null; adapterName?: string | null }) {
        adapterName = config.adapterName || null;
        sessionId = config.sessionId || null;
        middlewareAdapterName = adapterName;
        middlewareApiUrl = config.apiUrl;
        this.client = createMiddlewareClient();
      }

      async *streamChat(...args: Parameters<ApiClient['streamChat']>): AsyncGenerator<StreamResponse> {
        yield* this.client.streamChat(...args);
      }

      get createThread() { return this.client.createThread?.bind(this.client); }
      get getThreadInfo() { return this.client.getThreadInfo?.bind(this.client); }
      get deleteThread() { return this.client.deleteThread?.bind(this.client); }
      get clearConversationHistory() { return this.client.clearConversationHistory?.bind(this.client); }
      get deleteConversationWithFiles() { return this.client.deleteConversationWithFiles?.bind(this.client); }
      get getSessionId() { return this.client.getSessionId?.bind(this.client); }
      get uploadFile() { return this.client.uploadFile?.bind(this.client); }
      get listFiles() { return this.client.listFiles?.bind(this.client); }
      get getFileInfo() { return this.client.getFileInfo?.bind(this.client); }
      get queryFile() { return this.client.queryFile?.bind(this.client); }
      get deleteFile() { return this.client.deleteFile?.bind(this.client); }
      get validateApiKey() { return this.client.validateApiKey?.bind(this.client); }
      get getAdapterInfo() { return this.client.getAdapterInfo?.bind(this.client); }
    },
  };
}

/**
 * Import local API module with proper handling for aliases and relative paths
 */
async function importLocalApiModule(apiPath: string): Promise<LocalApiModule> {
  // When using alias, don't use @vite-ignore so Vite can resolve it
  // The alias is configured in vite.config.ts when VITE_USE_LOCAL_API=true
  if (apiPath === '@local-node-api/api.mjs') {
    // @ts-ignore - alias resolved by Vite at build/runtime
    return import('@local-node-api/api.mjs');
  }
  
  // For relative paths, use @vite-ignore to suppress Vite's static analysis warning
  // @ts-ignore - dynamic import path resolved at runtime
  return import(/* @vite-ignore */ apiPath);
}

/**
 * Dynamically loads the API based on environment configuration
 */
export async function loadApi(): Promise<ApiFunctions> {
  if (apiCache) {
    return apiCache;
  }

  // Get configuration outside try block so it's accessible in catch block
  const useLocalApi = getUseLocalApi();
  const localApiPath = getLocalApiPath();
  const enableMiddleware = getEnableApiMiddleware();

  try {
    if (useLocalApi) {
      // Determine the correct path for loading
      // Default to using Vite alias @local-node-api
      let apiPath: string;
      if (localApiPath) {
        // If a custom path is provided, use it (must be a relative path that Vite can resolve)
        if (localApiPath.startsWith('/')) {
          // Absolute path - convert to relative from src
          const hasAlias = (import.meta.env as any).VITE_USE_LOCAL_API === 'true';
          apiPath = localApiPath.startsWith('/src/')
            ? `.${localApiPath.substring(4)}${localApiPath.endsWith('.mjs') ? '' : '/api.mjs'}`
            : hasAlias ? '@local-node-api/api.mjs' : '../../../node-api/dist/api.mjs';
        } else if (localApiPath.startsWith('../') || localApiPath.startsWith('./')) {
          // Relative path - use as-is, appending /api.mjs if needed
          apiPath = localApiPath.endsWith('.mjs') ? localApiPath : `${localApiPath}/api.mjs`;
        } else {
          // Treat as path relative to current file
          apiPath = `./${localApiPath}${localApiPath.endsWith('.mjs') ? '' : '/api.mjs'}`;
        }
      } else {
        // Default: use Vite alias @local-node-api when VITE_USE_LOCAL_API=true
        // The alias is configured in vite.config.ts when VITE_USE_LOCAL_API=true
        // Check if we're in a context where the alias should be available
        const hasAlias = (import.meta.env as any).VITE_USE_LOCAL_API === 'true';
        if (hasAlias) {
          // Use alias - it's configured in vite.config.ts
          apiPath = '@local-node-api/api.mjs';
        } else {
          // Fallback to relative path (shouldn't happen if useLocalApi is true)
          // This path resolves to clients/node-api/dist/api.mjs from src/api/loader.ts
          apiPath = '../../../node-api/dist/api.mjs';
        }
      }
      
      debugLog(`🔧 Loading local API from: ${apiPath}`);
      // Load from src directory (can be imported by Vite)
      const localApi = await importLocalApiModule(apiPath);
      
      if (enableMiddleware) {
        debugLog('🔐 API Middleware enabled - routing through proxy');
        apiCache = createMiddlewareApi(localApi);
      } else {
        apiCache = {
          configureApi: localApi.configureApi,
          streamChat: localApi.streamChat,
          ApiClient: localApi.ApiClient
        };
      }
      debugLog('✅ Local API loaded successfully');
    } else {
      debugLog('📦 Loading npm package API');
      // @ts-ignore - Dynamic import that may not be available at compile time
      const npmApi = await import('@schmitech/chatbot-api');
      
      // Create a wrapper for streamChat to match our interface signature
      const streamChatWrapper = async function* (
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
        // Call npm package's streamChat with all parameters (same signature as local API)
        yield* npmApi.streamChat(
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
      };
      
      // Create a wrapper class for ApiClient to fix streamChat signature
      class ApiClientWrapper implements ApiClient {
        private client: any;
        
        constructor(config: { apiUrl: string; apiKey?: string | null; sessionId?: string | null; adapterName?: string | null }) {
          if (enableMiddleware && config.adapterName) {
            // In middleware mode, create a middleware client instead
            const middlewareApi = createMiddlewareApi(npmApi as any);
            this.client = new middlewareApi.ApiClient(config);
          } else {
            this.client = new npmApi.ApiClient(config);
          }
        }
        
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
          // Call npm package's streamChat with all parameters (same signature as local API)
          yield* this.client.streamChat(
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
        }
        
        get createThread() { return this.client.createThread?.bind(this.client); }
        get getThreadInfo() { return this.client.getThreadInfo?.bind(this.client); }
        get deleteThread() { return this.client.deleteThread?.bind(this.client); }
        get clearConversationHistory() { return this.client.clearConversationHistory?.bind(this.client); }
        get deleteConversationWithFiles() { return this.client.deleteConversationWithFiles?.bind(this.client); }
        get getSessionId() { return this.client.getSessionId?.bind(this.client); }
        get uploadFile() { return this.client.uploadFile?.bind(this.client); }
        get listFiles() { return this.client.listFiles?.bind(this.client); }
        get getFileInfo() { return this.client.getFileInfo?.bind(this.client); }
        get queryFile() { return this.client.queryFile?.bind(this.client); }
        get deleteFile() { return this.client.deleteFile?.bind(this.client); }
        get validateApiKey() { return this.client.validateApiKey?.bind(this.client); }
        get getAdapterInfo() { return this.client.getAdapterInfo?.bind(this.client); }
      }
      
      if (enableMiddleware) {
        debugLog('🔐 API Middleware enabled - routing through proxy');
        apiCache = createMiddlewareApi(npmApi as any);
      } else {
        apiCache = {
          configureApi: npmApi.configureApi,
          streamChat: streamChatWrapper,
          ApiClient: ApiClientWrapper
        };
      }
      const apiVersion = await getApiPackageVersion();
      debugLog(`✅ NPM package API loaded successfully (v${apiVersion})`);
    }
  } catch (error) {
    debugError('❌ Failed to load API:', error);

    // Fallback to npm package if local loading fails
    if (useLocalApi) {
      debugLog('🔄 Falling back to npm package...');
      try {
        // @ts-ignore - Dynamic import that may not be available at compile time
        const npmApi = await import('@schmitech/chatbot-api');
        
        // Create a wrapper for streamChat to match our interface signature
        const streamChatWrapper = async function* (
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
          // Call npm package's streamChat with all parameters (same signature as local API)
          yield* npmApi.streamChat(
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
        };
        
        // Create a wrapper class for ApiClient to fix streamChat signature
        class ApiClientWrapper implements ApiClient {
          private client: any;
          
          constructor(config: { apiUrl: string; apiKey?: string | null; sessionId?: string | null; adapterName?: string | null }) {
            if (enableMiddleware && config.adapterName) {
              // In middleware mode, create a middleware client instead
              const middlewareApi = createMiddlewareApi(npmApi as any);
              this.client = new middlewareApi.ApiClient(config);
            } else {
              this.client = new npmApi.ApiClient(config);
            }
          }
          
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
            // Call npm package's streamChat with all parameters (same signature as local API)
            yield* this.client.streamChat(
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
          }
          
          get createThread() { return this.client.createThread?.bind(this.client); }
          get getThreadInfo() { return this.client.getThreadInfo?.bind(this.client); }
          get deleteThread() { return this.client.deleteThread?.bind(this.client); }
          get clearConversationHistory() { return this.client.clearConversationHistory?.bind(this.client); }
          get deleteConversationWithFiles() { return this.client.deleteConversationWithFiles?.bind(this.client); }
          get getSessionId() { return this.client.getSessionId?.bind(this.client); }
          get uploadFile() { return this.client.uploadFile?.bind(this.client); }
          get listFiles() { return this.client.listFiles?.bind(this.client); }
          get getFileInfo() { return this.client.getFileInfo?.bind(this.client); }
          get queryFile() { return this.client.queryFile?.bind(this.client); }
          get deleteFile() { return this.client.deleteFile?.bind(this.client); }
          get validateApiKey() { return this.client.validateApiKey?.bind(this.client); }
          get getAdapterInfo() { return this.client.getAdapterInfo?.bind(this.client); }
        }
        
        if (enableMiddleware) {
          debugLog('🔐 API Middleware enabled - routing through proxy');
          apiCache = createMiddlewareApi(npmApi as any);
        } else {
          apiCache = {
            configureApi: npmApi.configureApi,
            streamChat: streamChatWrapper,
            ApiClient: ApiClientWrapper
          };
        }
        const apiVersion = await getApiPackageVersion();
        debugLog(`✅ Fallback to NPM package successful (v${apiVersion})`);
      } catch (fallbackError) {
        debugError('❌ Fallback to NPM package also failed:', fallbackError);
        throw new Error('Failed to load both local and npm API packages');
      }
    } else {
      throw error;
    }
  }

  return apiCache!;
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
