# Chatbot Widget

A reusable chatbot widget that can be easily integrated into any website.

## Features

- Easy to integrate with a single JavaScript snippet
- Responsive design with mobile support
- Customizable appearance
- Markdown support for rich text responses
- Link detection and formatting
- Scrollable chat interface with "scroll to top" button
- Clear conversation functionality

## Building the Widget

### Prerequisites

- Node.js 18+ and npm

### Build Steps

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd qa-chatbot-server
   ```

2. Install dependencies for the API:
   ```bash
   cd api
   npm install
   npm run build
   ```

3. Build the widget:
   ```bash
   cd ../widget
   npm install
   npm run build
   npm run build:bundle
   ```

4. The built files will be in the `widget/dist` directory:
   - `chatbot-widget.bundle.js` - Single file containing both JS and CSS (recommended for direct usage)
   - `chatbot-widget.umd.js` - UMD module (if you need the JS separately)
   - `chatbot-widget.css` - Styles (if you need the CSS separately)


## Customizing the Widget
Check file demo.html containing an working example on how to customize the widget.

To run the example:

```python
python3 -m http.server 8080
```

## Deployment

1. Host the bundled file (`chatbot-widget.bundle.js`) on a CDN or your web server
2. Update the script tag in your HTML to point to the hosted file
3. Make sure your chatbot API server is accessible at the URL you provide to `initChatbotWidget`

## API Reference

### initChatbotWidget(config)

Initializes the chatbot widget with the given configuration.

#### Parameters

- `config` (object):
  - `apiUrl` (string, required): The URL of your chatbot API server
  - `containerSelector` (string, optional): CSS selector for the container where the widget should be rendered. If not specified, the widget will be appended to the body.

## Development

```bash
# Start development server
npm run dev

# Run linting
npm run lint

# Build for production
npm run build
npm run build:bundle

# Preview build
npm run preview
```

## Publishing to npm

To publish a new version of the widget:

1. Build the widget:
   ```bash
   npm run build
   ```

2. Test the package locally (optional):
   ```bash
   npm pack --dry-run
   ```

   You should see an output like this:
   npm notice 
      ```bash
      npm notice 📦 @schmitech/chatbot-widget@0.2.0
      npm notice === Tarball Contents === 
      npm notice 1.1kB  package.json
      npm notice 31.0kB dist/chatbot-widget.css
      npm notice 160.0kB dist/chatbot-widget.umd.js
      npm notice 2.1kB dist/index.d.ts
      ...
      npm notice === Tarball Details === 
      npm notice name:          @schmitech/chatbot-widget
      npm notice version:       0.2.0
      npm notice package size:  193.2 kB
      npm notice unpacked size: 1.2 MB
      npm notice shasum:        abc123...
      npm notice integrity:     sha512-...
      npm notice total files:   15
      ```

3. Update the version:
   ```bash
   npm version patch  # for bug fixes
   npm version minor  # for new features
   npm version major  # for breaking changes
   ```

4. Publish to npm:
   ```bash
   npm publish --access public
   ```

### After Publishing

The package is available on npm as `@schmitech/chatbot-widget`. The latest version is 0.2.0.

You can use it in any project:

1. Visit the package on npm:
   ```
   https://www.npmjs.com/package/@schmitech/chatbot-widget
   ```

2. Install it in any project:
   ```bash
   npm install @schmitech/chatbot-widget
   ```

3. Test the bundle in a simple HTML file:
   ```html
   <!DOCTYPE html>
   <html lang="en">
   <head>
      <meta charset="UTF-8" />
      <link rel="icon" type="image/svg+xml" href="/favicon.ico" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <title>Your Web App</title>
      <!-- Add widget CSS -->
      <link rel="stylesheet" href="https://unpkg.com/@schmitech/chatbot-widget@0.2.0/dist/chatbot-widget.css">
   </head>
   <body>
      <div id="root"></div>
      
      <!-- Widget dependencies -->
      <script src="https://unpkg.com/react@18/umd/react.production.min.js" crossorigin></script>
      <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js" crossorigin></script>
      <script src="https://unpkg.com/@schmitech/chatbot-widget@0.2.0/dist/chatbot-widget.umd.js" crossorigin></script>
   </body>
   </html>
   ```

### Importing the Bundled Version

You can import the widget in different ways:

```html
<!-- HTML - Using the full bundle (JS + CSS combined) -->
<script src="https://unpkg.com/@schmitech/chatbot-widget@0.2.0/dist/chatbot-widget.bundle.js"></script>

<!-- Using UMD version + separate CSS -->
<script src="https://unpkg.com/@schmitech/chatbot-widget@0.2.0"></script>
<link rel="stylesheet" href="https://unpkg.com/@schmitech/chatbot-widget@0.2.0/dist/chatbot-widget.css" />
```

```javascript
// ES Module - Using direct import from node_modules
import { ChatWidget } from '@schmitech/chatbot-widget';
// For the bundled version (if you're using a bundler like webpack)
import '@schmitech/chatbot-widget/bundle';
```

Using in TSX components:

```javascript
useEffect(() => {
    // Initialize the widget when component mounts
    if (typeof window !== 'undefined' && window.initChatbotWidget) {
      console.log('Initializing chatbot widget...');
      setTimeout(() => {
        try {
          window.initChatbotWidget!({
            apiUrl: import.meta.env.VITE_API_ENDPOINT,
            widgetConfig: {
              header: {
                title: "Community Services Help Center"
              },
              welcome: {
                title: "Welcome to Our Community Services!",
                description: "I can help you with information about youth programs, senior services, adult education, family services, and more."
              },
              suggestedQuestions: [
                {
                  text: "What youth programs are available?",
                  query: "Tell me about the youth programs"
                },
                {
                  text: "Senior services information",
                  query: "What services are available for seniors?"
                },
                {
                  text: "Adult education courses",
                  query: "What adult education courses do you offer?"
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
          console.log('Chatbot widget initialized successfully');
        } catch (error) {
          console.error('Failed to initialize chatbot widget:', error);
        }
      }, 1000);
    } else {
      console.error('Chatbot widget initialization function not found');
    }
  }, []);
```

### Known Limitations and Troubleshooting

#### Scrolling Behavior

The chat widget has a maximum height of 500px by default. When the conversation exceeds this height:
- A scrollbar appears to navigate through the conversation
- A "scroll to top" button appears when scrolled down more than 200px
- The widget automatically scrolls to the bottom when new messages are added
- You can clear the entire conversation by clicking the "Clear" button in the header

If you need to customize the chat container height, you can modify it using CSS variables:

```css
:root {
  --chat-container-height: 600px; /* Increase maximum height */
}
```

## License

Apache 2.0 (See LICENSE in project folder).