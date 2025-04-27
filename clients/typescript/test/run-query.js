#!/usr/bin/env node

/**
 * This script runs a query against the chatbot API and displays the results.
 * Usage: npm run test-query "your query here" "http://your-api-url.com" "your-api-key"
 */

import { configureApi, streamChat } from '../api.ts';
import readline from 'readline';

// Get the query, API URL, and API key from command line arguments
const query = process.argv[2];
const apiUrl = process.argv[3] || 'http://localhost:3000';
const apiKey = process.argv[4];

if (!query) {
  console.error('Error: No query provided');
  console.error('Usage: npm run test-query "your query here" "http://your-api-url.com" "your-api-key"');
  process.exit(1);
}

if (!apiKey) {
  console.error('Error: No API key provided');
  console.error('Usage: npm run test-query "your query here" "http://your-api-url.com" "your-api-key"');
  process.exit(1);
}

console.log(`Using API URL: ${apiUrl}`);
console.log(`\n🔍 Testing query: "${query}"\n`);

// Configure the API with the provided URL and API key
configureApi(apiUrl, apiKey);

async function runQuery() {
  try {
    let buffer = '';
    process.stdout.write('🤖 Assistant: ');

    // Use streamChat with streaming enabled
    for await (const response of streamChat(query, false, true)) {
      if (response.text) {
        // Write the text directly
        process.stdout.write(response.text);
        buffer += response.text;
      }
      
      if (response.done) {
        // Add a newline at the end for clean output
        console.log('\n\n✅ Query test completed successfully');
        buffer = ''; // Clear the buffer after the query is complete
      }
    }

    // Create readline interface
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout
    });

    // Wait for user to press Enter before exiting
    await new Promise(resolve => {
      rl.question('\nPress Enter to exit...', () => {
        rl.close();
        resolve();
      });
    });
  } catch (error) {
    console.error('\n❌ Error during test:', error);
    process.exit(1);
  }
}

// Run the query
runQuery(); 