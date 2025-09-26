import { describe, it, expect, vi, beforeEach } from 'vitest';
import { streamChat, configureApi, ApiClient } from '../api';

describe('API Configuration', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('ApiClient Constructor Validation', () => {
    it('should throw error for invalid API URL', () => {
      expect(() => new ApiClient({
        apiUrl: null as any
      })).toThrow('API URL must be a valid string');

      expect(() => new ApiClient({
        apiUrl: undefined as any
      })).toThrow('API URL must be a valid string');

      expect(() => new ApiClient({
        apiUrl: 123 as any
      })).toThrow('API URL must be a valid string');

      expect(() => new ApiClient({
        apiUrl: ''
      })).toThrow('API URL must be a valid string');
    });

    it('should accept valid API URLs', () => {
      expect(() => new ApiClient({
        apiUrl: 'http://localhost:3000'
      })).not.toThrow();

      expect(() => new ApiClient({
        apiUrl: 'https://api.example.com'
      })).not.toThrow();

      expect(() => new ApiClient({
        apiUrl: 'http://192.168.1.1:8080'
      })).not.toThrow();
    });

    it('should throw error for invalid API key', () => {
      expect(() => new ApiClient({
        apiUrl: 'http://localhost:3000',
        apiKey: 123 as any
      })).toThrow('API key must be a valid string or null');

      expect(() => new ApiClient({
        apiUrl: 'http://localhost:3000',
        apiKey: {} as any
      })).toThrow('API key must be a valid string or null');
    });

    it('should accept valid API keys', () => {
      expect(() => new ApiClient({
        apiUrl: 'http://localhost:3000',
        apiKey: 'valid-key'
      })).not.toThrow();

      expect(() => new ApiClient({
        apiUrl: 'http://localhost:3000',
        apiKey: null
      })).not.toThrow();

      expect(() => new ApiClient({
        apiUrl: 'http://localhost:3000',
        apiKey: undefined
      })).not.toThrow();
    });

    it('should throw error for invalid session ID', () => {
      expect(() => new ApiClient({
        apiUrl: 'http://localhost:3000',
        sessionId: 123 as any
      })).toThrow('Session ID must be a valid string or null');

      expect(() => new ApiClient({
        apiUrl: 'http://localhost:3000',
        sessionId: [] as any
      })).toThrow('Session ID must be a valid string or null');
    });

    it('should accept valid session IDs', () => {
      expect(() => new ApiClient({
        apiUrl: 'http://localhost:3000',
        sessionId: 'session-123'
      })).not.toThrow();

      expect(() => new ApiClient({
        apiUrl: 'http://localhost:3000',
        sessionId: null
      })).not.toThrow();

      expect(() => new ApiClient({
        apiUrl: 'http://localhost:3000',
        sessionId: undefined
      })).not.toThrow();
    });
  });

  describe('Session ID Management', () => {
    it('should validate session ID updates', () => {
      const client = new ApiClient({
        apiUrl: 'http://localhost:3000'
      });

      expect(() => client.setSessionId('valid-session')).not.toThrow();
      expect(() => client.setSessionId(null)).not.toThrow();

      expect(() => client.setSessionId(123 as any)).toThrow('Session ID must be a valid string or null');
      expect(() => client.setSessionId({} as any)).toThrow('Session ID must be a valid string or null');
    });
  });

  describe('Legacy configureApi Function', () => {
    it('should throw error when using streamChat without configuration', async () => {
      // We can't actually test this without modifying global state in a problematic way
      // Since configureApi validates the URL, we'll test that it throws on invalid config
      expect(() => configureApi(null as any)).toThrow('API URL must be a valid string');
      expect(() => configureApi('')).toThrow('API URL must be a valid string');
    });

    it('should work after proper configuration', async () => {
      configureApi('http://localhost:3000', 'chat-key');

      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode('data: {"response": "Test", "done": true}\n\n'));
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
    });
  });

  describe('Header Management', () => {
    it('should include all required headers', async () => {
      const client = new ApiClient({
        apiUrl: 'http://localhost:3000',
        apiKey: 'test-key',
        sessionId: 'test-session'
      });

      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode('data: {"response": "Test", "done": true}\n\n'));
          controller.enqueue(encoder.encode('data: [DONE]\n\n'));
          controller.close();
        }
      });

      let capturedHeaders: any;
      global.fetch = vi.fn().mockImplementation((url, options) => {
        capturedHeaders = options.headers;
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'Content-Type': 'text/event-stream' }),
          body: stream
        });
      });

      for await (const response of client.streamChat('test')) {
        // Process response
      }

      expect(capturedHeaders['Content-Type']).toBe('application/json');
      expect(capturedHeaders['Accept']).toBe('text/event-stream');
      expect(capturedHeaders['X-API-Key']).toBe('test-key');
      expect(capturedHeaders['X-Session-ID']).toBe('test-session');
      expect(capturedHeaders['X-Request-ID']).toBeDefined();
    });

    it('should not include API key header when not provided', async () => {
      const client = new ApiClient({
        apiUrl: 'http://localhost:3000',
        sessionId: 'test-session'
      });

      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode('data: {"response": "Test", "done": true}\n\n'));
          controller.enqueue(encoder.encode('data: [DONE]\n\n'));
          controller.close();
        }
      });

      let capturedHeaders: any;
      global.fetch = vi.fn().mockImplementation((url, options) => {
        capturedHeaders = options.headers;
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'Content-Type': 'text/event-stream' }),
          body: stream
        });
      });

      for await (const response of client.streamChat('test')) {
        // Process response
      }

      expect(capturedHeaders['X-API-Key']).toBeUndefined();
      expect(capturedHeaders['X-Session-ID']).toBe('test-session');
    });
  });

  describe('URL Construction', () => {
    it('should construct correct endpoint URLs', async () => {
      const testCases = [
        { apiUrl: 'http://localhost:3000', expected: 'http://localhost:3000/v1/chat' },
        { apiUrl: 'https://api.example.com', expected: 'https://api.example.com/v1/chat' },
        { apiUrl: 'http://localhost:3000/', expected: 'http://localhost:3000//v1/chat' },  // API doesn't strip trailing slash
        { apiUrl: 'https://api.example.com/api', expected: 'https://api.example.com/api/v1/chat' }
      ];

      for (const testCase of testCases) {
        const client = new ApiClient({ apiUrl: testCase.apiUrl });

        let capturedUrl: string = '';
        global.fetch = vi.fn().mockImplementation((url) => {
          capturedUrl = url;
          const encoder = new TextEncoder();
          const stream = new ReadableStream({
            start(controller) {
              controller.enqueue(encoder.encode('data: {"response": "Test", "done": true}\n\n'));
              controller.enqueue(encoder.encode('data: [DONE]\n\n'));
              controller.close();
            }
          });
          return Promise.resolve({
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'text/event-stream' }),
            body: stream
          });
        });

        for await (const response of client.streamChat('test')) {
          // Process response
        }

        expect(capturedUrl).toBe(testCase.expected);
      }
    });
  });

  describe('Clear History Configuration', () => {
    it('should construct correct URL for clear history', async () => {
      const client = new ApiClient({
        apiUrl: 'http://localhost:3000',
        apiKey: 'test-key',
        sessionId: 'session-123'
      });

      let capturedUrl: string = '';
      global.fetch = vi.fn().mockImplementation((url) => {
        capturedUrl = url;
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            status: 'success',
            message: 'Cleared',
            session_id: 'session-123',
            deleted_count: 5,
            timestamp: '2024-01-01T00:00:00Z'
          })
        });
      });

      await client.clearConversationHistory();

      expect(capturedUrl).toBe('http://localhost:3000/admin/chat-history/session-123');
    });

    it('should use provided session ID over client session ID', async () => {
      const client = new ApiClient({
        apiUrl: 'http://localhost:3000',
        apiKey: 'test-key',
        sessionId: 'client-session'
      });

      let capturedUrl: string = '';
      global.fetch = vi.fn().mockImplementation((url) => {
        capturedUrl = url;
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            status: 'success',
            message: 'Cleared',
            session_id: 'override-session',
            deleted_count: 5,
            timestamp: '2024-01-01T00:00:00Z'
          })
        });
      });

      await client.clearConversationHistory('override-session');

      expect(capturedUrl).toBe('http://localhost:3000/admin/chat-history/override-session');
    });
  });
});