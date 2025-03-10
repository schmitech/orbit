# Chatbot API Client

A JavaScript/TypeScript client library for interacting with the Chatbot server.

## Installation

### Option 1: Using npm link (for local development)

To use this library in other projects on your local machine during development:

1. In this library directory, run:
   ```bash
   npm run build
   npm link
   ```

2. In your project directory, run:
   ```bash
   npm link chatbot-api
   ```

3. Now you can import and use the library in your project:
   ```javascript
   import { streamChat } from 'chatbot-api';
   ```

### Option 2: Installing from a local directory

You can also install the package directly from the local directory:

1. In this library directory, run:
   ```bash
   npm run build
   ```

2. In your project directory, run:
   ```bash
   npm install /path/to/qa-chatbot-server/api
   ```

3. Now you can import and use the library in your project:
   ```javascript
   import { streamChat } from 'chatbot-api';
   ```

### Option 3: Publishing to npm (for production)

To make this library available to anyone via npm:

1. Create an account on npmjs.com if you don't have one
2. Login to npm from the command line:
   ```bash
   npm login
   ```
3. Update the package name in package.json to ensure it's unique
4. Publish the package:
   ```bash
   npm publish
   ```

## Usage

### Basic Usage

```javascript
import { streamChat } from 'chatbot-api';

async function chat() {
  // Stream chat responses
  for await (const response of streamChat('Hello, how can I help you?', false)) {
    console.log(response.text);
    
    if (response.done) {
      console.log('Chat complete!');
    }
  }
}

chat();
```

### With Voice Enabled

```javascript
import { streamChat } from 'chatbot-api';

async function chatWithVoice() {
  // Stream chat responses with voice enabled
  for await (const response of streamChat('Tell me a joke', true)) {
    console.log(response.text);
    
    // Handle audio content
    if (response.type === 'audio' && response.content) {
      // Process audio content (base64 encoded)
      console.log('Received audio content');
    }
    
    if (response.done) {
      console.log('Chat complete!');
    }
  }
}

chatWithVoice();
```

## API Reference

### streamChat(message, voiceEnabled)

Streams chat responses from the server.

- **message** (string): The message to send to the chatbot
- **voiceEnabled** (boolean): Whether to enable voice responses
- **Returns**: AsyncGenerator that yields StreamResponse objects

### StreamResponse Interface

```typescript
interface StreamResponse {
  text?: string;       // The text response
  content?: string;    // Alternative property for text content
  done?: boolean;      // Whether this is the final response
  type?: string;       // Type of response (e.g., 'text', 'audio')
}
```

## Development

### Building the Library

```bash
npm run build
```

### Running Tests

```bash
# Run tests once
npm test

# Run tests in watch mode
npm run test:watch

# Test a specific query
npm run test-query "how much is the fee?"
```

## License

MIT