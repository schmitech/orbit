# 🤖 ORBIT Chatbot API Client

A TypeScript/JavaScript client for seamless interaction with the ORBIT server, supporting API key authentication and session tracking.

## 📥 Installation

```bash
npm install @schmitech/chatbot-api
```

## ⚙️ Basic Usage

### Configuration

First, configure the API client with your server details:

```typescript
import { configureApi, streamChat } from '@schmitech/chatbot-api';

configureApi({
  apiUrl: 'https://your-api-server.com',
  apiKey: 'your-api-key',
  sessionId: 'optional-session-id' // Optional, for conversation tracking
});
```

### Streaming Chat Example

```typescript
async function chat() {
  for await (const response of streamChat('Hello, how can I help?', true)) {
    console.log(response.text);
    if (response.done) {
      console.log('Chat complete!');
    }
  }
}
```
### Local test in Node.js environment

First, verify you have `Node.js` and its package manager, `npm`, installed. Then create a new folder.

```bash
node -v
npm -v
```

Initialize a `Node.js` Project

```bash
npm init -y
```

Modify `package.json`

```json
{
  "name": "orbit-node",
  "version": "1.0.0",
  "main": "index.js",
  "type": "module",
  "scripts": {
    "test": "echo \"Error: no test specified\" && exit 1"
  },
  "keywords": [],
  "author": "",
  "license": "ISC",
  "description": "",
  "dependencies": {
    "@schmitech/chatbot-api": "^0.5.0"
  }
}
```

Install chatbot api

```bash
npm install @schmitech/chatbot-api
```

Run this test

```bash
node test/test-npm-package.js "how many r are in a strawberry?" "http://localhost:3000" "my-session-123"
```

## ⚛️ React Integration

Here's how to use the API in a React component:

```tsx
import React, { useState } from 'react';
import { configureApi, streamChat } from '@schmitech/chatbot-api';

// Configure once at app startup
configureApi({
  apiUrl: 'https://your-api-server.com',
  apiKey: 'your-api-key',
  sessionId: 'user_123_session_456' // Optional
});

function ChatComponent() {
  const [messages, setMessages] = useState<Array<{ text: string; isUser: boolean }>>([]);
  const [input, setInput] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessages(prev => [...prev, { text: input, isUser: true }]);

    let responseText = '';
    for await (const response of streamChat(input, true)) {
      responseText += response.text;
      setMessages(prev => [...prev, { text: responseText, isUser: false }]);
      if (response.done) break;
    }
    setInput('');
  };

  return (
    <form onSubmit={handleSubmit}>
      <input 
        value={input} 
        onChange={(e) => setInput(e.target.value)} 
        placeholder="Type your message..."
      />
      <button type="submit">Send</button>
    </form>
  );
}
```

## 📱 Mobile Usage

### React Native Example

```typescript
import { configureApi, streamChat } from '@schmitech/chatbot-api';

// Configure once at app startup
configureApi({
  apiUrl: 'https://your-api-server.com',
  apiKey: 'your-api-key',
  sessionId: 'user_123_session_456' // Optional
});

async function handleChat(message: string) {
  for await (const response of streamChat(message, true)) {
    // Handle streaming response
    console.log(response.text);
    if (response.done) {
      console.log('Chat complete!');
    }
  }
}
```

## 🌐 CDN Integration

You can also use the API directly in the browser via CDN:

```html
<script type="module">
  import { configureApi, streamChat } from 'https://cdn.jsdelivr.net/npm/@schmitech/chatbot-api/dist/api.mjs';

  configureApi({
    apiUrl: 'https://your-api-server.com',
    apiKey: 'your-api-key',
    sessionId: 'your-session-id' // Optional
  });

  async function handleChat() {
    for await (const response of streamChat('Hello', true)) {
      console.log(response.text);
    }
  }
</script>
```

## 📚 API Reference

### `configureApi(config)`

Configure the API client with server details.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `apiUrl` | string | Yes | Chatbot API server URL |
| `apiKey` | string | Yes | API key for authentication |
| `sessionId` | string | No | Session ID for conversation tracking |

### `streamChat(message: string, stream: boolean = true)`

Stream chat responses from the server.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `message` | string | - | The message to send to the chat |
| `stream` | boolean | true | Whether to stream the response |

Returns an AsyncGenerator that yields `StreamResponse` objects:

```typescript
interface StreamResponse {
  text: string;    // The text content of the response
  done: boolean;   // Whether this is the final response
}
```

## 🔒 Security

- Always use HTTPS for your API URL
- Keep your API key secure and never expose it in client-side code
- Consider using environment variables for sensitive configuration