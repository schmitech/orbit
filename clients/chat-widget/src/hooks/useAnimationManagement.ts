import { useState, useRef, useCallback, useEffect } from 'react';
import { CHAT_CONSTANTS } from '../shared/styles';

export interface AnimationManagementReturn {
  // State
  isAnimating: boolean;
  
  // Refs
  animatedMessagesRef: React.MutableRefObject<Set<number>>;
  typingProgressRef: React.MutableRefObject<Map<number, number>>;
  isTypingRef: React.MutableRefObject<boolean>;
  lastMessageRef: React.RefObject<HTMLDivElement>;
  
  // Functions
  markMessageAnimated: (index: number, messagesLength: number, scrollToBottom: () => void) => void;
  hasBeenAnimated: (index: number) => boolean;
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
  const animatedMessagesRef = useRef<Set<number>>(new Set());
  const typingProgressRef = useRef<Map<number, number>>(new Map());
  const isTypingRef = useRef(false);
  const lastMessageRef = useRef<HTMLDivElement>(null);
  const messageKeysRef = useRef<Map<number, string>>(new Map());
  
  // Mark a message as having completed its animation
  const markMessageAnimated = useCallback((
    index: number, 
    messagesLength: number, 
    scrollToBottom: () => void
  ) => {
    animatedMessagesRef.current.add(index);
    
    // Clean up progress tracking for this message
    typingProgressRef.current.delete(index);
    
    // Check if this is the last message
    if (index === messagesLength - 1) {
      setIsAnimating(false);
      isTypingRef.current = false;
      // Delay scroll to ensure DOM updates
      setTimeout(() => scrollToBottom(), 100);
    }
  }, []);
  
  // Check if a message has been animated
  const hasBeenAnimated = useCallback((index: number): boolean => {
    return animatedMessagesRef.current.has(index);
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
    const maxIndex = Math.max(...Array.from(animatedMessagesRef.current), -1);
    if (maxIndex > 100) {
      // If we have too many tracked messages, clean up old ones
      const newSet = new Set<number>();
      const newProgress = new Map<number, number>();
      
      // Keep only the last 50 messages
      for (let i = maxIndex - 50; i <= maxIndex; i++) {
        if (animatedMessagesRef.current.has(i)) {
          newSet.add(i);
        }
        if (typingProgressRef.current.has(i)) {
          newProgress.set(i, typingProgressRef.current.get(i)!);
        }
      }
      
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