import React, { useState, useRef, useCallback, useEffect } from 'react';
import { Upload, X, Loader2 } from 'lucide-react';
import { FileAttachment } from '../types';
import { FileUploadService, FileUploadProgress } from '../services/fileService';

interface FileUploadProps {
  onFilesSelected: (files: FileAttachment[]) => void;
  onUploadError?: (error: string) => void;
  maxFiles?: number;
  disabled?: boolean;
}

export function FileUpload({ 
  onFilesSelected, 
  onUploadError,
  maxFiles = 5,
  disabled = false 
}: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploadingFiles, setUploadingFiles] = useState<Map<string, FileUploadProgress>>(new Map());
  const [uploadedFiles, setUploadedFiles] = useState<FileAttachment[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Notify parent component when uploaded files change
  // Use useEffect to avoid calling setState during render
  useEffect(() => {
    onFilesSelected(uploadedFiles);
  }, [uploadedFiles, onFilesSelected]);

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
      try {
        // Upload file and get the full response with correct file_size from server
        const uploadedAttachment = await FileUploadService.uploadFile(file, (progress) => {
          setUploadingFiles(prev => new Map(prev.set(file.name, progress)));
        });

        // Add completed file to list using the response from server (has correct file_size)
        if (uploadedAttachment) {
          newFiles.push(uploadedAttachment);
        }
      } catch (error: any) {
        console.error(`Failed to upload file ${file.name}:`, error);
        onUploadError?.(error.message || `Failed to upload ${file.name}`);
      } finally {
        setUploadingFiles(prev => {
          const next = new Map(prev);
          next.delete(file.name);
          return next;
        });
      }
    }
    
    // Update uploaded files list with all new files
    // The useEffect hook will call onFilesSelected when uploadedFiles changes
    if (newFiles.length > 0) {
      setUploadedFiles(prev => [...prev, ...newFiles]);
    }
  }, [maxFiles, onFilesSelected, onUploadError]);

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

  const handleRemoveFile = useCallback((fileId: string) => {
    // The useEffect hook will call onFilesSelected when uploadedFiles changes
    setUploadedFiles(prev => prev.filter(f => f.file_id !== fileId));
  }, []);

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

  return (
    <div className="w-full max-w-full overflow-hidden space-y-3">
      {/* Upload area */}
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

      {/* Upload progress */}
      {uploadingFiles.size > 0 && (
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

      {/* Uploaded files */}
      {uploadedFiles.length > 0 && (
        <div className="w-full max-w-full overflow-hidden space-y-2">
          {uploadedFiles.map((file) => (
            <div
              key={file.file_id}
              className="w-full max-w-full flex items-center gap-3 p-3 bg-white dark:bg-slate-800/70 border border-slate-200 dark:border-slate-700 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 overflow-hidden"
            >
              <span className="text-2xl">{getFileIcon(file.mime_type)}</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-slate-700 dark:text-slate-300 truncate">
                  {file.filename}
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {(file.file_size / 1024).toFixed(1)} KB
                  {file.chunk_count ? ` • ${file.chunk_count} chunks` : ''}
                </p>
              </div>
              {!disabled && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRemoveFile(file.file_id);
                  }}
                  className="p-1.5 text-slate-400 hover:text-red-600 dark:hover:text-red-400 transition-colors rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20"
                  title="Remove file"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

