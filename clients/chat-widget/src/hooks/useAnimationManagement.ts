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
  
  // Refs
  const animatedMessagesRef = useRef<Set<number>>(new Set());
  const typingProgressRef = useRef<Map<number, number>>(new Map());
  const isTypingRef = useRef(false);
  const lastMessageRef = useRef<HTMLDivElement>(null);
  
  // Mark a message as having completed its animation
  const markMessageAnimated = useCallback((
    index: number, 
    messagesLength: number, 
    scrollToBottom: () => void
  ) => {
    animatedMessagesRef.current.add(index);
    if (index === messagesLength - 1) {
      setIsAnimating(false);
      setTimeout(() => scrollToBottom(), 50);
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
    setIsAnimating(false);
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