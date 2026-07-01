import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ApiClient } from '../api';
import { TEST_API_KEY, TEST_API_URL, TEST_SESSION_ID } from './config';

describe('File endpoints', () => {
  let client: ApiClient;

  beforeEach(() => {
    vi.restoreAllMocks();
    client = new ApiClient({ apiUrl: TEST_API_URL, apiKey: TEST_API_KEY, sessionId: TEST_SESSION_ID });
  });

  describe('uploadFile', () => {
    it('should POST to /api/files/upload with FormData', async () => {
      const mockResponse = {
        file_id: 'f1',
        filename: 'test.pdf',
        mime_type: 'application/pdf',
        file_size: 1024,
        status: 'processed',
        chunk_count: 3,
        message: 'File uploaded successfully'
      };
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(mockResponse) });

      const file = new File(['content'], 'test.pdf', { type: 'application/pdf' });
      const result = await client.uploadFile(file);

      expect(result.file_id).toBe('f1');
      expect(result.filename).toBe('test.pdf');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/api/files/upload`);
      expect(opts.method).toBe('POST');
      expect(opts.body).toBeInstanceOf(FormData);
    });

    it('should require an API key', async () => {
      const clientNoKey = new ApiClient({ apiUrl: TEST_API_URL });
      const file = new File([''], 'test.txt');
      await expect(clientNoKey.uploadFile(file)).rejects.toThrow('API key is required');
    });
  });

  describe('listFiles', () => {
    it('should GET /api/files', async () => {
      const mockFiles = [
        { file_id: 'f1', filename: 'doc.pdf', mime_type: 'application/pdf', file_size: 100, upload_timestamp: '2024-01-01', processing_status: 'done', chunk_count: 2, storage_type: 'local' }
      ];
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(mockFiles) });

      const result = await client.listFiles();

      expect(result).toHaveLength(1);
      expect(result[0].file_id).toBe('f1');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/api/files`);
    });

    it('should require an API key', async () => {
      const clientNoKey = new ApiClient({ apiUrl: TEST_API_URL });
      await expect(clientNoKey.listFiles()).rejects.toThrow('API key is required');
    });
  });

  describe('getFileInfo', () => {
    it('should GET /api/files/{file_id}', async () => {
      const mockFile = { file_id: 'f1', filename: 'doc.pdf', mime_type: 'application/pdf', file_size: 100, upload_timestamp: '2024-01-01', processing_status: 'done', chunk_count: 2, storage_type: 'local' };
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(mockFile) });

      const result = await client.getFileInfo('f1');

      expect(result.file_id).toBe('f1');
      const [url] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/api/files/f1`);
    });
  });

  describe('queryFile', () => {
    it('should POST to /api/files/{file_id}/query', async () => {
      const mockResult = {
        file_id: 'f1',
        filename: 'doc.pdf',
        results: [{ content: 'relevant text', metadata: { chunk_id: 'c1', file_id: 'f1', chunk_index: 0, confidence: 0.9 } }]
      };
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(mockResult) });

      const result = await client.queryFile('f1', 'what is the summary?', 5);

      expect(result.results).toHaveLength(1);
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/api/files/f1/query`);
      expect(opts.method).toBe('POST');
      expect(JSON.parse(opts.body)).toEqual({ query: 'what is the summary?', max_results: 5 });
    });

    it('should use default max_results of 10', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ file_id: 'f1', filename: 'doc.pdf', results: [] }) });
      await client.queryFile('f1', 'query');
      const [, opts] = (global.fetch as any).mock.calls[0];
      expect(JSON.parse(opts.body).max_results).toBe(10);
    });
  });

  describe('deleteFile', () => {
    it('should DELETE /api/files/{file_id}', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ message: 'Deleted', file_id: 'f1' }) });

      const result = await client.deleteFile('f1');

      expect(result.file_id).toBe('f1');
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/api/files/f1`);
      expect(opts.method).toBe('DELETE');
    });

    it('should throw a friendly error on 404', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        text: () => Promise.resolve(JSON.stringify({ detail: 'File not found' }))
      });
      await expect(client.deleteFile('missing')).rejects.toThrow('File not found');
    });
  });

  describe('deleteAllFiles', () => {
    it('should DELETE /api/files', async () => {
      global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ message: 'All deleted', deleted_count: 3 }) });
      const result = await client.deleteAllFiles();
      expect(result.deleted_count).toBe(3);
      const [url, opts] = (global.fetch as any).mock.calls[0];
      expect(url).toBe(`${TEST_API_URL}/api/files`);
      expect(opts.method).toBe('DELETE');
    });
  });
});
