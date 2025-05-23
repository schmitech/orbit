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
  // Generate a unique session ID for this user
  function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      const r = Math.random() * 16 | 0;
      const v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }

  window.addEventListener('load', function() {
    window.initChatbotWidget({
      apiUrl: 'https://your-api-url.com',  // Your chatbot API endpoint
      apiKey: 'your-api-key',             // Your API key
      sessionId: generateUUID(),          // Unique session ID
      widgetConfig: {
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
          primary: '#2C3E50',
          secondary: '#f97316',
          background: '#ffffff',
          text: {
            primary: '#1a1a1a',
            secondary: '#666666',
            inverse: '#ffffff'
          },
          input: {
            background: '#f9fafb',
            border: '#e5e7eb'
          },
          message: {
            user: '#2C3E50',
            assistant: '#ffffff',
            userText: '#ffffff'
          },
          suggestedQuestions: {
            background: '#fff7ed',
            hoverBackground: '#ffedd5',
            text: '#2C3E50'
          },
          iconColor: '#f97316'
        },
        icon: "message-square"
      }
    });
  });
</script>
```

## Advanced Usage

### Custom Container

To place the widget in a specific container instead of the bottom-right corner:

```html
<div id="my-chat-container"></div>

<script>
  window.initChatbotWidget({
    apiUrl: 'https://your-api-url.com',
    apiKey: 'your-api-key',
    containerSelector: '#my-chat-container',
    widgetConfig: {
      // ... your config here
    }
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
        sessionId: generateUUID(),
        widgetConfig: {
          // ... your config here
        }
      });
    }
  }, []);

  return (
    // Your app content
  );
}
```

## Configuration Options

### Required Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `apiUrl` | string | Your chatbot API endpoint URL |
| `apiKey` | string | Your API authentication key |

### Optional Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `sessionId` | string | Unique identifier for the chat session |
| `containerSelector` | string | CSS selector for custom container |
| `widgetConfig` | object | Widget appearance and behavior settings |

### Widget Configuration

The `widgetConfig` object supports these properties:

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
      query: string;       // Question to send
    }
  ],
  theme: {                 // Theme customization
    primary: string;       // Primary color
    secondary: string;     // Secondary/accent color
    background: string;    // Background color
    text: {
      primary: string;     // Primary text color
      secondary: string;   // Secondary text color
      inverse: string;     // Inverse text color
    },
    input: {
      background: string;  // Input background
      border: string;      // Input border color
    },
    message: {
      user: string;        // User message bubble color
      assistant: string;   // Assistant message bubble color
      userText: string;    // User message text color
    },
    suggestedQuestions: {
      background: string;      // Suggested questions background
      hoverBackground: string; // Suggested questions hover background
      text: string;           // Suggested questions text color
    },
    iconColor: string;     // Widget icon color
  },
  icon: string;            // Widget icon type
}
```

## Available Icons

Choose from these built-in icons:
- `heart` ❤️
- `message-square` 💬
- `message-circle` 🗨️
- `help-circle` ❓
- `info` ℹ️
- `bot` 🤖
- `sparkles` ✨

## Customizing Height

To adjust the widget height, add this CSS to your website:

```css
:root {
  --chat-container-height: 600px; /* Default is 500px */
}
```

## Troubleshooting

1. **Widget not appearing?**
   - Check browser console for errors
   - Verify API URL and key are correct
   - Ensure all required scripts are loaded

2. **API connection issues?**
   - Verify your API endpoint is accessible
   - Check API key is valid
   - Ensure CORS is properly configured on your API

3. **Styling conflicts?**
   - The widget uses scoped CSS to prevent conflicts
   - If you see styling issues, check for conflicting CSS rules

## Support

For more help:
- Visit our [GitHub repository](https://github.com/schmitech/orbit)
- Open an issue on GitHub for bug reports