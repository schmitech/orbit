import { createContext } from 'react';

export type AgentHomeNavContextValue = {
  registerGoHome: (fn: (() => void) | null) => void;
  goHome: () => void;
};

export const AgentHomeNavContext = createContext<AgentHomeNavContextValue | null>(null);

export const fallbackAgentHomeNav: AgentHomeNavContextValue = {
  registerGoHome: () => {},
  goHome: () => {},
};
