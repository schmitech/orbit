import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ApiClient } from '../api';
import { TEST_API_KEY, TEST_API_URL } from './config';

describe('Health and metrics endpoints', () => {
  let client: ApiClient;

  beforeEach(() => {
    vi.restoreAllMocks();
    client = new ApiClient({ apiUrl: TEST_API_URL, apiKey: TEST_API_KEY });
  });

  describe('getHealth', () => {
    it('should GET /health/', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ status: 'ok' }) });
      const result = await client.getHealth();
      expect(result.status).toBe('ok');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/health/`);
    });

    it('should throw on unhealthy response', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 503, text: () => Promise.resolve('Service unavailable') });
      await expect(client.getHealth()).rejects.toThrow('Failed to get health status');
    });
  });

  describe('getHealthAdapters', () => {
    it('should GET /health/adapters', async () => {
      const mockAdapters = { adapters: [{ name: 'hr', status: 'healthy' }] };
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(mockAdapters) });
      const result = await client.getHealthAdapters();
      expect(result.adapters).toHaveLength(1);
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/health/adapters`);
    });
  });

  describe('resetAdapterCircuit', () => {
    it('should POST to /health/adapters/{adapter}/reset', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ status: 'reset' }) });
      await client.resetAdapterCircuit('hr');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/health/adapters/hr/reset`);
      expect(opts.method).toBe('POST');
    });
  });

  describe('getReadiness', () => {
    it('should GET /health/ready', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ ready: true }) });
      const result = await client.getReadiness();
      expect(result.ready).toBe(true);
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/health/ready`);
    });
  });

  describe('getSystemStatus', () => {
    it('should GET /health/system', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ cpu: 0.1, memory: 512 }) });
      const result = await client.getSystemStatus();
      expect(result).toHaveProperty('cpu');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/health/system`);
    });
  });

  describe('getAdapterHistory', () => {
    it('should GET /health/adapters/{adapter}/history by default', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ history: [] }) });
      await client.getAdapterHistory('hr');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/health/adapters/hr/history`);
    });

    it('should GET /history/full when full=true', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ history: [] }) });
      await client.getAdapterHistory('hr', true);
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/health/adapters/hr/history/full`);
    });
  });

  describe('getThreadPoolStats', () => {
    it('should GET /health/thread-pools', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ pools: [] }) });
      await client.getThreadPoolStats();
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/health/thread-pools`);
    });
  });

  describe('getVoiceStatus', () => {
    it('should GET /voice/status', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ available: true }) });
      const result = await client.getVoiceStatus();
      expect(result.available).toBe(true);
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/voice/status`);
    });
  });

  describe('getMetricsJson', () => {
    it('should GET /metrics/json', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ requests_total: 42 }) });
      const result = await client.getMetricsJson();
      expect(result.requests_total).toBe(42);
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/metrics/json`);
    });
  });

  describe('getPrometheusMetrics', () => {
    it('should return text from /metrics', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        text: () => Promise.resolve('# HELP requests_total\nrequests_total 42\n')
      });
      const result = await client.getPrometheusMetrics();
      expect(result).toContain('requests_total');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/metrics`);
    });

    it('should throw on HTTP error', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 503, text: () => Promise.resolve('Unavailable') });
      await expect(client.getPrometheusMetrics()).rejects.toThrow('Failed to fetch Prometheus metrics');
    });
  });

  describe('getVoiceWebSocketUrl', () => {
    it('should convert http to ws', () => {
      // API key is appended as a query param when present on the client
      const url = client.getVoiceWebSocketUrl('hr');
      expect(url).toMatch(/^ws:\/\/localhost:3000\/ws\/voice\/hr/);
      expect(url).toContain(`api_key=${TEST_API_KEY}`);
    });

    it('should convert https to wss', () => {
      const tlsClient = new ApiClient({ apiUrl: 'https://api.example.com', apiKey: 'mykey' });
      const url = tlsClient.getVoiceWebSocketUrl('hr');
      expect(url).toMatch(/^wss:\/\/api\.example\.com\/ws\/voice\/hr/);
      expect(url).toContain('api_key=mykey');
    });

    it('should work without an API key', () => {
      const anonClient = new ApiClient({ apiUrl: 'http://localhost:3000' });
      const url = anonClient.getVoiceWebSocketUrl('hr');
      expect(url).toBe('ws://localhost:3000/ws/voice/hr');
    });

    it('should append query params when provided', () => {
      const url = client.getVoiceWebSocketUrl('hr', { sessionId: 's1', userId: 'u1' });
      expect(url).toContain('session_id=s1');
      expect(url).toContain('user_id=u1');
    });
  });

  describe('getMetricsWebSocketUrl', () => {
    it('should return ws URL for /ws/metrics', () => {
      const url = client.getMetricsWebSocketUrl();
      expect(url).toBe('ws://localhost:3000/ws/metrics');
    });
  });
});
