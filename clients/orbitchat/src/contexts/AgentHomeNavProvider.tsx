import { useCallback, useRef, type ReactNode } from 'react';
import { AgentHomeNavContext } from './agentHomeNavContext';

export function AgentHomeNavProvider({ children }: { children: ReactNode }) {
  const goHomeRef = useRef<(() => void) | null>(null);

  const registerGoHome = useCallback((fn: (() => void) | null) => {
    goHomeRef.current = fn;
  }, []);

  const goHome = useCallback(() => {
    goHomeRef.current?.();
  }, []);

  return (
    <AgentHomeNavContext.Provider value={{ registerGoHome, goHome }}>
      {children}
    </AgentHomeNavContext.Provider>
  );
}
