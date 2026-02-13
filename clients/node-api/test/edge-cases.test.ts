import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { streamChat, configureApi, ApiClient } from '../api';
import { TEST_API_KEY, TEST_API_URL } from './config';

describe('Edge Cases and Error Handling', () => {
  beforeEach(() => {
    configureApi(TEST_API_URL, TEST_API_KEY);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Malformed Responses', () => {
    it('should handle malformed JSON in SSE stream', async () => {
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          // Send malformed JSON
          controller.enqueue(encoder.encode('data: {invalid json}\n\n'));
          // Then send valid JSON
          controller.enqueue(encoder.encode('data: {"response": "Valid response", "done": false}\n\n'));
          controller.enqueue(encoder.encode('data: {"done": true}\n\n'));
          controller.enqueue(encoder.encode('data: [DONE]\n\n'));
          controller.close();
        }
      });

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'text/event-stream' }),
        body: stream
      });

      const responses = [];
      for await (const response of streamChat('test')) {
        responses.push(response);
      }

      // Should skip malformed JSON and process valid response
      expect(responses.length).toBeGreaterThan(0);
      expect(responses.some(r => r.text === 'Valid response')).toBe(true);
    });

    it('should handle incomplete SSE chunks', async () => {
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          // Send incomplete chunk
          controller.enqueue(encoder.encode('data: {"response": "Part'));
          // Complete it in next chunk
          controller.enqueue(encoder.encode('ial response", "done": false}\n\n'));
          controller.enqueue(encoder.encode('data: {"response": "Complete", "done": true}\n\n'));
          controller.enqueue(encoder.encode('data: [DONE]\n\n'));
          controller.close();
        }
      });

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'text/event-stream' }),
        body: stream
      });

      const responses = [];
      for await (const response of streamChat('test')) {
        responses.push(response);
      }

      expect(responses.length).toBeGreaterThan(0);
      expect(responses.some(r => r.text === 'Partial response')).toBe(true);
    });
  });

  describe('Timeout Handling', () => {
    it('should handle request timeout', async () => {
      // Mock a fetch that never resolves within timeout
      global.fetch = vi.fn().mockImplementation(() =>
        new Promise((resolve) => {
          setTimeout(() => resolve({
            ok: false,
            status: 408,
            text: () => Promise.resolve('Request Timeout')
          }), 70000); // Longer than 60s timeout
        })
      );

      // Create AbortController mock
      const abortError = new Error('Connection timed out. Please check if the server is running.');
      abortError.name = 'AbortError';

      global.fetch = vi.fn().mockRejectedValue(abortError);

      await expect(async () => {
        const responses = [];
        for await (const response of streamChat('test')) {
          responses.push(response);
        }
      }).rejects.toThrow('Connection timed out');
    });
  });

  describe('Empty and Special Messages', () => {
    it('should handle empty message', async () => {
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode('data: {"response": "Received empty message", "done": true}\n\n'));
          controller.enqueue(encoder.encode('data: [DONE]\n\n'));
          controller.close();
        }
      });

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'text/event-stream' }),
        body: stream
      });

      const responses = [];
      for await (const response of streamChat('')) {
        responses.push(response);
      }

      expect(responses.length).toBeGreaterThan(0);
    });

    it('should handle very long messages', async () => {
      const longMessage = 'a'.repeat(10000);
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode('data: {"response": "Processed long message", "done": true}\n\n'));
          controller.enqueue(encoder.encode('data: [DONE]\n\n'));
          controller.close();
        }
      });

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'text/event-stream' }),
        body: stream
      });

      const responses = [];
      for await (const response of streamChat(longMessage)) {
        responses.push(response);
      }

      expect(responses.length).toBeGreaterThan(0);
      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          body: expect.stringContaining(longMessage)
        })
      );
    });

    it('should handle special characters in messages', async () => {
      const specialMessage = 'Test "quotes" and \'apostrophes\' and \n newlines \t tabs';
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode('data: {"response": "Handled special chars", "done": true}\n\n'));
          controller.enqueue(encoder.encode('data: [DONE]\n\n'));
          controller.close();
        }
      });

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'text/event-stream' }),
        body: stream
      });

      const responses = [];
      for await (const response of streamChat(specialMessage)) {
        responses.push(response);
      }

      expect(responses.length).toBeGreaterThan(0);
    });
  });

  describe('HTTP Status Codes', () => {
    it('should handle 401 Unauthorized', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        text: () => Promise.resolve('Unauthorized: Invalid API key')
      });

      await expect(async () => {
        const responses = [];
        for await (const response of streamChat('test')) {
          responses.push(response);
        }
      }).rejects.toThrow('Network response was not ok: 401');
    });

    it('should handle 429 Rate Limit', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 429,
        text: () => Promise.resolve('Too Many Requests')
      });

      await expect(async () => {
        const responses = [];
        for await (const response of streamChat('test')) {
          responses.push(response);
        }
      }).rejects.toThrow('Network response was not ok: 429');
    });

    it('should handle 500 Server Error', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        text: () => Promise.resolve('Internal Server Error')
      });

      await expect(async () => {
        const responses = [];
        for await (const response of streamChat('test')) {
          responses.push(response);
        }
      }).rejects.toThrow('Network response was not ok: 500');
    });
  });

  describe('Session Management', () => {
    it('should maintain session ID across requests', async () => {
      const client = new ApiClient({
        apiUrl: TEST_API_URL,
        apiKey: TEST_API_KEY,
        sessionId: 'test-session-123'
      });

      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode('data: {"response": "Response", "done": true}\n\n'));
          controller.enqueue(encoder.encode('data: [DONE]\n\n'));
          controller.close();
        }
      });

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'text/event-stream' }),
        body: stream
      });

      const responses = [];
      for await (const response of client.streamChat('test')) {
        responses.push(response);
      }

      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'X-Session-ID': 'test-session-123'
          })
        })
      );
    });

    it('should allow updating session ID', () => {
      const client = new ApiClient({
        apiUrl: TEST_API_URL,
        apiKey: TEST_API_KEY,
        sessionId: 'old-session'
      });

      expect(client.getSessionId()).toBe('old-session');

      client.setSessionId('new-session');
      expect(client.getSessionId()).toBe('new-session');

      client.setSessionId(null);
      expect(client.getSessionId()).toBeNull();
    });
  });

  describe('Non-Streaming Mode', () => {
    it('should handle non-streaming responses', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: () => Promise.resolve({
          response: 'Non-streaming response text'
        })
      });

      const responses = [];
      for await (const response of streamChat('test', false)) {
        responses.push(response);
      }

      expect(responses.length).toBe(1);
      expect(responses[0].text).toBe('Non-streaming response text');
      expect(responses[0].done).toBe(true);
    });
  });

  describe('Buffer Management', () => {
    it('should handle very large streaming responses', async () => {
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          // Send many chunks
          for (let i = 0; i < 100; i++) {
            controller.enqueue(encoder.encode(`data: {"response": "Chunk ${i} ", "done": false}\n\n`));
          }
          controller.enqueue(encoder.encode('data: {"response": "Final", "done": false}\n\n'));
          controller.enqueue(encoder.encode('data: {"done": true}\n\n'));
          controller.enqueue(encoder.encode('data: [DONE]\n\n'));
          controller.close();
        }
      });

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'text/event-stream' }),
        body: stream
      });

      const responses = [];
      for await (const response of streamChat('test')) {
        responses.push(response);
      }

      expect(responses.length).toBeGreaterThan(100);
      expect(responses.some(r => r.text === 'Final')).toBe(true);
    });
  });
});
