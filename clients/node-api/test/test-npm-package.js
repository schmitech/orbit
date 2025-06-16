#!/usr/bin/env node

/**
 * Simple test script for the ORBIT chatbot API
 * 
 * This script demonstrates basic usage of the @schmitech/chatbot-api package
 * by sending a message to the ORBIT server and streaming the response.
 * 
 * Usage:
 *   node test-npm-package.js "your message" [api-url] [session-id] [api-key]
 * 
 * Parameters:
 *   message    - The message to send to the chatbot (required)
 *   api-url    - The URL of the ORBIT server (default: http://localhost:3000)
 *   session-id - Optional session ID for conversation history
 *   api-key    - Optional API key for authentication
 * 
 * Examples:
 *   # Basic usage with default settings
 *   node test-npm-package.js "Hello, how can you help me?"
 * 
 *   # Custom server URL
 *   node test-npm-package.js "Hello" "http://my-server:3000"
 * 
 *   # With session ID for conversation history
 *   node test-npm-package.js "Hello" "http://localhost:3000" "my-session-123"
 * 
 *   # Full configuration
 *   node test-npm-package.js "Hello" "http://localhost:3000" "my-session-123" "my-api-key"
 * 
 * Requirements:
 *   - ORBIT server running
 *   - Node.js 16+ with ES modules support
 */

import { configureApi, streamChat } from '@schmitech/chatbot-api';

// Get command line arguments
const args = process.argv.slice(2);
const message = args[0];
const apiUrl = args[1] || 'http://localhost:3000';
const sessionId = args[2]; // Optional session ID
const apiKey = args[3]; // Optional API key

if (!message) {
  console.error('Error: No message provided');
  console.error('Usage: node test-npm-package.js "your message" [api-url] [session-id] [api-key]');
  process.exit(1);
}

console.log(`Using API URL: ${apiUrl}`);
if (sessionId) {
  console.log(`Using Session ID: ${sessionId}`);
}
if (apiKey) {
  console.log(`Using API Key: ${apiKey}`);
}
console.log(`\n🔍 Testing message: "${message}"\n`);

// Configure the API
configureApi(apiUrl, apiKey, sessionId);

// Run the test
async function runTest() {
  try {
    process.stdout.write('🤖 Assistant: ');
    
    for await (const response of streamChat(message, true)) {
      process.stdout.write(response.text);
      
      if (response.done) {
        console.log('\n\n✅ Test completed successfully');
        return;
      }
    }
  } catch (error) {
    console.error('\n❌ Error:', error.message);
    process.exit(1);
  }
}

runTest();