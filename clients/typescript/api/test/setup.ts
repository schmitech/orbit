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
  http.post(`${TEST_API_URL}/chat`, async ({ request }) => {
    // Add type annotation to fix linter error
    interface ChatRequest {
      message: string;
      voiceEnabled: boolean;
    }
    
    const { message, voiceEnabled } = await request.json() as ChatRequest;
    
    // Use message variable to avoid unused variable warning
    console.log(`Processing mock request with message: "${message}"`);
    
    // Mock streaming response
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      async start(controller) {
        // First chunk
        controller.enqueue(encoder.encode(JSON.stringify({ 
          text: 'Hello! ', 
          done: false 
        }) + '\n'));
        
        // Wait a bit to simulate streaming
        await new Promise(resolve => setTimeout(resolve, 50));
        
        // Second chunk
        controller.enqueue(encoder.encode(JSON.stringify({ 
          text: 'This is a test response. ', 
          done: false 
        }) + '\n'));
        
        // Wait a bit more
        await new Promise(resolve => setTimeout(resolve, 50));
        
        // Final chunk with voice data if requested
        if (voiceEnabled) {
          controller.enqueue(encoder.encode(JSON.stringify({ 
            text: 'Voice enabled response.',
            type: 'audio',
            content: 'mock-base64-audio-data',
            done: true 
          }) + '\n'));
        } else {
          controller.enqueue(encoder.encode(JSON.stringify({ 
            text: 'Response complete.',
            done: true 
          }) + '\n'));
        }
        
        controller.close();
      }
    });
    
    return new HttpResponse(stream, {
      headers: {
        'Content-Type': 'application/json'
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