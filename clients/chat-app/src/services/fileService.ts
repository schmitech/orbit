/**
 * File Upload Service
 * 
 * Handles file uploads to the ORBIT server and manages file metadata.
 */

import { getApi } from '../api/loader';
import { FileAttachment } from '../types';
import { debugLog, debugWarn, logError } from '../utils/debug';
import { AppConfig } from '../utils/config';
import { getDefaultKey, getApiUrl, DEFAULT_API_URL } from '../utils/runtimeConfig';

// Default API key from runtime configuration
const DEFAULT_API_KEY = getDefaultKey();
const getStoredApiUrl = (): string | null => {
  try {
    if (typeof window === 'undefined' || !window.localStorage) {
      return null;
    }
    const stored = window.localStorage.getItem('chat-api-url');
    if (stored && stored === DEFAULT_API_URL) {
      window.localStorage.removeItem('chat-api-url');
      return null;
    }
    return stored;
  } catch {
    return null;
  }
};

const determineApiUrl = (explicit?: string | null): string => {
  const trimmed = explicit?.trim();
  if (trimmed) {
    return trimmed;
  }
  const stored = getStoredApiUrl();
  if (stored && stored !== DEFAULT_API_URL) {
    return stored;
  }
  return getApiUrl();
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
   * @param apiKey - Optional API key (falls back to localStorage if not provided)
   * @param apiUrl - Optional API URL (falls back to localStorage if not provided)
   * @returns Promise resolving to file attachment metadata
   * @throws Error if upload fails
   */
  static async uploadFile(
    file: File,
    onProgress?: (progress: FileUploadProgress) => void,
    apiKey?: string,
    apiUrl?: string
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
      // Use provided API key/URL if available, otherwise fall back to localStorage
      const api = await getApi();
      const resolvedApiUrl = determineApiUrl(apiUrl);
      const resolvedApiKey = apiKey || 
                     localStorage.getItem('chat-api-key') || 
                     (window as any).CHATBOT_API_KEY ||
                     DEFAULT_API_KEY;
      
      // Validate API key is configured
      // Note: API keys typically start with "orbit_" but some may be custom/simple keys
      if (!resolvedApiKey || resolvedApiKey === 'your-api-key-here') {
        throw new Error(
          'API key not configured or invalid. Please:\n' +
          '1. Open Settings (⚙️ icon) in the top-right corner\n' +
          '2. Enter a valid API key\n' +
          '3. To create an API key: POST to /admin/api-keys with admin credentials\n' +
          '   Or use the admin interface to generate one'
        );
      }
      
      // Log masked API key for debugging (only first 8 and last 4 characters)
      const maskedKey = resolvedApiKey.length > 12 
        ? `${resolvedApiKey.substring(0, 8)}...${resolvedApiKey.substring(resolvedApiKey.length - 4)}`
        : `${resolvedApiKey.substring(0, Math.min(4, resolvedApiKey.length))}...`;
      
      debugLog(`🔑 Using API key: ${maskedKey} (masked for security)`);
      
      const client = new api.ApiClient({ apiUrl: resolvedApiUrl, apiKey: resolvedApiKey, sessionId: null });

      // Check if uploadFile method exists (for npm package compatibility)
      if (!client.uploadFile) {
        throw new Error('File upload is not available. Please use the local API build or update the npm package.');
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
        // Poll every 2 seconds for up to 60 seconds (30 attempts)
        // Note: checkMounted parameter not available in this context, but errors will be caught
        fileInfo = await this.pollFileStatus(response.file_id, 30, 2000);
      } catch (error: any) {
        // If polling fails, times out, or file was deleted, return the initial response
        // This allows the UI to handle the state appropriately
        if (error.message && error.message.includes('was deleted')) {
          // File was deleted during upload - re-throw to handle cleanup
          throw new Error(`File ${response.file_id} was deleted during upload`);
        }
        // For other errors, log and return initial response
        debugWarn(`File status polling failed for ${response.file_id}:`, error.message || error);
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

      // Return file attachment metadata with updated status
      return fileInfo;

    } catch (error: any) {
      let errorMessage = error.message || 'Upload failed';
      
      // Provide more helpful error messages
      if (errorMessage.includes('401') || errorMessage.includes('Invalid API key')) {
        const currentApiKey = localStorage.getItem('chat-api-key');
        const maskedKey = currentApiKey && currentApiKey.length > 12 
          ? `${currentApiKey.substring(0, 8)}...${currentApiKey.substring(currentApiKey.length - 4)}`
          : currentApiKey || 'not set';
        
        const adminApiUrl = determineApiUrl(apiUrl);
        errorMessage = `Invalid API key (using: ${maskedKey}). Please:\n` +
                      '1. Open Settings (⚙️ icon) in the top-right corner\n' +
                      '2. Enter a valid API key\n' +
                      '3. To create an API key: Use the admin interface or POST to /admin/api-keys\n' +
                      `   Example: curl -X POST ${adminApiUrl}/admin/api-keys \\\n` +
                      '     -H "Authorization: Bearer <admin-token>" \\\n' +
                      '     -H "Content-Type: application/json" \\\n' +
                      '     -d \'{"client_name": "chat-app", "adapter_name": "file-document-qa"}\'';
      } else if (errorMessage.includes('API key not configured')) {
        // Keep the detailed message we added above
        errorMessage = error.message;
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
      } catch (error) {
        // Continue with other files even if one fails
        logError(`Failed to upload file ${file.name}:`, error);
        throw error;
      }
    });

    return Promise.all(uploadPromises);
  }

  /**
   * List all files for the current API key
   * 
   * @param apiKey - Optional API key (falls back to localStorage if not provided)
   * @param apiUrl - Optional API URL (falls back to localStorage if not provided)
   * @returns Promise resolving to array of file attachments
   * @throws Error if request fails
   */
  static async listFiles(apiKey?: string, apiUrl?: string): Promise<FileAttachment[]> {
    try {
      const api = await getApi();
      const resolvedApiUrl = determineApiUrl(apiUrl);
      const resolvedApiKey = apiKey || 
                     localStorage.getItem('chat-api-key') || 
                     (window as any).CHATBOT_API_KEY ||
                     DEFAULT_API_KEY;
      
      if (!resolvedApiKey || resolvedApiKey === 'your-api-key-here' || resolvedApiKey === 'orbit-123456789') {
        throw new Error('API key not configured');
      }

      const client = new api.ApiClient({ apiUrl: resolvedApiUrl, apiKey: resolvedApiKey, sessionId: null });

      if (!client.listFiles) {
        throw new Error('File listing is not available. Please use the local API build or update the npm package.');
      }

      const files = await client.listFiles();
      
      // Convert server response to FileAttachment format
      return files.map(file => ({
        file_id: file.file_id,
        filename: file.filename,
        mime_type: file.mime_type,
        file_size: file.file_size,
        upload_timestamp: file.upload_timestamp,
        processing_status: file.processing_status,
        chunk_count: file.chunk_count
      }));
    } catch (error: any) {
      logError('Failed to list files:', error);
      throw new Error(error.message || 'Failed to list files');
    }
  }

  /**
   * Get file information from the server
   * 
   * @param fileId - The file ID to get info for
   * @param apiKey - Optional API key (falls back to localStorage if not provided)
   * @param apiUrl - Optional API URL (falls back to localStorage if not provided)
   * @returns Promise resolving to file attachment metadata
   * @throws Error if request fails
   */
  static async getFileInfo(fileId: string, apiKey?: string, apiUrl?: string): Promise<FileAttachment> {
    try {
      const api = await getApi();
      const resolvedApiUrl = determineApiUrl(apiUrl);
      const resolvedApiKey = apiKey || 
                     localStorage.getItem('chat-api-key') || 
                     (window as any).CHATBOT_API_KEY ||
                     DEFAULT_API_KEY;
      
      if (!resolvedApiKey || resolvedApiKey === 'your-api-key-here' || resolvedApiKey === 'orbit-123456789') {
        throw new Error('API key not configured');
      }

      const client = new api.ApiClient({ apiUrl: resolvedApiUrl, apiKey: resolvedApiKey, sessionId: null });

      if (!client.getFileInfo) {
        throw new Error('File info retrieval is not available. Please use the local API build or update the npm package.');
      }

      const fileInfo = await client.getFileInfo(fileId);
      
      // Convert server response to FileAttachment format
      return {
        file_id: fileInfo.file_id,
        filename: fileInfo.filename,
        mime_type: fileInfo.mime_type,
        file_size: fileInfo.file_size,
        upload_timestamp: fileInfo.upload_timestamp,
        processing_status: fileInfo.processing_status,
        chunk_count: fileInfo.chunk_count
      };
    } catch (error: any) {
      // Handle 404 specifically - file was deleted
      if (error.message && (error.message.includes('404') || error.message.includes('File not found'))) {
        throw new Error(`File ${fileId} was deleted`);
      }
      logError(`Failed to get file info for ${fileId}:`, error);
      throw new Error(error.message || `Failed to get file info: ${fileId}`);
    }
  }

  /**
   * Poll file status until processing is complete
   * 
   * @param fileId - The file ID to poll
   * @param maxAttempts - Maximum number of polling attempts (default: 30)
   * @param pollInterval - Interval between polls in milliseconds (default: 2000)
   * @param checkMounted - Optional function to check if component is still mounted
   * @returns Promise resolving to file attachment metadata when processing is complete
   * @throws Error if polling times out or fails
   */
  static async pollFileStatus(
    fileId: string,
    maxAttempts: number = 30,
    pollInterval: number = 2000,
    checkMounted?: () => boolean
  ): Promise<FileAttachment> {
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        // Check if component is still mounted before polling
        if (checkMounted && !checkMounted()) {
          throw new Error(`Polling cancelled - component unmounted`);
        }

        const fileInfo = await this.getFileInfo(fileId);
        
        // If processing is complete, return the file info
        if (fileInfo.processing_status === 'completed') {
          return fileInfo;
        }
        
        // If there's an error status, throw
        if (fileInfo.processing_status === 'error' || fileInfo.processing_status === 'failed') {
          throw new Error(`File processing failed for ${fileId}`);
        }
        
        // Wait before next poll
        if (attempt < maxAttempts - 1) {
          await new Promise(resolve => setTimeout(resolve, pollInterval));
        }
      } catch (error: any) {
        // If file not found (404) or was deleted, stop polling immediately
        if (error.message && (
          error.message.includes('404') || 
          error.message.includes('File not found') ||
          error.message.includes('was deleted')
        )) {
          throw new Error(`File ${fileId} was deleted during upload`);
        }
        
        // If component unmounted, stop polling
        if (error.message && error.message.includes('component unmounted')) {
          throw error;
        }
        
        // If it's not the last attempt, continue polling
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
   * @param apiKey - Optional API key (falls back to localStorage if not provided)
   * @param apiUrl - Optional API URL (falls back to localStorage if not provided)
   * @returns Promise resolving to deletion result
   * @throws Error if deletion fails
   */
  static async deleteFile(fileId: string, apiKey?: string, apiUrl?: string): Promise<{ message: string; file_id: string }> {
    try {
      const api = await getApi();
      const resolvedApiUrl = determineApiUrl(apiUrl);
      const resolvedApiKey = apiKey || 
                     localStorage.getItem('chat-api-key') || 
                     (window as any).CHATBOT_API_KEY ||
                     DEFAULT_API_KEY;
      
      if (!resolvedApiKey || resolvedApiKey === 'your-api-key-here' || resolvedApiKey === 'orbit-123456789') {
        throw new Error('API key not configured');
      }

      const client = new api.ApiClient({ apiUrl: resolvedApiUrl, apiKey: resolvedApiKey, sessionId: null });

      if (!client.deleteFile) {
        throw new Error('File deletion is not available. Please use the local API build or update the npm package.');
      }

      return await client.deleteFile(fileId);
    } catch (error: any) {
      // If file was already deleted (404), that's fine - return a success response
      if (error.message && (error.message.includes('404') || error.message.includes('File not found') || error.message.includes('Not Found'))) {
        debugLog(`File ${fileId} was already deleted from server`);
        return { message: 'File already deleted', file_id: fileId };
      }
      
      logError(`Failed to delete file ${fileId}:`, error);
      throw new Error(error.message || `Failed to delete file: ${fileId}`);
    }
  }
}
