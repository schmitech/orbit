import React, { useState, useRef, useEffect, useCallback } from 'react';
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
  // State for displayed content
  const [displayedContent, setDisplayedContent] = useState('');
  const [isThinking, setIsThinking] = useState(true);
  
  // Refs for animation control
  const currentIndexRef = useRef(0);
  const animationFrameRef = useRef<number>();
  const isLocallyAnimatingRef = useRef(false);
  const hasCompletedRef = useRef(false);
  const lastContentLengthRef = useRef(0);

  // Clean up animation on unmount
  useEffect(() => {
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      isLocallyAnimatingRef.current = false;
    };
  }, []);

  // Skip animation for already animated messages
  useEffect(() => {
    if (hasBeenAnimated(messageIndex)) {
      setDisplayedContent(content);
      setIsThinking(false);
      hasCompletedRef.current = true;
      return;
    }
  }, [hasBeenAnimated, messageIndex, content]);

  // Animation function
  const animate = useCallback(() => {
    if (!isLocallyAnimatingRef.current || hasCompletedRef.current) {
      return;
    }

    const currentContent = content;
    const targetLength = currentContent.length;
    
    if (currentIndexRef.current === 0 && targetLength > 0) {
      setIsThinking(false);
    }

    if (currentIndexRef.current < targetLength) {
      // Type one character
      currentIndexRef.current++;
      setDisplayedContent(currentContent.slice(0, currentIndexRef.current));
      
      // Save progress
      typingProgressRef.current.set(messageIndex, currentIndexRef.current);
      
      // Schedule next frame
      animationFrameRef.current = requestAnimationFrame(() => {
        setTimeout(() => animate(), 15); // 15ms delay between characters
      });
    } else if (targetLength > 0 && currentIndexRef.current === targetLength) {
      // Animation complete
      completeAnimation();
    }
  }, [content, messageIndex, typingProgressRef]);

  // Complete animation function
  const completeAnimation = useCallback(() => {
    if (hasCompletedRef.current) return;
    
    hasCompletedRef.current = true;
    isLocallyAnimatingRef.current = false;
    isTypingRef.current = false;
    setIsAnimating(false);
    setDisplayedContent(content);
    typingProgressRef.current.set(messageIndex, content.length);
    onComplete();
    scrollToBottom();
  }, [content, messageIndex, onComplete, scrollToBottom, setIsAnimating, isTypingRef, typingProgressRef]);

  // Skip animation on user input
  const skipAnimation = useCallback(() => {
    if (isLocallyAnimatingRef.current && !hasCompletedRef.current) {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      currentIndexRef.current = content.length;
      completeAnimation();
    }
  }, [content, completeAnimation]);

  // Start or continue animation when content changes
  useEffect(() => {
    if (hasCompletedRef.current || hasBeenAnimated(messageIndex)) {
      return;
    }

    const contentLength = content.length;
    
    // If content is empty, stay in thinking state
    if (contentLength === 0) {
      setIsThinking(true);
      return;
    }

    // If this is new content (not just growing), start animation
    if (!isLocallyAnimatingRef.current && contentLength > lastContentLengthRef.current) {
      isLocallyAnimatingRef.current = true;
      isTypingRef.current = true;
      setIsAnimating(true);
      
      // Restore progress if available
      const savedProgress = typingProgressRef.current.get(messageIndex) || 0;
      if (savedProgress > 0 && savedProgress < contentLength) {
        currentIndexRef.current = savedProgress;
        setDisplayedContent(content.slice(0, savedProgress));
        setIsThinking(false);
      } else {
        currentIndexRef.current = 0;
        setDisplayedContent('');
      }
      
      animate();
    }

    lastContentLengthRef.current = contentLength;
  }, [content, messageIndex, animate, hasBeenAnimated, setIsAnimating, isTypingRef, typingProgressRef]);

  // Handle user input to skip animation
  useEffect(() => {
    const handleUserInput = () => skipAnimation();
    const textarea = inputRef.current;
    
    if (textarea) {
      textarea.addEventListener('input', handleUserInput);
      textarea.addEventListener('keydown', handleUserInput);
    }

    return () => {
      if (textarea) {
        textarea.removeEventListener('input', handleUserInput);
        textarea.removeEventListener('keydown', handleUserInput);
      }
    };
  }, [inputRef, skipAnimation]);

  // Handle visibility changes
  useEffect(() => {
    let hiddenAt: number | null = null;
    
    const handleVisibilityChange = () => {
      if (document.hidden) {
        // Pause animation
        if (animationFrameRef.current) {
          cancelAnimationFrame(animationFrameRef.current);
        }
        hiddenAt = Date.now();
      } else if (hiddenAt && !hasCompletedRef.current) {
        // Resume or skip based on time away
        const awayTime = Date.now() - hiddenAt;
        if (awayTime > CHAT_CONSTANTS.ANIMATIONS.VISIBILITY_SKIP_THRESHOLD) {
          skipAnimation();
        } else if (isLocallyAnimatingRef.current) {
          animate();
        }
        hiddenAt = null;
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [animate, skipAnimation]);

  // Render
  if (isThinking && content.length === 0) {
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

  return <MarkdownRenderer content={displayedContent} />;
};