import React, { useState, useRef, useEffect, useCallback } from 'react';
import { CHAT_CONSTANTS } from '../shared/styles';
import { MarkdownRenderer } from '@schmitech/markdown-renderer';

export interface TypingEffectProps {
  content: string;
  onComplete: () => void;
  messageId: string;
  inputRef: React.RefObject<HTMLTextAreaElement>;
  hasBeenAnimated: (id: string) => boolean;
  typingProgressRef: React.MutableRefObject<Map<string, number>>;
  isTypingRef: React.MutableRefObject<boolean>;
  setIsAnimating: (value: boolean) => void;
  scrollToBottom: () => void;
  // Whether the assistant is still streaming tokens for this message
  isStreaming?: boolean;
}

/**
 * Helper function to detect if we're in the middle of a markdown token
 */
const isIncompleteMarkdownToken = (text: string): boolean => {
  if (!text) return false;
  
  // Check for incomplete code blocks (both inline and fenced)
  const backtickCount = (text.match(/`/g) || []).length;
  if (backtickCount % 2 !== 0) return true;
  
  // Check for incomplete fenced code blocks
  const fenceMatches = text.match(/```/g) || [];
  if (fenceMatches.length % 2 !== 0) return true;
  
  // Check for incomplete bold/italic markers at the end
  if (text.endsWith('*') || text.endsWith('_')) {
    // Count preceding markers
    const lastChar = text[text.length - 1];
    let count = 0;
    for (let i = text.length - 1; i >= 0 && text[i] === lastChar; i--) {
      count++;
    }
    // If we have 1 or 2 markers at the end, we might be incomplete
    if (count <= 2) return true;
  }
  
  // Check for list markers at the very end
  if (text.match(/\n[-*+]\s*$/) || text.match(/^\s*[-*+]\s*$/)) return true;
  
  // Check for incomplete link syntax
  if (text.endsWith('[') || (text.includes('[') && !text.includes(']('))) return true;
  
  // Check for incomplete math delimiters
  const dollarSigns = (text.match(/\$/g) || []).length;
  if (dollarSigns % 2 !== 0) return true;
  
  // Check for LaTeX start markers
  if (text.endsWith('\\') || text.endsWith('\\(') || text.endsWith('\\[')) return true;
  
  // Check for incomplete headers
  if (text.match(/(^|\n)#{1,6}\s*$/)) return true;
  
  return false;
};

/**
 * TypingEffect component handles the character-by-character typing animation
 * for assistant messages with support for pausing, resuming, and skipping
 */
export const TypingEffect: React.FC<TypingEffectProps> = ({
  content,
  onComplete,
  messageId,
  inputRef,
  hasBeenAnimated,
  typingProgressRef,
  isTypingRef,
  setIsAnimating,
  scrollToBottom,
  isStreaming = true,
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
    if (hasBeenAnimated(messageId)) {
      setDisplayedContent(content);
      setIsThinking(false);
      hasCompletedRef.current = true;
      return;
    }
  }, [hasBeenAnimated, messageId, content]);

  // Complete animation function
  const completeAnimation = useCallback(() => {
    if (hasCompletedRef.current) return;
    
    hasCompletedRef.current = true;
    isLocallyAnimatingRef.current = false;
    isTypingRef.current = false;
    setIsAnimating(false);
    setDisplayedContent(content);
    typingProgressRef.current.set(messageId, content.length);
    onComplete();
    scrollToBottom();
  }, [content, messageId, onComplete, scrollToBottom, setIsAnimating, isTypingRef, typingProgressRef]);

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
      // Type characters until we have a complete token
      let newIndex = currentIndexRef.current + 1;
      let potentialContent = currentContent.slice(0, newIndex);
      
      // Keep adding characters while we have an incomplete markdown token
      while (newIndex < targetLength && isIncompleteMarkdownToken(potentialContent)) {
        newIndex++;
        potentialContent = currentContent.slice(0, newIndex);
      }
      
      currentIndexRef.current = newIndex;
      setDisplayedContent(potentialContent);
      
      // Save progress
      typingProgressRef.current.set(messageId, currentIndexRef.current);
      
      // Scroll to bottom periodically (every 10 characters or on newlines)
      const justTypedNewline = potentialContent.includes('\n') && potentialContent.lastIndexOf('\n') > potentialContent.length - 10;
      if (currentIndexRef.current % 10 === 0 || justTypedNewline) {
        scrollToBottom();
      }
      
      // Schedule next frame
      animationFrameRef.current = requestAnimationFrame(() => {
        setTimeout(() => animate(), 2); // 2ms delay between characters (much faster)
      });
    } else if (targetLength > 0 && currentIndexRef.current === targetLength) {
      // We've caught up to the currently available content.
      // If streaming is still in progress, pause animation and wait for more tokens.
      // Only mark complete once streaming has fully finished.
      if (isStreaming) {
        isLocallyAnimatingRef.current = false;
        // Keep typing state true so UI knows we're mid-stream
        isTypingRef.current = true;
        return;
      }
      // Streaming finished and we've fully rendered: complete animation
      completeAnimation();
    }
  }, [content, messageId, typingProgressRef, scrollToBottom, isStreaming, completeAnimation, isTypingRef]);

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
    if (hasCompletedRef.current || hasBeenAnimated(messageId)) {
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
      
      // Restore progress if available. Fallback to the current index or currently displayed length.
      const savedProgress = typingProgressRef.current.get(messageId);
      const fallbackProgress = Math.max(currentIndexRef.current, displayedContent.length);
      const resumeFrom = Math.min(
        contentLength,
        savedProgress !== undefined ? savedProgress : fallbackProgress
      );

      if (resumeFrom > 0 && resumeFrom <= contentLength) {
        currentIndexRef.current = resumeFrom;
        setDisplayedContent(content.slice(0, resumeFrom));
        setIsThinking(false);
      } else {
        currentIndexRef.current = 0;
        setDisplayedContent('');
      }
      
      animate();
    }

    lastContentLengthRef.current = contentLength;
  }, [content, messageId, animate, hasBeenAnimated, setIsAnimating, isTypingRef, typingProgressRef, displayedContent.length]);

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

  // Handle visibility changes and window focus/blur
  useEffect(() => {
    let hiddenAt: number | null = null;
    let isPaused = false;
    
    const pauseAnimation = () => {
      if (!isPaused && isLocallyAnimatingRef.current) {
        // Pause animation
        if (animationFrameRef.current) {
          cancelAnimationFrame(animationFrameRef.current);
        }
        isPaused = true;
        hiddenAt = Date.now();
      }
    };
    
    const resumeAnimation = () => {
      if (isPaused && hiddenAt && !hasCompletedRef.current) {
        // Resume typing where it left off; do not fast-forward on return
        if (isLocallyAnimatingRef.current) {
          animate();
        }
        isPaused = false;
        hiddenAt = null;
      }
    };
    
    const handleVisibilityChange = () => {
      if (document.hidden) {
        pauseAnimation();
      } else {
        resumeAnimation();
      }
    };
    
    const handleWindowBlur = () => {
      pauseAnimation();
    };
    
    const handleWindowFocus = () => {
      resumeAnimation();
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('blur', handleWindowBlur);
    window.addEventListener('focus', handleWindowFocus);
    
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('blur', handleWindowBlur);
      window.removeEventListener('focus', handleWindowFocus);
    };
  }, [animate, skipAnimation]);

  // When streaming finishes, finalize animation if we've already caught up
  useEffect(() => {
    if (!isStreaming && !hasCompletedRef.current) {
      const contentLength = content.length;
      if (contentLength === 0) return;
      if (currentIndexRef.current >= contentLength) {
        completeAnimation();
      } else if (!isLocallyAnimatingRef.current) {
        // Ensure we resume to finish any remaining characters
        isLocallyAnimatingRef.current = true;
        animate();
      }
    }
  }, [isStreaming, content.length, completeAnimation, animate]);

  // Render
  if (isThinking && content.length === 0) {
    return (
      <div className="flex items-center gap-2">
        <div className="typing-dots-container">
          <div className="typing-dot"></div>
          <div className="typing-dot"></div>
          <div className="typing-dot"></div>
        </div>
      </div>
    );
  }

  return <MarkdownRenderer content={displayedContent} />;
};
