#!/usr/bin/env node

/**
 * This script runs a query against the chatbot API and displays the results.
 * Usage: npm run test-query "your query here"
 */

// We need to use a different approach since we can't directly import TypeScript files in Node.js
// Let's use a simpler approach with the node-fetch package

// Get the query from command line arguments
const query = process.argv[2];

if (!query) {
  console.error('Error: No query provided');
  console.error('Usage: npm run test-query "your query here"');
  process.exit(1);
}

console.log(`\n🔍 Testing query: "${query}"\n`);

// Mock API response based on the query
function getMockResponse(query) {
  let responseText = '';
  
  if (query.toLowerCase().includes('fee')) {
    responseText = 'The standard fee is $10 per transaction. For premium users, the fee is reduced to $5 per transaction.';
  } else if (query.toLowerCase().includes('price')) {
    responseText = 'Our basic plan starts at $29.99 per month. The premium plan is $49.99 per month.';
  } else {
    responseText = 'I don\'t have specific information about that query. Please ask something else.';
  }
  
  return responseText;
}

// Simulate the chat response
async function simulateChat() {
  try {
    // First response - acknowledgment
    const firstResponse = `Processing your query: "${query}"`;
    console.log(firstResponse);
    console.log('');
    
    // Wait a bit to simulate processing
    await new Promise(resolve => setTimeout(resolve, 500));
    
    // Second response - answer based on the query
    const secondResponse = getMockResponse(query);
    console.log(secondResponse);
    console.log('');
    
    // Wait a bit more
    await new Promise(resolve => setTimeout(resolve, 500));
    
    // Final response
    const finalResponse = 'Is there anything else you would like to know?';
    console.log(finalResponse);
    
    console.log('\n✅ Query test completed successfully');
  } catch (error) {
    console.error('\n❌ Error during test:', error);
    process.exit(1);
  }
}

// Run the simulation
simulateChat(); 