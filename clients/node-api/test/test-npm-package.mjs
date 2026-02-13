#!/usr/bin/env node

/**
 * Simple test script for the ORBIT chatbot API.
 *
 * Usage:
 *   npm run test:npm -- [--local|--npm] "message" [api-url] [session-id] [api-key]
 */

const args = process.argv.slice(2);

let useLocal = true;
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
const sessionId = args[argIndex + 2];
const apiKey = args[argIndex + 3];

if (!message || message === '--help' || message === '-h') {
  console.log('Usage: npm run test:npm -- [--local|--npm] "message" [api-url] [session-id] [api-key]');
  process.exit(message ? 0 : 1);
}

async function loadSdk() {
  if (useLocal) {
    return await import('../dist/api.mjs');
  }
  return await import('@schmitech/chatbot-api');
}

async function run() {
  try {
    const sdk = await loadSdk();
    sdk.configureApi(apiUrl, apiKey || undefined, sessionId || undefined);

    process.stdout.write('Assistant: ');
    for await (const response of sdk.streamChat(message, true)) {
      if (response.text) process.stdout.write(response.text);
      if (response.done) {
        process.stdout.write('\n');
        return;
      }
    }

    process.stdout.write('\n');
    process.exitCode = 1;
  } catch (error) {
    console.error('Error:', error?.message || error);
    process.exit(1);
  }
}

run();
