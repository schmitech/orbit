import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ApiClient } from '../api';
import { TEST_API_KEY, TEST_API_URL, TEST_SESSION_ID } from './config';

describe('Feedback endpoints', () => {
  let client: ApiClient;

  beforeEach(() => {
    vi.restoreAllMocks();
    client = new ApiClient({ apiUrl: TEST_API_URL, apiKey: TEST_API_KEY, sessionId: TEST_SESSION_ID });
  });

  describe('submitFeedback', () => {
    it('should POST to /api/feedback with thumbs up', async () => {
      const mockResponse = { message_id: 'msg-1', feedback_type: 'up', action: 'created' };
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(mockResponse) });

      const result = await client.submitFeedback('msg-1', TEST_SESSION_ID, 'up');

      expect(result.feedback_type).toBe('up');
      expect(result.action).toBe('created');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/api/feedback`);
      expect(opts.method).toBe('POST');
      expect(JSON.parse(opts.body)).toEqual({
        message_id: 'msg-1',
        session_id: TEST_SESSION_ID,
        feedback_type: 'up'
      });
    });

    it('should POST with thumbs down', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ message_id: 'msg-2', feedback_type: 'down', action: 'created' })
      });

      const result = await client.submitFeedback('msg-2', TEST_SESSION_ID, 'down');

      expect(result.feedback_type).toBe('down');
    });

    it('should toggle feedback when called again (action=removed)', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ message_id: 'msg-1', feedback_type: null, action: 'removed' })
      });

      const result = await client.submitFeedback('msg-1', TEST_SESSION_ID, 'up');

      expect(result.action).toBe('removed');
      expect(result.feedback_type).toBeNull();
    });

    it('should throw on HTTP error', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        text: () => Promise.resolve('Internal Server Error')
      });
      await expect(client.submitFeedback('m1', TEST_SESSION_ID, 'up')).rejects.toThrow('Failed to submit feedback');
    });
  });

  describe('getSessionFeedback', () => {
    it('should GET /api/feedback/{session_id}', async () => {
      const mockResponse = {
        feedbacks: [
          { message_id: 'msg-1', feedback_type: 'up' },
          { message_id: 'msg-2', feedback_type: 'down' }
        ]
      };
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(mockResponse) });

      const result = await client.getSessionFeedback(TEST_SESSION_ID);

      expect(result.feedbacks).toHaveLength(2);
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/api/feedback/${TEST_SESSION_ID}`);
    });

    it('should URL-encode the session ID', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ feedbacks: [] }) });
      await client.getSessionFeedback('session/with/slashes');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toContain('session%2Fwith%2Fslashes');
    });

    it('should return empty feedbacks when no feedback exists', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ feedbacks: [] }) });
      const result = await client.getSessionFeedback(TEST_SESSION_ID);
      expect(result.feedbacks).toHaveLength(0);
    });

    it('should throw on HTTP error', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404, text: () => Promise.resolve('Not found') });
      await expect(client.getSessionFeedback(TEST_SESSION_ID)).rejects.toThrow('Failed to get session feedback');
    });
  });
});
