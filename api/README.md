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

### Configuration (Required)

Before using any API functions, you **must** configure the client with your server URL:

```javascript
import { configureApi, streamChat } from 'chatbot-api';

// Configure the API with your server URL
configureApi('https://your-api-server.com');
```

If you don't configure the API before calling other functions, an error will be thrown.

### Basic Usage

```javascript
import { configureApi, streamChat } from 'chatbot-api';

async function chat() {
  // Configure the API with your server URL (required first step)
  configureApi('https://your-api-server.com');
  
  // Stream chat responses
  for await (const response of streamChat('Hello, how can I help you?', false)) {
    // Access the text response
    console.log(response.text);
    
    // Check if this is the final response
    if (response.done) {
      console.log('Chat complete!');
    }
  }
}

chat();
```

### With Voice Enabled

```javascript
import { configureApi, streamChat } from 'chatbot-api';

async function chatWithVoice() {
  // Configure the API with your server URL
  configureApi('https://your-api-server.com');
  
  // Stream chat responses with voice enabled (second parameter true)
  for await (const response of streamChat('Tell me a joke', true)) {
    // Process text responses
    if (response.text) {
      console.log(response.text);
    }
    
    // Handle audio content when available
    if (response.type === 'audio' && response.content) {
      // Process audio content (base64 encoded)
      console.log('Received audio content');
      // You can decode and play the audio here
    }
    
    if (response.done) {
      console.log('Chat complete!');
    }
  }
}

chatWithVoice();
```

### React Example

```jsx
import React, { useState, useEffect } from 'react';
import { configureApi, streamChat } from 'chatbot-api';

// Configure the API once at the application startup
configureApi('https://your-api-server.com');

function ChatComponent() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;
    
    const userMessage = input;
    setInput('');
    setMessages(prev => [...prev, { text: userMessage, isUser: true }]);
    setIsLoading(true);
    
    let fullResponse = '';
    
    try {
      for await (const response of streamChat(userMessage, false)) {
        if (response.text) {
          fullResponse += response.text;
          // Update the UI with each chunk of text as it arrives
          setMessages(prev => [
            ...prev.slice(0, -1),
            { text: userMessage, isUser: true },
            { text: fullResponse, isUser: false, isComplete: response.done }
          ]);
        }
        
        if (response.done) {
          setIsLoading(false);
        }
      }
    } catch (error) {
      console.error('Chat error:', error);
      setMessages(prev => [...prev, { 
        text: `Error: ${error.message}`, 
        isUser: false, 
        isError: true 
      }]);
      setIsLoading(false);
    }
  };

  return (
    <div className="chat-container">
      <div className="messages">
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.isUser ? 'user' : 'bot'}`}>
            {msg.text}
          </div>
        ))}
        {isLoading && <div className="loading">...</div>}
      </div>
      
      <form onSubmit={handleSubmit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type your message..."
          disabled={isLoading}
        />
        <button type="submit" disabled={isLoading}>Send</button>
      </form>
    </div>
  );
}

export default ChatComponent;
```

## API Reference

### configureApi(apiUrl)

Configures the API client with your server URL.

- **apiUrl** (string): The URL of your Chatbot server
- **Returns**: void

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
npm run test-query "how much is the fee?" "http://your-api-server.com"
```

## License

MIT