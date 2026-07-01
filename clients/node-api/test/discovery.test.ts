import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ApiClient } from '../api';
import { TEST_API_KEY, TEST_API_URL } from './config';

describe('Discovery endpoints (models & skills)', () => {
  let client: ApiClient;

  beforeEach(() => {
    vi.restoreAllMocks();
    client = new ApiClient({ apiUrl: TEST_API_URL, apiKey: TEST_API_KEY });
  });

  describe('getAdapterModels', () => {
    it('should GET /admin/adapters/{adapter}/models', async () => {
      const mockResponse = {
        adapter_name: 'hr',
        models: [{ id: 'gpt-4o', name: 'GPT-4o' }, { id: 'claude-sonnet-4-6' }]
      };
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(mockResponse) });

      const result = await client.getAdapterModels('hr');

      expect(result.adapter_name).toBe('hr');
      expect(result.models).toHaveLength(2);
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/admin/adapters/hr/models`);
    });

    it('should URL-encode the adapter name', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ adapter_name: 'my adapter', models: [] }) });
      await client.getAdapterModels('my adapter');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toContain('my%20adapter');
    });

    it('should throw on HTTP error', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404, text: () => Promise.resolve('Not found') });
      await expect(client.getAdapterModels('missing')).rejects.toThrow('Failed to get adapter models');
    });
  });

  describe('getAllModels', () => {
    it('should GET /admin/models', async () => {
      const mockResponse = {
        models: [
          { id: 'gpt-4o', adapter_name: 'openai' },
          { id: 'claude-sonnet-4-6', adapter_name: 'anthropic' }
        ]
      };
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(mockResponse) });

      const result = await client.getAllModels();

      expect(result.models).toHaveLength(2);
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/admin/models`);
    });

    it('should throw on HTTP error', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500, text: () => Promise.resolve('Error') });
      await expect(client.getAllModels()).rejects.toThrow('Failed to get all models');
    });
  });

  describe('getAdapterSkills', () => {
    it('should GET /admin/adapters/{adapter}/skills', async () => {
      const mockResponse = {
        adapter_name: 'hr',
        available_skills: ['summarize', 'translate', 'extract']
      };
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(mockResponse) });

      const result = await client.getAdapterSkills('hr');

      expect(result.adapter_name).toBe('hr');
      expect(result.available_skills).toContain('summarize');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/admin/adapters/hr/skills`);
    });

    it('should URL-encode the adapter name', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ adapter_name: 'my adapter', available_skills: [] }) });
      await client.getAdapterSkills('my adapter');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toContain('my%20adapter');
    });

    it('should throw on HTTP error', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404, text: () => Promise.resolve('Not found') });
      await expect(client.getAdapterSkills('missing')).rejects.toThrow('Failed to get adapter skills');
    });
  });

  describe('getAllSkills', () => {
    it('should GET /admin/skills', async () => {
      const mockResponse = {
        skills: [
          { name: 'summarize', description: 'Summarize text', adapter_name: 'hr', enabled: true },
          { name: 'translate', description: 'Translate content', adapter_name: 'hr', enabled: false }
        ]
      };
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(mockResponse) });

      const result = await client.getAllSkills();

      expect(result.skills).toHaveLength(2);
      expect(result.skills[0].name).toBe('summarize');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/admin/skills`);
    });

    it('should throw on HTTP error', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500, text: () => Promise.resolve('Error') });
      await expect(client.getAllSkills()).rejects.toThrow('Failed to get all skills');
    });
  });
});
