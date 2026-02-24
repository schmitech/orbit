/**
 * Adapter Configuration Utility
 *
 * Provides utilities for working with adapters via the Express proxy.
 *
 * Adapters are loaded from:
 * - /api/adapters endpoint (CLI or Vite dev server proxy)
 * - window.ORBIT_CHAT_CONFIG.adapters (runtime injection)
 */

import { debugLog, debugError } from './debug';

export interface Adapter {
  id: string;
  name: string;
  apiUrl?: string;
  description?: string; // Short description for dropdown previews
  notes?: string; // Longer markdown notes/description when available
  model?: string; // Optional model label from /api/adapters
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
    id?: unknown;
    name?: unknown;
    apiUrl?: unknown;
    description?: unknown;
    summary?: unknown;
    notes?: unknown;
    model?: unknown;
  };

  const name = toTrimmedString(candidate.name);
  if (!name) {
    return null;
  }

  const id = toTrimmedString(candidate.id);
  if (!id) {
    console.warn(`[middlewareConfig] Adapter "${name}" is missing a required 'id' field — skipping.`);
    return null;
  }

  const apiUrl = toTrimmedString(candidate.apiUrl);
  const model = toTrimmedString(candidate.model);
  const notes = typeof candidate.notes === 'string' ? candidate.notes.trim() : undefined;
  let description =
    toTrimmedString(candidate.description) ||
    toTrimmedString(candidate.summary);

  if (!description && typeof notes === 'string') {
    const firstLine = notes.split(/\r?\n/).find(line => line.trim().length > 0);
    description = firstLine ? firstLine.trim() : undefined;
  }

  const normalized: Adapter = { id, name };
  if (apiUrl) {
    normalized.apiUrl = apiUrl;
  }
  if (description) {
    normalized.description = description;
  }
  if (notes) {
    normalized.notes = notes;
  }
  if (model) {
    normalized.model = model;
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
let adaptersCacheAt = 0;
const ADAPTERS_CACHE_TTL_MS = 30000;

/**
 * Load adapters from environment variable or runtime config
 * Uses VITE_ADAPTER_KEYS (JSON object: {"Name": "Key"}) for secrets.
 */
function loadAdaptersFromConfig(): Adapter[] | null {
  // First check window.ORBIT_CHAT_CONFIG.adapters (injected at runtime)
  if (typeof window !== 'undefined') {
    const config = window.ORBIT_CHAT_CONFIG;
    if (config?.adapters && Array.isArray(config.adapters)) {
      debugLog('Loading adapters from window.ORBIT_CHAT_CONFIG');
      const runtimeAdapters = normalizeAdapterList(config.adapters);
      if (runtimeAdapters.length === 0) {
        return null;
      }

      // Strict mode: only expose YAML adapters that have a matching configured key.
      const rawEnvKeys = import.meta.env.VITE_ADAPTER_KEYS;
      if (!rawEnvKeys || !rawEnvKeys.trim()) {
        return [];
      }

      try {
        const parsed = JSON.parse(rawEnvKeys) as Record<string, unknown>;
        const configuredIds = new Set(
          Object.entries(parsed)
            .filter(([, value]) => {
              if (typeof value === 'string') {
                return value.trim().length > 0;
              }
              if (value && typeof value === 'object') {
                const asObj = value as { apiKey?: unknown; key?: unknown };
                if (typeof asObj.apiKey === 'string' && asObj.apiKey.trim().length > 0) return true;
                if (typeof asObj.key === 'string' && asObj.key.trim().length > 0) return true;
              }
              return false;
            })
            .map(([id]) => id)
        );
        return runtimeAdapters.filter(adapter => configuredIds.has(adapter.id));
      } catch {
        return [];
      }
    }
  }

  // VITE_ADAPTER_KEYS is handled by the Vite plugin / CLI.
  return null;
}

/**
 * Fetch available adapters from the server or fallback to config
 * Priority:
 * 1. /api/adapters endpoint (for orbitchat CLI middleware mode)
 * 2. window.ORBIT_CHAT_CONFIG.adapters filtered by VITE_ADAPTER_KEYS (for static deployments)
 */
export async function fetchAdapters(): Promise<Adapter[]> {
  if (adaptersCache && (Date.now() - adaptersCacheAt) < ADAPTERS_CACHE_TTL_MS) {
    return adaptersCache;
  }

  // Try fetching from /api/adapters endpoint first
  try {
    const response = await fetch('/api/adapters?refresh=1', {
      cache: 'no-store',
      headers: {
        'Cache-Control': 'no-cache',
      },
    });
    if (response.ok) {
      const data: AdaptersResponse = await response.json();
      const normalized = normalizeAdapterList(data.adapters);
      if (normalized.length > 0) {
        adaptersCache = normalized;
        adaptersCacheAt = Date.now();
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
    adaptersCacheAt = Date.now();
    debugLog('Loaded adapters from config:', adaptersCache);
    return adaptersCache;
  }

  debugError('No adapters available from API or config');
  throw new Error('No adapters available. Define adapters in orbitchat.yaml and provide matching ids in VITE_ADAPTER_KEYS.');
}

/**
 * Clear the adapters cache (useful for testing or when adapters change)
 */
export function clearAdaptersCache(): void {
  adaptersCache = null;
  adaptersCacheAt = 0;
}

/**
 * Get adapter by id
 */
export async function getAdapter(id: string): Promise<Adapter | null> {
  const adapters = await fetchAdapters();
  return adapters.find(a => a.id === id) || null;
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
