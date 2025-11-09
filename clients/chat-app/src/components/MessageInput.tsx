import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Mic, MicOff, Paperclip, X, Loader2 } from 'lucide-react';
import { useVoice } from '../hooks/useVoice';
import { FileUpload } from './FileUpload';
import { FileAttachment } from '../types';
import { useChatStore } from '../stores/chatStore';
import { debugLog, debugError } from '../utils/debug';
import { AppConfig } from '../utils/config';

interface MessageInputProps {
  onSend: (message: string, fileIds?: string[]) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function MessageInput({ 
  onSend, 
  disabled = false, 
  placeholder = "Ask me anything..." 
}: MessageInputProps) {
  const [message, setMessage] = useState('');
  const [isComposing, setIsComposing] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const [showFileUpload, setShowFileUpload] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<FileAttachment[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isHoveringUpload, setIsHoveringUpload] = useState(false);
  const [isHoveringMic, setIsHoveringMic] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const processedFilesRef = useRef<Set<string>>(new Set());

  const { createConversation, currentConversationId, removeFileFromConversation, conversations, isLoading } = useChatStore();

  const {
    isListening,
    isSupported: voiceSupported,
    startListening,
    stopListening,
    error: voiceError
  } = useVoice((text) => {
    setMessage(prev => (prev + text).slice(0, AppConfig.maxMessageLength));
  });

  // Check if any files are currently uploading or processing
  const currentConversation = conversations.find(conv => conv.id === currentConversationId);
  const conversationFiles = currentConversation?.attachedFiles || [];
  
  // Don't sync attachedFiles with conversationFiles - attachedFiles should only show files attached to current message
  // Files in conversation will be included when sending the message via conversationFiles
  
  // Check if any attached files are still processing
  // Include files with undefined status (still uploading), 'uploading', or 'processing' status
  const hasProcessingFiles = attachedFiles.some(file => {
    if (!file.processing_status) {
      // File doesn't have status yet - likely still uploading
      return true;
    }
    return file.processing_status !== 'completed' && 
           file.processing_status !== 'error' &&
           file.processing_status !== 'failed';
  }) || conversationFiles.some(file => {
    if (!file.processing_status) {
      // File doesn't have status yet - likely still uploading
      return true;
    }
    return file.processing_status !== 'completed' && 
           file.processing_status !== 'error' &&
           file.processing_status !== 'failed';
  });

  // Disable input if files are uploading, processing, or if already disabled
  const isInputDisabled = disabled || hasProcessingFiles || isUploading;

  // Auto-resize textarea with maximum height limit
  useEffect(() => {
    if (textareaRef.current) {
      const maxHeight = 120; // Maximum height in pixels (about 4-5 lines)
      textareaRef.current.style.height = 'auto';
      const scrollHeight = textareaRef.current.scrollHeight;
      // Set height to scrollHeight, but cap it at maxHeight
      textareaRef.current.style.height = `${Math.min(scrollHeight, maxHeight)}px`;
      // Enable overflow-y when content exceeds max height
      textareaRef.current.style.overflowY = scrollHeight > maxHeight ? 'auto' : 'hidden';
    }
  }, [message]);

  // Auto-focus when not disabled (when AI response is complete)
  useEffect(() => {
    if (!isInputDisabled && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [isInputDisabled]);

  // Focus input field when assistant response finishes (isLoading becomes false)
  const prevIsLoadingRef = useRef(isLoading);
  useEffect(() => {
    // If loading just finished (transitioned from true to false), focus the input
    if (prevIsLoadingRef.current && !isLoading && !isInputDisabled && textareaRef.current) {
      // Small delay to ensure the UI has updated
      setTimeout(() => {
        if (textareaRef.current) {
          textareaRef.current.focus();
        }
      }, 100);
    }
    prevIsLoadingRef.current = isLoading;
  }, [isLoading, isInputDisabled]);

  // Close upload area when upload starts (hide upload widget, show only progress)
  useEffect(() => {
    if (isUploading && showFileUpload) {
      // Upload has started - hide upload widget, only progress will be visible
      setShowFileUpload(false);
    }
  }, [isUploading, showFileUpload]);

  // Re-open upload area when upload completes (if user wants to upload more)
  // Only reopen if no files are attached yet (otherwise user probably doesn't need it)
  useEffect(() => {
    if (!isUploading && attachedFiles.length === 0 && !showFileUpload) {
      // Upload completed and no files attached - could reopen if needed
      // But we'll keep it closed by default and let user click icon to reopen
    }
  }, [isUploading, attachedFiles.length, showFileUpload]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if ((message.trim() || attachedFiles.length > 0) && !isInputDisabled && !isComposing) {
      // For multimodal conversations, send ALL files attached to the conversation
      // (not just the newly attached ones in this message)
      const conversationFiles = currentConversation?.attachedFiles || [];
      const allFileIds = conversationFiles.map(f => f.file_id);

      onSend(message.trim(), allFileIds.length > 0 ? allFileIds : undefined);
      setMessage('');
      setAttachedFiles([]);
      setShowFileUpload(false);
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
        textareaRef.current.style.overflowY = 'hidden';
      }
    }
  };

  const handleFilesSelected = useCallback((files: FileAttachment[]) => {
    debugLog(`[MessageInput] handleFilesSelected called with ${files.length} files:`, files);
    setAttachedFiles(files);
    
    // Automatically add uploaded files to the current conversation
    // Use setTimeout to defer state updates and avoid infinite loops
    setTimeout(() => {
      // Get fresh state inside setTimeout to avoid dependency issues
      const store = useChatStore.getState();
      let conversationId = store.currentConversationId;
      
      if (!conversationId) {
        // Create a new conversation if none exists
        conversationId = createConversation();
        // Get updated state after creating conversation
        const updatedStore = useChatStore.getState();
        conversationId = updatedStore.currentConversationId || conversationId;
      }
      
      // Get fresh store state to access addFileToConversation
      const updatedStore = useChatStore.getState();
      
      // Clean up processedFilesRef: remove entries for files that are no longer in the current list
      // This prevents stale entries from blocking new file uploads
      const currentFileIds = new Set(files.map(f => f.file_id));
      const keysToRemove: string[] = [];
      processedFilesRef.current.forEach((_, key) => {
        const fileId = key.split('-').slice(1).join('-'); // Extract file_id from "conversationId-file_id"
        if (!currentFileIds.has(fileId)) {
          keysToRemove.push(key);
        }
      });
      keysToRemove.forEach(key => processedFilesRef.current.delete(key));
      
      // Add each file to the conversation (will update status if already exists)
      // The upload polling will ensure status is updated when processing completes
      files.forEach(file => {
        const fileKey = `${conversationId}-${file.file_id}`;
        if (!processedFilesRef.current.has(fileKey)) {
          processedFilesRef.current.add(fileKey);
          
          debugLog(`[MessageInput] Adding file ${file.file_id} to conversation ${conversationId}`);
          // Always add/update the file in conversation (addFileToConversation handles updates)
          // This ensures the status is updated when polling completes
          updatedStore.addFileToConversation(conversationId!, file);
        }
      });
    }, 0);
  }, [createConversation]);

  const handleRemoveFile = async (fileId: string) => {
    // Remove from local attached files list
    setAttachedFiles(prev => prev.filter(f => f.file_id !== fileId));
    
    // Remove from processedFilesRef to allow re-uploading if needed
    if (currentConversationId) {
      const fileKey = `${currentConversationId}-${fileId}`;
      processedFilesRef.current.delete(fileKey);
    }
    
    // Remove from conversation and delete from server if conversation exists
    if (currentConversationId) {
      try {
        await removeFileFromConversation(currentConversationId, fileId);
      } catch (error) {
        debugError(`Failed to remove file ${fileId} from conversation:`, error);
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleVoiceToggle = () => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  };

  return (
    <div className="bg-white px-4 py-4 dark:bg-[#212121]">
      {voiceError && (
        <div className="mx-auto mb-3 w-full max-w-5xl rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-600/40 dark:bg-red-900/30 dark:text-red-200">
          {voiceError}
        </div>
      )}

      <form onSubmit={handleSubmit} className="mx-auto flex w-full max-w-5xl flex-col gap-3">
        <div
          className={`flex items-center gap-2 rounded-lg border px-4 py-3 shadow-sm transition-all ${
            isFocused
              ? 'border-gray-300 shadow-md dark:border-[#565869] dark:shadow-lg'
              : 'border-gray-200 dark:border-[#40414f]'
          } bg-gray-50 dark:bg-[#343541]`}
        >
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              if (!isInputDisabled) {
                setShowFileUpload(!showFileUpload);
              }
            }}
            disabled={isInputDisabled}
            onMouseEnter={() => setIsHoveringUpload(true)}
            onMouseLeave={() => setIsHoveringUpload(false)}
            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors ${
              showFileUpload || attachedFiles.length > 0
                ? 'bg-gray-100 text-[#353740] dark:bg-[#565869] dark:text-[#ececf1]'
                : isInputDisabled
                ? 'cursor-not-allowed text-gray-300 dark:text-[#6b6f7a]'
                : 'text-gray-500 hover:bg-gray-100 hover:text-[#353740] dark:text-[#bfc2cd] dark:hover:bg-[#565869]'
            }`}
            title={
              isInputDisabled
                ? 'Files are uploading/processing. Please wait...'
                : attachedFiles.length > 0
                ? `${attachedFiles.length} file(s) attached`
                : 'Attach files'
            }
          >
            {isInputDisabled && isHoveringUpload ? (
              <X className="h-4 w-4" />
            ) : (
              <Paperclip className="h-4 w-4" />
            )}
          </button>

          <textarea
            ref={textareaRef}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            onCompositionStart={() => setIsComposing(true)}
            onCompositionEnd={() => setIsComposing(false)}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder={(hasProcessingFiles || isUploading) ? 'Files are uploading/processing, please wait...' : placeholder}
            disabled={isInputDisabled}
            rows={1}
            maxLength={AppConfig.maxMessageLength}
            className="flex-1 resize-none bg-transparent py-1 text-sm text-[#353740] placeholder-gray-400 focus:outline-none dark:text-[#ececf1] dark:placeholder-[#bfc2cd]"
            style={{ 
              minHeight: '24px',
              maxHeight: '120px',
              border: 'none', 
              outline: 'none',
              boxShadow: 'none',
              WebkitAppearance: 'none',
              MozAppearance: 'none',
              appearance: 'none',
              caretColor: (message.trim() || isFocused) ? 'inherit' : 'transparent'
            }}
          />

          {message.length > 0 && (
            <div className="flex-shrink-0 text-xs text-gray-500 dark:text-[#bfc2cd]">
              <span className={message.length >= AppConfig.maxMessageLength ? 'text-red-600 font-semibold' : ''}>
                {message.length}/{AppConfig.maxMessageLength}
              </span>
            </div>
          )}

          {voiceSupported && (
            <button
              type="button"
              onClick={handleVoiceToggle}
              disabled={isInputDisabled}
              onMouseEnter={() => setIsHoveringMic(true)}
              onMouseLeave={() => setIsHoveringMic(false)}
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors ${
                isListening
                  ? 'bg-red-50 text-red-600 dark:bg-red-900/40 dark:text-red-300'
                  : isInputDisabled
                  ? 'cursor-not-allowed text-gray-300 dark:text-[#6b6f7a]'
                  : 'text-gray-500 hover:bg-gray-100 hover:text-[#353740] dark:text-[#bfc2cd] dark:hover:bg-[#565869]'
              }`}
              title={
                isInputDisabled
                  ? 'Files are uploading/processing. Please wait...'
                  : isListening
                  ? 'Stop recording'
                  : 'Start voice input'
              }
            >
              {isListening || (isInputDisabled && isHoveringMic) ? (
                <MicOff className="h-5 w-5" />
              ) : (
                <Mic className="h-5 w-5" />
              )}
            </button>
          )}

          {(hasProcessingFiles || isUploading) && (
            <div className="flex h-8 w-8 shrink-0 items-center justify-center">
              <Loader2 className="h-4 w-4 animate-spin text-gray-500 dark:text-[#bfc2cd]" />
            </div>
          )}

          <button
            type="submit"
            disabled={(!message.trim() && attachedFiles.length === 0) || isInputDisabled || isComposing}
            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors ${
              (message.trim() || attachedFiles.length > 0) && !isInputDisabled && !isComposing
                ? 'bg-black text-white hover:bg-gray-800 dark:bg-white dark:text-black dark:hover:bg-gray-200'
                : 'bg-gray-200 text-gray-400 dark:bg-[#565869] dark:text-[#6b6f7a]'
            }`}
            title="Send message"
          >
            <Send className="h-4 w-4" style={{ transform: 'translate(-1px, 0.5px)' }} />
          </button>
        </div>

        {attachedFiles.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {attachedFiles.map((file) => (
              <div
                key={file.file_id}
                className="flex items-center gap-2 rounded-md border border-gray-200 bg-white px-2 py-1 text-xs dark:border-[#4a4b54] dark:bg-[#2d2f39]"
              >
                <span className="truncate max-w-[150px] text-[#353740] dark:text-[#ececf1]">
                  {file.filename}
                </span>
                {!disabled && (
                  <button
                    onClick={() => handleRemoveFile(file.file_id)}
                    className="text-gray-500 hover:text-red-600 dark:text-[#bfc2cd] dark:hover:text-red-300"
                    title="Remove file"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {(showFileUpload || isUploading) && (
          <div className="rounded-md border border-gray-200 bg-white p-3 dark:border-[#4a4b54] dark:bg-[#2d2f39]">
            {showFileUpload && (
              <div className="mb-2 flex items-center justify-between text-sm text-[#353740] dark:text-[#ececf1]">
                <span>Upload files</span>
                <button
                  onClick={() => setShowFileUpload(false)}
                  className="rounded p-1 text-gray-500 hover:bg-gray-100 hover:text-[#353740] dark:text-[#bfc2cd] dark:hover:bg-[#3c3f4a]"
                  title="Close"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            )}
            {isUploading && !showFileUpload && (
              <div className="mb-2 text-sm text-[#353740] dark:text-[#ececf1]">
                Uploading files…
              </div>
            )}
            <FileUpload
              onFilesSelected={handleFilesSelected}
              onUploadError={(error) => {
                debugError('File upload error:', error);
              }}
              onUploadingChange={setIsUploading}
              maxFiles={AppConfig.maxFilesPerConversation}
              disabled={isInputDisabled}
            />
          </div>
        )}

        <div className="h-4">
          {isListening && (
            <span className="flex items-center gap-2 text-xs text-gray-500 dark:text-[#bfc2cd]">
              <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
              Listening...
            </span>
          )}
        </div>
      </form>
    </div>
  );
}
