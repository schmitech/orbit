import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ApiClient } from '../api';
import { TEST_API_KEY, TEST_API_URL } from './config';

describe('Admin endpoints', () => {
  let client: ApiClient;

  beforeEach(() => {
    vi.restoreAllMocks();
    client = new ApiClient({ apiUrl: TEST_API_URL, apiKey: TEST_API_KEY });
  });

  // ── API Key Management ────────────────────────────────────────────────────

  describe('createApiKey', () => {
    it('should POST to /admin/api-keys', async () => {
      const mockKey = { api_key: 'key-abc', client_name: 'myapp' };
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(mockKey) });

      const result = await client.createApiKey({ client_name: 'myapp', adapter_name: 'default' }, 'token');

      expect(result.client_name).toBe('myapp');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/admin/api-keys`);
      expect(opts.method).toBe('POST');
      expect(JSON.parse(opts.body)).toMatchObject({ client_name: 'myapp', adapter_name: 'default' });
    });
  });

  describe('listApiKeys', () => {
    it('should GET /admin/api-keys with no filters', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
      await client.listApiKeys({}, 'token');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/admin/api-keys`);
    });

    it('should append query params when provided', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
      await client.listApiKeys({ adapter: 'hr', active_only: true, limit: 5, offset: 10 }, 'token');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toContain('adapter=hr');
      expect(url).toContain('active_only=true');
      expect(url).toContain('limit=5');
      expect(url).toContain('offset=10');
    });
  });

  describe('getApiKeyStatusByValue', () => {
    it('should GET /admin/api-keys/{key}/status', async () => {
      const mockStatus = { exists: true, active: true, adapter_name: 'hr' };
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(mockStatus) });

      const result = await client.getApiKeyStatusByValue('my-key', 'token');

      expect(result.active).toBe(true);
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/admin/api-keys/my-key/status`);
    });
  });

  describe('renameApiKey', () => {
    it('should PATCH /admin/api-keys/{key}/rename with new key as query param', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ message: 'Renamed' }) });
      await client.renameApiKey('old-key', 'new-key', 'token');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toContain(`${TEST_API_URL}/admin/api-keys/old-key/rename`);
      expect(url).toContain('new_api_key=new-key');
      expect(opts.method).toBe('PATCH');
    });
  });

  describe('deactivateApiKey', () => {
    it('should POST to /admin/api-keys/{key}/deactivate using path param', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ message: 'Deactivated' }) });
      await client.deactivateApiKey('key-123', 'token');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/admin/api-keys/key-123/deactivate`);
      expect(opts.method).toBe('POST');
      // Must NOT use a JSON body — the server expects a path param, not a body
      expect(opts.body).toBeUndefined();
    });

    it('should URL-encode the key in the path', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ message: 'ok' }) });
      await client.deactivateApiKey('key/with/slashes', 'token');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toContain('key%2Fwith%2Fslashes');
    });
  });

  describe('deleteApiKey', () => {
    it('should DELETE /admin/api-keys/{key}', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ message: 'Deleted' }) });
      await client.deleteApiKey('key-abc', 'token');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/admin/api-keys/key-abc`);
      expect(opts.method).toBe('DELETE');
    });
  });

  describe('associatePromptWithApiKey', () => {
    it('should POST to /admin/api-keys/{key}/prompt', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ message: 'Associated' }) });
      await client.associatePromptWithApiKey('key-abc', 'prompt-123', 'token');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/admin/api-keys/key-abc/prompt`);
      expect(JSON.parse(opts.body)).toEqual({ prompt_id: 'prompt-123' });
    });
  });

  // ── Quota Management ──────────────────────────────────────────────────────

  describe('getApiKeyQuota', () => {
    it('should GET /admin/api-keys/{key}/quota', async () => {
      const mockQuota = {
        api_key_masked: 'key-***',
        quota: { daily_limit: 1000, monthly_limit: 30000 },
        usage: { daily_used: 5, monthly_used: 100, daily_reset_at: 0, monthly_reset_at: 0 }
      };
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(mockQuota) });

      const result = await client.getApiKeyQuota('key-abc', 'token');

      expect(result.quota.daily_limit).toBe(1000);
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/admin/api-keys/key-abc/quota`);
    });
  });

  describe('updateApiKeyQuota', () => {
    it('should PUT /admin/api-keys/{key}/quota', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ message: 'Updated' }) });
      await client.updateApiKeyQuota('key-abc', { daily_limit: 500 }, 'token');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/admin/api-keys/key-abc/quota`);
      expect(opts.method).toBe('PUT');
      expect(JSON.parse(opts.body)).toEqual({ daily_limit: 500 });
    });
  });

  describe('resetApiKeyQuota', () => {
    it('should POST with default period=daily', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ message: 'Reset' }) });
      await client.resetApiKeyQuota('key-abc', undefined, 'token');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toContain(`${TEST_API_URL}/admin/api-keys/key-abc/quota/reset`);
      expect(url).toContain('period=daily');
    });

    it('should accept monthly period', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ message: 'Reset' }) });
      await client.resetApiKeyQuota('key-abc', 'monthly', 'token');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toContain('period=monthly');
    });
  });

  describe('getQuotaUsageReport', () => {
    it('should GET /admin/quotas/usage-report', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ entries: [] }) });
      await client.getQuotaUsageReport('monthly', 50, 'token');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toContain(`${TEST_API_URL}/admin/quotas/usage-report`);
      expect(url).toContain('period=monthly');
      expect(url).toContain('limit=50');
    });
  });

  // ── Prompt Management ─────────────────────────────────────────────────────

  describe('createPrompt', () => {
    it('should POST to /admin/prompts', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ id: 'p1', name: 'system' }) });
      await client.createPrompt({ name: 'system', prompt: 'You are helpful.' }, 'token');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/admin/prompts`);
      expect(opts.method).toBe('POST');
    });
  });

  describe('listPrompts', () => {
    it('should GET /admin/prompts with optional filters', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
      await client.listPrompts({ name_filter: 'sys', limit: 20 }, 'token');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toContain('name_filter=sys');
      expect(url).toContain('limit=20');
    });
  });

  describe('getPrompt', () => {
    it('should GET /admin/prompts/{id}', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ id: 'p1' }) });
      await client.getPrompt('p1', 'token');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/admin/prompts/p1`);
    });
  });

  describe('updatePrompt', () => {
    it('should PUT /admin/prompts/{id}', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ id: 'p1' }) });
      await client.updatePrompt('p1', { prompt: 'Updated prompt' }, 'token');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/admin/prompts/p1`);
      expect(opts.method).toBe('PUT');
    });
  });

  describe('deletePrompt', () => {
    it('should DELETE /admin/prompts/{id}', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ message: 'Deleted' }) });
      await client.deletePrompt('p1', 'token');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/admin/prompts/p1`);
      expect(opts.method).toBe('DELETE');
    });
  });

  // ── System ────────────────────────────────────────────────────────────────

  describe('reloadAdapters', () => {
    it('should POST to /admin/reload-adapters', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ status: 'ok' }) });
      await client.reloadAdapters(undefined, 'token');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/admin/reload-adapters`);
      expect(opts.method).toBe('POST');
    });

    it('should append adapter_name when provided', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ status: 'ok' }) });
      await client.reloadAdapters('hr', 'token');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toContain('adapter_name=hr');
    });
  });

  describe('getServerInfo', () => {
    it('should GET /admin/info', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ pid: 1234, version: '1.0', status: 'running' }) });
      const result = await client.getServerInfo('token');
      expect(result.pid).toBe(1234);
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/admin/info`);
    });
  });
});
