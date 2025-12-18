import { useState, useRef, useCallback, useEffect } from 'react';
import { CHAT_CONSTANTS } from '../shared/styles';

export interface InputManagementReturn {
  // State
  message: string;
  isFocused: boolean;
  
  // Refs
  inputRef: React.RefObject<HTMLTextAreaElement>;
  
  // Functions
  handleMessageChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  handleKeyDown: (e: React.KeyboardEvent) => void;
  handleSendMessage: () => void;
  setIsFocused: (focused: boolean) => void;
  clearMessage: () => void;
  focusInput: () => void;
}

export interface InputManagementProps {
  onSendMessage: (message: string) => void;
  isLoading: boolean;
  isOpen: boolean;
}

/**
 * Custom hook for managing message input state and interactions
 * Handles input validation, keyboard shortcuts, and focus management
 */
export const useInputManagement = ({ 
  onSendMessage, 
  isLoading, 
  isOpen 
}: InputManagementProps): InputManagementReturn => {
  // State
  const [message, setMessage] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  
  // Refs
  const inputRef = useRef<HTMLTextAreaElement>(null);
  
  // Handle message input changes with validation
  const handleMessageChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const input = e.target.value;
    if (input.length <= CHAT_CONSTANTS.MAX_MESSAGE_LENGTH) {
      setMessage(input);
    }
  }, []);
  
  // Handle sending message
  const handleSendMessage = useCallback(() => {
    if (message.trim() && !isLoading) {
      onSendMessage(message.trim());
      setMessage('');
    }
  }, [message, isLoading, onSendMessage]);
  
  // Handle keyboard events (Enter to send, Shift+Enter for new line)
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  }, [handleSendMessage]);
  
  // Clear message
  const clearMessage = useCallback(() => {
    setMessage('');
  }, []);
  
  // Focus input programmatically
  const focusInput = useCallback(() => {
    if (inputRef.current) {
      inputRef.current.focus();
    }
  }, []);
  
  // Auto-focus input when chat opens
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);
  
  return {
    // State
    message,
    isFocused,
    
    // Refs
    inputRef,
    
    // Functions
    handleMessageChange,
    handleKeyDown,
    handleSendMessage,
    setIsFocused,
    clearMessage,
    focusInput,
  };
};