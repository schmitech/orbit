/**
 * Middleware Configuration Utility
 *
 * Provides utilities for working with API middleware mode.
 * When middleware is enabled, adapters are used instead of direct API keys.
 *
 * Adapters are loaded from VITE_ADAPTERS environment variable:
 * - For orbitchat CLI: The server reads VITE_ADAPTERS and exposes /api/adapters endpoint
 * - For static deployments (AWS Amplify): Build-time env var is baked into the bundle
 * - Runtime injection via window.ORBIT_CHAT_CONFIG.adapters is also supported
 */

import { getEnableApiMiddleware } from './runtimeConfig';
import { debugLog, debugError } from './debug';

export interface Adapter {
  name: string;
  apiUrl: string;
}

export interface AdaptersResponse {
  adapters: Adapter[];
}

let adaptersCache: Adapter[] | null = null;

/**
 * Check if API middleware is enabled
 */
export function isMiddlewareEnabled(): boolean {
  return getEnableApiMiddleware();
}

/**
 * Load adapters from environment variable or runtime config
 * Format: JSON array of adapter objects
 * Example: VITE_ADAPTERS='[{"name":"Simple Chat","apiUrl":"https://api.example.com"}]'
 */
function loadAdaptersFromConfig(): Adapter[] | null {
  // First check window.ORBIT_CHAT_CONFIG.adapters (injected at runtime)
  if (typeof window !== 'undefined') {
    const config = (window as any).ORBIT_CHAT_CONFIG;
    if (config?.adapters && Array.isArray(config.adapters)) {
      debugLog('Loading adapters from window.ORBIT_CHAT_CONFIG');
      return config.adapters.map((a: any) => ({
        name: a.name,
        apiUrl: a.apiUrl || 'http://localhost:3000',
      }));
    }
  }

  // Then check VITE_ADAPTERS build-time env var
  const envValue = import.meta.env.VITE_ADAPTERS;
  if (envValue) {
    try {
      const parsed = JSON.parse(envValue);
      if (Array.isArray(parsed)) {
        debugLog('Loading adapters from VITE_ADAPTERS environment variable');
        return parsed
          .filter((a: any) => a.name)
          .map((a: any) => ({
            name: a.name,
            apiUrl: a.apiUrl || 'http://localhost:3000',
          }));
      }
    } catch (error) {
      debugError('Failed to parse VITE_ADAPTERS:', error);
    }
  }

  return null;
}

/**
 * Fetch available adapters from the server or fallback to config
 * Priority:
 * 1. /api/adapters endpoint (for orbitchat CLI middleware mode)
 * 2. VITE_ADAPTERS env var / window.ORBIT_CHAT_CONFIG.adapters (for static deployments)
 */
export async function fetchAdapters(): Promise<Adapter[]> {
  if (adaptersCache) {
    return adaptersCache;
  }

  // Try fetching from /api/adapters endpoint first
  try {
    const response = await fetch('/api/adapters');
    if (response.ok) {
      const data: AdaptersResponse = await response.json();
      adaptersCache = data.adapters;
      debugLog('Fetched adapters from /api/adapters:', adaptersCache);
      return adaptersCache;
    }
  } catch (error) {
    debugLog('Could not fetch from /api/adapters, trying fallback:', error);
  }

  // Fallback to environment variable or runtime config
  const configAdapters = loadAdaptersFromConfig();
  if (configAdapters && configAdapters.length > 0) {
    adaptersCache = configAdapters;
    debugLog('Loaded adapters from config:', adaptersCache);
    return adaptersCache;
  }

  debugError('No adapters available from API or config');
  throw new Error('No adapters available. Configure VITE_ADAPTERS environment variable.');
}

/**
 * Clear the adapters cache (useful for testing or when adapters change)
 */
export function clearAdaptersCache(): void {
  adaptersCache = null;
}

/**
 * Get adapter by name
 */
export async function getAdapter(name: string): Promise<Adapter | null> {
  const adapters = await fetchAdapters();
  return adapters.find(a => a.name === name) || null;
}

