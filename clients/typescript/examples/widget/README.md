# How to Use the Chatbot Widget

This guide will help you integrate the chatbot widget into your website with minimal effort.

## Quick Start

### 1. Include the Widget Files

Choose one of these methods to include the widget:

**Option 1 - All-in-one bundle (Recommended):**
```html
<script src="https://unpkg.com/@schmitech/chatbot-widget@latest/dist/chatbot-widget.bundle.js"></script>
```

**Option 2 - Separate files:**
```html
<script src="https://unpkg.com/@schmitech/chatbot-widget@latest/dist/chatbot-widget.umd.js"></script>
<link rel="stylesheet" href="https://unpkg.com/@schmitech/chatbot-widget@latest/dist/chatbot-widget.css">
```

### 2. Initialize the Widget

Add this code to your website:

```html
<script>
  window.addEventListener('load', function() {
    window.initChatbotWidget({
      apiUrl: 'https://your-api-url.com',  // Your chatbot API endpoint  
      apiKey: 'your-api-key',             // Your API key
      sessionId: 'optional-session-id',    // Required: Provide a session ID
      // Optional widget configuration
      header: {
        title: "Chat Assistant"
      },
      welcome: {
        title: "Welcome!",
        description: "How can I help you today?"
      },
      suggestedQuestions: [
        {
          text: "How can you help me?",
          query: "What can you do?"
        },
        {
          text: "Contact support", 
          query: "How do I contact support?"
        }
      ],
      theme: {
        primary: '#4f46e5',
        secondary: '#7c3aed',
        background: '#ffffff',
        text: {
          primary: '#111827',
          inverse: '#ffffff'
        },
        input: {
          background: '#f9fafb',
          border: '#e5e7eb'
        },
        message: {
          user: '#4f46e5',
          assistant: '#f8fafc',
          userText: '#ffffff'
        },
        suggestedQuestions: {
          background: '#eef2ff',
          hoverBackground: '#e0e7ff',
          text: '#4338ca'
        },
        chatButton: {
          background: '#ffffff',
          hoverBackground: '#f8fafc'
        },
        iconColor: '#7c3aed'
      },
      icon: "message-square"
    });
  });
</script>
```

## Configuration Options

### Required Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `apiUrl` | string | Your chatbot API endpoint URL |
| `apiKey` | string | Your API authentication key |
| `sessionId` | string | Unique identifier for the chat session |

### Optional Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `containerSelector` | string | CSS selector for custom container (defaults to bottom-right corner) |
| `header` | object | Widget header configuration |
| `welcome` | object | Welcome message configuration |
| `suggestedQuestions` | array | Array of suggested question buttons |
| `theme` | object | Theme customization options |
| `icon` | string | Widget icon type |

## Advanced Usage

### Custom Container

To place the widget in a specific container instead of the bottom-right corner:

```html
<div id="my-chat-container"></div>

<script>
  window.initChatbotWidget({
    apiUrl: 'https://your-api-url.com',
    apiKey: 'your-api-key',
    sessionId: 'your-session-id',
    containerSelector: '#my-chat-container',
    // ... other config options
  });
</script>
```

### React/TypeScript Integration

For React applications, you can integrate the widget like this:

```tsx
import { useEffect } from 'react';

function App() {
  useEffect(() => {
    if (typeof window !== 'undefined' && window.initChatbotWidget) {
      window.initChatbotWidget({
        apiUrl: process.env.REACT_APP_API_ENDPOINT,
        apiKey: process.env.REACT_APP_API_KEY,
        sessionId: process.env.REACT_APP_SESSION_ID,
        header: {
          title: "AI Assistant"
        },
        // ... other config options
      });
    }
  }, []);

  return (
    // Your app content
  );
}
```

## Theme Configuration

The widget supports extensive theme customization:

```typescript
theme: {
  primary: string;           // Primary color (headers, user messages)
  secondary: string;         // Secondary/accent color  
  background: string;        // Widget background color
  text: {
    primary: string;         // Primary text color
    inverse: string;         // Text color on colored backgrounds
  },
  input: {
    background: string;      // Input field background
    border: string;          // Input field border color
  },
  message: {
    user: string;           // User message bubble color
    assistant: string;      // Assistant message bubble color
    userText: string;       // User message text color
  },
  suggestedQuestions: {
    background: string;      // Suggested questions background
    hoverBackground: string; // Suggested questions hover background
    text: string;           // Suggested questions text color
  },
  chatButton: {
    background: string;      // Chat button background
    hoverBackground: string; // Chat button hover background
  },
  iconColor: string;        // Widget icon color
}
```

### Built-in Themes

The demo includes several professional themes:
- **Modern** - Vibrant indigo/purple gradient
- **Minimal** - Clean gray palette  
- **Corporate** - Professional blue theme
- **Dark** - Sleek dark theme with cyan accents
- **Emerald** - Fresh green theme
- **Sunset** - Warm orange-red gradient
- **Lavender** - Elegant purple theme
- **Monochrome** - Sophisticated grayscale

## Available Icons

Choose from these built-in icons:
- `heart` - Heart icon
- `message-square` - Square message bubble (default)
- `message-circle` - Round message bubble  
- `message-dots` - Message bubble with dots
- `help-circle` - Question mark in circle
- `info` - Information icon
- `bot` - Robot icon
- `sparkles` - Sparkles icon

## Widget Configuration Structure

```typescript
{
  header: {
    title: string;          // Widget header title
  },
  welcome: {
    title: string;          // Welcome message title
    description: string;    // Welcome message description
  },
  suggestedQuestions: [     // Array of suggested questions
    {
      text: string;        // Button text
      query: string;       // Question to send when clicked
    }
  ],
  theme: { /* theme object */ },
  icon: string;            // Widget icon type
}
```

## Session Management

The widget requires a `sessionId` parameter for proper conversation management:

1. **Generate a unique session ID** for each user conversation
2. **Maintain the session ID** throughout the user's visit
3. **Use UUIDs or similar** for session identification

Example session ID generation:
```javascript
function generateSessionId() {
  return 'session-' + Math.random().toString(36).substr(2, 9) + '-' + Date.now();
}

window.initChatbotWidget({
  apiUrl: 'https://your-api-url.com',
  apiKey: 'your-api-key', 
  sessionId: generateSessionId(),
  // ... other config
});
```

## Typography

The widget uses **Mona Sans** font by default, with fallbacks to system fonts for optimal performance and consistency.

## Troubleshooting

1. **Widget not appearing?**
   - Check browser console for errors
   - Verify API URL and key are correct
   - Ensure all required scripts are loaded
   - Check if the container element exists

2. **Session ID issues?**
   - Ensure `sessionId` parameter is provided
   - Verify the session ID is unique per conversation
   - Check that your API supports session-based conversations

3. **API connection issues?**
   - Verify your API endpoint is accessible
   - Check API key is valid
   - Ensure CORS is properly configured on your API
   - Verify session ID is being sent with requests

4. **Styling conflicts?**
   - The widget uses scoped CSS to prevent conflicts
   - If you see styling issues, check for conflicting CSS rules
   - Dark themes require proper text color configuration

## Support

For more help:
- Visit our [GitHub repository](https://github.com/schmitech/orbit)
- Check the demo at `/demo.html` for live examples
- Open an issue on GitHub for bug reports