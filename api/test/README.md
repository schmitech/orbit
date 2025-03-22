# API Tests

This directory contains tests for the Chatbot API library.

## Test Structure

- `setup.ts`: Sets up the MSW (Mock Service Worker) server to intercept HTTP requests and provide mock responses
- `api.test.ts`: Tests for the API functions
- `query.test.ts`: Tests for specific query handling capabilities
- `run-query.js`: Script for testing individual queries from the command line

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
npm run test-query "your query here" "http://your-api-server.com"
```

## API Configuration

The tests use the new `configureApi` function to set the API URL for testing purposes. This reflects the way the library will be used in production, where clients must explicitly configure the API URL before using any other functions.

## Mock Server

The tests use MSW to mock the server responses. This allows us to test the API without making actual HTTP requests to a real server.

The mock server is configured to:

1. Respond to POST requests to `/chat`
2. Simulate streaming responses with multiple chunks
3. Include audio content when voice is enabled
4. Simulate network errors for error handling tests

## Test Cases

The tests cover:

1. Basic chat functionality without voice
2. Chat with voice enabled
3. Error handling for network issues
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

## Adding New Tests

When adding new tests:

1. Add new test cases to the appropriate test file
2. Remember to call `configureApi` before using any other SDK functions
3. If needed, add new mock handlers in `setup.ts`
4. To add new query types, update the `query.test.ts` file
5. Run the tests to ensure they pass 