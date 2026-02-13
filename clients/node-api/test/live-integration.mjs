#!/usr/bin/env node

/**
 * Live integration test runner.
 *
 * Env vars:
 *   ORBIT_TEST_API_URL   required
 *   ORBIT_TEST_API_KEY   required
 *   ORBIT_TEST_SESSION_ID optional (default: sdk-live-test-session)
 *   ORBIT_TEST_MESSAGE    optional (default: Hello from live integration test)
 */

import { configureApi, streamChat } from '../dist/api.mjs';

const apiUrl = process.env.ORBIT_TEST_API_URL;
const apiKey = process.env.ORBIT_TEST_API_KEY;
const sessionId = process.env.ORBIT_TEST_SESSION_ID || 'sdk-live-test-session';
const message = process.env.ORBIT_TEST_MESSAGE || 'Hello from live integration test';

if (!apiUrl || !apiKey) {
  console.error('Missing required env vars: ORBIT_TEST_API_URL and ORBIT_TEST_API_KEY');
  process.exit(1);
}

configureApi(apiUrl, apiKey, sessionId);

let sawDone = false;
let textLength = 0;

try {
  for await (const response of streamChat(message, true)) {
    if (response.text) {
      textLength += response.text.length;
      process.stdout.write(response.text);
    }
    if (response.done) {
      sawDone = true;
      break;
    }
  }

  process.stdout.write('\n');

  if (!sawDone || textLength === 0) {
    console.error('Live integration test failed: no completion signal or no text.');
    process.exit(1);
  }

  console.log('Live integration test passed.');
} catch (error) {
  console.error('Live integration test error:', error?.message || error);
  process.exit(1);
}
