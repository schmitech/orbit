import React, { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import { Upload, X, Loader2 } from 'lucide-react';
import { FileAttachment } from '../types';
import { FileUploadService, FileUploadProgress } from '../services/fileService';
import { useChatStore } from '../stores/chatStore';
import { debugLog, debugWarn, debugError } from '../utils/debug';
import { AppConfig } from '../utils/config';
import { getDefaultKey, resolveApiUrl } from '../utils/runtimeConfig';

// Default API key from runtime configuration
const DEFAULT_API_KEY = getDefaultKey();

// Persist upload state across component re-mounts and conversation switches
const uploadingFilesStore = new Map<string, Map<string, FileUploadProgress>>();
const uploadedFilesStore = new Map<string, FileAttachment[]>();
const uploadedFileIdsStore = new Map<string, string>();

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
}: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [globalUploadRevision, setGlobalUploadRevision] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploadedFileIdsRef = useRef<Map<string, string>>(uploadedFileIdsStore);
  const abortControllersRef = useRef<Map<string, AbortController>>(new Map());
  const isMountedRef = useRef<boolean>(true);
  const uploadingFilesStoreRef = useRef<Map<string, Map<string, FileUploadProgress>>>(uploadingFilesStore);
  const uploadedFilesStoreRef = useRef<Map<string, FileAttachment[]>>(uploadedFilesStore);
  const latestConversationIdRef = useRef<string | null>(conversationId);
  const conversations = useChatStore(state => state.conversations);

  const uploadingFiles = useMemo(() => {
    if (!conversationId) {
      return new Map<string, FileUploadProgress>();
    }
    const uploads = uploadingFilesStoreRef.current.get(conversationId);
    return uploads ? new Map(uploads) : new Map<string, FileUploadProgress>();
  }, [conversationId, globalUploadRevision]);

  const uploadedFiles = useMemo(() => {
    if (!conversationId) {
      return [] as FileAttachment[];
    }
    const files = uploadedFilesStoreRef.current.get(conversationId);
    return files ? [...files] : [];
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
      const processingFiles = conversation.attachedFiles.filter(f => 
        !f.processing_status || 
        f.processing_status === 'processing' || 
        f.processing_status === 'uploading'
      );
      
      // Merge existing uploads with processing files from conversation
      // This ensures we show progress even if upload progress was lost
      const mergedUploads = new Map(uploads);
      let hasNewUploads = false;
      
      processingFiles.forEach(file => {
        // Check if we already have progress for this file
        const existingProgress = Array.from(uploads.values()).find(p => p.fileId === file.file_id);
        
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

  // Cleanup: Delete uploaded files from server when component unmounts
  // Only delete files that aren't already in the conversation
  useEffect(() => {
    return () => {
      isMountedRef.current = false;
      abortControllersRef.current.forEach(controller => controller.abort());

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
              uploadedFileIdsRef.current.delete(fileId);
              return;
            }
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
                await FileUploadService.deleteFile(fileId);
              }
            } catch (error: any) {
              if (!error.message?.includes('404') && !error.message?.includes('File not found')) {
                debugWarn(`Failed to cleanup file ${fileId} during component unmount:`, error);
              }
            }
          });
        }
      }, 300);
    };
  }, [removeFileFromConversation, onClose]);

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
        onUploadError?.(error);
        return;
      }
    }

    if (!conversation.apiKey || conversation.apiKey === DEFAULT_API_KEY) {
      onUploadError?.('API key not configured for this conversation. Please configure API settings first.');
      return;
    }

    const conversationApiKey = conversation.apiKey;
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
          conversationApiKey,
          conversationApiUrl
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
          
          // Update the file in the conversation with final status
          // The file was already added during upload progress, now update it with complete info
          debugLog(`[FileUpload] Updating file ${uploadedAttachment.file_id} in conversation ${activeConversationId} with final status`);
          addFileToConversation(activeConversationId, uploadedAttachment);
          
          // Only remove progress if file is completed, otherwise keep it for processing status
          if (uploadedAttachment.processing_status === 'completed') {
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
      } catch (error: any) {
        if (error.name === 'AbortError' || abortController.signal.aborted) {
          debugLog(`Upload cancelled for ${file.name}`);
          if (uploadedFileId) {
            uploadedFileIdsRef.current.delete(uploadedFileId);
          }
          continue;
        }
        if (error.message && error.message.includes('was deleted')) {
          debugLog(`File ${file.name} was deleted during upload`);
          if (uploadedFileId) {
            uploadedFileIdsRef.current.delete(uploadedFileId);
          }
          const fileIdMatch = error.message.match(/File\s+([\w-]+)\s+was deleted/);
          if (fileIdMatch && fileIdMatch[1]) {
            uploadedFileIdsRef.current.delete(fileIdMatch[1]);
          }
          continue;
        }
        if (isMountedRef.current) {
          debugError(`Failed to upload file ${file.name}:`, error);
          debugError(`File type: ${file.type}, File name: ${file.name}`);
          onUploadError?.(error.message || `Failed to upload ${file.name}`);
        } else {
          debugWarn(`Upload error for ${file.name} (component unmounted):`, error.message);
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
  }, [conversationId, maxFiles, onUploadError, updateUploadedStore, updateUploadingStore]);

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
    const store = useChatStore.getState();
    const activeConversationId = conversationId || store.currentConversationId;

    debugLog(`[FileUpload] handleRemoveFile called for file ${fileId}`, {
      activeConversationId,
      hasRemoveFileFromConversation: !!removeFileFromConversation
    });

    if (!activeConversationId) {
      uploadedFileIdsRef.current.delete(fileId);
      try {
        await FileUploadService.deleteFile(fileId);
      } catch (error) {
        debugError(`[FileUpload] Failed to delete file ${fileId} from server:`, error);
      }
      return;
    }

    updateUploadedStore(activeConversationId, (prev) => prev.filter(f => f.file_id !== fileId));
    uploadedFileIdsRef.current.delete(fileId);

    try {
      await removeFileFromConversation(activeConversationId, fileId);
      debugLog(`[FileUpload] Successfully removed file ${fileId} from conversation ${activeConversationId}`);
    } catch (error) {
      debugError(`[FileUpload] Failed to remove file ${fileId} from conversation:`, error);
      try {
        await FileUploadService.deleteFile(fileId);
      } catch (deleteError) {
        debugError(`[FileUpload] Failed to delete file ${fileId} from server:`, deleteError);
      }
    }
  }, [conversationId, removeFileFromConversation, updateUploadedStore]);

  const handleClick = useCallback(() => {
    if (!disabled && fileInputRef.current) {
      fileInputRef.current.click();
    }
  }, [disabled]);

  // Hide upload area when files are uploading OR when files have been uploaded
  const isUploading = uploadingFiles.size > 0;
  const hasUploadedFiles = uploadedFiles.length > 0;
  const conversationNameMap = useMemo(() => {
    const map = new Map<string, string>();
    conversations.forEach(conv => {
      map.set(conv.id, conv.title || 'Conversation');
    });
    return map;
  }, [conversations]);

  const otherUploadingConversations = useMemo(() => {
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
            accept=".pdf,.doc,.docx,.txt,.md,.csv,.json,.html,.pptx,.xlsx,.py,.java,.sql,.js,.mjs,.ts,.tsx,.cpp,.cxx,.cc,.c,.h,.hpp,.go,.rs,.rb,.php,.sh,.bash,.zsh,.yaml,.yml,.xml,.css,.scss,.sass,.less,.png,.jpg,.jpeg,.tiff,.wav,.mp3,.mp4,.ogg,.flac,.webm,.m4a,.aac,.vtt"
          />
          
          <div className="flex flex-col items-center justify-center gap-2 text-center">
            <Upload className={`w-6 h-6 ${isDragging ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-400 dark:text-slate-500'}`} />
            <div className="px-2">
              <p className="text-xs sm:text-sm font-medium text-slate-700 dark:text-slate-300">
                {disabled ? 'File upload disabled' : isDragging ? 'Drop files here' : 'Click or drag files to upload'}
              </p>
              <p className="text-[10px] sm:text-xs text-slate-500 dark:text-slate-400 mt-0.5 px-1">
                PDF, DOCX, TXT, CSV, JSON, HTML, code files (.py, .js, .ts, .java, .sql, etc.), images, audio (max {maxFiles} files)
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

      {otherUploadingConversations.length > 0 && (
        <div className="w-full max-w-full space-y-3 rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900/40">
          <p className="text-xs font-semibold text-slate-600 dark:text-slate-300">
            Uploads in other conversations
          </p>
          {otherUploadingConversations.map(({ conversationId: otherId, uploads }) => (
            <div key={otherId} className="space-y-2">
              <div className="text-xs font-medium text-slate-500 dark:text-slate-400">
                {conversationNameMap.get(otherId) || 'Conversation'}
              </div>
              {uploads.map(({ key, progress }) => (
                <div key={key} className="w-full max-w-full flex items-center gap-3 p-3 bg-slate-50 dark:bg-slate-800/50 rounded-lg overflow-hidden">
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
          ))}
        </div>
      )}

      {/* Uploaded files are shown in MessageInput's attachedFiles pills above, not here */}
    </div>
  );
}
