#!/usr/bin/env node

/**
 * This script picks multiple random questions from a JSON file and runs them against the chatbot API.
 * Usage: npm run test-query path/to/questions.json "http://your-api-url.com" [number_of_questions]
 */

import { configureApi, streamChat } from '../api.ts';
import fs from 'fs';

// Get the JSON file path, API URL, and number of questions from command line arguments
const jsonFilePath = process.argv[2];
const numQuestions = parseInt(process.argv[3], 10) || 1; // Default to 1 if not specified
const apiUrl = process.argv[4] || 'http://localhost:3000';

if (!jsonFilePath) {
  console.error('Error: No JSON file provided');
  console.error('Usage: npm run test-query path/to/questions.json "http://your-api-url.com" [number_of_questions]');
  process.exit(1);
}

console.log(`Using API URL: ${apiUrl}`);
console.log(`Number of random questions to test: ${numQuestions}`);

try {
  // Read and parse the JSON file
  const qaData = JSON.parse(fs.readFileSync(jsonFilePath, 'utf8'));
  
  if (!Array.isArray(qaData) || qaData.length === 0) {
    console.error('Error: JSON file does not contain an array of questions');
    process.exit(1);
  }
  
  // Cap the number of questions to the available data
  const actualNumQuestions = Math.min(numQuestions, qaData.length);
  
  if (actualNumQuestions < numQuestions) {
    console.log(`Warning: Only ${actualNumQuestions} questions available in the dataset`);
  }
  
  // Select random questions without duplicates
  const selectedIndices = new Set();
  while (selectedIndices.size < actualNumQuestions) {
    selectedIndices.add(Math.floor(Math.random() * qaData.length));
  }
  
  // Configure the API with the provided URL
  configureApi(apiUrl);
  
  // Function to run a single query
  async function runSingleQuery(qa, index, totalQueries) {
    const query = qa.question;
    console.log(`\n-------------------------------------`);
    console.log(`🔍 Testing question ${index + 1}/${totalQueries}: "${query}"`);
    
    try {
      let fullResponse = '';
      console.log('🤖 Assistant:');
      
      // Use our SDK's streamChat function instead of raw fetch
      for await (const response of streamChat(query, false)) {
        if (response.text) {
          // Append new text to the full response
          fullResponse += response.text;
          
          // Write just the new text portion
          process.stdout.write(response.text);
        } else if (response.content) {
          console.log('\n' + response.content);
        }
      }
      
      // Display completion message after the entire response
      console.log('\n\n✅ Query completed successfully');
      
      // If the JSON includes an expected answer, show it
      if (qa.answer) {
        console.log('\n📝 Expected answer from JSON:');
        console.log(qa.answer);
      }
      console.log(`-------------------------------------\n`);
      
      return true;
    } catch (error) {
      console.error(`\n❌ Error during test for question ${index + 1}:`, error);
      return false;
    }
  }
  
  // Run all selected queries sequentially
  async function runAllQueries() {
    console.log(`\nSelected ${actualNumQuestions} random questions for testing\n`);
    
    let successCount = 0;
    let index = 0;
    
    for (const questionIndex of selectedIndices) {
      const success = await runSingleQuery(qaData[questionIndex], index, actualNumQuestions);
      if (success) successCount++;
      index++;
    }
    
    console.log(`\n=================================`);
    console.log(`Test Results: ${successCount}/${actualNumQuestions} successful queries`);
    console.log(`=================================\n`);
  }
  
  // Run all the queries
  runAllQueries();
  
} catch (error) {
  console.error('Error reading or parsing JSON file:', error);
  process.exit(1);
}