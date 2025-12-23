# 💬 ORBIT Chat App

A standalone chat application for ORBIT that can be installed as an npm package and run as a CLI tool. Provides a full-featured chat interface with streaming responses, file uploads, and conversation management.

---

## 🌟 Key Features

- 🚀 **CLI Tool**: Install globally and run as a command-line tool
- 📱 **Standalone App**: Full-featured chat interface served as a web application
- 🔧 **Runtime Configuration**: Configure via CLI arguments, config files, or environment variables
- 📝 **Streaming Responses**: Real-time streaming of AI responses
- 📎 **File Upload**: Upload and attach files (PDF, DOCX, TXT, CSV, JSON, HTML, images, audio)
- 💬 **Conversation Management**: Multiple conversations with persistent storage
- 🎨 **Modern UI**: Clean, responsive interface with dark mode support

---

## 🛠️ Installation

### ✅ Prerequisites
- Node.js 18+ and npm

### 📦 Setup Instructions

1. **Clone Repository**

```bash
git clone https://github.com/schmitech/orbit.git
cd orbit/clients/chat-app
```

2. **Install Dependencies**

```bash
npm install
```

3. **Build the Application**

```bash
npm run build
```

The build outputs are located in `dist/`:
- `index.html` - Main HTML file
- `assets/` - JavaScript, CSS, and other assets

---

## 🚀 Usage

### As an npm Package (CLI Tool)

**Install globally:**
```bash
npm install -g orbitchat
```

**Run the CLI:**
```bash
orbitchat
```

The app will start a server at `http://localhost:5173` by default.

**With custom configuration:**
```bash
orbitchat --api-url http://localhost:3000 --port 8080 --open
```

### CLI Options

```bash
orbitchat [options]

Options:
  --api-url URL                    API URL (default: http://localhost:3000)
  --api-key KEY                    Default API key (default: default-key)
  --use-local-api BOOLEAN          Use local API build (default: false)
  --local-api-path PATH            Path to local API
  --console-debug BOOLEAN          Enable console debug (default: false)
  --enable-upload BOOLEAN          Enable upload button (default: false)
  --enable-feedback BOOLEAN        Enable feedback buttons (default: false)
  --max-files-per-conversation N   Max files per conversation (default: 5)
  --max-file-size-mb N             Max file size in MB (default: 50)
  --max-total-files N              Max total files (default: 100, 0 = unlimited)
  --max-conversations N            Max conversations (default: 10, 0 = unlimited)
  --max-messages-per-conversation N Max messages per conversation (default: 1000, 0 = unlimited)
  --max-total-messages N           Max total messages (default: 10000, 0 = unlimited)
  --max-message-length N           Max message length (default: 1000)
  --port PORT                      Server port (default: 5173)
  --host HOST                      Server host (default: localhost)
  --open                           Open browser automatically
  --config PATH                    Path to config file (default: ~/.orbit-chat-app/config.json)
  --help, -h                       Show help message
```

### Configuration File

Create a config file at `~/.orbit-chat-app/config.json`:

```json
{
  "apiUrl": "http://localhost:3000",
  "defaultKey": "default-key",
  "port": 5173,
  "host": "localhost",
  "enableUploadButton": false,
  "enableFeedbackButtons": false,
  "maxFilesPerConversation": 5,
  "maxFileSizeMB": 50,
  "maxTotalFiles": 100,
  "maxConversations": 10,
  "maxMessagesPerConversation": 1000,
  "maxTotalMessages": 10000,
  "maxMessageLength": 1000
}
```

**Note:** GitHub stats and GitHub owner/repo are always shown and default to "schmitech/orbit". These are only configurable via build-time environment variables (`VITE_SHOW_GITHUB_STATS`, `VITE_GITHUB_OWNER`, `VITE_GITHUB_REPO`) for developers who fork the repository and build their own version.

### Configuration Priority

Configuration is loaded in the following priority order:
1. CLI arguments (highest priority)
2. Config file (`~/.orbit-chat-app/config.json`)
3. Environment variables (`VITE_*`)
4. Default values (lowest priority)

### 🔐 API Key Middleware (Adapter Proxy)

The CLI can run an Express middleware layer that injects API keys server-side so browsers only see adapter names.

1. **Create `adapters.yaml`** – the server loads the first file it finds from:
   - `<orbitchat install>/adapters.yaml` (next to `bin/orbitchat.js`)
   - The current working directory
   - `~/.orbit-chat-app/adapters.yaml`

   ```yaml
   adapters:
     local-dev:
       apiKey: orbit_dev_key
       apiUrl: http://localhost:3000
     production:
       apiKey: orbit_prod_key
       apiUrl: https://api.example.com
   ```

2. **Enable the proxy** – pass `--enable-api-middleware` or export `VITE_ENABLE_API_MIDDLEWARE=true` before running `orbitchat`. The Express server exposes:
   - `GET /api/adapters` – returns adapter names/URLs for the dropdown
   - `/api/*` – forwards chat, file, thread, and admin calls while injecting the adapter's real `X-API-Key`

3. **Client experience** – once enabled, the UI hides the API-key modal, shows an Adapter Selector, and routes every request through `/api/...` using an `X-Adapter-Name` header. Conversations remember adapter names instead of keys.

4. **Deployment checklist**
   - Keep `adapters.yaml` out of source control; treat it like secrets.
   - Provide HTTPS in front of the CLI (or run behind an existing reverse proxy).
   - Set `VITE_ENABLE_API_MIDDLEWARE=true` everywhere you build/run the CLI so runtime config matches server behaviour.
   - Verify `/api/adapters` works before inviting end users; the request should never include API keys.

---

## 🧑‍💻 Development

### Local Development Setup

**Start development server:**
```bash
npm run dev
```

**Start with local API build:**
```bash
npm run dev:local
```

**Build API and start dev server:**
```bash
npm run dev:with-api
```

### Using Local API Build

For local development, you can use the local API build instead of the npm package:

**Option 1: Use the convenience script** (recommended):
```bash
npm run dev:with-api
```
This script automatically:
1. Builds the API from `../node-api`
2. Copies the built files to `src/api/local/`
3. Starts the dev server with local API enabled

**Option 2: Manual setup**:
```bash
# Build and copy API files
npm run build:api

# Start dev server with local API
npm run dev:local
```

**Option 3: Build API separately**:
```bash
# From node-api directory
cd ../node-api
npm run build

# Then start chat-app
cd ../chat-app
npm run dev:local
```

The local API files will be copied to `src/api/local/` directory. When `VITE_USE_LOCAL_API=true` is set, the app will load `./local/api.mjs` from the src directory instead of the npm package.

### Development Commands

```bash
# Development server (uses npm package)
npm run dev

# Development server with local API
npm run dev:local

# Build API and start dev server
npm run dev:with-api

# Code linting
npm run lint

# Production builds
npm run build              # Build with npm package
npm run build:local       # Build with local API

# Preview build
npm run preview            # Preview with npm package
npm run preview:local      # Preview with local API
```

---

## 📤 Publish to npm

### Build Package

**Build for production:**
```bash
npm run build
```

The `prepublishOnly` script will automatically run `npm run build` before publishing.

### Test Locally (Optional)

**Test package contents:**
```bash
npm pack --dry-run
```

**Test installation locally:**
```bash
npm pack
npm install -g ./orbitchat-1.0.0.tgz
orbitchat --help
```

### Update Version

**Update version:**
```bash
npm version [patch|minor|major]
```

This will:
- Update `package.json` version
- Create a git tag
- Commit the changes

### Publish

**Publish to npm:**
```bash
npm publish --access public
```

**Note:** Make sure you're logged in to npm:
```bash
npm login
```

Package URL: [orbitchat](https://www.npmjs.com/package/orbitchat)

---

## 🔧 Configuration

### Environment Variables (Development)

For local development, create a `.env.local` file:

```bash
VITE_API_URL=http://localhost:3000
VITE_DEFAULT_KEY=default-key
VITE_USE_LOCAL_API=true
VITE_LOCAL_API_PATH=./local/api.mjs
VITE_CONSOLE_DEBUG=false
VITE_ENABLE_UPLOAD=false
VITE_ENABLE_FEEDBACK=false
VITE_SHOW_GITHUB_STATS=true
VITE_GITHUB_OWNER=schmitech
VITE_GITHUB_REPO=orbit
VITE_MAX_FILES_PER_CONVERSATION=5
VITE_MAX_FILE_SIZE_MB=50
VITE_MAX_TOTAL_FILES=100
VITE_MAX_CONVERSATIONS=10
VITE_MAX_MESSAGES_PER_CONVERSATION=1000
VITE_MAX_MESSAGES_PER_THREAD=1000
VITE_MAX_TOTAL_MESSAGES=10000
VITE_MAX_MESSAGE_LENGTH=1000
```

### Build-Time Configuration (For Forkers)

If you fork the repository and want to customize GitHub stats/owner/repo, set these environment variables before building:

```bash
VITE_SHOW_GITHUB_STATS=true
VITE_GITHUB_OWNER=your-username
VITE_GITHUB_REPO=your-repo
npm run build
```

---

## 📋 Features

### Streaming Responses
- Real-time streaming of AI responses
- Regenerate responses with a single click
- Copy responses to clipboard

### File Upload
- Upload and attach files to conversations
- Supported formats: PDF, DOCX, TXT, CSV, JSON, HTML, Markdown, images (PNG, JPEG, TIFF), audio (WAV, MP3)
- Files are automatically processed and indexed
- File context is included in chat messages

### Conversation Management
- Multiple conversations with persistent storage
- Edit conversation titles
- Delete individual conversations
- Clear all conversations
- Conversation limits (configurable)

### UI Features
- Dark mode support
- Responsive design
- Settings panel
- GitHub stats display (configurable for forkers)
- Feedback buttons (configurable)

---

## ⚠️ Known Issues & Troubleshooting

### Local API Not Loading

If you see a 404 error for `api.mjs`:

1. **Ensure API is built:**
   ```bash
   cd ../node-api
   npm run build
   ```

2. **Copy files to src/api/local directory:**
   ```bash
   mkdir -p ../chat-app/src/api/local
   cp dist/api.mjs ../chat-app/src/api/local/api.mjs
   cp dist/api.mjs.map ../chat-app/src/api/local/api.mjs.map
   cp dist/api.d.ts ../chat-app/src/api/local/api.d.ts
   ```

3. **Restart dev server with local API enabled:**
   ```bash
   npm run dev:local
   ```

4. **Check environment variable:**
   - Ensure `VITE_USE_LOCAL_API=true` is set (or use `npm run dev:local`)
   - The default path `./local/api.mjs` should work if files are in `src/api/local/`

### File Upload Issues

- **File size exceeded**: Check file size (max 50MB by default)
- **Unsupported format**: Verify file type is in supported list
- **Upload fails**: Check server logs and API key configuration
- **Processing fails**: Ensure file processing service is initialized on server

### CLI Issues

- **Command not found**: Make sure package is installed globally (`npm install -g orbitchat`)
- **dist directory not found**: Run `npm run build` first
- **Port already in use**: Use `--port` option to specify a different port

### Debug Mode

Enable debug logging by setting:
```bash
VITE_CONSOLE_DEBUG=true
```

Or via CLI:
```bash
orbitchat --console-debug true
```

This will show detailed API loading and file upload information in the console.

---

## 📃 License

Apache 2.0 License - See [LICENSE](../../LICENSE).

---

## 🔗 Related Packages

- [@schmitech/chatbot-api](https://www.npmjs.com/package/@schmitech/chatbot-api) - Core API package
- [@schmitech/chatbot-widget](https://www.npmjs.com/package/@schmitech/chatbot-widget) - Embeddable widget
- [@schmitech/markdown-renderer](https://www.npmjs.com/package/@schmitech/markdown-renderer) - Markdown rendering
