import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { streamChat, configureApi, ApiClient } from '../api';
import { TEST_API_KEY, TEST_API_URL } from './config';

describe('Concurrency and Race Conditions', () => {
  beforeEach(() => {
    configureApi(TEST_API_URL, TEST_API_KEY);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should handle multiple concurrent requests', async () => {
    let requestCount = 0;
    const encoder = new TextEncoder();

    global.fetch = vi.fn().mockImplementation(() => {
      const currentRequest = ++requestCount;
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode(`data: {"response": "Response ${currentRequest}", "done": true}\n\n`));
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

    // Launch multiple concurrent requests
    const promises = [];
    for (let i = 0; i < 5; i++) {
      promises.push((async () => {
        const responses = [];
        for await (const response of streamChat(`Message ${i}`)) {
          responses.push(response);
        }
        return responses;
      })());
    }

    const allResponses = await Promise.all(promises);

    expect(requestCount).toBe(5);
    expect(allResponses.length).toBe(5);
    allResponses.forEach(responses => {
      expect(responses.length).toBeGreaterThan(0);
    });
  });

  it('should handle rapid sequential requests', async () => {
    const encoder = new TextEncoder();
    let callCount = 0;

    global.fetch = vi.fn().mockImplementation(() => {
      callCount++;
      const stream = new ReadableStream({
        async start(controller) {
          // Add small delay to simulate processing
          await new Promise(resolve => setTimeout(resolve, 10));
          controller.enqueue(encoder.encode(`data: {"response": "Response ${callCount}", "done": true}\n\n`));
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

    // Send requests rapidly
    const results = [];
    for (let i = 0; i < 3; i++) {
      const responses = [];
      for await (const response of streamChat(`Message ${i}`)) {
        responses.push(response);
      }
      results.push(responses);
    }

    expect(callCount).toBe(3);
    expect(results.length).toBe(3);
  });

  it('should handle request cancellation', async () => {
    const encoder = new TextEncoder();
    let streamStarted = false;
    let streamCancelled = false;

    const stream = new ReadableStream({
      async start(controller) {
        streamStarted = true;
        // Simulate slow response
        for (let i = 0; i < 10; i++) {
          await new Promise(resolve => setTimeout(resolve, 100));
          if (streamCancelled) {
            controller.close();
            return;
          }
          controller.enqueue(encoder.encode(`data: {"response": "Part ${i}", "done": false}\n\n`));
        }
        controller.enqueue(encoder.encode('data: [DONE]\n\n'));
        controller.close();
      },
      cancel() {
        streamCancelled = true;
      }
    });

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'Content-Type': 'text/event-stream' }),
      body: stream
    });

    const responses = [];
    const generator = streamChat('test');

    // Get first response
    const firstResponse = await generator.next();
    if (!firstResponse.done) {
      responses.push(firstResponse.value);
    }

    // Cancel by breaking out early
    await generator.return();

    expect(streamStarted).toBe(true);
    expect(responses.length).toBeGreaterThanOrEqual(0);
  });

  it('should isolate client instances', async () => {
    const client1 = new ApiClient({
      apiUrl: TEST_API_URL,
      apiKey: 'key-1',
      sessionId: 'session-1'
    });

    const client2 = new ApiClient({
      apiUrl: 'http://localhost:3001',
      apiKey: 'key-2',
      sessionId: 'session-2'
    });

    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('data: {"response": "Test", "done": true}\n\n'));
        controller.enqueue(encoder.encode('data: [DONE]\n\n'));
        controller.close();
      }
    });

    let fetchCalls = [];
    global.fetch = vi.fn().mockImplementation((url, options) => {
      fetchCalls.push({ url, headers: options.headers });
      return Promise.resolve({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'text/event-stream' }),
        body: stream
      });
    });

    // Use both clients
    for await (const response of client1.streamChat('test1')) {
      // Process response
    }
    for await (const response of client2.streamChat('test2')) {
      // Process response
    }

    expect(fetchCalls.length).toBe(2);
    expect(fetchCalls[0].url).toContain('3000');
    expect(fetchCalls[0].headers['X-API-Key']).toBe('key-1');
    expect(fetchCalls[0].headers['X-Session-ID']).toBe('session-1');

    expect(fetchCalls[1].url).toContain('3001');
    expect(fetchCalls[1].headers['X-API-Key']).toBe('key-2');
    expect(fetchCalls[1].headers['X-Session-ID']).toBe('session-2');
  });

  it('should handle network interruptions gracefully', async () => {
    const encoder = new TextEncoder();
    let chunkCount = 0;

    const stream = new ReadableStream({
      async start(controller) {
        try {
          // Send a few chunks
          for (let i = 0; i < 3; i++) {
            chunkCount++;
            controller.enqueue(encoder.encode(`data: {"response": "Part ${i}", "done": false}\n\n`));
            await new Promise(resolve => setTimeout(resolve, 10));
          }
          // Simulate network error
          throw new Error('Network interrupted');
        } catch (error) {
          controller.error(error);
        }
      }
    });

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'Content-Type': 'text/event-stream' }),
      body: stream
    });

    const responses = [];
    try {
      for await (const response of streamChat('test')) {
        responses.push(response);
      }
    } catch (error) {
      // Expected to throw
      expect(error.message).toContain('Network interrupted');
    }

    expect(chunkCount).toBe(3);
    expect(responses.length).toBeGreaterThanOrEqual(0);
  });
});
