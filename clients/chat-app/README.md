# ORBIT Chat App

A standalone chat application for ORBIT that can be installed as an npm package and run as a CLI tool. Integrates with the `@schmitech/chatbot-api` package for real-time streaming chat responses and file upload capabilities.

## Installation

### As an npm Package (CLI Tool)

Install globally:
```bash
npm install -g orbitchat
```

Or install locally:
```bash
npm install orbitchat
```

## Usage

### CLI Tool

After installing globally, run:
```bash
orbitchat
```

The app will start a server at `http://localhost:5173` by default.

#### CLI Options

```bash
orbitchat [options]

Options:
  --api-url URL                    API URL (default: http://localhost:3000)
  --default-adapter NAME           Default adapter to preselect when middleware is enabled
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

#### Examples

```bash
# Start with custom API URL and port
orbitchat --api-url http://localhost:3000 --port 8080

# Start with API key and open browser
orbitchat --api-key my-key --open

# Start with custom config file
orbitchat --config /path/to/config.json
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

### Configuration Priority

Configuration is loaded in the following priority order:
1. CLI arguments (highest priority)
2. Config file (`~/.orbit-chat-app/config.json`)
3. Environment variables (`VITE_*`)
4. Default values (lowest priority)

**Note:** GitHub stats and GitHub owner/repo are always shown and default to "schmitech/orbit". These are only configurable via build-time environment variables (`VITE_SHOW_GITHUB_STATS`, `VITE_GITHUB_OWNER`, `VITE_GITHUB_REPO`) for developers who fork the repository and build their own version.

### Protect API Keys with the Middleware Proxy

You can prevent API keys from ever reaching the browser by enabling the built-in middleware layer:

1. Create an `adapters.yaml` file (next to `bin/orbitchat.js`, in your working directory, or in `~/.orbit-chat-app/`). Example:
   ```yaml
   adapters:
     local-dev:
       apiKey: orbit_dev_key
       apiUrl: http://localhost:3000
     production:
       apiKey: orbit_prod_key
       apiUrl: https://api.example.com
   ```
2. Start the CLI with `--enable-api-middleware` (or export `VITE_ENABLE_API_MIDDLEWARE=true`). The Express server now:
   - Serves `GET /api/adapters` so the React app can list safe adapter names.
   - Proxies all chat/file/thread/admin calls through `/api/...`, injecting the adapter's real `X-API-Key`.
3. The UI automatically swaps the API-key modal for an Adapter Selector and stores adapter names per conversation.

Keep `adapters.yaml` out of source control and run the CLI behind HTTPS (or another reverse proxy) when deploying.

### Environment Variables

You can also set configuration via environment variables (for development):

```bash
VITE_API_URL=http://localhost:3000
VITE_DEFAULT_KEY=default-key
VITE_ENABLE_UPLOAD=false
VITE_CONSOLE_DEBUG=false
# ... etc

`VITE_DEFAULT_KEY` is dual-purpose:
- When **middleware is disabled**, it should contain the literal API key that the frontend will send to the backend (same as before).
- When **middleware is enabled**, set it to the adapter name you want preselected (or pass `--default-adapter`). If you leave it as `default-key` or empty, the app automatically falls back to the first adapter defined in `VITE_ADAPTERS`/`ORBIT_ADAPTERS`.
```

## Development

### Local Development Setup

For local development, clone the repository and install dependencies:

```bash
npm install
npm run dev
```

## Configuration

The application supports multiple ways to configure the API:

### 1. Environment Variables (Vite)
Create a `.env.local` file in the root directory:

```bash
VITE_API_URL=https://your-api-endpoint.com
VITE_DEFAULT_KEY=default-key      # API key in direct mode, or adapter name in middleware mode
VITE_USE_LOCAL_API=true          # Set to 'true' to use local API build
VITE_LOCAL_API_PATH=/api.mjs      # Path to local API (defaults to /api.mjs from public directory)
VITE_CONSOLE_DEBUG=false          # Enable debug logging
```

### 2. Window Variables
Set global variables in your HTML or before the app loads:

```javascript
window.CHATBOT_API_URL = 'https://your-api-endpoint.com';
window.CHATBOT_API_KEY = 'your-api-key-here';
```

### 3. Runtime Configuration
Use the "Configure API" button in the chat interface to set the API URL and key at runtime.

## Local Development Setup

### Using Local API Build

For local development, you can use the local API build instead of the npm package:

**Option 1: Use the convenience script** (recommended):
```bash
npm run dev:with-api
```
This script automatically:
1. Builds the API from `../node-api`
2. Copies the built files to `public/api.mjs`
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
npm run build:chat-app

# Then start chat-app
cd ../chat-app
npm run dev:local
```

The local API files will be copied to `src/api/local/` directory. When `VITE_USE_LOCAL_API=true` is set, the app will load `./local/api.mjs` from the src directory instead of the npm package.

## Features

- **Streaming Responses**: Real-time streaming of AI responses
- **File Upload**: Upload and attach files (PDF, DOCX, TXT, CSV, JSON, HTML, images, audio) to conversations
- **File Context**: Query uploaded files and include them in chat context
- **Session Management**: Automatic session ID generation and persistence
- **Error Handling**: Comprehensive error handling with user-friendly messages
- **Conversation Persistence**: Chat history is saved to localStorage
- **API Configuration**: Flexible API configuration options

## Security

- When **API middleware** is enabled, the browser never sees your real API keys. The CLI proxy serves `/api/adapters` with adapter names only and injects the real `X-API-Key` on the server before calling the backend. Keep `ORBIT_ADAPTERS` / `VITE_ADAPTERS` on the server (out of git) and run the proxy behind HTTPS so users cannot intercept traffic.
- Even though the app falls back to the first adapter in `VITE_ADAPTERS`, the adapters list itself is still server-side; clients only learn the names you expose. Someone would need filesystem or shell access to the machine running `bin/orbitchat.js` to read the adapters config and extract the real keys.
- In direct mode (middleware disabled), the browser stores API keys locally to send them with requests—treat that mode as developer-only unless you’re comfortable distributing the key to end users.
- Regardless of mode, secure the host running the CLI and restrict who can reach it; a compromised host or misconfigured reverse proxy can leak the adapters file or intercept proxied traffic.

## Usage

### Basic Chat

1. Configure your API settings using one of the methods above
2. Start a conversation by typing a message
3. The AI will respond with streaming text
4. Use the regenerate button (↻) to regenerate responses
5. Use the copy button to copy AI responses to clipboard

### File Upload

1. Click the paperclip icon (📎) in the message input
2. Upload files using drag-and-drop or file picker
3. Supported formats: PDF, DOCX, TXT, CSV, JSON, HTML, Markdown, images (PNG, JPEG, TIFF), audio (WAV, MP3, MP4, OGG, FLAC, WebM, M4A, AAC)
4. Files are automatically processed and indexed
5. Attach files to messages - they will be included in the chat context
6. Files are chunked and stored in the vector store for semantic search

**File Upload Flow**:
- Upload files using the file upload UI
- Files are processed on the server (extraction, chunking, embedding)
- File IDs are automatically included with your messages
- The AI can query and reference uploaded files in responses

## File Upload Details

### Supported File Types

| Type | Formats | Processing |
|------|---------|------------|
| Documents | PDF, DOCX, PPTX, XLSX | Text extraction, chunking, vector indexing |
| Text | TXT, MD, HTML | Direct chunking and indexing |
| Data | CSV, Parquet | DuckDB integration or vector store |
| Images | PNG, JPEG, TIFF | OCR via vision service |
| Audio | WAV, MP3, MP4, OGG, FLAC, WebM, M4A, AAC | ASR (Automatic Speech Recognition) via audio transcription |

### File Size Limits

- Maximum file size: 50MB
- Maximum files per conversation: 5 (configurable)

### File Processing

Files are processed through the following pipeline:
1. **Upload**: File uploaded via `/api/files/upload`
2. **Validation**: File type and size validation
3. **Storage**: File saved to filesystem (or S3 in production)
4. **Extraction**: Text and metadata extracted using format-specific processors
5. **Chunking**: Content chunked using configured strategy (fixed or semantic)
6. **Indexing**: Chunks indexed in vector store for semantic search
7. **Metadata**: Processing status tracked in SQLite

## Available Scripts

- `npm run dev` - Start dev server (uses npm package)
- `npm run dev:local` - Start dev server with local API enabled
- `npm run dev:with-api` - Build API and start dev server with local API
- `npm run build` - Build for production (uses npm package)
- `npm run build:local` - Build for production with local API
- `npm run build:api` - Build API and copy to public directory
- `npm run preview` - Preview production build
- `npm run preview:local` - Preview production build with local API

## Integration Details

The integration uses:
- **Zustand** for state management (replacing React Context)
- **@schmitech/chatbot-api** for streaming chat functionality and file operations
- **localStorage** for persistent session and conversation storage
- **TypeScript** for type safety throughout the integration
- **File Upload Service** for handling file uploads with progress tracking
- **Vector Store** for semantic search over uploaded file content

## Troubleshooting

### Local API Not Loading

If you see a 404 error for `api.mjs`:

1. **Ensure API is built**:
   ```bash
   cd ../node-api
   npm run build
   ```

2. **Copy files to src/api/local directory**:
   ```bash
   mkdir -p ../chat-app/src/api/local
   cp dist/api.mjs ../chat-app/src/api/local/api.mjs
   cp dist/api.d.ts ../chat-app/src/api/local/api.d.ts
   ```

3. **Restart dev server with local API enabled**:
   ```bash
   npm run dev:local
   ```

4. **Check environment variable**:
   - Ensure `VITE_USE_LOCAL_API=true` is set (or use `npm run dev:local`)
   - The default path `./local/api.mjs` should work if files are in `src/api/local/`

### File Upload Issues

- **File size exceeded**: Check file size (max 50MB)
- **Unsupported format**: Verify file type is in supported list
- **Upload fails**: Check server logs and API key configuration
- **Processing fails**: Ensure file processing service is initialized on server

### Debug Mode

Enable debug logging by setting:
```bash
VITE_CONSOLE_DEBUG=true
```

This will show detailed API loading and file upload information in the console.
