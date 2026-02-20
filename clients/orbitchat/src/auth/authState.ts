/**
 * Module-scoped auth state with pub/sub pattern.
 * Avoids circular deps with config.ts (no zustand/React imports).
 * Read synchronously by AppConfig Proxy; subscribed reactively by React hook.
 */

type Listener = () => void;

let isAuthenticated = false;
const listeners = new Set<Listener>();

export function getIsAuthenticated(): boolean {
  return isAuthenticated;
}

export function setIsAuthenticated(value: boolean): void {
  if (isAuthenticated === value) return;
  isAuthenticated = value;
  listeners.forEach(listener => listener());
}

export function subscribeAuthState(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
