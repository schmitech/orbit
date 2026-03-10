/**
 * Module-scoped auth state with pub/sub pattern.
 * Avoids circular deps with config.ts (no zustand/React imports).
 * Read synchronously by AppConfig Proxy; subscribed reactively by React hook.
 */

type Listener = () => void;

let isAuthenticated = false;
let authenticatedUserId: string | null = null;
const listeners = new Set<Listener>();

function notifyListeners(): void {
  listeners.forEach(listener => listener());
}

export function getIsAuthenticated(): boolean {
  return isAuthenticated;
}

export function getAuthenticatedUserId(): string | null {
  return authenticatedUserId;
}

export function setIsAuthenticated(value: boolean): void {
  if (isAuthenticated === value) return;
  isAuthenticated = value;
  if (!value && authenticatedUserId !== null) {
    authenticatedUserId = null;
  }
  notifyListeners();
}

export function setAuthenticatedUserId(value: string | null): void {
  const normalized = typeof value === 'string' && value.trim().length > 0 ? value.trim() : null;
  if (authenticatedUserId === normalized) return;
  authenticatedUserId = normalized;
  notifyListeners();
}

export function subscribeAuthState(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
