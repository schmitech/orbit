import { describe, it, expect, vi, beforeEach } from 'vitest';
import { streamChat, StreamResponse, configureApi } from '../api';

describe('Chatbot API', () => {
  // Set up the API configuration before each test
  beforeEach(() => {
    // Configure with the test server URL - matches the one in setup.ts
    configureApi('http://test-api-server.com');
  });

  describe('streamChat', () => {
    it('should stream chat responses without voice', async () => {
      const responses: StreamResponse[] = [];
      
      for await (const response of streamChat('Hello', false)) {
        responses.push(response);
      }
      
      // Check that we got the expected number of responses
      expect(responses.length).toBeGreaterThanOrEqual(3);
      
      // Check the first response
      expect(responses[0].text).toBe('Hello! ');
      expect(responses[0].done).toBe(false);
      
      // Check the second response
      expect(responses[1].text).toBe('This is a test response. ');
      expect(responses[1].done).toBe(false);
      
      // Check the final response
      const lastResponse = responses[responses.length - 1];
      expect(lastResponse.text).toBe('Response complete.');
      expect(lastResponse.done).toBe(true);
    });
    
    it('should stream chat responses with voice enabled', async () => {
      const responses: StreamResponse[] = [];
      
      for await (const response of streamChat('Hello with voice', true)) {
        responses.push(response);
      }
      
      // Check that we got the expected number of responses
      expect(responses.length).toBeGreaterThanOrEqual(3);
      
      // Check the first response
      expect(responses[0].text).toBe('Hello! ');
      expect(responses[0].done).toBe(false);
      
      // Check the second response
      expect(responses[1].text).toBe('This is a test response. ');
      expect(responses[1].done).toBe(false);
      
      // Check the final response
      const lastResponse = responses[responses.length - 1];
      expect(lastResponse.text).toBe('Response complete.');
      expect(lastResponse.done).toBe(true);
    });
    
    it('should handle network errors gracefully', async () => {
      // Override the fetch implementation to simulate a network error
      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockRejectedValue(new Error('Network error'));
      
      try {
        const responses: StreamResponse[] = [];
        
        for await (const response of streamChat('Error test', false)) {
          responses.push(response);
        }
        
        // Should not reach here due to error
        expect(responses.length).toBe(0);
      } catch (error: any) {
        // Should throw the network error
        expect(error.message).toBe('Network error');
      } finally {
        // Restore the original fetch implementation
        global.fetch = originalFetch;
      }
    });
  });
}); 