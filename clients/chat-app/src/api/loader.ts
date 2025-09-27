/**
 * Dynamic API loader that can load either the npm package or local dist build
 * based on environment variables for testing before publishing
 */

import { getApiPackageVersion } from '../utils/version';

// Check if we should use local API
const useLocalApi = (import.meta.env as any).VITE_USE_LOCAL_API === 'true';
const localApiPath = (import.meta.env as any).VITE_LOCAL_API_PATH || '../node-api/dist';
const debugMode = (import.meta.env as any).VITE_CONSOLE_DEBUG === 'true';

// Type definitions for the API
export interface StreamResponse {
  text: string;
  done: boolean;
}

export interface ApiClient {
  streamChat(message: string, stream?: boolean): AsyncGenerator<StreamResponse>;
  clearConversationHistory?(sessionId?: string): Promise<{
    status: string;
    message: string;
    session_id: string;
    deleted_count: number;
    timestamp: string;
  }>;
  getSessionId(): string | null;
}

export interface ApiFunctions {
  configureApi: (apiUrl: string, apiKey?: string | null, sessionId?: string | null) => void;
  streamChat: (message: string, stream?: boolean) => AsyncGenerator<StreamResponse>;
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
      if (debugMode) console.log(`🔧 Loading local API from: ${localApiPath}`);
      // Load from public directory
      const localApi = await import(/* @vite-ignore */ `${localApiPath}/api.mjs`);
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
