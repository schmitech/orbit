import { useState, useRef, useCallback, useEffect } from 'react';
import { CHAT_CONSTANTS } from '../shared/styles';

export interface AnimationManagementReturn {
  // State
  isAnimating: boolean;
  
  // Refs
  animatedMessagesRef: React.MutableRefObject<Set<string>>;
  typingProgressRef: React.MutableRefObject<Map<string, number>>;
  isTypingRef: React.MutableRefObject<boolean>;
  lastMessageRef: React.RefObject<HTMLDivElement | null>;
  
  // Functions
  markMessageAnimated: (id: string, messagesLength: number, scrollToBottom: () => void) => void;
  hasBeenAnimated: (id: string) => boolean;
  clearAnimationTrackers: () => void;
  setIsAnimating: (value: boolean) => void;
}

/**
 * Custom hook for managing typing animations and animation state
 * Handles message animation tracking, progress persistence, and animation lifecycle
 */
export const useAnimationManagement = (): AnimationManagementReturn => {
  // State
  const [isAnimating, setIsAnimating] = useState(false);
  
  // Refs - using a unique key per message instead of just index
  const animatedMessagesRef = useRef<Set<string>>(new Set());
  const typingProgressRef = useRef<Map<string, number>>(new Map());
  const isTypingRef = useRef(false);
  const lastMessageRef = useRef<HTMLDivElement>(null);
  const messageKeysRef = useRef<Map<number, string>>(new Map());
  
  // Mark a message as having completed its animation
  const markMessageAnimated = useCallback((
    id: string, 
    messagesLength: number, 
    scrollToBottom: () => void
  ) => {
    animatedMessagesRef.current.add(id);
    
    // Clean up progress tracking for this message
    typingProgressRef.current.delete(id);
    
    // Check if this is the last message
    if (true /* last message check handled by caller context */) {
      setIsAnimating(false);
      isTypingRef.current = false;
      // Delay scroll to ensure DOM updates
      setTimeout(() => scrollToBottom(), 100);
    }
  }, []);
  
  // Check if a message has been animated
  const hasBeenAnimated = useCallback((id: string): boolean => {
    return animatedMessagesRef.current.has(id);
  }, []);
  
  // Clear animation trackers (used when messages are cleared)
  const clearAnimationTrackers = useCallback(() => {
    animatedMessagesRef.current.clear();
    typingProgressRef.current.clear();
    messageKeysRef.current.clear();
    setIsAnimating(false);
    isTypingRef.current = false;
  }, []);
  
  // Clean up old message tracking when message count changes significantly
  useEffect(() => {
    // Clean up tracking for messages that no longer exist
    // If we have too many tracked messages, clean up old ones
    if (animatedMessagesRef.current.size > 200) {
      // If we have too many tracked messages, clean up old ones
      const newSet = new Set<string>();
      const newProgress = new Map<string, number>();
      
      // Keep only the most recent 100 messages by insertion order
      const ids = Array.from(animatedMessagesRef.current);
      const keep = new Set(ids.slice(-100));
      keep.forEach(k => newSet.add(k));
      Array.from(typingProgressRef.current.keys()).forEach(k => {
        if (keep.has(k)) {
          newProgress.set(k, typingProgressRef.current.get(k)!);
        }
      });
      
      animatedMessagesRef.current = newSet;
      typingProgressRef.current = newProgress;
    }
  }, []);
  
  return {
    // State
    isAnimating,
    
    // Refs
    animatedMessagesRef,
    typingProgressRef,
    isTypingRef,
    lastMessageRef,
    
    // Functions
    markMessageAnimated,
    hasBeenAnimated,
    clearAnimationTrackers,
    setIsAnimating,
  };
};
