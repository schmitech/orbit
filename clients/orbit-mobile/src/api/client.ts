import { ApiClient } from './orbitApi';
import { getConfig } from '../config/env';

export type { StreamResponse } from './orbitApi';
export { ApiClient } from './orbitApi';

let clientInstance: ApiClient | null = null;

export function getApiClient(): ApiClient {
  if (!clientInstance) {
    const config = getConfig();
    clientInstance = new ApiClient({
      apiUrl: config.orbitHost,
      apiKey: config.apiKey,
    });
  }
  return clientInstance;
}

export function resetApiClient(): void {
  clientInstance = null;
}
