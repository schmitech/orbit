/**
 * Dynamic API loader that can load either the npm package or local dist build
 * based on runtime configuration for testing before publishing
 */

import { getApiPackageVersion } from '../utils/version';
import { debugLog, debugError } from '../utils/debug';
import { getUseLocalApi, getLocalApiPath } from '../utils/runtimeConfig';

// Type definitions for the API
export interface StreamResponse {
  text: string;
  done: boolean;
  audio?: string;  // Optional base64-encoded audio data (TTS response) - full audio
  audioFormat?: string;  // Audio format (mp3, wav, etc.)
  audio_chunk?: string;  // Optional streaming audio chunk (base64-encoded)
  chunk_index?: number;  // Index of the audio chunk for ordering
}

export interface ApiClient {
  streamChat(
    message: string, 
    stream?: boolean, 
    fileIds?: string[],
    audioInput?: string,
    audioFormat?: string,
    language?: string,
    returnAudio?: boolean,
    ttsVoice?: string,
    sourceLanguage?: string,
    targetLanguage?: string
  ): AsyncGenerator<StreamResponse>;
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
  configureApi: (apiUrl: string, apiKey?: string | null, sessionId?: string | null) => void;
  streamChat: (
    message: string, 
    stream?: boolean, 
    fileIds?: string[],
    audioInput?: string,
    audioFormat?: string,
    language?: string,
    returnAudio?: boolean,
    ttsVoice?: string,
    sourceLanguage?: string,
    targetLanguage?: string
  ) => AsyncGenerator<StreamResponse>;
  ApiClient: new (config: { apiUrl: string; apiKey?: string | null; sessionId?: string | null }) => ApiClient;
}

type LocalApiModule = {
  configureApi: ApiFunctions['configureApi'];
  streamChat: ApiFunctions['streamChat'];
  ApiClient: ApiFunctions['ApiClient'];
};

// Cache for loaded API
let apiCache: ApiFunctions | null = null;

/**
 * Ensure Vite can resolve aliases by avoiding @vite-ignore when we use them.
 */
async function importLocalApiModule(apiPath: string): Promise<LocalApiModule> {
  if (apiPath === '@local-node-api/api.mjs') {
    // @ts-ignore - resolved at build time via Vite alias
    return import('@local-node-api/api.mjs');
  }
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

  try {
    if (useLocalApi) {
      // Determine the correct path for loading
      // Default to using Vite alias @local-node-api
      let apiPath: string;
      if (localApiPath) {
        // If a custom path is provided, use it (must be a relative path that Vite can resolve)
        if (localApiPath.startsWith('/')) {
          // Absolute path - convert to relative from src
          apiPath = localApiPath.startsWith('/src/')
            ? `.${localApiPath.substring(4)}${localApiPath.endsWith('.mjs') ? '' : '/api.mjs'}`
            : '@local-node-api/api.mjs';
        } else if (localApiPath.startsWith('../') || localApiPath.startsWith('./')) {
          // Relative path - use as-is, appending /api.mjs if needed
          apiPath = localApiPath.endsWith('.mjs') ? localApiPath : `${localApiPath}/api.mjs`;
        } else {
          // Treat as path relative to current file
          apiPath = `./${localApiPath}${localApiPath.endsWith('.mjs') ? '' : '/api.mjs'}`;
        }
      } else {
        // Default: use Vite alias @local-node-api (configured in vite.config.ts)
        // This resolves to clients/node-api/dist
        apiPath = '@local-node-api/api.mjs';
      }
      
      debugLog(`🔧 Loading local API from: ${apiPath}`);
      // Load from src directory (can be imported by Vite)
      const localApi = await importLocalApiModule(apiPath);
      apiCache = {
        configureApi: localApi.configureApi,
        streamChat: localApi.streamChat,
        ApiClient: localApi.ApiClient
      };
      debugLog('✅ Local API loaded successfully');
    } else {
      debugLog('📦 Loading npm package API');
      // @ts-ignore - Dynamic import that may not be available at compile time
      const npmApi = await import('@schmitech/chatbot-api');
      apiCache = {
        configureApi: npmApi.configureApi,
        streamChat: npmApi.streamChat,
        ApiClient: npmApi.ApiClient
      };
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
        apiCache = {
          configureApi: npmApi.configureApi,
          streamChat: npmApi.streamChat,
          ApiClient: npmApi.ApiClient
        };
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
