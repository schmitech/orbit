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

1. Build the widget and create the bundle:
   ```bash
   npm run build
   npm run build:bundle
   ```

2. Login to npm with your account:
   ```bash
   npm login
   ```

3. Publish the package (if you're publishing for the first time, or updating the version):
   ```bash
   npm publish --access public
   ```

4. To update an existing package, first update the version in package.json, then run:
   ```bash
   npm version patch # or minor or major
   npm publish --access public
   ```

### After Publishing

The package has been successfully published to npm as `@schmitech/chatbot-widget` version 0.1.0!

You can now use it in any project:

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
   <html>
   <head>
     <title>Chatbot Widget Test</title>
   </head>
   <body>
     <script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
     <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
     <script src="https://unpkg.com/@schmitech/chatbot-widget@0.1.0/dist/chatbot-widget.bundle.js"></script>
     <script>
       window.addEventListener('load', function() {
         window.initChatbotWidget({
           apiUrl: 'https://your-api-server.com'
         });
       });
     </script>
   </body>
   </html>
   ```

4. Verify the files in an existing installation:
   ```bash
   ls -la node_modules/@schmitech/chatbot-widget/dist
   ```
   
   You should see these files:
   - `chatbot-widget.bundle.js` - The bundled JS+CSS file
   - `chatbot-widget.umd.js` - The UMD module 
   - `chatbot-widget.css` - The CSS file

### Troubleshooting npm Publishing

If you encounter issues publishing to npm, check the following:

1. **Package Not Found (404)**
   - Confirm you've successfully completed the `npm publish --access public` command
   - Ensure there were no errors during publishing
   - Wait a few minutes as npm registry might take time to update

2. **Authentication Issues**
   - Make sure you're logged in with `npm login`
   - Verify your account has permission to publish

3. **Name Already Taken**
   - If the package name is already taken, modify the name in package.json
   - Use a more specific scoped name like `@your-username/chatbot-widget`

4. **Local Testing Before Publishing**
   - To test locally before publishing, use Option 1 or 2 described above

### Importing the Bundled Version

After publishing, users can import your bundled widget in different ways:

```html
<!-- HTML - Using the full bundle (JS + CSS combined) -->
<script src="https://unpkg.com/@schmitech/chatbot-widget/dist/chatbot-widget.bundle.js"></script>

<!-- Using UMD version + separate CSS -->
<script src="https://unpkg.com/@schmitech/chatbot-widget"></script>
<link rel="stylesheet" href="https://unpkg.com/@schmitech/chatbot-widget/dist/chatbot-widget.css" />
```

```javascript
// ES Module - Using direct import from node_modules
import { ChatWidget } from '@schmitech/chatbot-widget';
// For the bundled version (if you're using a bundler like webpack)
import '@schmitech/chatbot-widget/bundle';
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