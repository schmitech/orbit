# API Tests

This directory contains tests for the Chatbot API library.

## Test Structure

- `setup.ts`: Sets up the MSW (Mock Service Worker) server to intercept HTTP requests and provide mock responses
- `api.test.ts`: Tests for the API functions
- `query.test.ts`: Tests for specific query handling capabilities
- `clear-history.test.ts`: Tests for conversation history clearing functionality
- `run-query.js`: Script for testing individual queries from the command line
- `test-npm-package.ts`: Script for testing the npm package functionality with real server

## Running Tests

To run the tests:

```bash
# Run tests once
npm test

# Run tests in watch mode
npm run test:watch

# Run tests with coverage
npm test -- --coverage

# Test a specific query
npm run test-query "your query here" "http://localhost:3000"

# Test npm package functionality with real server
npm run test:npm -- "your message here" "http://your-api-server.com"

# Live integration test with env vars
ORBIT_TEST_API_URL="https://orbit.schmitech.ai" \
ORBIT_TEST_API_KEY="default-key" \
npm run test:live
```

## API Configuration

The tests use `test/config.ts` defaults and support environment overrides:
- **Default API URL**: `http://localhost:3000`
- **Default API Key**: `chat-key`
- **Default Session ID**: `test-session`

Environment overrides:
- `TEST_API_URL`
- `TEST_API_KEY`
- `TEST_SESSION_ID`

This reflects the way the library will be used in production, where clients must explicitly configure the API URL and optionally provide an API key before using any other functions.

## Mock Server

The tests use MSW to mock the server responses. This allows us to test the API without making actual HTTP requests to a real server.

The mock server is configured to:

1. Respond to POST requests to `/v1/chat` endpoint
2. Simulate SSE (Server-Sent Events) streaming responses with multiple chunks
3. Return responses in the format: `data: {"response": "...", "done": false/true}`
4. Send a `data: [DONE]` signal at the end of streams
5. Simulate network errors for error handling tests

## Test Cases

The tests cover:

1. Streaming chat functionality
2. Error handling for network issues
3. Conversation history management:
   - Clearing conversation history successfully
   - Error handling when no session ID is available
   - Error handling when no API key is provided
4. Specific query handling:
   - Fee-related queries (e.g., "how much is the fee?")
   - Price-related queries (e.g., "what is the price?")
   - Unknown queries with graceful fallback responses

## Query Testing

The `test-query` command allows you to quickly test how the chatbot responds to specific queries:

```bash
npm run test-query "how much is the fee?" "http://your-api-server.com"
```

This will:
1. Configure the API with the provided server URL
2. Send the query to the API
3. Stream and display the responses

The implementation uses our SDK's `configureApi` and `streamChat` functions to illustrate the proper usage pattern.

## NPM Package Testing

The `test:npm` command allows you to test the actual npm package functionality with a real ORBIT server:

```bash
# Test with local dist build (default)
npm run test:npm -- "Hello, how can you help me?"

# Test with published npm package
npm run test:npm -- --npm "Hello, how can you help me?"

# Test with custom server URL and session
npm run test:npm -- --local "Hello" "http://my-server:3000" "session-123"

# Test with API key authentication
npm run test:npm -- --local "Hello" "http://localhost:3000" "session-123" "demo-key"
```

This script:
1. Tests both local dist build and published npm package
2. Connects to a real ORBIT server (not mocked)
3. Demonstrates proper usage of the SDK
4. Shows streaming responses in real-time
5. Provides helpful error messages for common issues

**Requirements:**
- ORBIT server must be running
- For local testing: run `npm run build` first
- For npm testing: install `@schmitech/chatbot-api` package

## Live Integration Test

`npm run test:live` provides a deterministic live smoke test using environment variables.

Required:
- `ORBIT_TEST_API_URL`
- `ORBIT_TEST_API_KEY`

Optional:
- `ORBIT_TEST_SESSION_ID`
- `ORBIT_TEST_MESSAGE`

## Adding New Tests

When adding new tests:

1. Add new test cases to the appropriate test file
2. Remember to call `configureApi` before using any other SDK functions
3. If needed, add new mock handlers in `setup.ts`
4. To add new query types, update the `query.test.ts` file
5. Run the tests to ensure they pass 
