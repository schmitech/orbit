import { afterAll, afterEach, beforeAll } from 'vitest';
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';
import { configureApi } from '../api';

// Define the default test API URL
const TEST_API_URL = 'http://test-api-server.com';

// Configure the API with the test URL
configureApi(TEST_API_URL);

// Define mock handlers
const handlers = [
  http.post(`${TEST_API_URL}/v1/chat`, async ({ request }) => {
    // Add type annotation to fix linter error
    interface ChatRequest {
      messages: Array<{ role: string; content: string; }>;
      stream: boolean;
    }
    
    const { messages, stream } = await request.json() as ChatRequest;
    const message = messages[0]?.content || '';
    
    // Use message variable to avoid unused variable warning
    console.log(`Processing mock request with message: "${message}"`);
    
    if (!stream) {
      // Non-streaming response
      return HttpResponse.json({
        response: 'Hello! This is a test response. Response complete.'
      });
    }
    
    // Mock streaming response
    const encoder = new TextEncoder();
    const streamResponse = new ReadableStream({
      async start(controller) {
        // First chunk
        controller.enqueue(encoder.encode('data: ' + JSON.stringify({ 
          response: 'Hello! ', 
          done: false 
        }) + '\n\n'));
        
        // Wait a bit to simulate streaming
        await new Promise(resolve => setTimeout(resolve, 50));
        
        // Second chunk
        controller.enqueue(encoder.encode('data: ' + JSON.stringify({ 
          response: 'This is a test response. ', 
          done: false 
        }) + '\n\n'));
        
        // Wait a bit more
        await new Promise(resolve => setTimeout(resolve, 50));
        
        // Final chunk
        controller.enqueue(encoder.encode('data: ' + JSON.stringify({ 
          response: 'Response complete.',
          done: true 
        }) + '\n\n'));
        
        // End of stream
        controller.enqueue(encoder.encode('data: [DONE]\n\n'));
        
        controller.close();
      }
    });
    
    return new HttpResponse(streamResponse, {
      headers: {
        'Content-Type': 'text/event-stream'
      }
    });
  })
];

// Setup MSW server
const server = setupServer(...handlers);

// Start server before all tests
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));

// Reset handlers after each test
afterEach(() => server.resetHandlers());

// Close server after all tests
afterAll(() => server.close()); 