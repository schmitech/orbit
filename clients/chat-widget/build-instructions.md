# 💬 Chatbot Widget

A simple, reusable chatbot widget seamlessly integrated into any website with minimal effort.

---

## 🌟 Key Features

- 🚀 **Quick Integration:** One-line JavaScript integration
- 📱 **Responsive Design:** Mobile-friendly and adaptive layout
- 🎨 **Customizable Appearance:** Easy theme adjustments
- 📝 **Rich Text:** Supports Markdown and automatic link formatting
- 🖱️ **User-Friendly UI:** Scrollable conversation view with "scroll to top" shortcut
- 🧹 **Clear Conversation:** Reset chat with a single click

---

## 🛠️ Installation

### ✅ Prerequisites
- Node.js 18+ and npm

### 📦 Setup Instructions

1. **Clone Repository**

```bash
git https://github.com/schmitech/orbit.git
cd orbit/widget
```

2. **Install & Build API**

```bash
cd api
npm install
npm run build
```

3. **Install & Build Widget**

```bash
cd ../widget
npm install
npm run build
npm run build:bundle
```

The build outputs are located in `widget/dist`:
- `chatbot-widget.bundle.js` (JS + CSS combined, recommended)
- `chatbot-widget.umd.js` (JS only, UMD)
- `chatbot-widget.css` (CSS only)

---

## 🎨 Customization

### Using the Theming App

The easiest way to customize your widget is through our interactive theming application:

1. **Navigate to the theming app:**
```bash
cd theming-app
npm install
npm run dev
```

2. **Open in browser:** Navigate to `http://localhost:5173`

3. **Customize your widget:**
   - Choose from 9 pre-built themes (Nebula, Ocean, Evergreen, etc.)
   - Adjust colors for header, buttons, text, and backgrounds
   - Customize suggested questions and welcome messages
   - Set your API key and endpoint
   - Export the final configuration as HTML or JavaScript

4. **Live preview:** See changes in real-time as you customize

---

## 🚢 Deployment

1. Host `chatbot-widget.bundle.js` on a CDN or server.
2. Update your HTML with the script reference.
3. Ensure your chatbot API URL is accessible.

---

## ⚙️ Widget API Reference

### `initChatbotWidget(config)`
Initializes widget configuration.

| Parameter | Description | Required |
|-----------|-------------|----------|
| `apiUrl` | URL of chatbot API | ✅ Yes |
| `apiKey` | API key for authentication | ✅ Yes |
| `sessionId` | Unique session identifier | ✅ Yes |
| `containerSelector` | CSS selector for widget container | ❌ No (Defaults to body) |
| `widgetConfig` | Widget appearance and behavior configuration | ❌ No |
| `widgetConfig.maxSuggestedQuestionLength` | Max display length for suggested questions (default: 50) | ❌ No |
| `widgetConfig.maxSuggestedQuestionQueryLength` | Max query length sent to API (default: 200) | ❌ No |

Example configuration:
```javascript
initChatbotWidget({
  apiUrl: 'https://your-api-url.com',
  apiKey: 'your-api-key',
  sessionId: 'unique-session-id',
  containerSelector: '#chat-container',
  widgetConfig: {
    header: { title: "Support Chat" },
    welcome: { 
      title: "How can we help?",
      description: "Ask us anything!"
    },
    suggestedQuestions: [
      {
        text: "I need help with my account",
        query: "Can you help me with account-related questions?"
      }
    ],
    maxSuggestedQuestionLength: 60,      // Custom display length
    maxSuggestedQuestionQueryLength: 300, // Custom query length
    theme: {
      primary: '#2563eb',
      secondary: '#3b82f6'
    }
  }
});
```

---

## 🧑‍💻 Development Commands

```bash
# Development server
npm run dev

# Code linting
npm run lint

# Production builds
npm run build
npm run build:bundle

# Preview build
npm run preview
```

---

## 📤 Publish to npm

**Build package:**

```bash
npm run build
```

**Test locally (optional):**

```bash
npm pack --dry-run
```

**Update version:**

```bash
npm version [patch|minor|major]
```

**Publish:**

```bash
npm publish --access public
```

Package URL: [@schmitech/chatbot-widget](https://www.npmjs.com/package/@schmitech/chatbot-widget)

---

## 🔗 Usage Examples

### HTML Integration

**Full bundle:**
```html
<script src="https://unpkg.com/@schmitech/chatbot-widget@0.2.0/dist/chatbot-widget.bundle.js"></script>
```

**UMD + CSS separately:**
```html
<script src="https://unpkg.com/@schmitech/chatbot-widget@0.4.4"></script>
<link rel="stylesheet" href="https://unpkg.com/@schmitech/chatbot-widget@0.4.4/dist/chatbot-widget.css">
```

### JavaScript/TypeScript

```javascript
import { ChatWidget } from '@schmitech/chatbot-widget';
import '@schmitech/chatbot-widget/bundle';
```

**React/TSX example:**
```tsx
useEffect(() => {
  if (typeof window !== 'undefined' && window.initChatbotWidget) {
    window.initChatbotWidget({
      apiUrl: import.meta.env.VITE_API_ENDPOINT,
      apiKey: import.meta.env.VITE_API_KEY,
      widgetConfig: { /* widget configurations */ }
    });
  }
}, []);
```

---

## ⚠️ Known Issues & Troubleshooting

### **Scrolling behavior:**

By default, widget height is `500px`. Customize with CSS:

```css
:root {
  --chat-container-height: 600px;
}
```

- Scrollbar auto-appears with long content
- "Scroll to top" button shows after scrolling `200px`
- Auto-scroll to bottom on new messages
- Clear conversations easily from the header

---

## 📃 License

Apache 2.0 License - See [LICENSE](LICENSE).