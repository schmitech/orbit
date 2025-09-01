#!/usr/bin/env node

/**
 * Simple test script for the ORBIT chatbot API
 * 
 * This script demonstrates basic usage of the @schmitech/chatbot-api package
 * by sending a message to the ORBIT server and streaming the response.
 * 
 * Usage:
 *   node test-npm-package.js [--local|--npm] "your message" [api-url] [session-id] [api-key]
 * 
 * Parameters:
 *   --local    - Test the local dist build (default)
 *   --npm      - Test the published npm package
 *   message    - The message to send to the chatbot (required)
 *   api-url    - The URL of the ORBIT server (default: http://localhost:3000)
 *   session-id - Optional session ID for conversation history
 *   api-key    - Optional API key for authentication
 * 
 * Examples:
 *   # Test local dist build (default)
 *   node test-npm-package.js "Hello, how can you help me?"
 *   node test-npm-package.js --local "Hello, how can you help me?"
 * 
 *   # Test published npm package
 *   node test-npm-package.js --npm "Hello, how can you help me?"
 * 
 *   # Custom server URL with local build
 *   node test-npm-package.js --local "Hello" "http://my-server:3000"
 * 
 *   # With session ID for conversation history
 *   node test-npm-package.js --local "Hello" "http://localhost:3000" "my-session-123"
 * 
 *   # Full configuration with npm package
 *   node test-npm-package.js --npm "Hello" "http://localhost:3000" "my-session-123" "my-api-key"
 * 
 *   # Test with API key (when auth is enabled)
 *   node test-npm-package.js --local "Hello" "http://localhost:3000" "session-123" "your-api-key"
 * 
 * Requirements:
 *   - ORBIT server running
 *   - Node.js 16+ with ES modules support
 *   - For --local: Run 'npm run build' first to generate dist files
 *   - For --npm: Install the package with 'npm install @schmitech/chatbot-api'
 */

// Get command line arguments
const args = process.argv.slice(2);

// Check for --local or --npm flag
let useLocal = true; // default to local
let argIndex = 0;

if (args[0] === '--local') {
  useLocal = true;
  argIndex = 1;
} else if (args[0] === '--npm') {
  useLocal = false;
  argIndex = 1;
}

const message = args[argIndex];
const apiUrl = args[argIndex + 1] || 'http://localhost:3000';
const sessionId = args[argIndex + 2]; // Optional session ID
const apiKey = args[argIndex + 3]; // Optional API key

if (!message || message === '--help' || message === '-h') {
  console.log('🚀 ORBIT API Test Script\n');
  console.log('Usage: node test-npm-package.js [--local|--npm] "your message" [api-url] [session-id] [api-key]\n');
  console.log('Options:');
  console.log('  --local    Test the local dist build (default)');
  console.log('  --npm      Test the published npm package');
  console.log('  --help     Show this help message\n');
  console.log('Parameters:');
  console.log('  message    The message to send to the chatbot (required)');
  console.log('  api-url    Server URL (default: http://localhost:3000)');
  console.log('  session-id Optional session ID for conversation history');
  console.log('  api-key    Optional API key for authentication\n');
  console.log('Examples:');
  console.log('  node test-npm-package.js "Hello, how can you help me?"');
  console.log('  node test-npm-package.js --local "Hello" "http://localhost:3000" "session-123" "your-api-key"');
  console.log('  node test-npm-package.js --npm "Hello" "http://localhost:3000"');
  process.exit(message ? 0 : 1);
}

console.log(`📦 Testing: ${useLocal ? 'Local dist build' : 'Published npm package'}`);
console.log(`🌐 Using API URL: ${apiUrl}`);
if (sessionId) {
  console.log(`🔗 Using Session ID: ${sessionId}`);
}
if (apiKey) {
  console.log(`🔑 Using API Key: ${apiKey}`);
}
console.log(`\n🔍 Testing message: "${message}"\n`);

// Run the test
async function runTest() {
  try {
    // Dynamic import based on whether we're testing local or npm package
    let configureApi, streamChat;
    
    if (useLocal) {
      console.log('📁 Loading local dist build...');
      try {
        const localApi = await import('../dist/api.mjs');
        configureApi = localApi.configureApi;
        streamChat = localApi.streamChat;
      } catch (importError) {
        if (importError.code === 'ERR_MODULE_NOT_FOUND') {
          console.error('❌ Local dist build not found!');
          console.error('💡 Run "npm run build" first to generate the dist files');
        }
        throw importError;
      }
    } else {
      console.log('📦 Loading npm package...');
      try {
        const npmApi = await import('@schmitech/chatbot-api');
        configureApi = npmApi.configureApi;
        streamChat = npmApi.streamChat;
      } catch (importError) {
        if (importError.code === 'ERR_MODULE_NOT_FOUND') {
          console.error('❌ npm package not found!');
          console.error('💡 Install the package with "npm install @schmitech/chatbot-api"');
        }
        throw importError;
      }
    }
    
    // Configure the API - pass undefined instead of null for optional parameters
    configureApi(apiUrl, apiKey || undefined, sessionId || undefined);
    
    console.log('🚀 Starting chat stream...\n');
    process.stdout.write('🤖 Assistant: ');
    
    let hasReceivedData = false;
    
    for await (const response of streamChat(message, true)) {
      if (response.text) {
        // Write the text directly only if it exists
        process.stdout.write(response.text);
        hasReceivedData = true;
      }
      
      if (response.done) {
        console.log('\n\n✅ Test completed successfully');
        return;
      }
    }
    
    // If we exit the loop without getting a done signal, that's an error
    if (!hasReceivedData) {
      console.log('\n\n❌ No response received from server');
    } else {
      console.log('\n\n⚠️  Stream ended without done signal');
    }
  } catch (error) {
    console.error('\n❌ Error:', error.message);
    
    // Provide helpful hints for common issues
    if (error.message.includes('401')) {
      console.error('\n💡 Authentication required:');
      console.error('   - Server has authentication enabled');
      console.error('   - Provide an API key as the 4th parameter');
      console.error('   - Example: node test-npm-package.js --local "Hello" "http://localhost:3000" "session-123" "your-api-key"');
    } else if (error.message.includes('Session ID is required')) {
      console.error('\n💡 Session ID required:');
      console.error('   - Server requires a session ID');
      console.error('   - Provide a session ID as the 3rd parameter');
      console.error('   - Example: node test-npm-package.js --local "Hello" "http://localhost:3000" "session-123"');
    } else if (error.message.includes('Could not connect')) {
      console.error('\n💡 Connection issues:');
      console.error('   - Make sure the ORBIT server is running');
      console.error('   - Check the server URL (default: http://localhost:3000)');
    } else if (error.message.includes('timeout')) {
      console.error('\n💡 Timeout issues:');
      console.error('   - Server might be slow to respond');
      console.error('   - Check server logs for issues');
    }
    
    process.exit(1);
  }
}

runTest();