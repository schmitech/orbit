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

## Usage

### Using direct script tags

Add the following code to your website's HTML:

```html
<!-- Include React and ReactDOM first -->
<script src="https://unpkg.com/react@18/umd/react.production.min.js" crossorigin></script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js" crossorigin></script>
<!-- Include the bundled widget -->
<script src="path/to/chatbot-widget.bundle.js"></script>

<script>
  // Initialize the widget when the page loads
  window.addEventListener('load', function() {
    window.initChatbotWidget({
      apiUrl: 'https://your-api-server.com'
    });
  });
</script>
```

### Using npm

1. Install the package:
   ```bash
   npm install chatbot-widget
   ```

2. Import in your application:
   ```javascript
   import { ChatWidget } from 'chatbot-widget';
   
   // Use in your React component
   function App() {
     return (
       <div className="App">
         <ChatWidget />
       </div>
     );
   }
   
   // Set API URL via the exposed function
   window.ChatbotWidget.setApiUrl('https://your-api-server.com');
   ```

### Advanced Usage

You can customize the widget by specifying a container:

```html
<div id="my-chat-container"></div>

<script>
  window.addEventListener('load', function() {
    window.initChatbotWidget({
      apiUrl: 'https://your-api-server.com',
      containerSelector: '#my-chat-container'
    });
  });
</script>
```

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

### Option 1: Using npm link (for local development)

To use this widget in other projects on your local machine during development:

1. In this widget directory, run:
   ```bash
   npm run build
   npm run build:bundle
   npm link
   ```

2. In your project directory, run:
   ```bash
   npm link chatbot-widget
   ```

3. Now you can import and use the widget in your project:
   ```javascript
   import { ChatWidget } from 'chatbot-widget';
   ```

### Option 2: Installing from a local directory

You can also install the package directly from the local directory:

1. In this widget directory, run:
   ```bash
   npm run build
   npm run build:bundle
   ```

2. In your project directory, run:
   ```bash
   npm install /path/to/qa-chatbot-server/widget
   ```

3. Now you can import and use the widget in your project:
   ```javascript
   import { ChatWidget } from 'chatbot-widget';
   ```

### Option 3: Publishing to npm (for production)

To make this widget available to anyone via npm:

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

### Option 4: Using via CDN (for websites)

You can include the widget directly in your website using jsDelivr CDN:

```html
<!-- For ESM (modern browsers) -->
<script type="module">
  import { ChatWidget } from 'https://cdn.jsdelivr.net/npm/@schmitech/chatbot-widget@0.1.0/dist/chatbot-widget.es.js';
  
  // Use the widget in your React component
  function App() {
    return (
      <div className="App">
        <ChatWidget />
      </div>
    );
  }
</script>
```

For production use, you can omit the version to always get the latest:

```html
<script type="module">
  import { ChatWidget } from 'https://cdn.jsdelivr.net/npm/@schmitech/chatbot-widget/dist/chatbot-widget.es.js';
  // ...
</script>
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