import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ApiClient } from '../api';
import { TEST_API_KEY, TEST_API_URL, TEST_SESSION_ID } from './config';

describe('Thread endpoints', () => {
  let client: ApiClient;

  beforeEach(() => {
    vi.restoreAllMocks();
    client = new ApiClient({ apiUrl: TEST_API_URL, apiKey: TEST_API_KEY, sessionId: TEST_SESSION_ID });
  });

  const mockThread = {
    thread_id: 'thread-abc',
    thread_session_id: 'ts-123',
    parent_message_id: 'msg-1',
    parent_session_id: TEST_SESSION_ID,
    adapter_name: 'hr',
    created_at: '2024-01-01T00:00:00Z',
    expires_at: '2024-01-02T00:00:00Z'
  };

  describe('createThread', () => {
    it('should POST to /api/threads', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(mockThread) });

      const result = await client.createThread('msg-1', TEST_SESSION_ID);

      expect(result.thread_id).toBe('thread-abc');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/api/threads`);
      expect(opts.method).toBe('POST');
      expect(JSON.parse(opts.body)).toEqual({ message_id: 'msg-1', session_id: TEST_SESSION_ID });
    });

    it('should include X-API-Key header', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(mockThread) });
      await client.createThread('msg-1', TEST_SESSION_ID);
      const [, opts] = (global.fetch as any).mock.calls[0];
      expect(opts.headers['X-API-Key']).toBe(TEST_API_KEY);
    });

    it('should require API key', async () => {
      const clientNoKey = new ApiClient({ apiUrl: TEST_API_URL, sessionId: TEST_SESSION_ID });
      await expect(clientNoKey.createThread('msg-1', TEST_SESSION_ID)).rejects.toThrow('API key is required');
    });

    it('should throw on HTTP error', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404, text: () => Promise.resolve('Not found') });
      await expect(client.createThread('msg-1', TEST_SESSION_ID)).rejects.toThrow('Failed to create thread');
    });
  });

  describe('getThreadInfo', () => {
    it('should GET /api/threads/{thread_id}', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(mockThread) });

      const result = await client.getThreadInfo('thread-abc');

      expect(result.parent_message_id).toBe('msg-1');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/api/threads/thread-abc`);
    });

    it('should require API key', async () => {
      const clientNoKey = new ApiClient({ apiUrl: TEST_API_URL });
      await expect(clientNoKey.getThreadInfo('t1')).rejects.toThrow('API key is required');
    });
  });

  describe('deleteThread', () => {
    it('should DELETE /api/threads/{thread_id}', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ status: 'deleted', message: 'Thread removed', thread_id: 'thread-abc' })
      });

      const result = await client.deleteThread('thread-abc');

      expect(result.status).toBe('deleted');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/api/threads/thread-abc`);
      expect(opts.method).toBe('DELETE');
    });

    it('should require API key', async () => {
      const clientNoKey = new ApiClient({ apiUrl: TEST_API_URL });
      await expect(clientNoKey.deleteThread('t1')).rejects.toThrow('API key is required');
    });
  });
});
