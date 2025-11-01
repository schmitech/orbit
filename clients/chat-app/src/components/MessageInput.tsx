import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Mic, MicOff, Paperclip, X, Loader2 } from 'lucide-react';
import { useVoice } from '../hooks/useVoice';
import { FileUpload } from './FileUpload';
import { FileAttachment } from '../types';
import { useChatStore } from '../stores/chatStore';

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

  const { createConversation, currentConversationId, removeFileFromConversation, conversations } = useChatStore();

  const {
    isListening,
    isSupported: voiceSupported,
    startListening,
    stopListening,
    error: voiceError
  } = useVoice((text) => {
    setMessage(prev => (prev + text).slice(0, 1000));
  });

  // Check if any files are currently uploading or processing
  const currentConversation = conversations.find(conv => conv.id === currentConversationId);
  const conversationFiles = currentConversation?.attachedFiles || [];
  
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

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [message]);

  // Auto-focus when not disabled (when AI response is complete)
  useEffect(() => {
    if (!isInputDisabled && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [isInputDisabled]);

  // Close upload area when files finish uploading (upload complete, processing may continue)
  // This prevents users from uploading more files while current ones are processing
  // Note: We don't close immediately when upload starts to allow files to be properly added to state
  useEffect(() => {
    if (!isUploading && attachedFiles.length > 0 && showFileUpload) {
      // Upload has finished - close the upload area (processing may continue in background)
      setShowFileUpload(false);
    }
  }, [isUploading, attachedFiles.length, showFileUpload]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if ((message.trim() || attachedFiles.length > 0) && !isInputDisabled && !isComposing) {
      const fileIds = attachedFiles.map(f => f.file_id);
      onSend(message.trim(), fileIds.length > 0 ? fileIds : undefined);
      setMessage('');
      setAttachedFiles([]);
      setShowFileUpload(false);
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleFilesSelected = useCallback((files: FileAttachment[]) => {
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
        console.error(`Failed to remove file ${fileId} from conversation:`, error);
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
    <div className={`px-6 sm:px-10 pt-3 relative z-10 bg-gradient-to-t from-white/40 via-transparent to-transparent dark:from-slate-950/30 dark:via-transparent dark:to-transparent backdrop-blur-sm transition-all duration-200 ${
      showFileUpload ? 'pb-36' : 'pb-8'
    }`}>
      {voiceError && (
        <div className="mb-4 text-sm text-red-600 dark:text-red-400 bg-gradient-to-r from-red-50/80 to-rose-50/80 dark:from-red-900/40 dark:to-rose-900/40 p-3 rounded-xl shadow-sm backdrop-blur-sm">
          {voiceError}
        </div>
      )}
      
      <form onSubmit={handleSubmit} className="relative w-full max-w-3xl mx-auto">
        <div className={`relative flex items-center gap-3 rounded-2xl border px-4 py-3 transition-all duration-200 ${
          isFocused
            ? 'border-slate-300/80 dark:border-emerald-400/60 shadow-[0_20px_50px_rgba(71,85,105,0.15)] dark:shadow-[0_20px_50px_rgba(16,185,129,0.25)] bg-white dark:bg-slate-900'
            : 'border-slate-200/70 dark:border-slate-700/60 bg-white/80 dark:bg-slate-900/70 shadow-[0_12px_40px_rgba(15,23,42,0.12)]'
        }`}>
          {/* Attachment button */}
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
            className={`flex-shrink-0 p-2 transition-all duration-200 rounded-lg ${
              showFileUpload || attachedFiles.length > 0
                ? 'text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20'
                : isInputDisabled
                ? 'text-slate-300 dark:text-slate-600 cursor-not-allowed opacity-50'
                : 'text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'
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
              <X className="w-5 h-5" />
            ) : (
              <Paperclip className="w-5 h-5" />
            )}
          </button>

          {/* Text input */}
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
            maxLength={1000}
            className="flex-1 bg-transparent border-none outline-none resize-none text-slate-900 dark:text-slate-100 placeholder-slate-500 dark:placeholder-slate-400 max-h-32 leading-relaxed font-medium focus:outline-none focus:ring-0 focus:border-none appearance-none"
            style={{ 
              minHeight: '24px', 
              border: 'none !important', 
              outline: 'none !important',
              boxShadow: 'none !important',
              WebkitAppearance: 'none',
              MozAppearance: 'none',
              appearance: 'none'
            }}
          />

          {/* Character count */}
          {message.length > 0 && (
            <div className="flex-shrink-0 text-xs text-slate-400 dark:text-slate-500 font-medium">
              <span className={message.length >= 1000 ? 'text-red-500 font-bold' : ''}>
                {message.length}/1000
              </span>
            </div>
          )}

          {/* Voice input button */}
          {voiceSupported && (
            <button
              type="button"
              onClick={handleVoiceToggle}
              disabled={isInputDisabled}
              onMouseEnter={() => setIsHoveringMic(true)}
              onMouseLeave={() => setIsHoveringMic(false)}
              className={`flex-shrink-0 p-2 transition-all duration-200 rounded-lg ${
                isListening
                  ? 'text-red-500 bg-red-50 dark:text-red-400 dark:bg-red-900/20 shadow-sm transform scale-110'
                  : isInputDisabled
                  ? 'text-slate-300 dark:text-slate-600 cursor-not-allowed opacity-50'
                  : 'text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 hover:scale-110'
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
                <MicOff className="w-5 h-5" />
              ) : (
                <Mic className="w-5 h-5" />
              )}
            </button>
          )}

          {/* Processing indicator (spinning icon) */}
          {(hasProcessingFiles || isUploading) && (
            <div className="flex-shrink-0 flex items-center justify-center">
              <Loader2 className="w-5 h-5 text-amber-500 dark:text-amber-400 animate-spin" />
            </div>
          )}

          {/* Send button */}
          <button
            type="submit"
            disabled={(!message.trim() && attachedFiles.length === 0) || isInputDisabled || isComposing}
            className={`flex-shrink-0 px-4 py-2 rounded-xl transition-all duration-200 font-semibold ${
              (message.trim() || attachedFiles.length > 0) && !isInputDisabled && !isComposing
                ? 'bg-slate-800 dark:bg-emerald-500 text-white shadow-[0_14px_40px_rgba(15,23,42,0.25)] dark:shadow-[0_14px_40px_rgba(16,185,129,0.35)] hover:bg-slate-900 dark:hover:bg-emerald-600 hover:-translate-y-0.5 active:translate-y-0'
                : 'bg-slate-200 dark:bg-slate-700 text-slate-400 dark:text-slate-500 cursor-not-allowed'
            }`}
            title="Send message"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>

        {/* Attached files preview */}
        {attachedFiles.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {attachedFiles.map((file) => (
              <div
                key={file.file_id}
                className="flex items-center gap-2 px-3 py-1.5 bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-700 rounded-lg"
              >
                <span className="text-xs font-medium text-emerald-700 dark:text-emerald-300 truncate max-w-[150px]">
                  {file.filename}
                </span>
                {!disabled && (
                  <button
                    onClick={() => handleRemoveFile(file.file_id)}
                    className="p-0.5 text-emerald-600 dark:text-emerald-400 hover:text-red-600 dark:hover:text-red-400 transition-colors"
                    title="Remove file"
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {/* File upload component */}
        {showFileUpload && (
          <div className="mt-4 mb-2 w-full max-w-full overflow-visible p-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl shadow-lg">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs sm:text-sm font-semibold text-slate-700 dark:text-slate-300">
                Upload Files
              </h3>
              <button
                onClick={() => setShowFileUpload(false)}
                className="p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
                title="Close"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="w-full overflow-visible pb-1">
              <FileUpload
                onFilesSelected={handleFilesSelected}
                onUploadError={(error) => {
                  console.error('File upload error:', error);
                  // Could show toast notification here
                }}
                onUploadingChange={setIsUploading}
                maxFiles={5}
                disabled={isInputDisabled}
              />
            </div>
          </div>
        )}

        {/* Hints */}
        <div className="h-4 mt-3 px-1">
          {isListening && (
            <span className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400 font-medium">
              <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></span>
              <span>Listening...</span>
            </span>
          )}
        </div>
      </form>
    </div>
  );
}
