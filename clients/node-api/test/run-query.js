#!/usr/bin/env node

/**
 * This script runs a query against the chatbot API and displays the results.
 * Usage: DEBUG=1 npm run test-query "your query here" "http://your-api-url.com" ["your-api-key"] ["your-session-id"]
 */

import { configureApi, streamChat } from '../api.ts';
import readline from 'readline';

// Get the query, API URL, API key, and optional session ID from command line arguments
const args = process.argv.slice(2);
const debug = process.env.DEBUG === '1';
const query = args[0];
const apiUrl = args[1] || 'http://localhost:3000';
const apiKey = args[2];
const sessionId = args[3]; // Optional session ID

if (!query) {
  console.error('Error: No query provided');
  console.error('Usage: DEBUG=1 npm run test-query "your query here" "http://your-api-url.com" ["your-api-key"] ["your-session-id"]');
  process.exit(1);
}

console.log(`Using API URL: ${apiUrl}`);
if (apiKey) {
  console.log(`Using API Key: ${apiKey}`);
}
if (sessionId) {
  console.log(`Using Session ID: ${sessionId}`);
}
if (debug) {
  console.log('Debug mode: Enabled');
}
console.log(`\n🔍 Testing query: "${query}"\n`);

// Configure the API with the provided URL, API key, and optional session ID
configureApi(apiUrl, apiKey, sessionId);

async function runQuery() {
  try {
    let buffer = '';
    let hasReceivedData = false;
    process.stdout.write('🤖 Assistant: ');

    // Use streamChat with correct parameters (message, stream)
    for await (const response of streamChat(query, true)) {
      if (debug) {
        console.log('\n📦 Response payload:', JSON.stringify(response, null, 2));
      }
      
      if (response.text) {
        // Write the text directly
        process.stdout.write(response.text);
        buffer += response.text;
        hasReceivedData = true;
      }
      
      if (response.done) {
        // Add a newline at the end for clean output
        console.log('\n\n✅ Query test completed successfully');
        if (debug) {
          console.log(`📝 Total response length: ${buffer.length} characters`);
        }
        return; // Exit the function when done
      }
    }
    
    // If we exit the loop without getting a done signal, that's an error
    if (!hasReceivedData) {
      console.log('\n\n❌ No response received from server');
    } else {
      console.log('\n\n⚠️  Stream ended without done signal');
    }
    
  } catch (error) {
    console.error('\n❌ Error during test:', error);
    if (debug) {
      console.error('Error details:', JSON.stringify(error, null, 2));
    }
    process.exit(1);
  }
}

// Run the query
runQuery(); 