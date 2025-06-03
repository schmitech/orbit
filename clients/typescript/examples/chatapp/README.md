# ORBIT Chatapp

# Requisites ⚙️

To use the web interface, these requisites must be met:

1. Have access to an ORBIT API endpoint
2. [Node.js](https://nodejs.org/en/download) (18+) and [yarn](https://classic.yarnpkg.com/lang/en/docs/install/#mac-stable) is required.

# Usage 🚀

## Environment Configuration

Create a `.env.local` file in the root directory with your ORBIT API configuration:

```
NEXT_PUBLIC_API_URL=http://localhost:3000
NEXT_PUBLIC_API_KEY=your-api-key-here
```

You can also configure these settings directly in the application through the settings panel in the left sidebar.

# Development 📖

To install and run a local environment of the web interface, follow the instructions below.

1. **Install dependencies:**

   ```
   yarn install
   ```

2. **Start the development server:**

   ```
   yarn dev
   ```
   
   Or on a specific port:
   ```
   yarn dev -p 3001
   ```

3. **Go to [localhost:3000](http://localhost:3000) (or your specified port) and start chatting!**

   - Configure your API settings in the left sidebar settings panel
   - Click "New chat" to start a fresh conversation with a new session ID
   - Start a conversation and enjoy streaming responses

# Key Features Explained

## Session Management
- **Persistent Sessions:** Each app instance maintains a session ID throughout its lifetime
- **New Chat Button:** Creates a completely new session ID and resets backend conversation history
- **Session Tracking:** Current session ID visible in the chat topbar for transparency
- **Backend Integration:** Session IDs are passed to the ORBIT API for conversation continuity

## Chat History
- **Backend Storage:** All chat history is stored and managed by the ORBIT API backend
- **Session-Based:** Conversations are tied to session IDs for proper context management
- **No Local Storage:** No chat data is stored locally - everything is managed server-side
- **Fresh Starts:** New chat sessions completely reset conversation context

# Troubleshooting

## Common Issues

**API not configured:** 
- Check that your ORBIT API endpoint is running and accessible
- Verify your API URL and key in the settings panel
- Check browser console for connection errors

**Messages not loading:**
- Ensure your session ID is properly configured (visible in topbar)
- Try clicking "New chat" to reset the session
- Check that the ORBIT API backend is responding to requests

**Styling issues:**
- Clear browser cache and reload
- Check that TailwindCSS is properly compiled
- Verify theme settings in the sidebar

Make sure your ORBIT inference server is running and accessible at the configured URL before starting conversations.
