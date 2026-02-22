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

Installed CLI commands:
- `orbitchat` — starts the ORBIT Chat server directly
- `orbitchat-daemon` — shell wrapper with `--start/--stop/--restart/--force-restart/--status`

## Quick Start

1. Define your adapter secrets via the `ORBIT_ADAPTER_KEYS` or `VITE_ADAPTER_KEYS` environment variable:
   ```bash
   # Mapping of Agent Name -> API Key
   export ORBIT_ADAPTER_KEYS='{"Simple Chat":"my-secret-key"}'
   ```

2. (Optional) Configure adapter URLs and metadata in `orbitchat.yaml`:
   ```yaml
   adapters:
     - name: "Simple Chat"
       apiUrl: "http://localhost:3000"
       description: "Default conversational agent."
   ```

3. Run the CLI:
   ```bash
   orbitchat --config ./orbitchat.yaml --port 5173
   ```

4. Open `http://localhost:5173` — select an agent and start chatting.

## Architecture

```
Browser  ──X-Adapter-Name──▶  Express proxy  ──X-API-Key──▶  ORBIT backend
                              (bin/orbitchat.js)
```

The frontend never handles API keys. Instead:
- The browser sends an `X-Adapter-Name` header with every API request.
- The Express proxy looks up the adapter, injects the real `X-API-Key`, and forwards the request to the configured backend URL.
- `GET /api/adapters` returns non-secret adapter metadata (name, description, notes, model) — never keys or backend URLs.

## CLI Options

```bash
orbitchat [options]

Options:
  --port PORT        Server port (default: 5173)
  --host HOST        Server host (default: localhost)
  --open             Open browser automatically
  --config PATH      Path to orbitchat.yaml (default: ./orbitchat.yaml)
  --api-only         Run API proxy only (no UI serving)
  --cors-origin URL  Allowed CORS origin in api-only mode (default: *)
  --help, -h         Show help message
  --version, -v      Show version number
```

### Examples

```bash
# Start with a custom config file
orbitchat --config /path/to/orbitchat.yaml

# Start with adapter keys defined inline
ORBIT_ADAPTER_KEYS='{"Chat":"mykey"}' orbitchat

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
       { "name": "Simple Chat", "description": "...", "notes": "...", "model": "gpt-4o-mini" }
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
| GET | `/api/adapters` | — | List available adapter metadata (name, description, notes, model) |
| POST | `/api/v1/chat` | `X-Adapter-Name`, `X-Session-ID` | Send a chat message (SSE streaming response) |
| POST | `/api/files/upload` | `X-Adapter-Name` | Upload a file (multipart/form-data) |
| GET | `/api/files` | `X-Adapter-Name` | List uploaded files |
| GET | `/api/files/:id` | `X-Adapter-Name` | Get file info |
| DELETE | `/api/files/:id` | `X-Adapter-Name` | Delete a file |
| GET | `/api/v1/autocomplete?q=...&limit=5` | `X-Adapter-Name` | Autocomplete suggestions |

## Configuring Adapters

Configuration is split between **metadata/URLs** (in `orbitchat.yaml`) and **secrets** (in environment variables).

### 1. Metadata in `orbitchat.yaml`

Define your adapters list in the YAML file:

```yaml
adapters:
  - name: "Simple Chat"
    apiUrl: "http://localhost:3000"
    description: "Basic chat interface using the default conversational agent."
  - name: "Document QA"
    apiUrl: "http://localhost:3000"
    description: "Chat with uploaded documents."
    notes: "Supports PDF, DOCX, and plain text uploads."
```

| Field | Description |
|-------|-------------|
| `name` | Display name shown in the agent selector (must match the key in `.env`) |
| `apiUrl` | Backend URL (defaults to `api.url`, then `http://localhost:3000`) |
| `description` | Short summary shown in dropdowns |
| `notes` | Markdown content shown in the chat empty state |

### 2. Secrets in `.env`

Provide the API keys via `ORBIT_ADAPTER_KEYS` (or `VITE_ADAPTER_KEYS`) as a JSON object:

```bash
VITE_ADAPTER_KEYS='{
  "Simple Chat": "secret-key-1",
  "Document QA": "secret-key-2"
}'
```

The system deep-merges these sources at runtime.

## Configuration

### Runtime Config File

Runtime settings are loaded from `orbitchat.yaml` (see `orbitchat.yaml.example`). The configuration uses a nested structure:

```yaml
application:
  name: "ORBIT Chat"
api:
  url: "http://localhost:3000"
features:
  enableUpload: true
```

Header logos (`header.logoUrl`, `header.logoUrlLight`, `header.logoUrlDark`) support:
- Remote URLs, for example `https://example.com/logo.png`
- Local file paths (absolute or relative to `orbitchat.yaml`), for example `./public/logo.png`

Theme-aware logo selection order:
- Light theme: `header.logoUrlLight` -> `header.logoUrl` -> `header.logoUrlDark`
- Dark theme: `header.logoUrlDark` -> `header.logoUrl` -> `header.logoUrlLight`

Default logo fallback behavior:
- If `header.logoUrlLight` is empty or whitespace, ORBIT Chat uses `/orbit-logo-light.png`.
- If `header.logoUrlDark` is empty or whitespace, ORBIT Chat uses `/orbit-logo-dark.png`.
- These paths are resolved from the app root (Vite `public/` directory), alongside `favicon.svg`.
- Example:
  ```yaml
  header:
    logoUrlLight: ""
    logoUrlDark: ""
  ```
  With this config, light/dark themes automatically use the default files from `public/`.

### Environment Variables

Adapter secrets are provided via:
- `ORBIT_ADAPTER_KEYS` (Preferred)
- `VITE_ADAPTER_KEYS`

Auth secrets are read from:
- `VITE_AUTH_DOMAIN`
- `VITE_AUTH_CLIENT_ID`
- `VITE_AUTH_AUDIENCE`

The CLI loads `.env` and `.env.local` from the current working directory on startup.

## Development

### Local Development Setup

Clone the repository and install dependencies:

```bash
npm install
npm run dev
```

### Building for Production

```bash
npm run build
```

The output is written to `dist/`. Serve it with:

```bash
orbitchat --port 8080
```

`public/` assets are copied into `dist/` during build. Because the npm package publishes `dist/`, default logo assets such as `orbit-logo-light.png` and `orbit-logo-dark.png` are included in published builds.

## Troubleshooting

### No Adapters Available

If the agent selector shows no adapters:
1. Ensure `VITE_ADAPTER_KEYS` is set and contains valid JSON.
2. Verify that the adapter `name` in `orbitchat.yaml` exactly matches the key used in `VITE_ADAPTER_KEYS`.
3. Check the CLI startup logs for "Available Adapters: ...".

### Stale Configuration

If you've updated `orbitchat.yaml` but don't see changes:
1. The CLI watches the YAML file and should restart automatically.
2. Clear browser site data/localStorage for the app origin to ensure no stale session state is being used.

## Security

- The browser **never** sees real API keys. The Express proxy maps adapter names to keys server-side.
- `GET /api/adapters` only exposes non-secret metadata (name, description, notes, model) — never keys or backend URLs.
- Keep `VITE_ADAPTER_KEYS` out of source control.
- Run the proxy behind HTTPS in production.

## License

MIT
