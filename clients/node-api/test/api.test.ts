import { describe, it, expect, vi, beforeEach } from 'vitest';
import { streamChat, StreamResponse, configureApi } from '../api';
import { TEST_API_KEY, TEST_API_URL } from './config';

describe('Chatbot API', () => {
  // Set up the API configuration before each test
  beforeEach(() => {
    // Configure with the test server URL and API key
    configureApi(TEST_API_URL, TEST_API_KEY);
  });

  describe('streamChat', () => {
    it('should stream chat responses', async () => {
      const responses: StreamResponse[] = [];

      for await (const response of streamChat('Hello')) {
        responses.push(response);
      }

      // Check that we got the expected number of responses (3 content chunks + 1 final empty done signal)
      expect(responses.length).toBe(4);

      // Check the first response
      expect(responses[0].text).toBe('Hello! ');
      expect(responses[0].done).toBe(false);

      // Check the second response
      expect(responses[1].text).toBe('This is a test response. ');
      expect(responses[1].done).toBe(false);

      // Check the third response (last content)
      expect(responses[2].text).toBe('Response complete.');
      expect(responses[2].done).toBe(false);

      // Check the final empty done signal
      expect(responses[3].text).toBe('');
      expect(responses[3].done).toBe(true);
    });
    
    it('should handle network errors gracefully', async () => {
      // Override the fetch implementation to simulate a network error
      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockRejectedValue(new Error('Network error'));
      
      try {
        const responses: StreamResponse[] = [];
        
        for await (const response of streamChat('Error test', true)) {
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
