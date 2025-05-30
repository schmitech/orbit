import { useState, useRef, useCallback } from 'react';
import { CHAT_CONSTANTS } from '../shared/styles';

export interface ScrollManagementReturn {
  // State
  showScrollTop: boolean;
  showScrollBottom: boolean;
  isScrolling: boolean;
  
  // Refs
  messagesContainerRef: React.RefObject<HTMLDivElement>;
  messagesEndRef: React.RefObject<HTMLDivElement>;
  shouldScrollRef: React.MutableRefObject<boolean>;
  scrollTimeoutRef: React.MutableRefObject<number | undefined>;
  
  // Functions
  scrollToBottom: (immediate?: boolean) => void;
  scrollToTop: () => void;
  handleScroll: () => void;
}

/**
 * Custom hook for managing scroll behavior in the chat messages container
 * Handles scroll buttons visibility, smooth scrolling, and scroll position tracking
 */
export const useScrollManagement = (isAnimating: boolean): ScrollManagementReturn => {
  // State
  const [showScrollTop, setShowScrollTop] = useState(false);
  const [showScrollBottom, setShowScrollBottom] = useState(false);
  const [isScrolling, setIsScrolling] = useState(false);
  
  // Refs
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const shouldScrollRef = useRef(true);
  const scrollTimeoutRef = useRef<number>();
  
  // Scroll to bottom function with immediate option
  const scrollToBottom = useCallback((immediate = false) => {
    if (messagesContainerRef.current) {
      const { scrollHeight } = messagesContainerRef.current;
      messagesContainerRef.current.scrollTo({
        top: scrollHeight,
        behavior: immediate ? 'auto' : 'smooth'
      });
      
      // Update scroll buttons visibility after scrolling
      setTimeout(() => {
        handleScroll();
      }, immediate ? 0 : CHAT_CONSTANTS.ANIMATIONS.SCROLL_TIMEOUT);
    }
  }, []);
  
  // Check scroll position to determine if scroll buttons should be shown
  const handleScroll = useCallback(() => {
    if (messagesContainerRef.current && !isAnimating) {
      const { scrollTop, scrollHeight, clientHeight } = messagesContainerRef.current;
      const isAtBottom = Math.abs(scrollHeight - scrollTop - clientHeight) < CHAT_CONSTANTS.SCROLL_THRESHOLDS.BOTTOM_THRESHOLD;
      const isAtTop = scrollTop < CHAT_CONSTANTS.SCROLL_THRESHOLDS.TOP_THRESHOLD;
      
      setShowScrollTop(!isAtTop && scrollTop > CHAT_CONSTANTS.SCROLL_THRESHOLDS.SHOW_SCROLL_TOP_OFFSET);
      setShowScrollBottom(!isAtBottom);
    }
  }, [isAnimating]);
  
  // Scroll to top function
  const scrollToTop = useCallback(() => {
    if (messagesContainerRef.current) {
      setIsScrolling(true);
      messagesContainerRef.current.scrollTo({
        top: 0,
        behavior: 'smooth'
      });
      setTimeout(() => {
        setIsScrolling(false);
        handleScroll();
      }, CHAT_CONSTANTS.ANIMATIONS.SCROLL_TIMEOUT);
    }
  }, [handleScroll]);
  
  return {
    // State
    showScrollTop,
    showScrollBottom,
    isScrolling,
    
    // Refs
    messagesContainerRef,
    messagesEndRef,
    shouldScrollRef,
    scrollTimeoutRef,
    
    // Functions
    scrollToBottom,
    scrollToTop,
    handleScroll,
  };
};