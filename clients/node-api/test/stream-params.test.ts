import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ApiClient } from '../api';
import { TEST_API_KEY, TEST_API_URL, TEST_SESSION_ID } from './config';

const makeStreamResponse = (chunks: object[]): Response => {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(chunk)}\n\n`));
      }
      controller.enqueue(encoder.encode('data: [DONE]\n\n'));
      controller.close();
    }
  });
  return {
    ok: true,
    headers: new Headers({ 'Content-Type': 'text/event-stream' }),
    body
  } as unknown as Response;
};

describe('streamChat — model, skill, and media response fields', () => {
  let client: ApiClient;

  beforeEach(() => {
    vi.restoreAllMocks();
    client = new ApiClient({ apiUrl: TEST_API_URL, apiKey: TEST_API_KEY, sessionId: TEST_SESSION_ID });
  });

  describe('request body', () => {
    it('should include model in request body when provided', async () => {
      global.fetch = vi.fn().mockResolvedValue(makeStreamResponse([{ response: 'Hi', done: true }]));

      for await (const _ of client.streamChat('hello', true, undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined, 'gpt-4o')) {
        // consume
      }

      const [, opts] = (global.fetch as any).mock.calls[0];
      const body = JSON.parse(opts.body);
      expect(body.model).toBe('gpt-4o');
    });

    it('should include skill in request body when provided', async () => {
      global.fetch = vi.fn().mockResolvedValue(makeStreamResponse([{ response: 'Hi', done: true }]));

      for await (const _ of client.streamChat('hello', true, undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined, 'summarize')) {
        // consume
      }

      const [, opts] = (global.fetch as any).mock.calls[0];
      const body = JSON.parse(opts.body);
      expect(body.skill).toBe('summarize');
    });

    it('should omit model and skill when not provided', async () => {
      global.fetch = vi.fn().mockResolvedValue(makeStreamResponse([{ response: 'Hi', done: true }]));

      for await (const _ of client.streamChat('hello')) {
        // consume
      }

      const [, opts] = (global.fetch as any).mock.calls[0];
      const body = JSON.parse(opts.body);
      expect(body.model).toBeUndefined();
      expect(body.skill).toBeUndefined();
    });
  });

  describe('image response fields', () => {
    it('should forward image fields from done chunk', async () => {
      const doneChunk = {
        done: true,
        image: 'base64imagecontent',
        image_format: 'png',
        image_revised_prompt: 'A cat on a mat',
        image_url: 'https://storage.example.com/img.png'
      };
      global.fetch = vi.fn().mockResolvedValue(makeStreamResponse([doneChunk]));

      const results = [];
      for await (const chunk of client.streamChat('draw a cat')) {
        results.push(chunk);
      }

      const done = results.find(r => r.done);
      expect(done?.image).toBe('base64imagecontent');
      expect(done?.image_format).toBe('png');
      expect(done?.image_revised_prompt).toBe('A cat on a mat');
      expect(done?.image_url).toBe('https://storage.example.com/img.png');
    });
  });

  describe('video response fields', () => {
    it('should forward video fields from done chunk', async () => {
      const doneChunk = {
        done: true,
        video: 'base64videocontent',
        video_format: 'mp4',
        video_revised_prompt: 'A flying bird',
        video_url: 'https://storage.example.com/vid.mp4'
      };
      global.fetch = vi.fn().mockResolvedValue(makeStreamResponse([doneChunk]));

      const results = [];
      for await (const chunk of client.streamChat('make a video')) {
        results.push(chunk);
      }

      const done = results.find(r => r.done);
      expect(done?.video).toBe('base64videocontent');
      expect(done?.video_format).toBe('mp4');
      expect(done?.video_url).toBe('https://storage.example.com/vid.mp4');
    });
  });

  describe('document response fields', () => {
    it('should forward document fields from done chunk', async () => {
      const doneChunk = {
        done: true,
        document: 'base64docontent',
        document_format: 'pdf',
        document_revised_prompt: 'Q3 report',
        document_url: 'https://storage.example.com/report.pdf'
      };
      global.fetch = vi.fn().mockResolvedValue(makeStreamResponse([doneChunk]));

      const results = [];
      for await (const chunk of client.streamChat('generate report')) {
        results.push(chunk);
      }

      const done = results.find(r => r.done);
      expect(done?.document).toBe('base64docontent');
      expect(done?.document_format).toBe('pdf');
      expect(done?.document_url).toBe('https://storage.example.com/report.pdf');
    });
  });

  describe('assistant_message_id field', () => {
    it('should forward assistant_message_id from done chunk', async () => {
      const doneChunk = { done: true, assistant_message_id: 'msg-db-id-123' };
      global.fetch = vi.fn().mockResolvedValue(makeStreamResponse([doneChunk]));

      const results = [];
      for await (const chunk of client.streamChat('hello')) {
        results.push(chunk);
      }

      const done = results.find(r => r.done);
      expect(done?.assistant_message_id).toBe('msg-db-id-123');
    });
  });
});
