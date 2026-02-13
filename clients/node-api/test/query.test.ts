import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { streamChat, StreamResponse, configureApi } from '../api';
import { TEST_API_KEY, TEST_API_URL } from './config';

// Import the server from setup.ts (it's automatically imported by Vitest)
// We'll just add handlers to the existing server instead of creating a new one

describe('Query Testing', () => {
  // Add query-specific handlers before each test
  beforeEach(() => {
    // Configure API with test URL and API key
    configureApi(TEST_API_URL, TEST_API_KEY);
    
    // Reset the server handlers and add our custom handler
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url, options) => {
      if (url.toString().includes('/chat')) {
        const body = JSON.parse(options.body);
        const messages = body.messages || [];
        const message = messages[0]?.content || '';

        // Mock streaming response based on the query
        const encoder = new TextEncoder();
        const stream = new ReadableStream({
          async start(controller) {
            // SSE format requires "data: " prefix
            // First chunk - acknowledgment
            controller.enqueue(encoder.encode('data: ' + JSON.stringify({
              response: 'Processing your query: "' + message + '". ',
              done: false
            }) + '\n\n'));

            // Wait a bit to simulate processing
            await new Promise(resolve => setTimeout(resolve, 50));

            // Second chunk - response based on the query
            let responseText = '';

            if (message.toLowerCase().includes('fee')) {
              responseText = 'The standard fee is $10 per transaction. For premium users, the fee is reduced to $5 per transaction. ';
            } else if (message.toLowerCase().includes('price')) {
              responseText = 'Our basic plan starts at $29.99 per month. The premium plan is $49.99 per month. ';
            } else {
              responseText = 'I don\'t have specific information about that query. Please ask something else. ';
            }

            controller.enqueue(encoder.encode('data: ' + JSON.stringify({
              response: responseText,
              done: false
            }) + '\n\n'));

            // Wait a bit more
            await new Promise(resolve => setTimeout(resolve, 50));

            // Final chunk
            controller.enqueue(encoder.encode('data: ' + JSON.stringify({
              response: 'Is there anything else you would like to know?',
              done: false
            }) + '\n\n'));

            // Terminal done chunk
            controller.enqueue(encoder.encode('data: ' + JSON.stringify({
              done: true
            }) + '\n\n'));

            // Send done signal
            controller.enqueue(encoder.encode('data: [DONE]\n\n'));

            controller.close();
          }
        });
        
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'Content-Type': 'text/event-stream' }),
          body: stream,
          json: () => Promise.resolve({}),
          text: () => Promise.resolve(''),
        };
      }
      
      // For other URLs, use a simple mock response
      return Promise.resolve({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: () => Promise.resolve({}),
        text: () => Promise.resolve(''),
      });
    }));
  });

  // Clean up after each test
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should correctly respond to fee-related queries', async () => {
    const query = 'how much is the fee?';
    const responses: StreamResponse[] = [];
    
    for await (const response of streamChat(query)) {
      responses.push(response);
    }
    
    // Check that we got the expected number of responses (3 content + 1 done signal)
    expect(responses.length).toBe(4);

    // Check the first response acknowledges the query
    expect(responses[0].text).toContain('Processing your query');
    expect(responses[0].text).toContain(query);
    expect(responses[0].done).toBe(false);

    // Check the second response contains fee information
    expect(responses[1].text).toContain('$10 per transaction');
    expect(responses[1].text).toContain('$5 per transaction');
    expect(responses[1].done).toBe(false);

    // Check the third response
    expect(responses[2].text).toContain('anything else');
    expect(responses[2].done).toBe(false);

    // Check the final done signal
    expect(responses[3].text).toBe('');
    expect(responses[3].done).toBe(true);
  });

  it('should correctly respond to price-related queries', async () => {
    const query = 'what is the price?';
    const responses: StreamResponse[] = [];
    
    for await (const response of streamChat(query)) {
      responses.push(response);
    }
    
    // Check that we got the expected number of responses
    expect(responses.length).toBe(4);

    // Check the second response contains price information
    expect(responses[1].text).toContain('$29.99');
    expect(responses[1].text).toContain('$49.99');
  });

  it('should handle unknown queries gracefully', async () => {
    const query = 'something completely unrelated';
    const responses: StreamResponse[] = [];
    
    for await (const response of streamChat(query)) {
      responses.push(response);
    }
    
    // Check that we got the expected number of responses
    expect(responses.length).toBe(4);

    // Check the second response indicates lack of information
    expect(responses[1].text).toContain('don\'t have specific information');
  });
}); 
