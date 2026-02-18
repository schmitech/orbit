# ORBIT Chat App

A standalone chat application for ORBIT that can be installed as an npm package and run as a CLI tool. All API communication is routed through a built-in Express proxy that maps adapter names to backend API keys, so **no secrets ever reach the browser**. Uses the open-source [`@schmitech/markdown-renderer`](https://github.com/schmitech/markdown-renderer) for rich content display including math and charts.

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

## Quick Start

1. Define your adapters (agents) via the `ORBIT_ADAPTERS` or `VITE_ADAPTERS` environment variable:
   ```bash
   export ORBIT_ADAPTERS='[
     {"name":"Simple Chat","apiKey":"my-key","apiUrl":"http://localhost:3000","description":"Default conversational agent."}
   ]'
   ```

2. Run the CLI:
   ```bash
   orbitchat --enable-upload --port 5173
   ```

3. Open `http://localhost:5173` — select an agent and start chatting.

## Architecture

```
Browser  ──X-Adapter-Name──▶  Express proxy  ──X-API-Key──▶  ORBIT backend
                              (bin/orbitchat.js)
```

The frontend never handles API keys. Instead:
- The browser sends an `X-Adapter-Name` header with every API request.
- The Express proxy looks up the adapter, injects the real `X-API-Key`, and forwards the request to the configured backend URL.
- `GET /api/adapters` returns only adapter names and descriptions — never keys or URLs.

## CLI Options

```bash
orbitchat [options]

Options:
  --api-url URL                    Default backend URL (default: http://localhost:3000)
  --default-adapter NAME           Adapter to preselect for new conversations
  --application-name NAME          Name shown in browser tab (default: ORBIT Chat)
  --application-description TEXT   Subtitle shown under the welcome heading
  --default-input-placeholder TEXT Message input placeholder (default: Message ORBIT...)
  --console-debug                  Enable console debug logging (default: false)
  --enable-upload                  Enable file upload button (default: false)
  --enable-audio                   Enable audio output button (default: false)
  --enable-feedback                Enable feedback buttons (default: false)
  --enable-autocomplete            Enable autocomplete suggestions (default: false)
  --out-of-service-message TEXT    Show maintenance screen blocking access
  --max-files-per-conversation N   Max files per conversation (default: 5)
  --max-file-size-mb N             Max file size in MB (default: 50)
  --max-total-files N              Max total files (default: 100, 0 = unlimited)
  --max-conversations N            Max conversations (default: 10, 0 = unlimited)
  --max-messages-per-conversation N Max messages per conversation (default: 1000, 0 = unlimited)
  --max-messages-per-thread N      Max messages per thread (default: 1000, 0 = unlimited)
  --max-total-messages N           Max total messages (default: 10000, 0 = unlimited)
  --max-message-length N           Max message length (default: 1000)
  --port PORT                      Server port (default: 5173)
  --host HOST                      Server host (default: localhost)
  --open                           Open browser automatically
  --api-only                       Run API proxy only (no UI serving, no build required)
  --cors-origin ORIGIN             Allowed CORS origin in api-only mode (default: *)
  --config PATH                    Path to config file (default: ~/.orbit-chat-app/config.json)
  --help, -h                       Show help message
  --version, -v                    Show version number
```

### Examples

```bash
# Start with custom API URL and port
orbitchat --api-url http://localhost:3000 --port 8080

# Start with upload, audio and autocomplete enabled
orbitchat --enable-upload --enable-audio --enable-autocomplete --open

# Start with a custom config file
orbitchat --config /path/to/config.json

# Start with adapters defined inline
ORBIT_ADAPTERS='[{"name":"Chat","apiKey":"mykey","apiUrl":"https://api.example.com"}]' orbitchat

# API proxy only — no UI, no build required
orbitchat --api-only --port 5174

# API proxy with restricted CORS origin
orbitchat --api-only --port 5174 --cors-origin http://localhost:3001
```

## API-Only Mode

Use `--api-only` to run the Express proxy **without** serving the built-in chat UI. This is useful when you are building your own frontend and only need the proxy layer to keep API keys off the browser.

```bash
orbitchat --api-only --port 5174
```

In this mode:
- No `dist/` directory or `npm run build` is required.
- CORS headers are added automatically (default `Access-Control-Allow-Origin: *`). Use `--cors-origin` to restrict to a specific origin.
- All `/api/*` proxy routes and `GET /api/adapters` work exactly the same as in full mode.

### API contract for custom UIs

Your frontend needs to do two things:

1. **Discover adapters** — `GET /api/adapters` returns:
   ```json
   {
     "adapters": [
       { "name": "Simple Chat", "description": "...", "notes": "..." }
     ]
   }
   ```

2. **Send requests with `X-Adapter-Name`** — every call to `/api/*` must include the header:
   ```
   X-Adapter-Name: Simple Chat
   ```
   The proxy resolves the adapter, injects the real `X-API-Key`, and forwards the request to the backend URL configured for that adapter.

### Endpoint reference

| Method | Path | Headers | Description |
|--------|------|---------|-------------|
| GET | `/api/adapters` | — | List available adapter names and descriptions |
| POST | `/api/v1/chat` | `X-Adapter-Name`, `X-Session-ID` | Send a chat message (SSE streaming response) |
| POST | `/api/files/upload` | `X-Adapter-Name` | Upload a file (multipart/form-data) |
| GET | `/api/files` | `X-Adapter-Name` | List uploaded files |
| GET | `/api/files/:id` | `X-Adapter-Name` | Get file info |
| DELETE | `/api/files/:id` | `X-Adapter-Name` | Delete a file |
| GET | `/api/v1/autocomplete?q=...&limit=5` | `X-Adapter-Name` | Autocomplete suggestions |

### Example: calling from a custom React app

```js
// Discover adapters
const res = await fetch('http://localhost:5174/api/adapters');
const { adapters } = await res.json();

// Send a chat message (SSE stream)
const response = await fetch('http://localhost:5174/api/v1/chat', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-Adapter-Name': adapters[0].name,
    'X-Session-ID': crypto.randomUUID(),
  },
  body: JSON.stringify({ message: 'Hello!' }),
});

// Read the SSE stream
const reader = response.body.getReader();
const decoder = new TextDecoder();
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  console.log(decoder.decode(value));
}
```

## Configuring Adapters

Adapters map a user-visible name to a backend API key and URL. Configure them via the `ORBIT_ADAPTERS` (or `VITE_ADAPTERS`) environment variable as a JSON array:

```bash
export ORBIT_ADAPTERS='[
  {
    "name": "Simple Chat",
    "apiKey": "default-key",
    "apiUrl": "http://localhost:3000",
    "description": "Basic chat interface using the default conversational agent."
  },
  {
    "name": "Document QA",
    "apiKey": "doc-qa-key",
    "apiUrl": "http://localhost:3000",
    "description": "Chat with uploaded documents.",
    "notes": "Supports PDF, DOCX, and plain text uploads."
  }
]'
```

Each adapter object supports:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Display name shown in the agent selector |
| `apiKey` | Yes | Backend API key (never exposed to the browser) |
| `apiUrl` | No | Backend URL (defaults to `--api-url` value) |
| `description` | No | Short summary shown in dropdowns |
| `notes` | No | Markdown content shown in the chat empty state |

If `--default-adapter` is not specified, the first adapter in the list is preselected for new conversations.

### Agent Selector UX

- When a conversation has no messages, the chat canvas shows a centered agent selector with the adapter's notes rendered beneath it.
- Once an adapter is selected, the input field unlocks.
- Sidebar cards display the agent assigned to each conversation.
- To change the adapter after messages exist, use the "Change agent" action in the sidebar.

## Configuration

### Configuration Priority

Configuration is loaded in the following priority order:
1. CLI arguments (highest priority)
2. Config file (`~/.orbit-chat-app/config.json`)
3. Environment variables (`VITE_*`)
4. Default values (lowest priority)

### Configuration File

Create a config file at `~/.orbit-chat-app/config.json`:

```json
{
  "apiUrl": "http://localhost:3000",
  "defaultKey": "Simple Chat",
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

> **Note:** `defaultKey` should be set to an adapter name (e.g. `"Simple Chat"`). If left as `"default-key"` or empty, the app falls back to the first adapter in `ORBIT_ADAPTERS`.

### Environment Variables

For development, set configuration via environment variables:

```bash
VITE_API_URL=http://localhost:3000
VITE_DEFAULT_KEY=Simple Chat          # Adapter name to preselect
VITE_ENABLE_UPLOAD=false
VITE_ENABLE_AUDIO_OUTPUT=false
VITE_ENABLE_FEEDBACK=false
VITE_ENABLE_AUTOCOMPLETE=false
VITE_CONSOLE_DEBUG=false
```

> **Note:** GitHub stats and owner/repo are hardcoded and only configurable via build-time environment variables (`VITE_SHOW_GITHUB_STATS`, `VITE_GITHUB_OWNER`, `VITE_GITHUB_REPO`) for developers who fork the repository.

## Development

### Local Development Setup

Clone the repository and install dependencies:

```bash
npm install
npm run dev
```

### Development with Express Proxy

To run both the Express proxy and Vite dev server together:

```bash
node bin/dev-server.js
```

This starts:
- Express proxy on port 5174 (handles `/api/*` routes)
- Vite dev server on port 5173 (proxies API requests to Express)

### Building for Production

```bash
npm run build
```

The output is written to `dist/`. Serve it with:

```bash
orbitchat --port 8080
```

### Running as a Daemon

Use the included `run-chat-app.sh` script:

```bash
./run-chat-app.sh --start        # Start in background
./run-chat-app.sh --start 8080   # Start on custom port
./run-chat-app.sh --stop          # Stop
./run-chat-app.sh --status        # Check status
```

## Available Scripts

- `npm run dev` — Start Vite dev server
- `npm run build` — Build for production
- `npm run preview` — Preview production build
- `npm run dev:local` — Start dev server with local API build
- `npm run dev:with-api` — Build API from `../node-api` and start dev server
- `npm run build:local` — Build for production with local API
- `npm run build:api` — Build and copy API from `../node-api`

## Features

- **Streaming Responses**: Real-time streaming of AI responses via SSE
- **Agent Selection**: Choose from configured adapters per conversation
- **File Upload**: Upload and attach files (PDF, DOCX, TXT, CSV, JSON, HTML, images, audio) to conversations
- **File Context**: Query uploaded files — they are chunked, embedded, and included in chat context
- **Autocomplete**: Optional type-ahead suggestions via `/api/v1/autocomplete`
- **Conversation Threads**: Branch conversations into focused sub-threads
- **Session Management**: Automatic session ID generation and persistence
- **Conversation Persistence**: Chat history saved to localStorage
- **Audio Output**: Optional text-to-speech for AI responses
- **Feedback Buttons**: Optional thumbs-up/down per message

## Security

- The browser **never** sees real API keys. The Express proxy maps adapter names to keys server-side.
- `GET /api/adapters` only exposes names and descriptions — never keys or backend URLs.
- Keep `ORBIT_ADAPTERS` / `VITE_ADAPTERS` out of source control.
- Run the proxy behind HTTPS (or another reverse proxy) in production so users cannot intercept traffic.
- Secure the host running the CLI — a compromised host can leak the adapters config or intercept proxied traffic.

## File Upload

### Supported File Types

| Type | Formats | Processing |
|------|---------|------------|
| Documents | PDF, DOCX, PPTX, XLSX | Text extraction, chunking, vector indexing |
| Text | TXT, MD, HTML | Direct chunking and indexing |
| Data | CSV, JSON | Chunking and indexing |
| Code | PY, JS, TS, Java, Go, Rust, C/C++, and more | Direct indexing |
| Images | PNG, JPEG, TIFF | OCR via vision service |
| Audio | WAV, MP3, MP4, OGG, FLAC, WebM, M4A, AAC | ASR (Automatic Speech Recognition) |
| Subtitles | VTT | Direct indexing |

### Limits

- Maximum file size: 50 MB (configurable via `--max-file-size-mb`)
- Maximum files per conversation: 5 (configurable via `--max-files-per-conversation`)

### Processing Pipeline

1. **Upload** — File uploaded via the Express proxy to `/api/files/upload`
2. **Validation** — File type and size validated client-side and server-side
3. **Storage** — File saved to filesystem (or S3 in production)
4. **Extraction** — Text and metadata extracted using format-specific processors
5. **Chunking** — Content chunked using configured strategy (fixed or semantic)
6. **Indexing** — Chunks indexed in vector store for semantic search
7. **Status Polling** — Client polls until processing completes

## Integration Details

The application uses:
- **Zustand** for state management
- **Express** + `http-proxy-middleware` for the API proxy layer
- **@schmitech/markdown-renderer** ([GitHub](https://github.com/schmitech/markdown-renderer) | [NPM](https://www.npmjs.com/package/@schmitech/markdown-renderer)) for rich markdown rendering
- **localStorage** for persistent session and conversation storage
- **TypeScript** for type safety throughout

## Troubleshooting

### No Adapters Available

If the agent selector shows no adapters:
1. Ensure `ORBIT_ADAPTERS` or `VITE_ADAPTERS` is set and valid JSON
2. Check the CLI startup logs for "Available Adapters: ..."
3. Verify each adapter has a `name` and `apiKey` field

### File Upload Issues

- **File size exceeded** — Check file size against the configured limit
- **Unsupported format** — Verify file type is in the supported list above
- **Upload fails** — Check server logs and adapter configuration
- **Processing fails** — Ensure the file processing service is initialized on the backend

### Debug Mode

Enable debug logging:
```bash
orbitchat --console-debug
```
Or set `VITE_CONSOLE_DEBUG=true` during development. This shows detailed API and file upload information in the browser console.

## Deployment Checklist

1. **Build the app**: `npm run build`
2. **Set `ORBIT_ADAPTERS`** with your production adapter configs (keep out of git)
3. **Run behind HTTPS** — use a reverse proxy like nginx or Caddy in front of `orbitchat`
4. **Bind to the right interface**: use `--host 0.0.0.0` to allow external access, or keep the default `localhost` for local-only
5. **Tune limits** — set `--max-conversations`, `--max-message-length`, etc. appropriate for your deployment
6. **Monitor logs** — use `run-chat-app.sh --start` for daemon mode with log file, or run directly and pipe to your log aggregator
