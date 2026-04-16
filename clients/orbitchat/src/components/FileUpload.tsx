import React, { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import { Upload, Loader2, CircleAlert } from 'lucide-react';
import { FileAttachment } from '../types';
import { FileUploadService, FileUploadProgress } from '../services/fileService';
import { useChatStore } from '../stores/chatStore';
import { getIsAuthenticated } from '../auth/authState';
import { useLoginPromptStore } from '../stores/loginPromptStore';
import { debugLog, debugWarn, debugError } from '../utils/debug';
import { AppConfig } from '../utils/config';
import { getIsAuthConfigured, resolveApiUrl } from '../utils/runtimeConfig';

// Persist upload state across component re-mounts and conversation switches
const uploadingFilesStore = new Map<string, Map<string, FileUploadProgress>>();
const uploadedFilesStore = new Map<string, FileAttachment[]>();
const uploadedFileIdsStore = new Map<string, string>();
const seenConversationFileIdsStore = new Set<string>();

const getStoredAdapterName = (): string | null => {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    return localStorage.getItem('chat-adapter-name');
  } catch {
    return null;
  }
};

const isErrorWithMessage = (error: unknown): error is { message?: string } => {
  return typeof error === 'object' && error !== null && 'message' in error;
};

const getErrorMessage = (error: unknown): string => {
  if (error instanceof Error) return error.message;
  if (typeof error === 'string') return error;
  if (isErrorWithMessage(error)) return error.message ?? 'Unknown error';
  return 'Unknown error';
};

interface FileUploadProps {
  conversationId: string | null;
  onFilesSelected: (conversationId: string | null, files: FileAttachment[]) => void;
  onUploadError?: (error: string) => void;
  onClose?: () => void;
  onUploadingChange?: (conversationId: string | null, isUploading: boolean) => void;
  onUploadSuccess?: (conversationId: string, newFiles: FileAttachment[]) => void;
  maxFiles?: number;
  disabled?: boolean;
}

export function FileUpload({ 
  conversationId,
  onFilesSelected, 
  onUploadError,
  onClose,
  onUploadingChange,
  onUploadSuccess,
  maxFiles = AppConfig.maxFilesPerConversation,
  disabled = false 
}: FileUploadProps): React.ReactElement {
  const [isDragging, setIsDragging] = useState(false);
  const [globalUploadRevision, setGlobalUploadRevision] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploadedFileIdsRef = useRef<Map<string, string>>(uploadedFileIdsStore);
  const seenConversationFileIdsRef = useRef<Set<string>>(seenConversationFileIdsStore);
  const abortControllersRef = useRef<Map<string, AbortController>>(new Map());
  const isMountedRef = useRef<boolean>(true);
  const uploadingFilesStoreRef = useRef<Map<string, Map<string, FileUploadProgress>>>(uploadingFilesStore);
  const uploadedFilesStoreRef = useRef<Map<string, FileAttachment[]>>(uploadedFilesStore);
  const latestConversationIdRef = useRef<string | null>(conversationId);
  const conversations = useChatStore(state => state.conversations);

  const uploadingFiles = useMemo(() => {
    void globalUploadRevision;
    if (!conversationId) {
      return new Map<string, FileUploadProgress>();
    }
    const uploads = uploadingFilesStoreRef.current.get(conversationId);
    return uploads ? new Map(uploads) : new Map<string, FileUploadProgress>();
  }, [conversationId, globalUploadRevision]);

  const refreshVisibleUploads = useCallback((targetConversationId: string | null) => {
    if (!targetConversationId) {
      onUploadingChange?.(null, false);
      setGlobalUploadRevision(prev => prev + 1);
      return;
    }
    const uploads = uploadingFilesStoreRef.current.get(targetConversationId) || new Map<string, FileUploadProgress>();

    // Also check if there are files in the conversation that are still processing
    // This handles the case where user switched conversations during upload
    const conversation = conversations.find(conv => conv.id === targetConversationId);
    if (conversation && conversation.attachedFiles) {
      // Build a set of file IDs that are no longer processing (completed, failed, error)
      const finishedFileIds = new Set(
        conversation.attachedFiles
          .filter(f => f.processing_status === 'completed' || f.processing_status === 'failed' || f.processing_status === 'error')
          .map(f => f.file_id)
      );

      const processingFiles = conversation.attachedFiles.filter(f =>
        !f.processing_status ||
        f.processing_status === 'processing' ||
        f.processing_status === 'uploading'
      );

      // Merge existing uploads with processing files from conversation
      // This ensures we show progress even if upload progress was lost
      const mergedUploads = new Map(uploads);
      let hasNewUploads = false;

      // Remove progress entries for files that are no longer processing
      mergedUploads.forEach((progress, key) => {
        if (progress.fileId && finishedFileIds.has(progress.fileId)) {
          mergedUploads.delete(key);
        }
      });

      processingFiles.forEach(file => {
        // Check if we already have progress for this file
        const existingProgress = Array.from(mergedUploads.values()).find(p => p.fileId === file.file_id);

        if (!existingProgress) {
          // Create progress entry for this processing file
          const progressKey = `${targetConversationId}-${file.filename}-${file.file_id}`;
          mergedUploads.set(progressKey, {
            filename: file.filename,
            progress: file.processing_status === 'uploading' ? 50 : 90, // Estimate progress
            status: (file.processing_status as 'uploading' | 'processing') || 'processing',
            fileId: file.file_id
          });
          hasNewUploads = true;
        }
      });

      if (hasNewUploads || mergedUploads.size > 0) {
        uploadingFilesStoreRef.current.set(targetConversationId, mergedUploads);
        onUploadingChange?.(targetConversationId, true);
      } else {
        uploadingFilesStoreRef.current.delete(targetConversationId);
        onUploadingChange?.(targetConversationId, false);
      }
    } else {
      // No conversation or no processing files - just use existing uploads
      if (uploads.size > 0) {
        uploadingFilesStoreRef.current.set(targetConversationId, uploads);
      } else {
        uploadingFilesStoreRef.current.delete(targetConversationId);
      }
      onUploadingChange?.(targetConversationId, uploads.size > 0);
    }
    setGlobalUploadRevision(prev => prev + 1);
  }, [conversations, onUploadingChange]);

  useEffect(() => {
    latestConversationIdRef.current = conversationId;
    refreshVisibleUploads(conversationId);
  }, [conversationId, refreshVisibleUploads]);

  // Also refresh when conversations update (in case files were added/updated)
  useEffect(() => {
    if (conversationId) {
      refreshVisibleUploads(conversationId);
    }
  }, [conversations, conversationId, refreshVisibleUploads]);

  const updateUploadingStore = useCallback((targetConversationId: string, updater: (prev: Map<string, FileUploadProgress>) => Map<string, FileUploadProgress>) => {
    if (!targetConversationId) {
      return;
    }
    const previous = uploadingFilesStoreRef.current.get(targetConversationId) || new Map<string, FileUploadProgress>();
    const next = updater(new Map(previous));
    if (next.size > 0) {
      uploadingFilesStoreRef.current.set(targetConversationId, next);
    } else {
      uploadingFilesStoreRef.current.delete(targetConversationId);
    }
    onUploadingChange?.(targetConversationId, next.size > 0);
    setGlobalUploadRevision(prev => prev + 1);
  }, [onUploadingChange]);

  const updateUploadedStore = useCallback((targetConversationId: string, updater: (prev: FileAttachment[]) => FileAttachment[]) => {
    if (!targetConversationId) {
      return;
    }
    const previous = uploadedFilesStoreRef.current.get(targetConversationId) || [];
    const next = updater([...(previous || [])]);
    const previousIds = new Set(previous.map(f => f.file_id));
    uploadedFilesStoreRef.current.set(targetConversationId, next);
    onFilesSelected(targetConversationId, next);
    if (onUploadSuccess) {
      const newFiles = next.filter(file => !previousIds.has(file.file_id));
      if (newFiles.length > 0) {
        onUploadSuccess(targetConversationId, newFiles);
      }
    }
    setGlobalUploadRevision(prev => prev + 1);
  }, [onFilesSelected, onUploadSuccess]);
  
  const removeFileFromConversation = useChatStore(state => state.removeFileFromConversation);
  const addFileToConversation = useChatStore(state => state.addFileToConversation);

  // Track mount status
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const cleanupPendingUploads = useCallback(() => {
    isMountedRef.current = false;
    const abortControllers = new Map(abortControllersRef.current);
    abortControllers.forEach(controller => controller.abort());

    setTimeout(() => {
      const store = useChatStore.getState();
      const conversationsById = new Map(store.conversations.map(conv => [conv.id, conv]));
      const fileIdsToDelete: Array<{ fileId: string; conversationId: string | null }> = [];

      uploadedFileIdsRef.current.forEach((convId, fileId) => {
        if (convId) {
          const conversation = conversationsById.get(convId);
          const filesInConversation = new Set(
            conversation?.attachedFiles?.map(f => f.file_id) || []
          );
          if (filesInConversation.has(fileId)) {
            seenConversationFileIdsRef.current.add(fileId);
            uploadedFileIdsRef.current.delete(fileId);
            return;
          }
        }
        if (seenConversationFileIdsRef.current.has(fileId)) {
          debugLog(`[FileUpload] Skipping cleanup delete for ${fileId}; file was previously attached and already handled`);
          uploadedFileIdsRef.current.delete(fileId);
          seenConversationFileIdsRef.current.delete(fileId);
          return;
        }
        fileIdsToDelete.push({ fileId, conversationId: convId || null });
      });

      if (fileIdsToDelete.length > 0) {
        onClose?.();
        fileIdsToDelete.forEach(async ({ fileId, conversationId }) => {
          try {
            if (conversationId) {
              await removeFileFromConversation(conversationId, fileId);
            } else {
              const adapterName = getStoredAdapterName();
              await FileUploadService.deleteFile(fileId, undefined, undefined, adapterName ?? undefined);
            }
          } catch (error) {
            if (isErrorWithMessage(error)) {
              const message = error.message ?? '';
              if (!message.includes('404') && !message.includes('File not found')) {
                debugWarn(`Failed to cleanup file ${fileId} during component unmount:`, error);
              }
            } else {
              debugWarn(`Failed to cleanup file ${fileId} during component unmount`, error);
            }
          }
        });
      }
    }, 300);
  }, [onClose, removeFileFromConversation]);

  // Cleanup: Delete uploaded files from server when component unmounts
  // Only delete files that aren't already in the conversation
  useEffect(() => cleanupPendingUploads, [cleanupPendingUploads]);

  const handleFiles = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    const fileArray = Array.from(files);
    const store = useChatStore.getState();
    const activeConversationId = conversationId || store.currentConversationId;

    if (!activeConversationId) {
      onUploadError?.('Please select or create a conversation before uploading files.');
      return;
    }

    const conversation = store.conversations.find(conv => conv.id === activeConversationId);
    if (!conversation) {
      onUploadError?.('Conversation not found. Please try again.');
      return;
    }

    const existingUploads = uploadedFilesStoreRef.current.get(activeConversationId) || [];
    if (existingUploads.length + fileArray.length > maxFiles) {
      const error = `Maximum ${maxFiles} files allowed per conversation. Please remove some files first.`;
      if (getIsAuthConfigured() && !getIsAuthenticated()) {
        useLoginPromptStore.getState().openLoginPrompt(
          `You've reached the guest limit of ${maxFiles} files per conversation. Sign in to upload more files.`
        );
      }
      onUploadError?.(error);
      return;
    }

    if (AppConfig.maxTotalFiles !== null) {
      const totalFilesAcrossConversations = store.conversations.reduce(
        (total, conv) => total + (conv.attachedFiles?.length || 0),
        0
      );
      const projectedTotal = totalFilesAcrossConversations + fileArray.length;
      if (projectedTotal > AppConfig.maxTotalFiles) {
        const error = `Maximum ${AppConfig.maxTotalFiles} total files allowed across all conversations. Please remove some files from other conversations first.`;
        if (getIsAuthConfigured() && !getIsAuthenticated()) {
          useLoginPromptStore.getState().openLoginPrompt(
            `You've reached the guest limit of ${AppConfig.maxTotalFiles} total files. Sign in to upload more files.`
          );
        }
        onUploadError?.(error);
        return;
      }
    }

    if (!conversation.adapterName) {
      onUploadError?.('Adapter not configured for this conversation. Please select an adapter first.');
      return;
    }

    const conversationAdapterName = conversation.adapterName;
    const conversationApiUrl = resolveApiUrl(conversation.apiUrl);

    for (let index = 0; index < fileArray.length; index++) {
      const file = fileArray[index];
      const abortController = new AbortController();
      abortControllersRef.current.set(file.name, abortController);
      const progressKey = `${activeConversationId}-${file.name}-${Date.now()}-${index}`;
      let uploadedFileId: string | null = null;

      try {
        const uploadedAttachment = await FileUploadService.uploadFile(
          file,
          (progress) => {
            updateUploadingStore(activeConversationId, (prev) => {
              prev.set(progressKey, progress);
              return prev;
            });

            if (progress.fileId && !uploadedFileId) {
              uploadedFileId = progress.fileId;
              uploadedFileIdsRef.current.set(progress.fileId, activeConversationId);
              seenConversationFileIdsRef.current.add(progress.fileId);

              // Add file to conversation immediately when we get the fileId
              // This ensures the file persists even if user switches conversations
              const fileAttachment: FileAttachment = {
                file_id: progress.fileId,
                filename: file.name,
                mime_type: file.type || 'application/octet-stream',
                file_size: file.size,
                processing_status: progress.status === 'uploading' ? 'uploading' :
                                  progress.status === 'processing' ? 'processing' :
                                  progress.status === 'completed' ? 'completed' : undefined
              };

              debugLog(`[FileUpload] Adding file ${progress.fileId} to conversation ${activeConversationId} immediately (status: ${fileAttachment.processing_status})`);
              addFileToConversation(activeConversationId, fileAttachment);
            }
          },
          undefined,
          conversationApiUrl,
          conversationAdapterName
        ).catch(error => {
          if (error.message && error.message.includes('was deleted')) {
            if (uploadedFileId) {
              uploadedFileIdsRef.current.delete(uploadedFileId);
            }
            const fileIdMatch = error.message.match(/File\s+([\w-]+)\s+was deleted/);
            if (fileIdMatch && fileIdMatch[1]) {
              uploadedFileIdsRef.current.delete(fileIdMatch[1]);
            }
            debugLog(`File ${file.name} was deleted during upload`);
            return null;
          }
          throw error;
        });

        if (uploadedAttachment) {
          uploadedFileIdsRef.current.set(uploadedAttachment.file_id, activeConversationId);
          seenConversationFileIdsRef.current.add(uploadedAttachment.file_id);
          
          // Update the file in the conversation with final status
          // The file was already added during upload progress, now update it with complete info
          debugLog(`[FileUpload] Updating file ${uploadedAttachment.file_id} in conversation ${activeConversationId} with final status`);
          addFileToConversation(activeConversationId, uploadedAttachment);
          
          // Remove progress if file is completed or failed; keep only for still-processing files
          const fileFinished = uploadedAttachment.processing_status === 'completed' ||
            uploadedAttachment.processing_status === 'failed' ||
            uploadedAttachment.processing_status === 'error';
          if (fileFinished) {
            updateUploadingStore(activeConversationId, (prev) => {
              prev.delete(progressKey);
              return prev;
            });
          } else {
            // File is still processing - update progress to show processing status
            updateUploadingStore(activeConversationId, (prev) => {
              const existing = prev.get(progressKey);
              if (existing) {
                prev.set(progressKey, {
                  ...existing,
                  progress: 90,
                  status: 'processing',
                  fileId: uploadedAttachment.file_id
                });
              }
              return prev;
            });
          }
          
          updateUploadedStore(activeConversationId, (prev) => {
            const existingIds = new Set(prev.map(f => f.file_id));
            if (existingIds.has(uploadedAttachment.file_id)) {
              return prev;
            }
            const updated = [...prev, uploadedAttachment];
            debugLog(`[FileUpload] Updated uploadedFiles for ${activeConversationId}: ${updated.length} files`, updated);
            return updated;
          });
        } else {
          debugWarn(`Upload completed for ${file.name} but uploadedAttachment is null`);
          // Remove progress on error
          updateUploadingStore(activeConversationId, (prev) => {
            prev.delete(progressKey);
            return prev;
          });
        }
      } catch (error) {
        const message = getErrorMessage(error);
        if ((error instanceof DOMException && error.name === 'AbortError') || abortController.signal.aborted) {
          debugLog(`Upload cancelled for ${file.name}`);
          if (uploadedFileId) {
            uploadedFileIdsRef.current.delete(uploadedFileId);
          }
          continue;
        }
        if (message.includes('was deleted')) {
          debugLog(`File ${file.name} was deleted during upload`);
          if (uploadedFileId) {
            uploadedFileIdsRef.current.delete(uploadedFileId);
          }
          const fileIdMatch = message.match(/File\s+([\w-]+)\s+was deleted/);
          if (fileIdMatch && fileIdMatch[1]) {
            uploadedFileIdsRef.current.delete(fileIdMatch[1]);
          }
          continue;
        }
        if (isMountedRef.current) {
          debugError(`Failed to upload file ${file.name}:`, error);
          debugError(`File type: ${file.type}, File name: ${file.name}`);
          onUploadError?.(message || `Failed to upload ${file.name}`);
        } else {
          debugWarn(`Upload error for ${file.name} (component unmounted):`, message);
        }
        if (uploadedFileId) {
          uploadedFileIdsRef.current.delete(uploadedFileId);
        }
      } finally {
        abortControllersRef.current.delete(file.name);
        // Don't remove progress here - it's handled above based on file status
        // Progress will be removed when file completes or on error
      }
    }
  }, [addFileToConversation, conversationId, maxFiles, onUploadError, updateUploadedStore, updateUploadingStore]);

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

  const handleClick = useCallback(() => {
    if (!disabled && fileInputRef.current) {
      fileInputRef.current.click();
    }
  }, [disabled]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleClick();
    }
  }, [disabled, handleClick]);

  // While uploads are active, show only progress and hide the upload dropzone.
  const isUploading = uploadingFiles.size > 0;
  const conversationNameMap = useMemo(() => {
    const map = new Map<string, string>();
    conversations.forEach(conv => {
      map.set(conv.id, conv.title || 'Conversation');
    });
    return map;
  }, [conversations]);

  const otherUploadingConversations = useMemo(() => {
    void globalUploadRevision;
    const entries: Array<{ conversationId: string; uploads: Array<{ key: string; progress: FileUploadProgress }> }> = [];
    uploadingFilesStoreRef.current.forEach((progressMap, convId) => {
      if (convId !== conversationId && progressMap.size > 0) {
        entries.push({
          conversationId: convId,
          uploads: Array.from(progressMap.entries()).map(([key, progress]) => ({ key, progress }))
        });
      }
    });
    return entries;
  }, [conversationId, globalUploadRevision]);

  const renderProgressRow = (progress: FileUploadProgress, key: string) => {
    const isError = progress.status === 'error';
    return (
      <div
        key={key}
        className={`group relative w-full flex items-center gap-3 rounded-lg px-3 py-2.5 overflow-hidden transition-colors ${
          isError ? 'bg-red-50 dark:bg-red-950/30' : 'bg-gray-50 dark:bg-[#1f1f24]'
        }`}
      >
        {/* Animated progress background fill */}
        {!isError && (
          <div
            className="absolute inset-0 bg-blue-50 dark:bg-blue-900/15 transition-all duration-500 ease-out rounded-lg"
            style={{ width: `${progress.progress}%` }}
          />
        )}
        <div className="relative flex items-center gap-3 w-full min-w-0">
          <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md ${
            isError ? 'bg-red-100 dark:bg-red-900/30' : 'bg-blue-100 dark:bg-blue-900/30'
          }`}>
            {isError ? (
              <CircleAlert className="h-4 w-4 text-red-500 dark:text-red-400" />
            ) : (
              <Loader2 className="h-4 w-4 text-blue-600 dark:text-blue-400 animate-spin" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-[#353740] dark:text-[#ececf1] truncate">
              {progress.filename}
            </p>
            {isError ? (
              <p className="mt-0.5 text-xs text-red-600 dark:text-red-400 truncate">
                {progress.error || 'Processing failed'}
              </p>
            ) : (
              <div className="mt-1 flex items-center gap-2">
                <div className="flex-1 bg-gray-200 dark:bg-[#3c3f4a] rounded-full h-1">
                  <div
                    className="bg-blue-500 dark:bg-blue-400 h-1 rounded-full transition-all duration-500 ease-out"
                    style={{ width: `${progress.progress}%` }}
                  />
                </div>
                <span className="text-[11px] tabular-nums text-gray-400 dark:text-[#8e8ea0] shrink-0">
                  {Math.round(progress.progress)}%
                </span>
              </div>
            )}
          </div>
          <span className={`text-xs font-medium shrink-0 ${
            isError ? 'text-red-500 dark:text-red-400' : 'text-gray-500 dark:text-[#bfc2cd]'
          }`}>
            {progress.status === 'uploading' ? 'Uploading' :
             progress.status === 'processing' ? 'Processing' :
             progress.status === 'completed' ? 'Done' : 'Failed'}
          </span>
        </div>
      </div>
    );
  };

  const progressContent = (
    <div className="w-full max-w-full overflow-hidden space-y-1.5" role="status" aria-live="polite">
      {Array.from(uploadingFiles.entries()).map(([key, progress]) =>
        renderProgressRow(progress, key)
      )}
    </div>
  );

  return (
    <div className="w-full max-w-full overflow-hidden space-y-2">
      {isUploading && progressContent}

      {!isUploading && (
        <button
          type="button"
          onClick={handleClick}
          onKeyDown={handleKeyDown}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          disabled={disabled}
          className={`
            group relative w-full max-w-full rounded-lg p-4 transition-all duration-200 text-left overflow-hidden
            ${isDragging
              ? 'bg-blue-50 dark:bg-blue-900/20 ring-2 ring-blue-400 dark:ring-blue-500 ring-inset'
              : disabled
              ? 'bg-gray-50 dark:bg-[#1f1f24] cursor-not-allowed opacity-50'
              : 'bg-gray-50 dark:bg-[#1f1f24] hover:bg-gray-100 dark:hover:bg-[#252530] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/50 focus-visible:ring-inset'
            }
          `}
          aria-label={disabled ? 'File upload disabled' : 'Upload files'}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            onChange={handleFileInputChange}
            className="hidden"
            disabled={disabled}
            accept=".pdf,.doc,.docx,.txt,.md,.csv,.json,.html,.pptx,.xlsx,.py,.java,.sql,.js,.mjs,.ts,.tsx,.cpp,.cxx,.cc,.c,.h,.hpp,.go,.rs,.rb,.php,.sh,.bash,.zsh,.yaml,.yml,.xml,.css,.scss,.sass,.less,.png,.jpg,.jpeg,.tiff,.wav,.mp3,.mp4,.ogg,.flac,.webm,.m4a,.aac,.vtt"
          />

          <div className="flex items-center gap-3">
            <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg transition-colors duration-200 ${
              isDragging
                ? 'bg-blue-100 dark:bg-blue-800/40'
                : 'bg-gray-200/70 dark:bg-[#2d2f39] group-hover:bg-blue-100 dark:group-hover:bg-blue-900/30'
            }`}>
              <Upload className={`h-5 w-5 transition-colors duration-200 ${
                isDragging
                  ? 'text-blue-600 dark:text-blue-400'
                  : 'text-gray-400 dark:text-[#8e8ea0] group-hover:text-blue-500 dark:group-hover:text-blue-400'
              }`} />
            </div>
            <div className="flex-1 min-w-0">
              <p className={`text-sm font-medium transition-colors duration-200 ${
                isDragging
                  ? 'text-blue-700 dark:text-blue-300'
                  : 'text-[#353740] dark:text-[#ececf1]'
              }`}>
                {disabled ? 'File upload disabled' : isDragging ? 'Drop files here' : 'Drop files or click to browse'}
              </p>
              <p className="text-xs text-gray-400 dark:text-[#8e8ea0] mt-0.5">
                PDF, DOCX, TXT, CSV, code files, images, audio &middot; max {maxFiles} files
              </p>
            </div>
          </div>
        </button>
      )}

      {otherUploadingConversations.length > 0 && (
        <div className="w-full max-w-full space-y-2 rounded-lg bg-gray-50 dark:bg-[#1f1f24] p-2.5">
          <p className="text-xs font-medium text-gray-500 dark:text-[#8e8ea0] px-1">
            Other conversations
          </p>
          {otherUploadingConversations.map(({ conversationId: otherId, uploads }) => (
            <div key={otherId} className="space-y-1.5">
              <div className="text-[11px] font-medium text-gray-400 dark:text-[#6b6f7a] px-1">
                {conversationNameMap.get(otherId) || 'Conversation'}
              </div>
              {uploads.map(({ key, progress }) => renderProgressRow(progress, key))}
            </div>
          ))}
        </div>
      )}

      {/* Uploaded files are shown in MessageInput's attachedFiles pills above, not here */}
    </div>
  );
}
