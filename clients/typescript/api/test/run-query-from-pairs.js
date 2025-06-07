#!/usr/bin/env node

/**
 * This script picks multiple random questions from a JSON file and runs them against the chatbot API.
 * Usage: npm run test-query-from-pairs path/to/questions.json "http://your-api-url.com" ["your-api-key"] [number_of_questions] ["your-session-id"]
 */

import { configureApi, streamChat } from '../api.ts';
import fs from 'fs';

// Get the JSON file path, API URL, API key, number of questions, and optional session ID from command line arguments
const jsonFilePath = process.argv[2];
const apiUrl = process.argv[3] || 'http://localhost:3000';
const apiKey = process.argv[4];
const numQuestions = parseInt(process.argv[5], 10) || 1; // Default to 1 if not specified
const sessionId = process.argv[6]; // Optional session ID

if (!jsonFilePath) {
  console.error('Error: No JSON file provided');
  console.error('Usage: npm run test-query-from-pairs path/to/questions.json "http://your-api-url.com" ["your-api-key"] [number_of_questions] ["your-session-id"]');
  process.exit(1);
}

console.log(`Using API URL: ${apiUrl}`);
console.log(`Number of random questions to test: ${numQuestions}`);
if (apiKey) {
  console.log(`Using API Key: ${apiKey}`);
}
if (sessionId) {
  console.log(`Using Session ID: ${sessionId}`);
}

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
  
  // Configure the API with the provided URL, API key, and optional session ID
  configureApi(apiUrl, apiKey, sessionId);
  
  // Function to run a single query
  async function runSingleQuery(qa, index, totalQueries) {
    const query = qa.question;
    console.log(`\n-------------------------------------`);
    console.log(`🔍 Testing question ${index + 1}/${totalQueries}: "${query}"`);
    
    try {
      let buffer = '';
      let hasReceivedData = false;
      let currentFullText = '';
      let lastChunk = '';
      console.log('🤖 Assistant: ');
      
      // Use streamChat with correct parameters (message, stream)
      for await (const response of streamChat(query, true)) {
        if (response.text) {
          // Only write new text that hasn't been seen before
          const newText = response.text.slice(currentFullText.length);
          if (newText) {
            // Clean the text by removing extra spaces and newlines
            const cleanText = newText
              .replace(/\n/g, ' ')
              .replace(/\s+/g, ' ')
              .trim();
            
            if (cleanText) {
              // Add a space if needed between existing and new text
              if (buffer && !buffer.endsWith(' ') && !cleanText.startsWith(' ')) {
                process.stdout.write(' ');
                buffer += ' ';
              }
              
              // Handle partial words
              if (lastChunk && !lastChunk.endsWith(' ')) {
                const words = lastChunk.split(' ');
                const lastWord = words[words.length - 1];
                
                // If the new text starts with the last word, skip it
                if (cleanText.startsWith(lastWord)) {
                  const nonOverlappingText = cleanText.slice(lastWord.length);
                  if (nonOverlappingText) {
                    process.stdout.write(nonOverlappingText);
                    buffer += nonOverlappingText;
                  }
                } else {
                  // Check if we have a partial word at the end
                  const lastChar = lastChunk[lastChunk.length - 1];
                  if (cleanText.startsWith(lastChar)) {
                    const nonOverlappingText = cleanText.slice(1);
                    if (nonOverlappingText) {
                      process.stdout.write(nonOverlappingText);
                      buffer += nonOverlappingText;
                    }
                  } else {
                    process.stdout.write(cleanText);
                    buffer += cleanText;
                  }
                }
              } else {
                process.stdout.write(cleanText);
                buffer += cleanText;
              }
              
              lastChunk = cleanText;
              currentFullText = response.text;
              hasReceivedData = true;
            }
          }
        }
        
        if (response.done) {
          // Display completion message after the entire response
          console.log('\n\n✅ Query completed successfully');
          
          // If the JSON includes an expected answer, show it
          if (qa.answer) {
            console.log('\n📝 Expected answer from JSON:');
            console.log(qa.answer);
          }
          console.log(`-------------------------------------\n`);
          return true; // Exit the function when done
        }
      }
      
      // If we exit the loop without getting a done signal, that's an issue
      if (!hasReceivedData) {
        console.log('\n\n❌ No response received from server');
      } else {
        console.log('\n\n⚠️  Stream ended without done signal');
      }
      return false;
      
    } catch (error) {
      console.error(`\n❌ Error during test for question ${index + 1}:`, error);
      if (process.env.DEBUG === '1') {
        console.error('Error details:', JSON.stringify(error, null, 2));
      }
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