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
      
      // Ensure no audio content in non-voice mode
      for (const response of responses) {
        expect(response.type).not.toBe('audio');
      }
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
      expect(lastResponse.text).toBe('Voice enabled response.');
      expect(lastResponse.done).toBe(true);
      
      // Check for audio content in the final response
      expect(lastResponse.type).toBe('audio');
      expect(lastResponse.content).toBe('mock-base64-audio-data');
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
        
        // Should only get one error response
        expect(responses.length).toBe(1);
        expect(responses[0].text).toContain('Error connecting to chat server: Network error');
        expect(responses[0].done).toBe(true);
      } finally {
        // Restore the original fetch implementation
        global.fetch = originalFetch;
      }
    });
  });
}); 