/**
 * Adapter Configuration Utility
 *
 * Provides utilities for working with adapters via the Express proxy.
 *
 * Adapters are loaded from VITE_ADAPTERS environment variable:
 * - For orbitchat CLI: The server reads VITE_ADAPTERS and exposes /api/adapters endpoint
 * - For static deployments (AWS Amplify): Build-time env var is baked into the bundle
 * - Runtime injection via window.ORBIT_CHAT_CONFIG.adapters is also supported
 */

import { debugLog, debugError } from './debug';

export interface Adapter {
  name: string;
  apiUrl?: string;
  description?: string; // Short description for dropdown previews
  notes?: string; // Longer markdown notes/description when available
}

export interface AdaptersResponse {
  adapters: Adapter[];
}

const toTrimmedString = (value: unknown): string | undefined => {
  if (typeof value !== 'string') {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
};

const normalizeAdapter = (input: unknown): Adapter | null => {
  if (!input || typeof input !== 'object') {
    return null;
  }

  const candidate = input as {
    name?: unknown;
    apiUrl?: unknown;
    description?: unknown;
    summary?: unknown;
    notes?: unknown;
  };

  const name = toTrimmedString(candidate.name);
  if (!name) {
    return null;
  }

  const apiUrl = toTrimmedString(candidate.apiUrl);
  const notes = typeof candidate.notes === 'string' ? candidate.notes.trim() : undefined;
  let description =
    toTrimmedString(candidate.description) ||
    toTrimmedString(candidate.summary);

  if (!description && typeof notes === 'string') {
    const firstLine = notes.split(/\r?\n/).find(line => line.trim().length > 0);
    description = firstLine ? firstLine.trim() : undefined;
  }

  const normalized: Adapter = { name };
  if (apiUrl) {
    normalized.apiUrl = apiUrl;
  }
  if (description) {
    normalized.description = description;
  }
  if (notes) {
    normalized.notes = notes;
  }

  return normalized;
};

const normalizeAdapterList = (list: unknown): Adapter[] => {
  if (!Array.isArray(list)) {
    return [];
  }
  return list
    .map(normalizeAdapter)
    .filter((adapter): adapter is Adapter => adapter !== null);
};

let adaptersCache: Adapter[] | null = null;

/**
 * Load adapters from environment variable or runtime config
 * Format: JSON array of adapter objects
 * Example: VITE_ADAPTERS='[{"name":"Simple Chat","apiUrl":"https://api.example.com"}]'
 */
function loadAdaptersFromConfig(): Adapter[] | null {
  // First check window.ORBIT_CHAT_CONFIG.adapters (injected at runtime)
  if (typeof window !== 'undefined') {
    const config = window.ORBIT_CHAT_CONFIG;
    if (config?.adapters && Array.isArray(config.adapters)) {
      debugLog('Loading adapters from window.ORBIT_CHAT_CONFIG');
      const runtimeAdapters = normalizeAdapterList(config.adapters);

      if (runtimeAdapters.length > 0) {
        return runtimeAdapters;
      }
    }
  }

  // Then check VITE_ADAPTERS build-time env var
  const envValue = import.meta.env.VITE_ADAPTERS;
  if (envValue) {
    try {
      const parsed = JSON.parse(envValue);
      if (Array.isArray(parsed)) {
        debugLog('Loading adapters from VITE_ADAPTERS environment variable');
        const parsedAdapters = normalizeAdapterList(parsed);
        if (parsedAdapters.length > 0) {
          return parsedAdapters;
        }
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
      const normalized = normalizeAdapterList(data.adapters);
      if (normalized.length > 0) {
        adaptersCache = normalized;
        debugLog('Fetched adapters from /api/adapters:', adaptersCache);
        return adaptersCache;
      }
      debugLog('/api/adapters response did not contain valid adapters, trying fallback');
    }
    debugLog(`/api/adapters returned ${response.status}, trying fallback`);
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

/**
 * Get the first available adapter (for auto-selection when middleware is enabled)
 */
export async function getFirstAdapter(): Promise<Adapter | null> {
  try {
    const adapters = await fetchAdapters();
    return adapters.length > 0 ? adapters[0] : null;
  } catch {
    return null;
  }
}
