const STORAGE_KEY_URL = 'orbit-demo-api-url';
const STORAGE_KEY_API_KEY = 'orbit-demo-api-key';

export interface ConnectionConfig {
  apiUrl: string;
  apiKey: string;
}

export function getStoredConnection(): ConnectionConfig | null {
  try {
    const url = localStorage.getItem(STORAGE_KEY_URL);
    const apiKey = localStorage.getItem(STORAGE_KEY_API_KEY);
    if (url && url.trim()) {
      return { apiUrl: url.trim(), apiKey: apiKey ?? '' };
    }
  } catch {
    // ignore
  }
  return null;
}

export function saveConnection(config: ConnectionConfig): void {
  localStorage.setItem(STORAGE_KEY_URL, config.apiUrl.trim());
  localStorage.setItem(STORAGE_KEY_API_KEY, config.apiKey);
}

export function clearConnection(): void {
  localStorage.removeItem(STORAGE_KEY_URL);
  localStorage.removeItem(STORAGE_KEY_API_KEY);
}
