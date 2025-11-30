/**
 * Middleware Configuration Utility
 * 
 * Provides utilities for working with API middleware mode.
 * When middleware is enabled, adapters are used instead of direct API keys.
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
 * Fetch available adapters from the server
 */
export async function fetchAdapters(): Promise<Adapter[]> {
  if (adaptersCache) {
    return adaptersCache;
  }

  try {
    const response = await fetch('/api/adapters');
    if (!response.ok) {
      throw new Error(`Failed to fetch adapters: ${response.status} ${response.statusText}`);
    }
    const data: AdaptersResponse = await response.json();
    adaptersCache = data.adapters;
    debugLog('Fetched adapters:', adaptersCache);
    return adaptersCache;
  } catch (error) {
    debugError('Error fetching adapters:', error);
    throw error;
  }
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

