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
npm run test-query "your query here"
```

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
npm run test-query "how much is the fee?"
```

This will simulate the chatbot's response, showing:
1. An acknowledgment of the query
2. A response based on the content of the query
3. A final message asking if there's anything else the user would like to know

The implementation uses a simple simulation that matches keywords in the query to provide appropriate responses.

## Adding New Tests

When adding new tests:

1. Add new test cases to the appropriate test file
2. If needed, add new mock handlers in `setup.ts`
3. To add new query types, update the `query.test.ts` file and the `getMockResponse` function in `run-query.js`
4. Run the tests to ensure they pass 