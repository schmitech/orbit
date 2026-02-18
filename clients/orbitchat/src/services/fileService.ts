/**
 * File Upload Service
 *
 * Handles file uploads to the ORBIT server and manages file metadata.
 * All requests go through the Express proxy with X-Adapter-Name headers.
 */

import { getApi } from '../api/loader';
import { FileAttachment } from '../types';
import { debugLog, debugWarn, logError } from '../utils/debug';
import { AppConfig } from '../utils/config';
import { getApiUrl } from '../utils/runtimeConfig';

const resolveAdapterName = (explicit?: string | null): string | null => {
  const trimmed = explicit?.trim();
  if (trimmed) {
    return trimmed;
  }
  if (typeof window !== 'undefined' && window.localStorage) {
    return localStorage.getItem('chat-adapter-name');
  }
  return null;
};

export interface FileUploadProgress {
  filename: string;
  progress: number;  // 0-100
  status: 'uploading' | 'processing' | 'completed' | 'error';
  error?: string;
  fileId?: string;
}

export class FileUploadService {
  /**
   * Upload a file to the server
   *
   * @param file - The file to upload
   * @param onProgress - Optional progress callback
   * @param _reserved - Unused (previously apiKey)
   * @param apiUrl - Optional API URL
   * @param adapterName - Optional adapter name
   * @returns Promise resolving to file attachment metadata
   * @throws Error if upload fails
   */
  static async uploadFile(
    file: File,
    onProgress?: (progress: FileUploadProgress) => void,
    _reserved?: string,
    apiUrl?: string,
    adapterName?: string
  ): Promise<FileAttachment> {
    try {
      // Validate file size using configurable limit
      const maxSize = AppConfig.maxFileSizeMB * 1024 * 1024; // Convert MB to bytes
      if (file.size > maxSize) {
        throw new Error(`File size exceeds maximum limit of ${AppConfig.maxFileSizeMB}MB`);
      }

      // Validate file type (basic check - server will do full validation)
      const allowedTypes = [
        'application/pdf',
        'text/plain',
        'text/markdown',
        'text/csv',
        'application/json',
        'text/html',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        // Alternative Excel MIME types browsers might use
        'application/vnd.ms-excel',
        'application/vnd.ms-excel.sheet.macroEnabled.12',
        // Code file types
        'text/x-python',
        'text/x-python-script',  // Alternative MIME type for Python files
        'text/x-java-source',
        'text/x-java',
        'text/x-sql',
        'text/javascript',
        'application/javascript',
        'text/typescript',
        'application/typescript',
        'text/x-c++src',
        'text/x-csrc',
        'text/x-c',
        'text/x-go',
        'text/x-rust',
        'text/x-ruby',
        'text/x-php',
        'text/x-shellscript',
        'text/x-sh',
        'text/yaml',
        'text/x-yaml',
        'text/xml',
        'application/xml',
        'text/css',
        'text/x-scss',
        'text/x-sass',
        'text/x-less',
        'image/png',
        'image/jpeg',
        'image/tiff',
        // Audio types
        'audio/wav',
        'audio/mpeg',
        'audio/mp3',
        'audio/mp4',
        'audio/ogg',
        'audio/flac',
        'audio/webm',
        'audio/x-m4a',
        'audio/aac',
        'text/vtt'
      ];

      // Check MIME type or extension
      // Note: Some browsers may detect Excel files as application/x-zip-compressed
      // or application/zip because XLSX files are ZIP archives, so we also check by extension
      const isValidType = allowedTypes.includes(file.type) ||
        /\.(pdf|txt|md|csv|json|html|docx|pptx|xlsx|py|java|sql|js|mjs|ts|tsx|cpp|cxx|cc|c|h|hpp|go|rs|rb|php|sh|bash|zsh|yaml|yml|xml|css|scss|sass|less|png|jpe?g|tiff?|wav|mp3|mp4|ogg|flac|webm|m4a|aac|vtt)$/i.test(file.name) ||
        // Handle cases where Excel files are detected as ZIP
        (file.type === 'application/x-zip-compressed' || file.type === 'application/zip') &&
        /\.xlsx$/i.test(file.name);

      if (!isValidType) {
        throw new Error(`File type not supported: ${file.type || 'unknown'}`);
      }

      // Report upload start
      if (onProgress) {
        onProgress({
          filename: file.name,
          progress: 0,
          status: 'uploading'
        });
      }

      // Get API client
      const api = await getApi();
      const resolvedApiUrl = apiUrl?.trim() || getApiUrl();
      const resolvedAdapterName = resolveAdapterName(adapterName);

      if (!resolvedAdapterName) {
        throw new Error(
          'Adapter not configured. Please select an adapter from the dropdown.'
        );
      }

      debugLog(`Using adapter: ${resolvedAdapterName}`);

      const client = new api.ApiClient({
        apiUrl: resolvedApiUrl,
        sessionId: null,
        adapterName: resolvedAdapterName
      });

      // Check if uploadFile method exists
      if (!client.uploadFile) {
        throw new Error('File upload is not available.');
      }

      // Upload file
      const response = await client.uploadFile(file);

      // Report processing
      if (onProgress) {
        onProgress({
          filename: file.name,
          progress: 75,
          status: 'processing',
          fileId: response.file_id
        });
      }

      // Poll file status until processing is complete
      let fileInfo: FileAttachment;
      try {
        fileInfo = await this.pollFileStatus(
          response.file_id,
          30,
          2000,
          undefined, // checkMounted
          resolvedApiUrl,
          resolvedAdapterName
        );
      } catch (error: unknown) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        if (errorMessage.includes('was deleted')) {
          throw new Error(`File ${response.file_id} was deleted during upload`);
        }
        debugWarn(`File status polling failed for ${response.file_id}:`, error);
        fileInfo = {
          file_id: response.file_id,
          filename: response.filename,
          mime_type: response.mime_type,
          file_size: response.file_size,
          processing_status: response.status || 'processing',
          chunk_count: response.chunk_count
        };
      }

      // Report completion
      if (onProgress) {
        onProgress({
          filename: file.name,
          progress: 100,
          status: fileInfo.processing_status === 'completed' ? 'completed' : 'processing',
          fileId: response.file_id
        });
      }

      return fileInfo;

    } catch (error: unknown) {
      let errorMessage = error instanceof Error ? error.message : 'Upload failed';

      if (errorMessage.includes('401')) {
        errorMessage = 'Authentication failed. Please check your adapter configuration.';
      }

      if (onProgress) {
        onProgress({
          filename: file.name,
          progress: 0,
          status: 'error',
          error: errorMessage
        });
      }
      throw new Error(errorMessage);
    }
  }

  /**
   * Upload multiple files
   *
   * @param files - Array of files to upload
   * @param onProgress - Optional progress callback for each file
   * @returns Promise resolving to array of file attachments
   */
  static async uploadFiles(
    files: File[],
    onProgress?: (fileIndex: number, progress: FileUploadProgress) => void
  ): Promise<FileAttachment[]> {
    const uploadPromises = files.map(async (file, index) => {
      try {
        return await this.uploadFile(file, progress => {
          if (onProgress) {
            onProgress(index, progress);
          }
        });
      } catch (error: unknown) {
        logError(`Failed to upload file ${file.name}:`, error);
        throw error;
      }
    });

    return Promise.all(uploadPromises);
  }

  /**
   * List all files for the current adapter
   *
   * @param _reserved - Unused (previously apiKey)
   * @param apiUrl - Optional API URL
   * @param adapterName - Optional adapter name
   * @returns Promise resolving to array of file attachments
   * @throws Error if request fails
   */
  static async listFiles(_reserved?: string, apiUrl?: string, adapterName?: string): Promise<FileAttachment[]> {
    try {
      const api = await getApi();
      const resolvedApiUrl = apiUrl?.trim() || getApiUrl();
      const resolvedAdapterName = resolveAdapterName(adapterName);

      if (!resolvedAdapterName) {
        throw new Error('Adapter not configured');
      }

      const client = new api.ApiClient({
        apiUrl: resolvedApiUrl,
        sessionId: null,
        adapterName: resolvedAdapterName
      });

      if (!client.listFiles) {
        throw new Error('File listing is not available.');
      }

      const filesResponse = await client.listFiles();
      const files = Array.isArray(filesResponse)
        ? filesResponse
        : Array.isArray((filesResponse as { files?: FileAttachment[] }).files)
          ? (filesResponse as { files: FileAttachment[] }).files
          : [];

      return files.map((file: {
        file_id: string;
        filename: string;
        mime_type: string;
        file_size: number;
        upload_timestamp?: string;
        processing_status?: string;
        chunk_count?: number;
      }) => ({
        file_id: file.file_id,
        filename: file.filename,
        mime_type: file.mime_type,
        file_size: file.file_size,
        upload_timestamp: file.upload_timestamp,
        processing_status: file.processing_status,
        chunk_count: file.chunk_count
      }));
    } catch (error: unknown) {
      logError('Failed to list files:', error);
      const message = error instanceof Error ? error.message : 'Failed to list files';
      throw new Error(message);
    }
  }

  /**
   * Get file information from the server
   *
   * @param fileId - The file ID to get info for
   * @param _reserved - Unused (previously apiKey)
   * @param apiUrl - Optional API URL
   * @param adapterName - Optional adapter name
   * @returns Promise resolving to file attachment metadata
   * @throws Error if request fails
   */
  static async getFileInfo(fileId: string, _reserved?: string, apiUrl?: string, adapterName?: string): Promise<FileAttachment> {
    try {
      const api = await getApi();
      const resolvedApiUrl = apiUrl?.trim() || getApiUrl();
      const resolvedAdapterName = resolveAdapterName(adapterName);

      if (!resolvedAdapterName) {
        throw new Error('Adapter not configured');
      }

      const client = new api.ApiClient({
        apiUrl: resolvedApiUrl,
        sessionId: null,
        adapterName: resolvedAdapterName
      });

      if (!client.getFileInfo) {
        throw new Error('File info retrieval is not available.');
      }

      const fileInfo = await client.getFileInfo(fileId);

      return {
        file_id: fileInfo.file_id,
        filename: fileInfo.filename,
        mime_type: fileInfo.mime_type,
        file_size: fileInfo.file_size,
        upload_timestamp: fileInfo.upload_timestamp,
        processing_status: fileInfo.processing_status,
        chunk_count: fileInfo.chunk_count
      };
    } catch (error: unknown) {
      if (
        error instanceof Error &&
        (error.message.includes('404') || error.message.includes('File not found'))
      ) {
        throw new Error(`File ${fileId} was deleted`);
      }
      logError(`Failed to get file info for ${fileId}:`, error);
      const message = error instanceof Error ? error.message : `Failed to get file info: ${fileId}`;
      throw new Error(message);
    }
  }

  /**
   * Poll file status until processing is complete
   *
   * @param fileId - The file ID to poll
   * @param maxAttempts - Maximum number of polling attempts (default: 30)
   * @param pollInterval - Interval between polls in milliseconds (default: 2000)
   * @param checkMounted - Optional function to check if component is still mounted
   * @param apiUrl - Optional API URL
   * @param adapterName - Optional adapter name
   * @returns Promise resolving to file attachment metadata when processing is complete
   * @throws Error if polling times out or fails
   */
  static async pollFileStatus(
    fileId: string,
    maxAttempts: number = 30,
    pollInterval: number = 2000,
    checkMounted?: () => boolean,
    apiUrl?: string,
    adapterName?: string
  ): Promise<FileAttachment> {
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        if (checkMounted && !checkMounted()) {
          throw new Error(`Polling cancelled - component unmounted`);
        }

        const fileInfo = await this.getFileInfo(fileId, undefined, apiUrl, adapterName);

        if (fileInfo.processing_status === 'completed') {
          return fileInfo;
        }

        if (fileInfo.processing_status === 'error' || fileInfo.processing_status === 'failed') {
          throw new Error(`File processing failed for ${fileId}`);
        }

        if (attempt < maxAttempts - 1) {
          await new Promise(resolve => setTimeout(resolve, pollInterval));
        }
      } catch (error: unknown) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        if (
          errorMessage.includes('404') ||
          errorMessage.includes('File not found') ||
          errorMessage.includes('was deleted')
        ) {
          throw new Error(`File ${fileId} was deleted during upload`);
        }

        if (errorMessage.includes('component unmounted')) {
          throw error;
        }

        if (attempt < maxAttempts - 1) {
          await new Promise(resolve => setTimeout(resolve, pollInterval));
          continue;
        }
        throw error;
      }
    }

    throw new Error(`File processing timeout: ${fileId} did not complete within ${maxAttempts * pollInterval / 1000} seconds`);
  }

  /**
   * Delete a file from the server
   *
   * @param fileId - The file ID to delete
   * @param _reserved - Unused (previously apiKey)
   * @param apiUrl - Optional API URL
   * @param adapterName - Optional adapter name
   * @returns Promise resolving to deletion result
   * @throws Error if deletion fails
   */
  static async deleteFile(fileId: string, _reserved?: string, apiUrl?: string, adapterName?: string): Promise<{ message: string; file_id: string }> {
    try {
      const api = await getApi();
      const resolvedApiUrl = apiUrl?.trim() || getApiUrl();
      const resolvedAdapterName = resolveAdapterName(adapterName);

      if (!resolvedAdapterName) {
        throw new Error('Adapter not configured');
      }

      const client = new api.ApiClient({
        apiUrl: resolvedApiUrl,
        sessionId: null,
        adapterName: resolvedAdapterName
      });

      if (!client.deleteFile) {
        throw new Error('File deletion is not available.');
      }

      return await client.deleteFile(fileId);
    } catch (error: unknown) {
      if (
        error instanceof Error &&
        (error.message.includes('404') || error.message.includes('File not found') || error.message.includes('Not Found'))
      ) {
        debugLog(`File ${fileId} was already deleted from server`);
        return { message: 'File already deleted', file_id: fileId };
      }

      logError(`Failed to delete file ${fileId}:`, error);
      const message = error instanceof Error ? error.message : `Failed to delete file: ${fileId}`;
      throw new Error(message);
    }
  }
}
