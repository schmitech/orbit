# Chatbot API Integration

This chat application nintegrates with the `@schmitech/chatbot-api` package for real-time streaming chat responses.

## Configuration

The application supports multiple ways to configure the API:

### 1. Environment Variables (Vite)
Create a `.env.local` file in the root directory:

```bash
VITE_API_URL=https://your-api-endpoint.com
VITE_API_KEY=your-api-key-here
```

### 2. Window Variables
Set global variables in your HTML or before the app loads:

```javascript
window.CHATBOT_API_URL = 'https://your-api-endpoint.com';
window.CHATBOT_API_KEY = 'your-api-key-here';
```

### 3. Runtime Configuration
Use the "Configure API" button in the chat interface to set the API URL and key at runtime.

## Features

- **Streaming Responses**: Real-time streaming of AI responses
- **Session Management**: Automatic session ID generation and persistence
- **Error Handling**: Comprehensive error handling with user-friendly messages
- **Conversation Persistence**: Chat history is saved to localStorage
- **API Configuration**: Flexible API configuration options

## Usage

1. Configure your API settings using one of the methods above
2. Start a conversation by typing a message
3. The AI will respond with streaming text
4. Use the regenerate button (↻) to regenerate responses
5. Use the copy button to copy AI responses to clipboard

## Integration Details

The integration uses:
- **Zustand** for state management (replacing React Context)
- **@schmitech/chatbot-api** for streaming chat functionality  
- **localStorage** for persistent session and conversation storage
- **TypeScript** for type safety throughout the integration
