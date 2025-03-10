import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { streamChat, StreamResponse } from '../api';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';

// Import the server from setup.ts (it's automatically imported by Vitest)
// We'll just add handlers to the existing server instead of creating a new one

describe('Query Testing', () => {
  // Add query-specific handlers before each test
  beforeEach(() => {
    // Reset the server handlers and add our custom handler
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url, options) => {
      if (url.toString().includes('/chat')) {
        const body = JSON.parse(options.body);
        const { message } = body;
        
        // Mock streaming response based on the query
        const encoder = new TextEncoder();
        const stream = new ReadableStream({
          async start(controller) {
            // First chunk - acknowledgment
            controller.enqueue(encoder.encode(JSON.stringify({ 
              text: 'Processing your query: "' + message + '". ', 
              done: false 
            }) + '\n'));
            
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
            
            controller.enqueue(encoder.encode(JSON.stringify({ 
              text: responseText, 
              done: false 
            }) + '\n'));
            
            // Wait a bit more
            await new Promise(resolve => setTimeout(resolve, 50));
            
            // Final chunk
            controller.enqueue(encoder.encode(JSON.stringify({ 
              text: 'Is there anything else you would like to know?',
              done: true 
            }) + '\n'));
            
            controller.close();
          }
        });
        
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'Content-Type': 'application/json' }),
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
    
    for await (const response of streamChat(query, false)) {
      responses.push(response);
    }
    
    // Check that we got the expected number of responses
    expect(responses.length).toBeGreaterThanOrEqual(3);
    
    // Check the first response acknowledges the query
    expect(responses[0].text).toContain('Processing your query');
    expect(responses[0].text).toContain(query);
    expect(responses[0].done).toBe(false);
    
    // Check the second response contains fee information
    expect(responses[1].text).toContain('$10 per transaction');
    expect(responses[1].text).toContain('$5 per transaction');
    expect(responses[1].done).toBe(false);
    
    // Check the final response
    const lastResponse = responses[responses.length - 1];
    expect(lastResponse.text).toContain('anything else');
    expect(lastResponse.done).toBe(true);
  });

  it('should correctly respond to price-related queries', async () => {
    const query = 'what is the price?';
    const responses: StreamResponse[] = [];
    
    for await (const response of streamChat(query, false)) {
      responses.push(response);
    }
    
    // Check the second response contains price information
    expect(responses[1].text).toContain('$29.99');
    expect(responses[1].text).toContain('$49.99');
  });

  it('should handle unknown queries gracefully', async () => {
    const query = 'something completely unrelated';
    const responses: StreamResponse[] = [];
    
    for await (const response of streamChat(query, false)) {
      responses.push(response);
    }
    
    // Check the second response indicates lack of information
    expect(responses[1].text).toContain('don\'t have specific information');
  });
}); 