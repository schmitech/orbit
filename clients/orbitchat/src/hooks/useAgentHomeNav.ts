import { useContext } from 'react';
import {
  AgentHomeNavContext,
  fallbackAgentHomeNav,
  type AgentHomeNavContextValue,
} from '../contexts/agentHomeNavContext';

export function useAgentHomeNav(): AgentHomeNavContextValue {
  return useContext(AgentHomeNavContext) ?? fallbackAgentHomeNav;
}
