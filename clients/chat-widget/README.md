# Schmitech Chatbot Widget

A customizable chatbot widget that integrates seamlessly into any website. Perfect for customer support, lead generation, and user engagement.

## 🚀 Quick Start

### Prerequisites
- Any modern web browser
- A web server (for local development, you can use a simple HTTP server)
- Basic knowledge of HTML/JavaScript

### Installation Methods

**Option 1 - CDN:**
```html
<!-- Add to your HTML head -->
<link rel="stylesheet" href="https://unpkg.com/@schmitech/chatbot-widget@latest/dist/chatbot-widget.css">

<!-- Add before closing body tag -->
<script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
<script src="https://unpkg.com/@schmitech/chatbot-widget@latest/dist/chatbot-widget.umd.js"></script>
```

**Option 2 - npm install:**
```bash
npm install @schmitech/chatbot-widget
```

### 30-Second Setup

1. **Add the widget to your HTML:**
```html
<!DOCTYPE html>
<html>
<head>
    <link rel="stylesheet" href="https://unpkg.com/@schmitech/chatbot-widget@latest/dist/chatbot-widget.css">
</head>
<body>
    <!-- Your website content -->
    
    <!-- Chatbot container (optional - for embedded mode) -->
    <div id="chatbot-container"></div>
    
    <!-- Widget dependencies -->
    <script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
    <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
    <script src="https://unpkg.com/@schmitech/chatbot-widget@latest/dist/chatbot-widget.umd.js"></script>
    
    <!-- Initialize widget -->
    <script>
        window.addEventListener('load', function() {
            window.initChatbotWidget({
                apiUrl: 'https://your-api-endpoint.com',
                apiKey: 'your-api-key',
                sessionId: 'user-session-' + Date.now(),
                containerSelector: '#chatbot-container', // Remove for floating widget
                widgetConfig: {
                    header: { title: "Chat Assistant" },
                    welcome: { 
                        title: "Hello! 👋", 
                        description: "How can I help you today?" 
                    }
                }
            });
        });
    </script>
</body>
</html>
```

2. **Replace the placeholder values:**
   - `https://your-api-endpoint.com` → Your chatbot API URL
   - `your-api-key` → Your API authentication key

3. **Done!** The widget will appear on your website.

## 📋 Two Integration Modes

### Floating Widget (Default)
The widget appears as a chat button in the bottom-right corner:
```html
<script>
window.addEventListener('load', function() {
    window.initChatbotWidget({
        apiUrl: 'https://your-api-endpoint.com',
        apiKey: 'your-api-key',
        sessionId: 'user-session-' + Date.now(),
        // No containerSelector = floating mode
        widgetConfig: {
            header: { title: "Chat Assistant" },
            welcome: { title: "Hi there! 👋", description: "How can I help?" }
        }
    });
});
</script>
```

### Embedded Widget
The widget embeds directly into a specific container:
```html
<!-- Add container div where you want the widget -->
<div id="chat-widget" style="height: 500px; width: 100%;"></div>

<script>
window.addEventListener('load', function() {
    window.initChatbotWidget({
        apiUrl: 'https://your-api-endpoint.com',
        apiKey: 'your-api-key',
        sessionId: 'user-session-' + Date.now(),
        containerSelector: '#chat-widget', // Embed in this container
        widgetConfig: {
            header: { title: "Chat Assistant" },
            welcome: { title: "Hi there! 👋", description: "How can I help?" }
        }
    });
});
</script>
```

## 🛠️ Settings

```html
<script>
  window.addEventListener('load', function() {
    window.initChatbotWidget({
      // Required parameters
      apiUrl: 'https://your-api-url.com',  // Your chatbot API endpoint  
      apiKey: 'your-api-key',             // Your API key
      sessionId: 'optional-session-id',    // Required: Provide a session ID
      
      // Optional: Custom container selector
      containerSelector: '#my-chat-container', // Place widget in specific container
      
      // Widget configuration
      widgetConfig: {
        // Header configuration
        header: {
          title: "Chat Assistant"  // Title shown in the chat header
        },
        
        // Welcome message configuration
        welcome: {
          title: "Welcome!",       // Welcome message title
          description: "How can I help you today?"  // Welcome message description
        },
        
        // Suggested questions configuration
        suggestedQuestions: [
          {
            text: "How can you help me?",  // Display text (truncated based on maxSuggestedQuestionLength)
            query: "What can you do?"      // Query sent to API (truncated based on maxSuggestedQuestionQueryLength)
          },
          {
            text: "Contact support",       // Display text
            query: "How do I contact support?" // Query sent to API
          }
        ],
        
        // Optional: Customize length limits for suggested questions
        maxSuggestedQuestionLength: 60,      // Display length limit (default: 120)
        maxSuggestedQuestionQueryLength: 300, // Query length limit (default: 200)
        
        // Theme configuration
        theme: {
          // Main colors
          primary: '#4f46e5',    // Header and minimized button color
          secondary: '#7c3aed',  // Send button and header title color
          background: '#ffffff', // Widget background color
          
          // Text colors
          text: {
            primary: '#111827',   // Main text color
            secondary: '#6b7280', // Secondary text color
            inverse: '#ffffff'    // Text color on colored backgrounds
          },
          
          // Input field styling
          input: {
            background: '#f9fafb', // Input field background
            border: '#e5e7eb'     // Input field border color
          },
          
          // Message bubble styling
          message: {
            user: '#4f46e5',      // User message bubble color
            userText: '#ffffff',  // User message text color
            assistant: '#f8fafc', // Assistant message bubble color
            assistantText: '#374151' // Assistant message text color
          },
          
          // Suggested questions styling
          suggestedQuestions: {
            background: '#f3f4f6',    // Background color
            text: '#1f2937',          // Text color
            highlightedBackground: '#fef3c7' // Hover background color
          },
          
          // Chat button styling
          chatButton: {
            background: '#ffffff',     // Button background
            hoverBackground: '#f8fafc', // Button hover background
            iconColor: '#7c3aed',      // Icon color
            iconBorderColor: '#e5e7eb', // Icon border color
            borderColor: '#e5e7eb',     // Button border color
            iconName: 'MessageSquare'   // Icon name (see available icons below)
          }
        }
      }
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
| `suggestedQuestions` | array | Array of suggested question buttons (max 120 chars per question, max 200 chars per query) |
| `maxSuggestedQuestionLength` | number | Maximum display length for suggested question text (default: 120) |
| `maxSuggestedQuestionQueryLength` | number | Maximum length for suggested question queries sent to API (default: 200) |
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

### Separate JavaScript File (Recommended for Complex Sites)

For better organization, create a separate file for your chatbot configuration:

**1. Create `chatbot-config.js`:**
```javascript
// chatbot-config.js
function getSessionId() {
  const storageKey = 'chatbot_session_id';
  let sessionId = sessionStorage.getItem(storageKey);
  
  if (!sessionId) {
    sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    sessionStorage.setItem(storageKey, sessionId);
  }
  
  return sessionId;
}

function initializeChatbot() {
  if (!window.initChatbotWidget) {
    console.error('Chatbot widget not loaded');
    return;
  }

  window.initChatbotWidget({
    apiUrl: 'https://your-api-endpoint.com',
    apiKey: 'your-api-key',
    sessionId: getSessionId(),
    widgetConfig: {
      header: { title: "Support Chat" },
      welcome: { 
        title: "Welcome! 👋", 
        description: "How can we help you today?" 
      },
      suggestedQuestions: [
        { text: "How can I get started?", query: "Help me get started" },
        { text: "Contact support", query: "I need to contact support" }
      ],
      theme: {
        primary: '#4f46e5',
        secondary: '#7c3aed'
      }
    }
  });
}

window.addEventListener('load', initializeChatbot);
```

**2. Include in your HTML:**
```html
<!DOCTYPE html>
<html>
<head>
    <link rel="stylesheet" href="https://unpkg.com/@schmitech/chatbot-widget@latest/dist/chatbot-widget.css">
</head>
<body>
    <!-- Your website content -->
    
    <!-- Widget dependencies -->
    <script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
    <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
    <script src="https://unpkg.com/@schmitech/chatbot-widget@latest/dist/chatbot-widget.umd.js"></script>
    
    <!-- Your chatbot configuration -->
    <script src="chatbot-config.js"></script>
</body>
</html>
```

### React/TypeScript Integration

For React applications:

```tsx
import React, { useEffect, useRef } from 'react';

declare global {
  interface Window {
    initChatbotWidget?: (config: any) => void;
  }
}

function App() {
  const widgetInitialized = useRef(false);

  useEffect(() => {
    if (!widgetInitialized.current && window.initChatbotWidget) {
      window.initChatbotWidget({
        apiUrl: process.env.REACT_APP_API_ENDPOINT || 'https://your-api-endpoint.com',
        apiKey: process.env.REACT_APP_API_KEY || 'your-api-key',
        sessionId: `session_${Date.now()}`,
        widgetConfig: {
          header: { title: "AI Assistant" },
          welcome: { title: "Hello!", description: "How can I help?" }
        }
      });
      widgetInitialized.current = true;
    }
  }, []);

  return <div>{/* Your app content */}</div>;
}

export default App;
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
    userText: string;       // User message text color
    assistant: string;      // Assistant message bubble color
    assistantText?: string; // Assistant message text color (optional)
  },
  suggestedQuestions: {
    background: string;      // Suggested questions background
    text: string;           // Suggested questions text color
    highlightedBackground: string; // Suggested questions hover background
  },
  chatButton: {
    background: string;      // Chat button background
    hoverBackground: string; // Chat button hover background
    iconColor: string;       // Icon color
    iconBorderColor: string; // Icon border color
    borderColor: string;     // Button border color
    iconName: string;        // Icon name (see available icons above)
  }
}
```

### Built-in Themes

The demo includes several professional themes:
- **Default** - Orange and blue gradient (AI Assistant theme)
- **Modern** - Vibrant indigo/purple gradient
- **Minimal** - Clean gray palette  
- **Corporate** - Professional blue theme
- **Dark** - Sleek dark theme with cyan accents
- **Emerald** - Fresh green theme
- **Sunset** - Warm orange-red gradient
- **Lavender** - Elegant purple theme
- **Monochrome** - Sophisticated grayscale

Each theme includes appropriate icon selection and color coordination for a cohesive look.

## Suggested Questions Length Configuration

The widget provides flexible length controls for suggested questions:

### Display Length (`maxSuggestedQuestionLength`)
- Controls how much text is shown on the suggestion buttons
- Default: 120 characters
- Text longer than this limit will be truncated with "..."
- Example: "This is a very long question that will be truncated..." 

### Query Length (`maxSuggestedQuestionQueryLength`) 
- Controls the maximum length of the actual query sent to your API
- Default: 200 characters
- Queries longer than this limit will be truncated (no ellipsis)
- Helps prevent overly long API requests

### Usage Example

```javascript
window.initChatbotWidget({
  apiUrl: 'https://your-api-url.com',
  apiKey: 'your-api-key', 
  sessionId: 'your-session-id',
  suggestedQuestions: [
    {
      text: "Tell me about your company's history and founding story",  // 52 chars - will be truncated if maxSuggestedQuestionLength < 52
      query: "I'd like to learn about your company's history, founding story, key milestones, and how you've grown over the years"  // 127 chars - will be truncated if maxSuggestedQuestionQueryLength < 127
    }
  ],
  maxSuggestedQuestionLength: 40,    // Button shows: "Tell me about your company's histor..."
  maxSuggestedQuestionQueryLength: 100  // API receives: "I'd like to learn about your company's history, founding story, key milestones, and how you'"
});
```

## Available Icons

Choose from these chatbot and AI assistant related icons:

### Chat and Communication
- `MessageSquare` - Square message bubble (default)
- `MessageCircle` - Round message bubble  
- `MessageCircleMore` - Round message bubble with dots
- `MessageSquareText` - Square message bubble with text lines
- `MessageSquareDots` - Square message bubble with dots
- `ChatBubble` - Classic chat bubble
- `ChatBubbleLeft` - Left-aligned chat bubble
- `ChatBubbleLeftRight` - Two-way chat bubble
- `ChatBubbleLeftEllipsis` - Chat bubble with ellipsis
- `ChatBubbleLeftDots` - Chat bubble with dots
- `Send` - Send icon
- `Reply` - Reply icon

### Help and Information
- `HelpCircle` - Question mark in circle
- `QuestionMarkCircle` - Question mark in circle (alias)
- `Info` - Information icon
- `Lightbulb` - Lightbulb (ideas/help)
- `Sparkles` - Sparkles (magic/assistance)

### AI and Technology
- `Bot` - Robot icon
- `Brain` - Brain icon (AI/intelligence)
- `Cpu` - CPU chip icon
- `Chip` - Microchip icon
- `Zap` - Lightning bolt (power/energy)
- `Target` - Target icon (precision/accuracy)

### People and Users
- `User` - Single user icon
- `Users` - Multiple users icon
- `UserCheck` - User with checkmark
- `UserPlus` - User with plus sign
- `UserMinus` - User with minus sign

### Search and Discovery
- `Search` - Magnifying glass
- `SearchX` - Search with X (clear search)
- `Filter` - Filter icon

### Usage Example
```javascript
theme: {
  chatButton: {
    iconName: 'Bot',           // Use robot icon
    iconColor: '#7c3aed',      // Purple icon color
    iconBorderColor: '#e5e7eb', // Light gray border
    borderColor: '#e5e7eb'      // Button border color
  }
}
```

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
      text: string;        // Button text (truncated based on maxSuggestedQuestionLength)
      query: string;       // Question to send when clicked (truncated based on maxSuggestedQuestionQueryLength)
    }
  ],
  maxSuggestedQuestionLength?: number;      // Display length limit (default: 120)
  maxSuggestedQuestionQueryLength?: number; // Query length limit (default: 200)
  theme: { /* theme object */ }
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

## 🐛 Troubleshooting

### Common Issues

**1. Widget doesn't appear:**
```javascript
// Check if widget loaded in browser console
console.log(typeof window.initChatbotWidget); // Should not be 'undefined'

// Check for error messages in console
// Make sure CSS file is loaded in Network tab
```

**2. "Chatbot container not found" error:**
```html
<!-- Make sure CSS file is included BEFORE the widget script -->
<link rel="stylesheet" href="https://unpkg.com/@schmitech/chatbot-widget@latest/dist/chatbot-widget.css">

<!-- For embedded mode, ensure container exists -->
<div id="chatbot-container"></div>
```

**3. Widget appears but doesn't work:**
```javascript
// Verify your API configuration
{
  apiUrl: 'https://your-actual-api-url.com', // Must be a valid URL
  apiKey: 'your-actual-api-key',             // Must be valid
  sessionId: 'unique-session-id'             // Must be unique per user
}
```

**4. Styling issues:**
```css
/* If widget styling conflicts with your site */
.chatbot-widget {
  z-index: 9999 !important;
}
```

### Browser Compatibility
- ✅ Chrome 60+
- ✅ Firefox 55+
- ✅ Safari 12+
- ✅ Edge 79+
- ❌ Internet Explorer (not supported)

### Cache Issues
If changes don't appear:
```html
<!-- Add version parameter to force reload -->
<script src="https://unpkg.com/@schmitech/chatbot-widget@latest/dist/chatbot-widget.umd.js?v=1.0"></script>
<script src="chatbot-config.js?v=1.0"></script>
```

## 📱 Mobile Responsiveness

The widget automatically adapts to mobile devices:
- Floating mode: Full-screen overlay on mobile
- Embedded mode: Responsive to container size
- Touch-friendly buttons and input

## 🔧 Local Development

For testing locally:
```bash
# Simple HTTP server with Python
python -m http.server 8000

# Or with Node.js
npx http-server

# Or with PHP
php -S localhost:8000
```

Then visit `http://localhost:8000`

## Support

For help and questions:
- 📖 [Full Documentation](https://github.com/schmitech/chatbot-widget)
- 🐛 [Report Issues](https://github.com/schmitech/chatbot-widget/issues)
- 💬 [Community Discussions](https://github.com/schmitech/chatbot-widget/discussions)
- 📧 Email: info@schmitech.ai