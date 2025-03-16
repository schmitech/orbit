#!/usr/bin/env node

/**
 * This script runs a query against the chatbot API and displays the results.
 * Usage: npm run test-query "your query here"
 */

import fetch from 'node-fetch';

// Get the query from command line arguments
const query = process.argv[2];

if (!query) {
  console.error('Error: No query provided');
  console.error('Usage: npm run test-query "your query here"');
  process.exit(1);
}

console.log(`\n🔍 Testing query: "${query}"\n`);

async function runQuery() {
  try {
    const response = await fetch('http://localhost:3000/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message: query,
        voiceEnabled: false
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    // Handle streaming response
    const reader = response.body;
    for await (const chunk of reader) {
      const lines = chunk.toString().split('\n').filter(line => line.trim());
      for (const line of lines) {
        try {
          const data = JSON.parse(line);
          if (data.type === 'text') {
            console.log(data.content);
          }
        } catch (e) {
          console.error('Error parsing chunk:', e);
        }
      }
    }

    console.log('\n✅ Query test completed successfully');
  } catch (error) {
    console.error('\n❌ Error during test:', error);
    process.exit(1);
  }
}

// Run the query
runQuery(); 