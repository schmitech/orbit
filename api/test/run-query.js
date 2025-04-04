#!/usr/bin/env node

/**
 * This script runs a query against the chatbot API and displays the results.
 * Usage: npm run test-query "your query here" "http://your-api-url.com"
 */

import { configureApi, streamChat } from '../api.ts';
import readline from 'readline';

// Get the query and API URL from command line arguments
const query = process.argv[2];
const apiUrl = process.argv[3] || 'http://localhost:3000';

if (!query) {
  console.error('Error: No query provided');
  console.error('Usage: npm run test-query "your query here" "http://your-api-url.com"');
  process.exit(1);
}

console.log(`Using API URL: ${apiUrl}`);
console.log(`\n🔍 Testing query: "${query}"\n`);

// Configure the API with the provided URL
configureApi(apiUrl);

async function runQuery() {
  try {
    let buffer = '';
    process.stdout.write('🤖 Assistant: ');

    // Use our SDK's streamChat function instead of raw fetch
    for await (const response of streamChat(query, false)) {
      if (response.text) {
        // Append new text to the buffer
        buffer += response.text;

        // Write the buffer from the last known position
        process.stdout.write(response.text);
      } else if (response.content) {
        console.log('\n' + response.content);
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