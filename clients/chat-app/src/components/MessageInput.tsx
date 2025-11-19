import React, { useState, useRef, useEffect, useCallback } from 'react';
import { ArrowUp, Mic, MicOff, Paperclip, X, Loader2, CheckCircle2, Volume2, VolumeX } from 'lucide-react';
import { useVoice } from '../hooks/useVoice';
import { FileUpload } from './FileUpload';
import { FileAttachment } from '../types';
import { useChatStore } from '../stores/chatStore';
import { debugLog, debugError } from '../utils/debug';
import { AppConfig } from '../utils/config';
import { FileUploadService, FileUploadProgress } from '../services/fileService';
import { getDefaultKey, resolveApiUrl } from '../utils/runtimeConfig';
import { useSettings } from '../contexts/SettingsContext';
import { playSoundEffect } from '../utils/soundEffects';

interface MessageInputProps {
  onSend: (message: string, fileIds?: string[]) => void;
  disabled?: boolean;
  placeholder?: string;
  /**
   * When true, constrains the input to a tighter max width and centers it.
   * Used for the empty state layout so the field and title feel aligned.
   */
  isCentered?: boolean;
}

const MIME_EXTENSION_MAP: Record<string, string> = {
  'image/jpeg': 'jpg',
  'image/jpg': 'jpg',
  'image/png': 'png',
  'image/tiff': 'tiff',
  'image/tif': 'tif',
  'image/gif': 'gif',
  'image/webp': 'webp',
  'application/pdf': 'pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
  'application/msword': 'doc',
  'text/plain': 'txt',
  'text/markdown': 'md',
  'application/json': 'json'
};

function getExtensionFromMimeType(mimeType: string | undefined): string {
  if (!mimeType) {
    return 'bin';
  }
  if (MIME_EXTENSION_MAP[mimeType]) {
    return MIME_EXTENSION_MAP[mimeType];
  }
  const parts = mimeType.split('/');
  return parts.length === 2 && parts[1] ? parts[1] : 'bin';
}

function sanitizeFilenamePart(name: string): string {
  const sanitized = name.replace(/[^a-zA-Z0-9._-]/g, '_').replace(/_+/g, '_');
  return sanitized || 'pasted-file';
}

function getExtensionFromName(name: string): string | null {
  const lastDot = name.lastIndexOf('.');
  if (lastDot === -1 || lastDot === name.length - 1) {
    return null;
  }
  return name.slice(lastDot + 1).toLowerCase();
}

function getBaseName(name: string): string {
  const lastDot = name.lastIndexOf('.');
  if (lastDot === -1) {
    return name;
  }
  return name.slice(0, lastDot);
}

function prepareClipboardFile(file: File, index: number): File {
  const timestamp = Date.now();
  const originalName = file.name && file.name.trim().length > 0 ? file.name.trim() : `pasted-file`;
  const baseName = sanitizeFilenamePart(getBaseName(originalName));
  const existingExtension = getExtensionFromName(originalName);
  const extension = existingExtension || getExtensionFromMimeType(file.type);
  const uniqueName = `${baseName}-${timestamp}-${index}.${extension}`;
  return new File([file], uniqueName, { type: file.type || 'application/octet-stream' });
}

export function MessageInput({ 
  onSend, 
  disabled = false, 
  placeholder = "Ask me anything...",
  isCentered = false
}: MessageInputProps) {
  const [message, setMessage] = useState('');
  const [isComposing, setIsComposing] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const [showFileUpload, setShowFileUpload] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<FileAttachment[]>([]);
  const [conversationUploadingState, setConversationUploadingState] = useState<Record<string, boolean>>({});
  const [pasteUploadingFiles, setPasteUploadingFiles] = useState<Map<string, FileUploadProgress>>(new Map());
  const [isHoveringUpload, setIsHoveringUpload] = useState(false);
  const [isHoveringMic, setIsHoveringMic] = useState(false);
  const [pasteError, setPasteError] = useState<string | null>(null);
  const [pasteSuccess, setPasteSuccess] = useState<string | null>(null);
  const [removeFileSuccess, setRemoveFileSuccess] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const processedFilesRef = useRef<Set<string>>(new Set());
  const voiceMessageRef = useRef('');
  const pendingVoiceAutoSendRef = useRef(false);
  const lastProcessedVoiceCompletionRef = useRef(0);
  const lastConversationIdRef = useRef<string | null>(null);
  const { settings, updateSettings } = useSettings();
  const setConversationUploading = useCallback((conversationId: string | null, uploading: boolean) => {
    if (!conversationId) {
      return;
    }
    setConversationUploadingState(prev => {
      if (prev[conversationId] === uploading) {
        return prev;
      }
      const next = { ...prev };
      if (uploading) {
        next[conversationId] = true;
      } else {
        delete next[conversationId];
      }
      return next;
    });
  }, []);
  const [voiceCompletionCount, setVoiceCompletionCount] = useState(0);

  const { createConversation, currentConversationId, removeFileFromConversation, conversations, isLoading, syncConversationFiles } = useChatStore();

  const handleVoiceCompletion = useCallback(() => {
    setVoiceCompletionCount((count) => count + 1);
  }, []);

  const {
    isListening,
    isSupported: voiceSupported,
    startListening,
    stopListening,
    error: voiceError
  } = useVoice((text) => {
    setMessage(prev => {
      const updated = (prev + text).slice(0, AppConfig.maxMessageLength);
      voiceMessageRef.current = updated;
      return updated;
    });
  }, handleVoiceCompletion);

  // Check if any files are currently uploading or processing
  const currentConversation = conversations.find(conv => conv.id === currentConversationId);
  const conversationFiles = currentConversation?.attachedFiles || [];
  
  // Check if adapter supports file processing
  const isFileSupported = currentConversation?.adapterInfo?.isFileSupported ?? false;
  
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

  const isUploading = currentConversationId ? !!conversationUploadingState[currentConversationId] : false;
  const hasAnyUploadingConversations = Object.values(conversationUploadingState).some(Boolean);

  // Disable input if files are uploading, processing, or if already disabled
  const isInputDisabled = disabled || hasProcessingFiles || isUploading;
  
  // Disable file upload button if adapter doesn't support files or input is disabled
  const isFileUploadDisabled = !isFileSupported || isInputDisabled;

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

  // Auto-send message when voice recording completes
  useEffect(() => {
    if (voiceCompletionCount > lastProcessedVoiceCompletionRef.current) {
      pendingVoiceAutoSendRef.current = true;
      lastProcessedVoiceCompletionRef.current = voiceCompletionCount;
    }

    if (!pendingVoiceAutoSendRef.current || voiceCompletionCount === 0) {
      return;
    }

    debugLog('[MessageInput] Voice recording completed, scheduling auto-send');
    const timeoutId = setTimeout(() => {
      const voiceMessage = voiceMessageRef.current.trim();
      const currentState = useChatStore.getState();

      debugLog('[MessageInput] Auto-send check after voice completion:', {
        hasMessage: !!voiceMessage,
        isInputDisabled,
        isComposing,
        isLoading: currentState.isLoading
      });

      if (!voiceMessage) {
        pendingVoiceAutoSendRef.current = false;
        return;
      }

      if (!isInputDisabled && !isComposing && !currentState.isLoading) {
        const currentConv = currentState.conversations.find(conv => conv.id === currentState.currentConversationId);
        const conversationFiles = currentConv?.attachedFiles || [];
        const allFileIds = conversationFiles.map(f => f.file_id);

        debugLog('[MessageInput] Auto-sending voice message:', voiceMessage);
        onSend(voiceMessage, allFileIds.length > 0 ? allFileIds : undefined);

        pendingVoiceAutoSendRef.current = false;
        setMessage('');
        voiceMessageRef.current = '';
        if (textareaRef.current) {
          textareaRef.current.style.height = 'auto';
          textareaRef.current.style.overflowY = 'hidden';
        }
      } else {
        debugLog('[MessageInput] Auto-send paused, waiting for input to become available');
      }
    }, 400);

    return () => clearTimeout(timeoutId);
  }, [voiceCompletionCount, isInputDisabled, isComposing, onSend]);

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

  const syncFilesWithConversation = useCallback((files: FileAttachment[], targetConversationId?: string | null) => {
    setTimeout(() => {
      let store = useChatStore.getState();
      let conversationId = targetConversationId || store.currentConversationId;
      
      if (!conversationId) {
        conversationId = createConversation();
        store = useChatStore.getState();
        conversationId = store.currentConversationId || conversationId;
      }

      if (!conversationId) {
        debugError('[MessageInput] Unable to sync files: conversation ID missing');
        return;
      }
      
      const currentFileIds = new Set(files.map(f => f.file_id));
      const keysToRemove: string[] = [];
      processedFilesRef.current.forEach((_, key) => {
        const [, ...fileIdParts] = key.split('-');
        const fileId = fileIdParts.join('-');
        if (!currentFileIds.has(fileId)) {
          keysToRemove.push(key);
        }
      });
      keysToRemove.forEach(key => processedFilesRef.current.delete(key));
      
      files.forEach(file => {
        const fileKey = `${conversationId}-${file.file_id}`;
        if (!processedFilesRef.current.has(fileKey)) {
          processedFilesRef.current.add(fileKey);
          
          debugLog(`[MessageInput] Adding file ${file.file_id} to conversation ${conversationId}`);
          store.addFileToConversation(conversationId!, file);
        }
      });
    }, 0);
  }, [createConversation]);

  // Reset attached files when switching conversations to avoid bleed-through
  useEffect(() => {
    if (currentConversationId !== lastConversationIdRef.current) {
      lastConversationIdRef.current = currentConversationId || null;
      if (currentConversationId && currentConversation) {
        const convFiles = currentConversation.attachedFiles || [];
        setAttachedFiles(convFiles.map(file => ({ ...file })));
      } else {
        setAttachedFiles([]);
      }
    }
  }, [currentConversationId, currentConversation]);

  // Sync attachedFiles with conversationFiles to ensure pasted files appear in UI
  useEffect(() => {
    if (currentConversationId && currentConversation) {
      const convFiles = currentConversation.attachedFiles || [];
      if (convFiles.length > 0) {
        setAttachedFiles(prev => {
          const attachedFileIds = new Set(prev.map(f => f.file_id));
          const missingFiles = convFiles.filter(f => !attachedFileIds.has(f.file_id));
          
          if (missingFiles.length > 0) {
            debugLog(`[MessageInput] Syncing ${missingFiles.length} missing files from conversation to UI`);
            return [...prev, ...missingFiles];
          }
          return prev;
        });
      } else if (convFiles.length === 0 && attachedFiles.length > 0) {
        setAttachedFiles([]);
      }
    }
  }, [currentConversationId, currentConversation, conversations, attachedFiles.length]);

  // Sync and poll file status when switching to a conversation
  useEffect(() => {
    if (!currentConversationId || !currentConversation || !currentConversation.apiKey) {
      return;
    }

    const convFiles = currentConversation.attachedFiles || [];
    const hasFiles = convFiles.length > 0;
    const processingFiles = convFiles.filter(f => 
      !f.processing_status || 
      f.processing_status === 'processing' || 
      f.processing_status === 'uploading'
    );

    // Always sync files when switching to a conversation (to get latest status)
    if (hasFiles) {
      debugLog(`[MessageInput] Syncing ${convFiles.length} files for conversation ${currentConversationId}...`);
      syncConversationFiles(currentConversationId).catch(error => {
        debugError('[MessageInput] Failed to sync conversation files:', error);
      });
    }

    // Only poll if there are files still processing
    if (processingFiles.length === 0) {
      return;
    }

    debugLog(`[MessageInput] Found ${processingFiles.length} files still processing, starting poll...`);

    // Poll for file status updates every 3 seconds for files that are still processing
    const pollInterval = setInterval(async () => {
      const currentState = useChatStore.getState();
      const currentConv = currentState.conversations.find(conv => conv.id === currentConversationId);
      
      if (!currentConv) {
        clearInterval(pollInterval);
        return;
      }

      const currentFiles = currentConv.attachedFiles || [];
      const stillProcessing = currentFiles.filter(f => 
        !f.processing_status || 
        f.processing_status === 'processing' || 
        f.processing_status === 'uploading'
      );

      if (stillProcessing.length === 0) {
        debugLog('[MessageInput] All files completed processing, stopping poll');
        clearInterval(pollInterval);
        return;
      }

      // Sync again to get updated statuses
      try {
        await syncConversationFiles(currentConversationId);
      } catch (error) {
        debugError('[MessageInput] Failed to poll file status:', error);
      }
    }, 3000);

    return () => {
      clearInterval(pollInterval);
    };
  }, [currentConversationId, currentConversation, syncConversationFiles]);

  useEffect(() => {
    setConversationUploadingState(prev => {
      const existingIds = new Set(conversations.map(conv => conv.id));
      let changed = false;
      const next = { ...prev };
      Object.keys(next).forEach(id => {
        if (!existingIds.has(id)) {
          delete next[id];
          changed = true;
        }
      });
      return changed ? next : prev;
    });
  }, [conversations]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if ((message.trim() || attachedFiles.length > 0) && !isInputDisabled && !isComposing) {
      // Stop listening if still active
      if (isListening) {
        stopListening();
      }
      
      // For multimodal conversations, send ALL files attached to the conversation
      // (not just the newly attached ones in this message)
      const conversationFiles = currentConversation?.attachedFiles || [];
      const allFileIds = conversationFiles.map(f => f.file_id);

      onSend(message.trim(), allFileIds.length > 0 ? allFileIds : undefined);
      playSoundEffect('messageSent', settings.soundEnabled);
      setMessage('');
      voiceMessageRef.current = ''; // Clear voice message ref when manually submitting
      setAttachedFiles([]);
      setShowFileUpload(false);
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
        textareaRef.current.style.overflowY = 'hidden';
      }
    }
  };

  const handleFilesSelected = useCallback((conversationId: string | null, files: FileAttachment[]) => {
    debugLog(`[MessageInput] handleFilesSelected called with ${files.length} files for conversation ${conversationId}:`, files);
    if (!conversationId) {
      return;
    }
    if (conversationId === currentConversationId) {
      setAttachedFiles(files);
    }
    syncFilesWithConversation(files, conversationId);
  }, [currentConversationId, syncFilesWithConversation]);

  const handleRemoveFile = async (fileId: string) => {
    // Get filename before removing for success message
    const fileToRemove = attachedFiles.find(f => f.file_id === fileId);
    const filename = fileToRemove?.filename || 'File';
    
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
        // Show success message
        playSoundEffect('success', settings.soundEnabled);
        setRemoveFileSuccess(`File "${filename}" removed successfully`);
        setTimeout(() => {
          setRemoveFileSuccess(null);
        }, 3000);
      } catch (error) {
        debugError(`Failed to remove file ${fileId} from conversation:`, error);
        playSoundEffect('error', settings.soundEnabled);
      }
    } else {
      // Even if no conversation, show success for local removal
      playSoundEffect('success', settings.soundEnabled);
      setRemoveFileSuccess(`File "${filename}" removed successfully`);
      setTimeout(() => {
        setRemoveFileSuccess(null);
      }, 3000);
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

  const handleVoiceResponseToggle = () => {
    updateSettings({ voiceEnabled: !settings.voiceEnabled });
  };

  const handlePaste = useCallback(async (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    if (!isFocused || !isFileSupported || isInputDisabled) {
      return;
    }

    const clipboardData = e.clipboardData;
    if (!clipboardData || !clipboardData.items) {
      return;
    }

    const items = Array.from(clipboardData.items);
    const fileItems = items.filter(item => item.kind === 'file');

    if (fileItems.length === 0) {
      return;
    }

    const filesFromClipboard: File[] = [];
    fileItems.forEach((item, index) => {
      const file = item.getAsFile();
      if (file) {
        filesFromClipboard.push(prepareClipboardFile(file, index));
      }
    });

    if (filesFromClipboard.length === 0) {
      return;
    }

    e.preventDefault();
    setPasteError(null);
    setPasteSuccess(null);

    let pasteConversationId: string | null = null;

    try {
      const pasteStore = useChatStore.getState();
      const currentConv = pasteStore.conversations.find(conv => conv.id === pasteStore.currentConversationId);
      const currentFiles = currentConv?.attachedFiles || [];
      const projectedConversationFileCount = currentFiles.length + filesFromClipboard.length;

      if (projectedConversationFileCount > AppConfig.maxFilesPerConversation) {
        throw new Error(`Maximum ${AppConfig.maxFilesPerConversation} files allowed per conversation. Please remove some files first.`);
      }

      if (AppConfig.maxTotalFiles !== null) {
        const totalFilesAcrossConversations = pasteStore.conversations.reduce(
          (total, conv) => total + (conv.attachedFiles?.length || 0),
          0
        );
        if (totalFilesAcrossConversations + filesFromClipboard.length > AppConfig.maxTotalFiles) {
          throw new Error(`Maximum ${AppConfig.maxTotalFiles} total files allowed across all conversations. Please remove some files from other conversations first.`);
        }
      }

      if (!currentConv || !currentConv.apiKey || currentConv.apiKey === getDefaultKey()) {
        throw new Error('API key not configured for this conversation. Please configure API settings first.');
      }

      const conversationApiKey = currentConv.apiKey;
      const conversationApiUrl = resolveApiUrl(currentConv.apiUrl);
      pasteConversationId = currentConv.id;

      setConversationUploading(pasteConversationId, true);
      const uploadedAttachments: FileAttachment[] = [];
      const completionPromises: Promise<void>[] = [];
      
      for (let index = 0; index < filesFromClipboard.length; index++) {
        const file = filesFromClipboard[index];
        const fallbackName = file.name || `Clipboard file ${index + 1}`;
        const progressKey = `${fallbackName}-${Date.now()}-${index}`;
        
        setPasteUploadingFiles(prev => {
          const next = new Map(prev);
          next.set(progressKey, {
            filename: fallbackName,
            progress: 0,
            status: 'uploading'
          });
          return next;
        });

        const updateEntry = (progress: FileUploadProgress) => {
          setPasteUploadingFiles(prev => {
            const next = new Map(prev);
            const existing = next.get(progressKey);
            if (!existing) {
              return next;
            }
            next.set(progressKey, {
              ...existing,
              filename: fallbackName,
              progress: progress.progress,
              status: progress.status,
              fileId: progress.fileId
            });
            return next;
          });
        };

        const markEntryComplete = () => {
          return new Promise<void>((resolve) => {
            setPasteUploadingFiles(prev => {
              const next = new Map(prev);
              const existing = next.get(progressKey);
              if (!existing) {
                return next;
              }
              next.set(progressKey, {
                ...existing,
                progress: 100,
                status: 'completed'
              });
              return next;
            });
            setTimeout(() => {
              setPasteUploadingFiles(prev => {
                const next = new Map(prev);
                next.delete(progressKey);
                return next;
              });
              resolve();
            }, 2500);
          });
        };

        debugLog(`[MessageInput] Pasting file: ${file.name}, type: ${file.type || 'unknown'}, size: ${file.size}`);
        const uploadedAttachment = await FileUploadService.uploadFile(
          file,
          (progress) => {
            debugLog(`[MessageInput] Paste upload progress for ${file.name}: ${progress.progress}% - ${progress.status}`);
            updateEntry(progress);
          },
          conversationApiKey,
          conversationApiUrl
        );
        uploadedAttachments.push(uploadedAttachment);
        completionPromises.push(markEntryComplete());
      }

      if (uploadedAttachments.length > 0) {
        let filesForSync = uploadedAttachments;
        if (pasteConversationId && pasteConversationId === currentConversationId) {
          const existingIds = new Set(attachedFiles.map(f => f.file_id));
          const filteredAdds = uploadedAttachments.filter(f => !existingIds.has(f.file_id));
          if (filteredAdds.length > 0) {
            setAttachedFiles(prev => [...prev, ...filteredAdds]);
            filesForSync = filteredAdds;
          } else {
            filesForSync = [];
          }
        }

        if (filesForSync.length > 0) {
          syncFilesWithConversation(filesForSync, pasteConversationId);
        }

        const successMessage =
          uploadedAttachments.length === 1
            ? `File "${uploadedAttachments[0].filename}" uploaded successfully`
            : `${uploadedAttachments.length} files uploaded successfully`;

        await Promise.all(completionPromises);

        playSoundEffect('success', settings.soundEnabled);
        setPasteSuccess(successMessage);
        setTimeout(() => {
          setPasteSuccess(null);
        }, 6000);
      }
    } catch (error: any) {
      const errorMessage = error.message || 'Failed to paste file';
      debugError('[MessageInput] Paste error:', error);
      playSoundEffect('error', settings.soundEnabled);
      setPasteError(errorMessage);
      setTimeout(() => {
        setPasteError(null);
      }, 5000);
      setPasteUploadingFiles(new Map());
    } finally {
      setConversationUploading(pasteConversationId, false);
    }
  }, [attachedFiles, currentConversationId, isFocused, isFileSupported, isInputDisabled, setConversationUploading, syncFilesWithConversation]);

  const effectivePlaceholder = (hasProcessingFiles || isUploading)
    ? 'Files are uploading/processing, please wait...'
    : isFileSupported
    ? 'Message ORBIT or drop files here'
    : placeholder;

  // Play sound when voice error appears
  useEffect(() => {
    if (voiceError) {
      playSoundEffect('error', settings.soundEnabled);
    }
  }, [voiceError, settings.soundEnabled]);

  const contentMaxWidth = isCentered ? 'max-w-3xl' : 'max-w-5xl';
  const containerAlignmentClasses = isCentered ? 'flex justify-center' : '';

  return (
    <div className={`bg-white px-3 py-4 dark:bg-[#212121] sm:px-4 ${containerAlignmentClasses}`}>
      {voiceError && (
        <div className={`mx-auto mb-3 w-full ${contentMaxWidth} rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-600/40 dark:bg-red-900/30 dark:text-red-200`}>
          {voiceError}
        </div>
      )}
      {pasteError && (
        <div className={`mx-auto mb-3 w-full ${contentMaxWidth} rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-600/40 dark:bg-red-900/30 dark:text-red-200`}>
          {pasteError}
        </div>
      )}
      {pasteSuccess && (
        <div className={`mx-auto mb-3 w-full ${contentMaxWidth} flex items-center gap-2 rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700 dark:border-green-600/40 dark:bg-green-900/30 dark:text-green-200`}>
          <CheckCircle2 className="h-4 w-4 flex-shrink-0" />
          <span>{pasteSuccess}</span>
        </div>
      )}
      {removeFileSuccess && (
        <div className={`mx-auto mb-3 w-full ${contentMaxWidth} flex items-center gap-2 rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700 dark:border-green-600/40 dark:bg-green-900/30 dark:text-green-200`}>
          <CheckCircle2 className="h-4 w-4 flex-shrink-0" />
          <span>{removeFileSuccess}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className={`mx-auto flex w-full ${contentMaxWidth} flex-col gap-3`}>
        <div
          className={`flex flex-wrap gap-2 rounded-lg border px-3 py-3 shadow-sm transition-all sm:flex-nowrap sm:px-4 ${
            isFocused
              ? 'border-gray-400 shadow-md dark:border-[#565869] dark:shadow-lg'
              : 'border-gray-300 dark:border-[#40414f]'
          } bg-gray-50 dark:bg-[#2d2f39]`}
        >
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              if (!isFileUploadDisabled) {
                setShowFileUpload(!showFileUpload);
              }
            }}
            disabled={isFileUploadDisabled}
            onMouseEnter={() => setIsHoveringUpload(true)}
            onMouseLeave={() => setIsHoveringUpload(false)}
            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors ${
              showFileUpload || attachedFiles.length > 0
                ? 'bg-gray-100 text-[#353740] dark:bg-[#565869] dark:text-[#ececf1]'
                : isFileUploadDisabled
                ? 'cursor-not-allowed text-gray-300 dark:text-[#6b6f7a]'
                : 'text-gray-500 hover:bg-gray-100 hover:text-[#353740] dark:text-[#bfc2cd] dark:hover:bg-[#565869]'
            }`}
            title={
              !isFileSupported
                ? 'File upload not supported by this adapter'
                : isInputDisabled
                ? 'Files are uploading/processing. Please wait...'
                : attachedFiles.length > 0
                ? `${attachedFiles.length} file(s) attached`
                : 'Attach files'
            }
          >
            {isFileUploadDisabled && isHoveringUpload ? (
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
            onPaste={handlePaste}
            onCompositionStart={() => setIsComposing(true)}
            onCompositionEnd={() => setIsComposing(false)}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder={effectivePlaceholder}
            disabled={isInputDisabled}
            rows={1}
            maxLength={AppConfig.maxMessageLength}
            className="flex-1 min-w-[150px] resize-none bg-transparent py-1 text-sm text-[#353740] placeholder-gray-600 focus:outline-none dark:text-[#ececf1] dark:placeholder-[#bfc2cd]"
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
            <>
              <button
                type="button"
                onClick={handleVoiceResponseToggle}
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors ${
                  settings.voiceEnabled
                    ? 'bg-blue-50 text-blue-600 dark:bg-blue-900/40 dark:text-blue-300'
                    : 'text-gray-500 hover:bg-gray-100 hover:text-[#353740] dark:text-[#bfc2cd] dark:hover:bg-[#565869]'
                }`}
                title={
                  settings.voiceEnabled
                    ? 'Voice responses enabled - Click to disable'
                    : 'Enable voice responses (text-to-speech)'
                }
              >
                {settings.voiceEnabled ? (
                  <Volume2 className="h-5 w-5" />
                ) : (
                  <VolumeX className="h-5 w-5" />
                )}
              </button>
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
            </>
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
            <ArrowUp className="h-4 w-4" />
          </button>
        </div>

        {attachedFiles.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {attachedFiles.map((file) => {
              const isProcessing = !file.processing_status || 
                file.processing_status === 'processing' || 
                file.processing_status === 'uploading';
              return (
                <div
                  key={file.file_id}
                  className="flex items-center gap-2 rounded-md border border-gray-200 bg-white px-2 py-1 text-xs dark:border-[#4a4b54] dark:bg-[#2d2f39]"
                >
                  {isProcessing && (
                    <Loader2 className="h-3 w-3 animate-spin text-emerald-600 dark:text-emerald-400 flex-shrink-0" />
                  )}
                  <span className="truncate max-w-[150px] text-[#353740] dark:text-[#ececf1]">
                    {file.filename}
                  </span>
                  {isProcessing && (
                    <span className="text-xs text-gray-500 dark:text-[#bfc2cd]">
                      {file.processing_status === 'uploading' ? 'Uploading...' : 'Processing...'}
                    </span>
                  )}
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
              );
            })}
          </div>
        )}

        {(isFileSupported || hasAnyUploadingConversations) && (
          <div
            className={`rounded-md border border-gray-200 bg-white p-3 dark:border-[#4a4b54] dark:bg-[#2d2f39] ${
              !showFileUpload && !isUploading && pasteUploadingFiles.size === 0 && !hasAnyUploadingConversations
                ? 'hidden'
                : ''
            }`}
          >
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
            {(isUploading || pasteUploadingFiles.size > 0) && !showFileUpload && pasteUploadingFiles.size === 0 && (
              <div className="mb-2 text-sm text-[#353740] dark:text-[#ececf1]">
                Uploading files…
              </div>
            )}
            {pasteUploadingFiles.size > 0 && (
              <div className="mb-2 space-y-2">
                {Array.from(pasteUploadingFiles.entries()).map(([key, progress]) => (
                  <div
                    key={key}
                    className="w-full max-w-full flex items-center gap-3 p-3 bg-gray-50 dark:bg-[#1f1f24] rounded-lg overflow-hidden"
                  >
                    <Loader2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 animate-spin flex-shrink-0" />
                    <div className="flex-1 min-w-0 overflow-hidden">
                      <p className="text-sm font-medium text-[#353740] dark:text-[#ececf1] truncate">
                        {progress.filename}
                      </p>
                      <div className="mt-1 bg-gray-200 dark:bg-[#3c3f4a] rounded-full h-1.5">
                        <div
                          className="bg-emerald-600 dark:bg-emerald-400 h-1.5 rounded-full transition-all duration-300"
                          style={{ width: `${progress.progress ?? 0}%` }}
                        />
                      </div>
                    </div>
                    <span className="text-xs text-gray-500 dark:text-[#bfc2cd]">
                      {progress.status === 'uploading'
                        ? 'Uploading...'
                        : progress.status === 'processing'
                        ? 'Processing...'
                        : progress.status === 'completed'
                        ? 'Done'
                        : 'Pending'}
                    </span>
                  </div>
                ))}
              </div>
            )}
            <FileUpload
              conversationId={currentConversationId}
              onFilesSelected={handleFilesSelected}
              onUploadError={(error) => {
                debugError('File upload error:', error);
              }}
              onUploadingChange={setConversationUploading}
              maxFiles={AppConfig.maxFilesPerConversation}
              disabled={isFileUploadDisabled}
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
