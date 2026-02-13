import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ApiClient } from '../api';
import { TEST_API_KEY, TEST_API_URL, TEST_SESSION_ID } from './config';

describe('Clear History', () => {
  let client: ApiClient;
  
  beforeEach(() => {
    client = new ApiClient({
      apiUrl: TEST_API_URL,
      apiKey: TEST_API_KEY,
      sessionId: TEST_SESSION_ID
    });
  });
  
  it('should clear conversation history successfully', async () => {
    const mockResponse = {
      status: 'success',
      message: 'Cleared 5 messages from session test-session',
      session_id: TEST_SESSION_ID,
      deleted_count: 5,
      timestamp: '2024-01-01T00:00:00Z'
    };
    
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResponse)
    });
    
    const result = await client.clearConversationHistory();
    
    expect(result.status).toBe('success');
    expect(result.deleted_count).toBe(5);
    expect(result.session_id).toBe(TEST_SESSION_ID);
  });
  
  it('should throw error when no session ID available', async () => {
    const clientWithoutSession = new ApiClient({
      apiUrl: TEST_API_URL,
      apiKey: TEST_API_KEY,
      sessionId: null
    });
    
    await expect(clientWithoutSession.clearConversationHistory()).rejects.toThrow(
      'No session ID provided and no current session available'
    );
  });
  
  it('should throw error when no API key available', async () => {
    const clientWithoutApiKey = new ApiClient({
      apiUrl: TEST_API_URL,
      apiKey: null,
      sessionId: TEST_SESSION_ID
    });
    
    await expect(clientWithoutApiKey.clearConversationHistory()).rejects.toThrow(
      'API key is required for clearing conversation history'
    );
  });
});
