# Community Services Organization

A demo website showcasing the integration of a chatbot widget for community services information.

## Getting Started

```bash
# Install dependencies
npm install

# Run the development server
npm run dev

# Build for production
npm run build
```

## Chatbot Widget Integration Guide

The chatbot widget provides an interactive chat interface that can be added to any website. Here's how to integrate it into your own project:

### Step 1: Build the Widget

```bash
cd widget
npm install
npx vite build
```

This generates the following files in the `widget/dist` folder:
- `chatbot-widget.umd.js` - UMD module for direct script tag usage
- `chatbot-widget.es.js` - ES module for import usage
- `style.css` - Widget styling

### Step 2: Copy Widget Files

Copy these files to your website's static/public folder:
- `chatbot-widget.umd.js`
- `style.css`

### Step 3: Add to HTML

Include these scripts and styles in your HTML file:

```html
<!-- Include React and ReactDOM first -->
<script src="https://unpkg.com/react@18/umd/react.production.min.js" crossorigin></script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js" crossorigin></script>
<!-- Include the widget -->
<script src="/chatbot-widget.umd.js"></script>
<link rel="stylesheet" href="/style.css">
```

### Step 4: Initialize the Widget

Add this script to initialize the widget:

```html
<script>
  // Initialize the widget when the page loads
  window.addEventListener('load', function() {
    window.initChatbotWidget({
      apiUrl: 'https://your-api-endpoint.com', // Replace with your API URL
      widgetConfig: {
        header: {
          title: "Your Chat Title"
        },
        welcome: {
          title: "Welcome Message",
          description: "This is a description of what the chatbot can do."
        },
        suggestedQuestions: [
          {
            text: "Question 1",
            query: "What exactly happens when I ask this?"
          },
          {
            text: "Question 2",
            query: "Technical details about something"
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
          }
        }
      }
    });
  });
</script>
```

You can also use the DOM Content Loaded event:

```javascript
document.addEventListener('DOMContentLoaded', () => {
  window.initChatbotWidget({
    apiUrl: 'https://your-api-endpoint.com',
    widgetConfig: {
      // Configuration options
    }
  });
});
```

### Step 5: Dynamically Update Configuration

You can update the widget's configuration anytime:

```javascript
// Update theme
window.ChatbotWidget.updateWidgetConfig({
  theme: {
    primary: '#1a365d',
    secondary: '#e53e3e'
    // Other theme properties...
  }
});

// Update content
window.ChatbotWidget.updateWidgetConfig({
  header: {
    title: "New Title"
  },
  welcome: {
    title: "Updated Welcome",
    description: "New description"
  }
});
```

### Advanced Usage: Custom Container

You can specify a custom container for the widget:

```html
<div id="my-chat-container"></div>

<script>
  window.addEventListener('load', function() {
    window.initChatbotWidget({
      apiUrl: 'https://your-api-endpoint.com',
      containerSelector: '#my-chat-container'
    });
  });
</script>
```

## Integration with React Applications

### Option 1: Direct Import (Recommended for React Apps)

```jsx
import { ChatWidget } from 'chatbot-widget';
import 'chatbot-widget/style.css';

function App() {
  return (
    <div className="App">
      <ChatWidget />
      {/* Your other components */}
    </div>
  );
}

// Set API URL via the exposed function
window.ChatbotWidget.setApiUrl('https://your-api-server.com');
```

### Option 2: Script Initialization in React

```jsx
import React, { useEffect } from 'react';
import 'chatbot-widget/style.css';

function App() {
  useEffect(() => {
    // Initialize the widget when component mounts
    if (typeof window !== 'undefined' && window.initChatbotWidget) {
      window.initChatbotWidget({
        apiUrl: 'https://your-api-endpoint.com',
        widgetConfig: {
          // Configuration options as shown above
        }
      });
    }
  }, []);

  return (
    // Your application components
  );
}
```

## Requirements

- API endpoint that follows the expected format
- Static file hosting for the widget files
- Modern browser support (ES6+)

## Configuration Options

| Option | Description |
|--------|-------------|
| `apiUrl` | URL of the API endpoint for the chatbot |
| `containerSelector` | (Optional) CSS selector for the container where the widget should be rendered |
| `header.title` | Title displayed in the chat header |
| `welcome.title` | Welcome message title |
| `welcome.description` | Welcome message description |
| `suggestedQuestions` | Array of suggested questions with `text` (display text) and `query` (actual query sent) |
| `theme` | Object containing color configurations for all widget elements |

## Features

- Easy to integrate with a single JavaScript snippet
- Responsive design with mobile support
- Customizable appearance
- Markdown support for rich text responses
- Link detection and formatting

## License

MIT
