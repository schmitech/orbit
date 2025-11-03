/**
 * Dynamic API loader that can load either the npm package or local dist build
 * based on environment variables for testing before publishing
 */

import { getApiPackageVersion } from '../utils/version';

// Check if we should use local API
const useLocalApi = (import.meta.env as any).VITE_USE_LOCAL_API === 'true';
// Vite serves files from public/ directory at root path
// So /api.mjs maps to public/api.mjs
// If VITE_LOCAL_API_PATH is not set, use /api.mjs (public directory)
// If VITE_LOCAL_API_PATH is set, use it as-is (must be a path Vite can serve)
const localApiPath = (import.meta.env as any).VITE_LOCAL_API_PATH;
const debugMode = (import.meta.env as any).VITE_CONSOLE_DEBUG === 'true';

// Type definitions for the API
export interface StreamResponse {
  text: string;
  done: boolean;
}

export interface ApiClient {
  streamChat(message: string, stream?: boolean, fileIds?: string[]): AsyncGenerator<StreamResponse>;
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
}

export interface ApiFunctions {
  configureApi: (apiUrl: string, apiKey?: string | null, sessionId?: string | null) => void;
  streamChat: (message: string, stream?: boolean, fileIds?: string[]) => AsyncGenerator<StreamResponse>;
  ApiClient: new (config: { apiUrl: string; apiKey?: string | null; sessionId?: string | null }) => ApiClient;
}

// Cache for loaded API
let apiCache: ApiFunctions | null = null;

/**
 * Dynamically loads the API based on environment configuration
 */
export async function loadApi(): Promise<ApiFunctions> {
  if (apiCache) {
    return apiCache;
  }

  try {
    if (useLocalApi) {
      // Determine the correct path for loading
      // Files should be in src/api/local/ directory (not public/) to be importable by Vite
      // If VITE_LOCAL_API_PATH is set, use it; otherwise default to local directory
      let apiPath: string;
      if (localApiPath) {
        // If a custom path is provided, use it (must be a relative path that Vite can resolve)
        if (localApiPath.startsWith('/')) {
          // Absolute path - convert to relative from src
          apiPath = localApiPath.startsWith('/src/') 
            ? `.${localApiPath.substring(4)}${localApiPath.endsWith('.mjs') ? '' : '/api.mjs'}`
            : `./local/api.mjs`;
        } else if (localApiPath.startsWith('../') || localApiPath.startsWith('./')) {
          // Relative path - if it's ../node-api/dist, use local directory instead
          if (localApiPath.includes('node-api/dist')) {
            apiPath = './local/api.mjs';
          } else {
            apiPath = localApiPath.endsWith('.mjs') ? localApiPath : `${localApiPath}/api.mjs`;
          }
        } else {
          // Treat as path relative to current file
          apiPath = `./${localApiPath}${localApiPath.endsWith('.mjs') ? '' : '/api.mjs'}`;
        }
      } else {
        // Default: use local directory (src/api/local/api.mjs)
        apiPath = './local/api.mjs';
      }
      
      if (debugMode) console.log(`🔧 Loading local API from: ${apiPath}`);
      // Load from src directory (can be imported by Vite)
      const localApi = await import(/* @vite-ignore */ apiPath);
      apiCache = {
        configureApi: localApi.configureApi,
        streamChat: localApi.streamChat,
        ApiClient: localApi.ApiClient
      };
      if (debugMode) console.log('✅ Local API loaded successfully');
    } else {
      if (debugMode) console.log('📦 Loading npm package API');
      // @ts-ignore - Dynamic import that may not be available at compile time
      const npmApi = await import('@schmitech/chatbot-api');
      apiCache = {
        configureApi: npmApi.configureApi,
        streamChat: npmApi.streamChat,
        ApiClient: npmApi.ApiClient
      };
      if (debugMode) {
        const apiVersion = await getApiPackageVersion();
        console.log(`✅ NPM package API loaded successfully (v${apiVersion})`);
      }
    }
  } catch (error) {
    if (debugMode) console.error('❌ Failed to load API:', error);

    // Fallback to npm package if local loading fails
    if (useLocalApi) {
      if (debugMode) console.log('🔄 Falling back to npm package...');
      try {
        // @ts-ignore - Dynamic import that may not be available at compile time
        const npmApi = await import('@schmitech/chatbot-api');
        apiCache = {
          configureApi: npmApi.configureApi,
          streamChat: npmApi.streamChat,
          ApiClient: npmApi.ApiClient
        };
        if (debugMode) {
          const apiVersion = await getApiPackageVersion();
          console.log(`✅ Fallback to NPM package successful (v${apiVersion})`);
        }
      } catch (fallbackError) {
        if (debugMode) console.error('❌ Fallback to NPM package also failed:', fallbackError);
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
