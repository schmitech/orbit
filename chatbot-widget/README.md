# React Chatbot Widget

A customizable, draggable chatbot widget for React applications with TypeScript support.

## Features

- 🎨 Fully customizable theme and appearance
- 🔄 Draggable chat window
- 📱 Responsive design
- 💅 Modern UI with smooth animations
- 🔒 TypeScript support
- 🎯 Zero external dependencies (besides React)

## Installation

```bash
npm install @yourusername/react-chatbot-widget
```

## Quick Start

```tsx
import { ChatbotWidget } from './components/ChatbotWidget';
import { useChatStore } from './store/chatStore';

// Configure your chatbot
const config = {
  theme: {
    primaryColor: '#0066cc',
    size: 'medium', // 'small' | 'medium' | 'large'
    font: 'Inter, sans-serif'
  },
  messages: {
    greeting: 'Hi there! 👋 How can I assist you today?'
  },
  position: {
    bottom: 20,
    right: 20
  },
  dimensions: {
    width: 350,
    height: 500
  },
  api: {
    endpoint: 'http://localhost:3001' // Your chatbot API endpoint
  }
};

function App() {
  const setConfig = useChatStore((state) => state.setConfig);

  useEffect(() => {
    setConfig(config);
  }, []);

  return <ChatbotWidget />;
}
```

## Configuration Options

### Theme Configuration

```typescript
interface ThemeConfig {
  primaryColor?: string;        // Primary color for buttons and headers
  size?: 'small' | 'medium' | 'large'; // Widget size
  font?: string;               // Custom font family
}
```

### Message Configuration

```typescript
interface MessageConfig {
  greeting?: string;           // Initial greeting message
}
```

### Position Configuration

```typescript
interface PositionConfig {
  bottom?: number;            // Distance from bottom (px)
  right?: number;            // Distance from right (px)
}
```

### Dimension Configuration

```typescript
interface DimensionConfig {
  width?: number;             // Chat window width (px)
  height?: number;            // Chat window height (px)
}
```

### API Configuration

```typescript
interface ApiConfig {
  endpoint: string;           // Chatbot API endpoint URL
}
```

## Customization Examples

### Custom Theme

```tsx
const config = {
  theme: {
    primaryColor: '#FF5733',
    size: 'large',
    font: 'Poppins, sans-serif'
  }
};
```

### Custom Position

```tsx
const config = {
  position: {
    bottom: 40,
    right: 40
  }
};
```

### Custom Dimensions

```tsx
const config = {
  dimensions: {
    width: 400,
    height: 600
  }
};
```

### Custom API Endpoint

```tsx
const config = {
  api: {
    endpoint: 'https://api.yourdomain.com/chatbot'
  }
};
```

## Message Handling

To handle messages programmatically, you can use the `useChatStore` hook:

```tsx
const { addMessage } = useChatStore();

// Add a user message
addMessage({
  content: 'Hello!',
  sender: 'user'
});

// Add a bot message
addMessage({
  content: 'Hi there!',
  sender: 'bot'
});
```

## TypeScript Support

The widget comes with full TypeScript support. All configuration options and message types are properly typed:

```typescript
interface ChatbotConfig {
  theme?: ThemeConfig;
  messages?: MessageConfig;
  position?: PositionConfig;
  dimensions?: DimensionConfig;
  api: ApiConfig;
}
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT