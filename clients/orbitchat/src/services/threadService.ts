/**
 * Thread Service
 * 
 * API client for thread management operations.
 */

import { ThreadInfo } from '../types';
import { ApiClient } from '../api/loader';

export class ThreadService {
  private apiClient: ApiClient;

  constructor(apiClient: ApiClient) {
    this.apiClient = apiClient;
  }

  /**
   * Create a thread from a parent message.
   * 
   * @param messageId - ID of the parent message
   * @param sessionId - Session ID of the parent conversation
   * @returns Promise resolving to thread information
   */
  async createThread(messageId: string, sessionId: string): Promise<ThreadInfo> {
    if (!this.apiClient.createThread) {
      throw new Error('Thread creation is not supported by this API client');
    }
    return await this.apiClient.createThread(messageId, sessionId);
  }

  /**
   * Get thread information by thread ID.
   * 
   * @param threadId - Thread identifier
   * @returns Promise resolving to thread information
   */
  async getThreadInfo(threadId: string): Promise<ThreadInfo> {
    if (!this.apiClient.getThreadInfo) {
      throw new Error('Thread info retrieval is not supported by this API client');
    }
    return await this.apiClient.getThreadInfo(threadId);
  }

  /**
   * Delete a thread and its associated dataset.
   * 
   * @param threadId - Thread identifier
   * @returns Promise resolving to deletion result
   */
  async deleteThread(threadId: string): Promise<{ status: string; message: string; thread_id: string }> {
    if (!this.apiClient.deleteThread) {
      throw new Error('Thread deletion is not supported by this API client');
    }
    return await this.apiClient.deleteThread(threadId);
  }
}
