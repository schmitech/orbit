import { useSyncExternalStore } from 'react';
import { subscribeAuthState, getIsAuthenticated } from '../auth/authState';

/**
 * React hook that re-renders when auth state changes.
 * Bridges the module-scoped authState into React's render cycle.
 */
export function useIsAuthenticated(): boolean {
  return useSyncExternalStore(subscribeAuthState, getIsAuthenticated, getIsAuthenticated);
}
