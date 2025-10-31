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
        'image/png',
        'image/jpeg',
        'image/tiff',
        'audio/wav',
        'audio/mpeg',
        'text/vtt'
      ];

      // Check MIME type or extension
      const isValidType = allowedTypes.includes(file.type) ||
        /\.(pdf|txt|md|csv|json|html|docx|pptx|xlsx|png|jpe?g|tiff?|wav|mp3|vtt)$/i.test(file.name);

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

      // Wait a moment for processing to complete
      await new Promise(resolve => setTimeout(resolve, 1000));

      // Report completion
      if (onProgress) {
        onProgress({
          filename: file.name,
          progress: 100,
          status: 'completed',
          fileId: response.file_id
        });
      }

      // Return file attachment metadata
      return {
        file_id: response.file_id,
        filename: response.filename,
        mime_type: response.mime_type,
        file_size: response.file_size,
        processing_status: response.status,
        chunk_count: response.chunk_count
      };

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
}

