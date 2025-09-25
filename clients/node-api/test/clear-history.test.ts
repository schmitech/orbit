import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ApiClient } from '../api';

describe('Clear History', () => {
  let client: ApiClient;
  
  beforeEach(() => {
    client = new ApiClient({
      apiUrl: 'http://localhost:3000',
      apiKey: 'test-key',
      sessionId: 'test-session'
    });
  });
  
  it('should clear conversation history successfully', async () => {
    const mockResponse = {
      status: 'success',
      message: 'Cleared 5 messages from session test-session',
      session_id: 'test-session',
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
    expect(result.session_id).toBe('test-session');
  });
  
  it('should throw error when no session ID available', async () => {
    const clientWithoutSession = new ApiClient({
      apiUrl: 'http://localhost:3000',
      apiKey: 'test-key',
      sessionId: null
    });
    
    await expect(clientWithoutSession.clearConversationHistory()).rejects.toThrow(
      'No session ID provided and no current session available'
    );
  });
  
  it('should throw error when no API key available', async () => {
    const clientWithoutApiKey = new ApiClient({
      apiUrl: 'http://localhost:3000',
      apiKey: null,
      sessionId: 'test-session'
    });
    
    await expect(clientWithoutApiKey.clearConversationHistory()).rejects.toThrow(
      'API key is required for clearing conversation history'
    );
  });
});
