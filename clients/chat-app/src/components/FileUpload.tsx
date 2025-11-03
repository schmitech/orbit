import React, { useState, useRef, useCallback, useEffect } from 'react';
import { Upload, X, Loader2 } from 'lucide-react';
import { FileAttachment } from '../types';
import { FileUploadService, FileUploadProgress } from '../services/fileService';
import { useChatStore } from '../stores/chatStore';

interface FileUploadProps {
  onFilesSelected: (files: FileAttachment[]) => void;
  onUploadError?: (error: string) => void;
  onClose?: () => void;
  onUploadingChange?: (isUploading: boolean) => void;
  maxFiles?: number;
  disabled?: boolean;
}

export function FileUpload({ 
  onFilesSelected, 
  onUploadError,
  onClose,
  onUploadingChange,
  maxFiles = 5,
  disabled = false 
}: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploadingFiles, setUploadingFiles] = useState<Map<string, FileUploadProgress>>(new Map());
  const [uploadedFiles, setUploadedFiles] = useState<FileAttachment[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploadedFileIdsRef = useRef<Set<string>>(new Set());
  const abortControllersRef = useRef<Map<string, AbortController>>(new Map());
  const isMountedRef = useRef<boolean>(true);
  
  const { currentConversationId, removeFileFromConversation } = useChatStore();

  // Notify parent component when upload status changes
  useEffect(() => {
    const isUploading = uploadingFiles.size > 0;
    onUploadingChange?.(isUploading);
  }, [uploadingFiles, onUploadingChange]);

  // Notify parent component when uploaded files change
  // Use a ref to track previous length to avoid unnecessary updates
  const prevUploadedFilesLengthRef = useRef(0);
  
  useEffect(() => {
    // Only notify if the length actually changed
    if (uploadedFiles.length !== prevUploadedFilesLengthRef.current) {
      prevUploadedFilesLengthRef.current = uploadedFiles.length;
      
      console.log(`[FileUpload] Notifying parent about ${uploadedFiles.length} files:`, uploadedFiles);
      onFilesSelected(uploadedFiles);
      
      // When files are selected and parent adds them to conversation,
      // remove them from cleanup tracking (they're now safely in conversation)
      if (uploadedFiles.length > 0 && currentConversationId) {
        setTimeout(() => {
          // Check mount status inside timeout
          if (isMountedRef.current) {
            const store = useChatStore.getState();
            const conversation = store.conversations.find(conv => conv.id === currentConversationId);
            const filesInConversation = new Set(
              conversation?.attachedFiles?.map(f => f.file_id) || []
            );
            
            // Remove files that are now in conversation from cleanup tracking
            uploadedFiles.forEach(file => {
              if (filesInConversation.has(file.file_id)) {
                uploadedFileIdsRef.current.delete(file.file_id);
              }
            });
          }
        }, 100); // Small delay to allow conversation update to complete
      }
    }
  }, [uploadedFiles.length, onFilesSelected, currentConversationId]); // Only depend on length

  // Track mount status
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // Cleanup: Delete uploaded files from server when component unmounts
  // Only delete files that aren't already in the conversation
  useEffect(() => {
    return () => {
      // Mark as unmounting to stop any ongoing operations
      isMountedRef.current = false;
      
      // Cancel any ongoing uploads
      abortControllersRef.current.forEach(controller => {
        controller.abort();
      });
      
      // Wait a moment to allow any pending conversation updates to complete
      // This prevents race condition where files are added to conversation asynchronously
      // We use a slightly longer delay to ensure async operations complete
      setTimeout(() => {
        // Get current conversation to check which files are already added
        const store = useChatStore.getState();
        const conversation = store.conversations.find(conv => conv.id === store.currentConversationId);
        const filesInConversation = new Set(
          conversation?.attachedFiles?.map(f => f.file_id) || []
        );
        
        // Delete only files that aren't in the conversation
        // Double-check by looking at both uploadedFileIdsRef AND actual conversation state
        // Files that are in the conversation should NOT be deleted, even if still in uploadedFileIdsRef
        const fileIdsToDelete = Array.from(uploadedFileIdsRef.current).filter(
          fileId => {
            // Don't delete if file is in conversation
            if (filesInConversation.has(fileId)) {
              // Remove from tracking since it's safely in conversation
              uploadedFileIdsRef.current.delete(fileId);
              return false;
            }
            return true;
          }
        );
        
        if (fileIdsToDelete.length > 0) {
          // Notify parent that we're cleaning up
          if (onClose) {
            onClose();
          }
          
          // Delete files from server
          fileIdsToDelete.forEach(async (fileId) => {
            try {
              if (store.currentConversationId) {
                // Try to remove from conversation first (handles server deletion)
                const fileInUploadedList = uploadedFiles.find(f => f.file_id === fileId);
                if (fileInUploadedList) {
                  await removeFileFromConversation(store.currentConversationId, fileId);
                } else {
                  // File was uploaded but not in uploadedFiles, delete directly
                  await FileUploadService.deleteFile(fileId);
                }
              } else {
                // Just delete from server if no conversation
                await FileUploadService.deleteFile(fileId);
              }
            } catch (error: any) {
              // Silently handle errors during cleanup (including 404s)
              if (!error.message?.includes('404') && !error.message?.includes('File not found')) {
                console.warn(`Failed to cleanup file ${fileId} during component unmount:`, error);
              }
            }
          });
        }
      }, 300); // Longer delay to ensure async conversation updates complete
    };
  }, [currentConversationId, removeFileFromConversation, uploadedFiles, onClose]);

  const handleFiles = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    const fileArray = Array.from(files);
    
    // Limit number of files
    if (uploadedFiles.length + fileArray.length > maxFiles) {
      const error = `Maximum ${maxFiles} files allowed. Please remove some files first.`;
      onUploadError?.(error);
      return;
    }

    // Process each file
    const newFiles: FileAttachment[] = [];
    for (const file of fileArray) {
      // Create abort controller for this upload (though uploadFile doesn't support abort yet)
      const abortController = new AbortController();
      abortControllersRef.current.set(file.name, abortController);
      
      let uploadedFileId: string | null = null;
      
      try {
        // Upload file and get the full response with correct file_size from server
        // Note: We allow upload to proceed even if component unmounts, cleanup will handle orphaned files
        const uploadedAttachment = await FileUploadService.uploadFile(file, (progress) => {
          // Only update state if component is still mounted (to avoid React warnings)
          if (isMountedRef.current) {
            setUploadingFiles(prev => new Map(prev.set(file.name, progress)));
          }
          // Track file ID once we get it (even if unmounted, for cleanup purposes)
          if (progress.fileId) {
            uploadedFileId = progress.fileId;
            uploadedFileIdsRef.current.add(progress.fileId);
          }
        }).catch(error => {
          // If file was deleted during upload, handle gracefully
          if (error.message && error.message.includes('was deleted')) {
            // File was deleted during upload - remove from tracking if we have the ID
            if (uploadedFileId) {
              uploadedFileIdsRef.current.delete(uploadedFileId);
            }
            // Extract file ID from error message if available
            const fileIdMatch = error.message.match(/File\s+([\w-]+)\s+was deleted/);
            if (fileIdMatch && fileIdMatch[1]) {
              uploadedFileIdsRef.current.delete(fileIdMatch[1]);
            }
            console.log(`File ${file.name} was deleted during upload`);
            return null;
          }
          throw error;
        });

        // Add completed file to list using the response from server (has correct file_size)
        // Always add to newFiles so files are included even if component unmounts during upload
        if (uploadedAttachment) {
          if (!uploadedFileId || uploadedFileId !== uploadedAttachment.file_id) {
            uploadedFileIdsRef.current.add(uploadedAttachment.file_id);
          }
          newFiles.push(uploadedAttachment);
          console.log(`File ${file.name} uploaded successfully, added to list:`, uploadedAttachment);
        } else {
          console.warn(`Upload completed for ${file.name} but uploadedAttachment is null`);
        }
      } catch (error: any) {
        // If error is from abort or component unmounted, don't show error message
        if (error.name === 'AbortError' || abortController.signal.aborted || !isMountedRef.current) {
          console.log(`Upload cancelled for ${file.name}`);
          // Remove from tracking if we have the ID
          if (uploadedFileId) {
            uploadedFileIdsRef.current.delete(uploadedFileId);
          }
          continue;
        }
        // If file was deleted during upload, handle gracefully
        if (error.message && error.message.includes('was deleted')) {
          console.log(`File ${file.name} was deleted during upload`);
          // Remove from tracking since it's already deleted
          if (uploadedFileId) {
            uploadedFileIdsRef.current.delete(uploadedFileId);
          }
          // Try to extract file ID from error message
          const fileIdMatch = error.message.match(/File\s+([\w-]+)\s+was deleted/);
          if (fileIdMatch && fileIdMatch[1]) {
            uploadedFileIdsRef.current.delete(fileIdMatch[1]);
          }
          continue;
        }
        // Only show error if component is still mounted
        if (isMountedRef.current) {
          console.error(`Failed to upload file ${file.name}:`, error);
          console.error(`File type: ${file.type}, File name: ${file.name}`);
          onUploadError?.(error.message || `Failed to upload ${file.name}`);
        } else {
          // Log even if unmounted for debugging
          console.warn(`Upload error for ${file.name} (component unmounted):`, error.message);
        }
        // Remove from tracking on error
        if (uploadedFileId) {
          uploadedFileIdsRef.current.delete(uploadedFileId);
        }
      } finally {
        // Clean up abort controller
        abortControllersRef.current.delete(file.name);
        // Only update state if component is still mounted
        if (isMountedRef.current) {
          setUploadingFiles(prev => {
            const next = new Map(prev);
            next.delete(file.name);
            return next;
          });
        }
      }
    }
    
    // Update uploaded files list with all new files
    // The useEffect hook will call onFilesSelected when uploadedFiles changes
    // Always update state - this will trigger the useEffect to notify parent
    if (newFiles.length > 0) {
      setUploadedFiles(prev => {
        const existingIds = new Set(prev.map(f => f.file_id));
        const filesToAdd = newFiles.filter(f => !existingIds.has(f.file_id));
        if (filesToAdd.length > 0) {
          const updated = [...prev, ...filesToAdd];
          console.log(`[FileUpload] Updated uploadedFiles: ${updated.length} files`, updated);
          return updated;
        }
        return prev;
      });
    }
  }, [maxFiles, onFilesSelected, onUploadError, onUploadingChange]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!disabled) {
      setIsDragging(true);
    }
  }, [disabled]);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    if (disabled) return;

    const files = e.dataTransfer.files;
    handleFiles(files);
  }, [disabled, handleFiles]);

  const handleFileInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    handleFiles(files);
    // Reset input so same file can be selected again
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, [handleFiles]);

  const handleRemoveFile = useCallback(async (fileId: string) => {
    console.log(`[FileUpload] handleRemoveFile called for file ${fileId}`, {
      currentConversationId,
      hasRemoveFileFromConversation: !!removeFileFromConversation
    });
    
    // Remove from local list first
    setUploadedFiles(prev => prev.filter(f => f.file_id !== fileId));
    
    // Remove from tracking ref
    uploadedFileIdsRef.current.delete(fileId);
    
    // Remove from conversation and delete from server if conversation exists
    if (currentConversationId) {
      try {
        console.log(`[FileUpload] Calling removeFileFromConversation for ${fileId}`);
        await removeFileFromConversation(currentConversationId, fileId);
        console.log(`[FileUpload] Successfully removed file ${fileId} from conversation`);
      } catch (error) {
        console.error(`[FileUpload] Failed to remove file ${fileId} from conversation:`, error);
        // File is already removed from local list, so continue
      }
    } else {
      // If no conversation, just delete from server
      try {
        console.log(`[FileUpload] Calling FileUploadService.deleteFile for ${fileId}`);
        await FileUploadService.deleteFile(fileId);
        console.log(`[FileUpload] Successfully deleted file ${fileId} from server`);
      } catch (error) {
        console.error(`[FileUpload] Failed to delete file ${fileId} from server:`, error);
      }
    }
  }, [currentConversationId, removeFileFromConversation]);

  const handleClick = useCallback(() => {
    if (!disabled && fileInputRef.current) {
      fileInputRef.current.click();
    }
  }, [disabled]);

  const getFileIcon = (mimeType: string) => {
    if (mimeType.startsWith('image/')) return '🖼️';
    if (mimeType.startsWith('audio/')) return '🎵';
    if (mimeType.includes('pdf')) return '📄';
    if (mimeType.includes('word') || mimeType.includes('document')) return '📝';
    if (mimeType.includes('spreadsheet') || mimeType.includes('excel')) return '📊';
    return '📎';
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  // Hide upload area when files are uploading OR when files have been uploaded
  const isUploading = uploadingFiles.size > 0;
  const hasUploadedFiles = uploadedFiles.length > 0;

  return (
    <div className="w-full max-w-full overflow-hidden space-y-3">
      {/* Upload area - only show when not uploading AND no files uploaded yet */}
      {!isUploading && !hasUploadedFiles && (
        <div
          onClick={handleClick}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`
            relative w-full max-w-full border-2 border-dashed rounded-xl p-3 sm:p-4 transition-all cursor-pointer
            ${isDragging 
              ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-900/20 dark:border-emerald-400' 
              : disabled
              ? 'border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 cursor-not-allowed opacity-50'
              : 'border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900/50 hover:border-emerald-400 hover:bg-emerald-50/30 dark:hover:bg-emerald-900/10'
            }
          `}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            onChange={handleFileInputChange}
            className="hidden"
            disabled={disabled}
            accept=".pdf,.doc,.docx,.txt,.md,.csv,.json,.html,.pptx,.xlsx,.png,.jpg,.jpeg,.tiff,.wav,.mp3,.vtt"
          />
          
          <div className="flex flex-col items-center justify-center gap-2 text-center">
            <Upload className={`w-6 h-6 ${isDragging ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-400 dark:text-slate-500'}`} />
            <div className="px-2">
              <p className="text-xs sm:text-sm font-medium text-slate-700 dark:text-slate-300">
                {disabled ? 'File upload disabled' : isDragging ? 'Drop files here' : 'Click or drag files to upload'}
              </p>
              <p className="text-[10px] sm:text-xs text-slate-500 dark:text-slate-400 mt-0.5 px-1">
                PDF, DOCX, TXT, CSV, JSON, HTML, images, audio (max {maxFiles} files)
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Upload progress - show when uploading */}
      {isUploading && (
        <div className="w-full max-w-full overflow-hidden space-y-2">
          {Array.from(uploadingFiles.values()).map((progress) => (
            <div key={progress.filename} className="w-full max-w-full flex items-center gap-3 p-3 bg-slate-50 dark:bg-slate-800/50 rounded-lg overflow-hidden">
              <Loader2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 animate-spin flex-shrink-0" />
              <div className="flex-1 min-w-0 overflow-hidden">
                <p className="text-sm font-medium text-slate-700 dark:text-slate-300 truncate">
                  {progress.filename}
                </p>
                <div className="mt-1 bg-slate-200 dark:bg-slate-700 rounded-full h-1.5">
                  <div
                    className="bg-emerald-600 dark:bg-emerald-400 h-1.5 rounded-full transition-all duration-300"
                    style={{ width: `${progress.progress}%` }}
                  />
                </div>
              </div>
              <span className="text-xs text-slate-500 dark:text-slate-400">
                {progress.status === 'uploading' ? 'Uploading...' :
                 progress.status === 'processing' ? 'Processing...' :
                 progress.status === 'completed' ? 'Done' : 'Error'}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Uploaded files are shown in MessageInput's attachedFiles pills above, not here */}
    </div>
  );
}

