/**
 * File Upload Service
 * 
 * Handles file uploads to the ORBIT server and manages file metadata.
 */

import { getApi } from '../api/loader';
import { FileAttachment } from '../types';

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
   * @returns Promise resolving to file attachment metadata
   * @throws Error if upload fails
   */
  static async uploadFile(
    file: File,
    onProgress?: (progress: FileUploadProgress) => void
  ): Promise<FileAttachment> {
    try {
      // Validate file size (50MB limit)
      const maxSize = 50 * 1024 * 1024; // 50MB
      if (file.size > maxSize) {
        throw new Error(`File size exceeds maximum limit of ${maxSize / 1024 / 1024}MB`);
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
        'image/png',
        'image/jpeg',
        'image/tiff',
        'audio/wav',
        'audio/mpeg',
        'text/vtt'
      ];

      // Check MIME type or extension
      // Note: Some browsers may detect Excel files as application/x-zip-compressed
      // or application/zip because XLSX files are ZIP archives, so we also check by extension
      const isValidType = allowedTypes.includes(file.type) ||
        /\.(pdf|txt|md|csv|json|html|docx|pptx|xlsx|png|jpe?g|tiff?|wav|mp3|vtt)$/i.test(file.name) ||
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
      // Use the same API configuration as the chat store
      const api = await getApi();
      const apiUrl = localStorage.getItem('chat-api-url') || 
                     (import.meta.env as any).VITE_API_URL || 
                     (window as any).CHATBOT_API_URL ||
                     'http://localhost:3000';
      const apiKey = localStorage.getItem('chat-api-key') || 
                     (import.meta.env as any).VITE_API_KEY ||
                     (window as any).CHATBOT_API_KEY ||
                     'orbit-123456789';
      
      // Validate API key is configured
      // Note: API keys typically start with "orbit_" but some may be custom/simple keys
      if (!apiKey || apiKey === 'your-api-key-here' || apiKey === 'orbit-123456789') {
        throw new Error(
          'API key not configured or invalid. Please:\n' +
          '1. Open Settings (⚙️ icon) in the top-right corner\n' +
          '2. Enter a valid API key\n' +
          '3. To create an API key: POST to /admin/api-keys with admin credentials\n' +
          '   Or use the admin interface to generate one'
        );
      }
      
      // Log masked API key for debugging (only first 8 and last 4 characters)
      const maskedKey = apiKey.length > 12 
        ? `${apiKey.substring(0, 8)}...${apiKey.substring(apiKey.length - 4)}`
        : `${apiKey.substring(0, Math.min(4, apiKey.length))}...`;
      
      const debugMode = (import.meta.env as any).VITE_CONSOLE_DEBUG === 'true';
      if (debugMode) {
        console.log(`🔑 Using API key: ${maskedKey} (masked for security)`);
      }
      
      const client = new api.ApiClient({ apiUrl, apiKey, sessionId: null });

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
        console.warn(`File status polling failed for ${response.file_id}:`, error.message || error);
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
        
        errorMessage = `Invalid API key (using: ${maskedKey}). Please:\n` +
                      '1. Open Settings (⚙️ icon) in the top-right corner\n' +
                      '2. Enter a valid API key\n' +
                      '3. To create an API key: Use the admin interface or POST to /admin/api-keys\n' +
                      '   Example: curl -X POST http://localhost:3000/admin/api-keys \\\n' +
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
        console.error(`Failed to upload file ${file.name}:`, error);
        throw error;
      }
    });

    return Promise.all(uploadPromises);
  }

  /**
   * List all files for the current API key
   * 
   * @returns Promise resolving to array of file attachments
   * @throws Error if request fails
   */
  static async listFiles(): Promise<FileAttachment[]> {
    try {
      const api = await getApi();
      const apiUrl = localStorage.getItem('chat-api-url') || 
                     (import.meta.env as any).VITE_API_URL || 
                     (window as any).CHATBOT_API_URL ||
                     'http://localhost:3000';
      const apiKey = localStorage.getItem('chat-api-key') || 
                     (import.meta.env as any).VITE_API_KEY ||
                     (window as any).CHATBOT_API_KEY ||
                     'orbit-123456789';
      
      if (!apiKey || apiKey === 'your-api-key-here' || apiKey === 'orbit-123456789') {
        throw new Error('API key not configured');
      }

      const client = new api.ApiClient({ apiUrl, apiKey, sessionId: null });

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
      console.error('Failed to list files:', error);
      throw new Error(error.message || 'Failed to list files');
    }
  }

  /**
   * Get file information from the server
   * 
   * @param fileId - The file ID to get info for
   * @returns Promise resolving to file attachment metadata
   * @throws Error if request fails
   */
  static async getFileInfo(fileId: string): Promise<FileAttachment> {
    try {
      const api = await getApi();
      const apiUrl = localStorage.getItem('chat-api-url') || 
                     (import.meta.env as any).VITE_API_URL || 
                     (window as any).CHATBOT_API_URL ||
                     'http://localhost:3000';
      const apiKey = localStorage.getItem('chat-api-key') || 
                     (import.meta.env as any).VITE_API_KEY ||
                     (window as any).CHATBOT_API_KEY ||
                     'orbit-123456789';
      
      if (!apiKey || apiKey === 'your-api-key-here' || apiKey === 'orbit-123456789') {
        throw new Error('API key not configured');
      }

      const client = new api.ApiClient({ apiUrl, apiKey, sessionId: null });

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
      console.error(`Failed to get file info for ${fileId}:`, error);
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
   * @returns Promise resolving to deletion result
   * @throws Error if deletion fails
   */
  static async deleteFile(fileId: string): Promise<{ message: string; file_id: string }> {
    try {
      const api = await getApi();
      const apiUrl = localStorage.getItem('chat-api-url') || 
                     (import.meta.env as any).VITE_API_URL || 
                     (window as any).CHATBOT_API_URL ||
                     'http://localhost:3000';
      const apiKey = localStorage.getItem('chat-api-key') || 
                     (import.meta.env as any).VITE_API_KEY ||
                     (window as any).CHATBOT_API_KEY ||
                     'orbit-123456789';
      
      if (!apiKey || apiKey === 'your-api-key-here' || apiKey === 'orbit-123456789') {
        throw new Error('API key not configured');
      }

      const client = new api.ApiClient({ apiUrl, apiKey, sessionId: null });

      if (!client.deleteFile) {
        throw new Error('File deletion is not available. Please use the local API build or update the npm package.');
      }

      return await client.deleteFile(fileId);
    } catch (error: any) {
      // If file was already deleted (404), that's fine - return a success response
      if (error.message && (error.message.includes('404') || error.message.includes('File not found') || error.message.includes('Not Found'))) {
        console.log(`File ${fileId} was already deleted from server`);
        return { message: 'File already deleted', file_id: fileId };
      }
      
      console.error(`Failed to delete file ${fileId}:`, error);
      throw new Error(error.message || `Failed to delete file: ${fileId}`);
    }
  }
}

