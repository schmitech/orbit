import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { MarkdownLink } from '../shared/MarkdownComponents';
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
  normalizeText: (text: string) => string;
  linkifyText: (text: string) => string;
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
  normalizeText,
  linkifyText,
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

    // Skip if we've already initialized
    if (hasInitializedRef.current) {
      return;
    }

    // Mark as initialized to prevent restart on re-render
    hasInitializedRef.current = true;
    fullContentRef.current = content;

    // Start the animation
    startTypingAnimation();

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [messageIndex, content]); // Removed hasBeenAnimated and onComplete from deps

  // Function to handle animation
  const startTypingAnimation = () => {
    if (isAnimatingRef.current) return;

    isAnimatingRef.current = true;
    isTypingRef.current = true;
    setIsAnimating(true);
    
    // Start from current position (important for resuming after tab switching)
    let currentIndex = currentIndexRef.current;
    let lastScrollTime = 0;

    // Show thinking state only at the beginning
    if (currentIndex === 0) {
      setIsThinking(true);
    } else {
      setIsThinking(false);
    }

    const animateText = (timestamp: number) => {
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

    animationFrameRef.current = requestAnimationFrame(animateText);
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
  }, []); // Removed inputRef and onComplete from deps

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

  return (
    <>
      {displayedContent && (
        <div className="prose prose-base max-w-full whitespace-pre-wrap" style={{ 
          overflowWrap: 'anywhere',
          wordBreak: 'break-word', 
          width: '100%',
          maxWidth: '100%',
          fontSize: '16px',
        }}>
          <ReactMarkdown
            components={{
              a: (props) => <MarkdownLink {...props} />,
              p: (props) => <p style={{ 
                overflowWrap: 'anywhere', 
                wordBreak: 'break-word',
                margin: '0 0 0.2em 0'
              }} {...props} />,
              code: (props) => <code style={{ display: 'block', whiteSpace: 'pre-wrap', overflowX: 'auto', overflowWrap: 'anywhere' }} {...props} />
            }}
          >
            {normalizeText(linkifyText(displayedContent))}
          </ReactMarkdown>
        </div>
      )}
      {isThinking && (
        <div className="text-gray-500">
          <span className="font-medium">Thinking</span>
          <span className="animate-dots ml-1">
            <span className="dot">.</span>
            <span className="dot">.</span>
            <span className="dot">.</span>
          </span>
        </div>
      )}
    </>
  );
};