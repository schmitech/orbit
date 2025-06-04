import React, { useState, useRef, useEffect } from 'react';
import { MarkdownRenderer } from '../shared/MarkdownComponents';
import { CHAT_CONSTANTS } from '../shared/styles';

export interface TypingEffectProps {
  content: string;
  onComplete: () => void;
  messageIndex: number;
  inputRef: React.RefObject<HTMLTextAreaElement>;
  hasBeenAnimated: (index: number) => boolean;
  typingProgressRef: React.MutableRefObject<Map<number, number>>;
  isTypingRef: React.MutableRefObject<boolean>;
  setIsAnimating: (value: boolean) => void;
  scrollToBottom: () => void;
}

/**
 * TypingEffect component handles the character-by-character typing animation
 * for assistant messages with support for pausing, resuming, and skipping
 */
export const TypingEffect: React.FC<TypingEffectProps> = ({
  content,
  onComplete,
  messageIndex,
  inputRef,
  hasBeenAnimated,
  typingProgressRef,
  isTypingRef,
  setIsAnimating,
  scrollToBottom,
}) => {
  // Use a ref to store the current animation progress
  const [displayedContent, setDisplayedContent] = useState(() => {
    // Restore progress if available
    const progress = typingProgressRef.current.get(messageIndex);
    return progress ? content.slice(0, progress) : '';
  });
  const [isThinking, setIsThinking] = useState(true);
  const currentIndexRef = useRef(typingProgressRef.current.get(messageIndex) || 0);
  const isAnimatingRef = useRef(false);
  const animationFrameRef = useRef<number>();
  // This flag tracks whether animation has been initialized
  const hasInitializedRef = useRef(false);
  // We'll use this to store the full content to ensure continuity
  const fullContentRef = useRef(content);

  // Initialize animation only once
  useEffect(() => {
    // Skip if this message has already been animated
    if (hasBeenAnimated(messageIndex)) {
      setDisplayedContent(content);
      setIsThinking(false);
      onComplete();
      typingProgressRef.current.set(messageIndex, content.length);
      return;
    }

    // Update content if it changed but don't restart animation
    if (hasInitializedRef.current && content !== fullContentRef.current) {
      fullContentRef.current = content;
      return;
    }

    // Skip if we've already initialized
    if (hasInitializedRef.current) {
      return;
    }

    // Mark as initialized to prevent restart on re-render
    hasInitializedRef.current = true;
    fullContentRef.current = content;

    // Start the animation with a small delay to ensure component is ready
    setTimeout(() => {
      startTypingAnimation();
    }, 10);

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [messageIndex, content, hasBeenAnimated, onComplete]);

  // Function to handle animation
  const startTypingAnimation = () => {
    if (isAnimatingRef.current) {
      return;
    }

    if (!hasInitializedRef.current) {
      return;
    }

    isAnimatingRef.current = true;
    isTypingRef.current = true;
    setIsAnimating(true);
    
    // Start from current position (important for resuming after tab switching)
    let currentIndex = currentIndexRef.current;
    let lastScrollTime = 0;
    let lastTypingTime = 0;
    const typingSpeed = 15; // milliseconds between characters (faster speed)

    // Show thinking state only at the beginning
    if (currentIndex === 0) {
      setIsThinking(true);
    } else {
      setIsThinking(false);
    }

    const animateText = (timestamp: number) => {
      // Check if animation was canceled or component unmounted
      if (!isAnimatingRef.current || !hasInitializedRef.current) {
        return;
      }
      
      // Check if enough time has passed for the next character
      if (timestamp - lastTypingTime < typingSpeed) {
        animationFrameRef.current = requestAnimationFrame(animateText);
        return;
      }
      
      lastTypingTime = timestamp;
      
      if (currentIndex < fullContentRef.current.length) {
        const newContent = fullContentRef.current.slice(0, currentIndex + 1);
        setDisplayedContent(newContent);
        typingProgressRef.current.set(messageIndex, currentIndex + 1);
        
        // Exit thinking state after first character
        if (currentIndex === 0) {
          setIsThinking(false);
        }

        // Scroll occasionally during animation
        if (timestamp - lastScrollTime > CHAT_CONSTANTS.ANIMATIONS.ANIMATION_SCROLL_INTERVAL) {
          scrollToBottom();
          lastScrollTime = timestamp;
        }

        // Save the current position (crucial for resuming)
        currentIndex++;
        currentIndexRef.current = currentIndex;
        
        animationFrameRef.current = requestAnimationFrame(animateText);
      } else {
        // Animation is complete
        completeAnimation();
      }
    };

    // Use setTimeout to ensure the first frame is scheduled properly
    setTimeout(() => {
      if (isAnimatingRef.current && hasInitializedRef.current) {
        animationFrameRef.current = requestAnimationFrame(animateText);
      }
    }, 0);
  };

  // Handle animation completion
  const completeAnimation = () => {
    isTypingRef.current = false;
    onComplete();
    isAnimatingRef.current = false;
    setIsAnimating(false);
    scrollToBottom();
    typingProgressRef.current.set(messageIndex, fullContentRef.current.length);
  };

  // Handle user input to skip animation
  useEffect(() => {
    const handleUserInput = () => {
      if (isAnimatingRef.current) {
        if (animationFrameRef.current) {
          cancelAnimationFrame(animationFrameRef.current);
        }
        setDisplayedContent(fullContentRef.current);
        setIsThinking(false);
        completeAnimation();
        typingProgressRef.current.set(messageIndex, fullContentRef.current.length);
      }
    };

    const textarea = inputRef.current;
    if (textarea) {
      textarea.addEventListener('input', handleUserInput);
    }

    return () => {
      if (textarea) {
        textarea.removeEventListener('input', handleUserInput);
      }
    };
  }, [inputRef]);

  // This is the key handler for document visibility changes
  useEffect(() => {
    let hiddenAt: number | null = null;
    const handleVisibilityChange = () => {
      if (document.hidden) {
        // Page is hidden, pause by canceling current animation
        if (animationFrameRef.current) {
          cancelAnimationFrame(animationFrameRef.current);
          isAnimatingRef.current = false;
        }
        hiddenAt = Date.now();
      } else if (hasInitializedRef.current && !isAnimatingRef.current && currentIndexRef.current > 0 && currentIndexRef.current < fullContentRef.current.length) {
        // Page is visible again
        const now = Date.now();
        if (hiddenAt && now - hiddenAt > CHAT_CONSTANTS.ANIMATIONS.VISIBILITY_SKIP_THRESHOLD) {
          // If away for more than 1s, instantly finish animation
          setDisplayedContent(fullContentRef.current);
          setIsThinking(false);
          completeAnimation();
          typingProgressRef.current.set(messageIndex, fullContentRef.current.length);
        } else {
          // Resume animation
          startTypingAnimation();
        }
        hiddenAt = null;
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  if (isThinking && currentIndexRef.current === 0) {
    return (
      <div className="text-gray-500">
        <span className="font-medium">Thinking</span>
        <span className="animate-dots ml-1">
          <span className="dot">.</span>
          <span className="dot">.</span>
          <span className="dot">.</span>
        </span>
      </div>
    );
  }

  return (
    <div>
      <MarkdownRenderer content={displayedContent} />
    </div>
  );
};