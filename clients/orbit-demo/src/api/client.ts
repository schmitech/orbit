import { ApiClient } from '@schmitech/chatbot-api';
import { getStoredConnection } from '../config/connection';

let clientInstance: ApiClient | null = null;

export function getApiClient(): ApiClient | null {
  const config = getStoredConnection();
  if (!config?.apiUrl) return null;
  if (!clientInstance) {
    clientInstance = new ApiClient({
      apiUrl: config.apiUrl,
      apiKey: config.apiKey || undefined,
    });
  }
  return clientInstance;
}

export function setApiClientFromConfig(apiUrl: string, apiKey: string): ApiClient {
  clientInstance = new ApiClient({ apiUrl: apiUrl.trim(), apiKey: apiKey || undefined });
  return clientInstance;
}

export function resetApiClient(): void {
  clientInstance = null;
}

export type { ApiClient } from '@schmitech/chatbot-api';
