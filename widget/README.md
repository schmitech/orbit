# Chatbot Widget

A reusable chatbot widget that can be easily integrated into any website.

## Features

- Easy to integrate with a single JavaScript snippet
- Responsive design with mobile support
- Customizable appearance
- Markdown support for rich text responses
- Link detection and formatting

## Building the Widget

### Prerequisites

- Node.js 16+ and npm

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
   npx vite build
   ```

4. The built files will be in the `widget/dist` directory:
   - `chatbot-widget.es.js` - ES module
   - `chatbot-widget.umd.js` - UMD module
   - `style.css` - Styles for the widget

## Usage

### Using npm

1. Install the package:
   ```bash
   npm install chatbot-widget
   ```

2. Import in your application:
   ```javascript
   import { ChatWidget } from 'chatbot-widget';
   import 'chatbot-widget/style.css';
   
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

### Using direct script tags

Add the following code to your website's HTML:

```html
<!-- Include React and ReactDOM first -->
<script src="https://unpkg.com/react@18/umd/react.production.min.js" crossorigin></script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js" crossorigin></script>
<!-- Include the widget -->
<script src="path/to/chatbot-widget.umd.js"></script>
<link rel="stylesheet" href="path/to/style.css">

<script>
  // Initialize the widget when the page loads
  window.addEventListener('load', function() {
    window.initChatbotWidget({
      apiUrl: 'https://your-api-server.com'
    });
  });
</script>
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

## Testing the Widget

After building, you can test the widget using the included demo page:

1. Make sure your API server is running at `http://localhost:3000` (or update the URL in demo.html)
2. Build the widget: `npx vite build`
3. Serve the files locally:
   ```bash
   # Use a static file server
   npx serve .
   # Then navigate to http://localhost:3000/public/demo.html
   ```
   
   Or open the demo file directly (may not work with all browsers due to CORS):
   ```bash
   # On macOS
   open public/demo.html
   
   # On Linux
   xdg-open public/demo.html
   
   # On Windows
   start public/demo.html
   ```
4. You should see a chat icon in the bottom right corner - click it to open the chat
5. If you encounter any errors:
   - Check the browser console for error messages
   - Make sure React and ReactDOM are properly loaded
   - Verify your API server is running and accessible

## Deployment

1. Host the built files (`chatbot-widget.umd.js`, `chatbot-widget.es.js`, and `style.css`) on a CDN or your web server
2. Update the script and link tags in your HTML to point to the hosted files
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
npx vite build

# Preview build
npm run preview
```

## License

Apache 2.0 (See LICENSE in project folder).