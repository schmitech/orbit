# ORBIT Middleware Proxy

A standalone middleware proxy for ORBIT chat applications. This service hides API keys from clients and provides rate limiting, logging, and CORS protection.

## Features

- **API Key Protection**: Clients send adapter names, not API keys
- **Rate Limiting**: Per-adapter request limits to prevent abuse
- **CORS Protection**: Control which origins can access the proxy
- **Request Logging**: Structured logging with Pino
- **SSE Streaming Support**: Properly handles Server-Sent Events for chat responses
- **Health Checks**: `/health` and `/ready` endpoints for container orchestration
- **Docker Ready**: Multi-stage Dockerfile with non-root user

## Quick Start

### Using npm

```bash
# Install dependencies
npm install

# Build
npm run build

# Start with environment variables
ORBIT_ADAPTERS='[{"name":"Chat","apiKey":"mykey","apiUrl":"https://orbit.example.com"}]' \
ALLOWED_ORIGINS='https://app.example.com' \
npm start
```

### Using Docker

```bash
# Build image
docker build -t middleware-proxy .

# Run container
docker run -p 3001:3001 \
  -e ORBIT_ADAPTERS='[{"name":"Chat","apiKey":"mykey","apiUrl":"https://orbit.example.com"}]' \
  -e ALLOWED_ORIGINS='https://app.example.com' \
  middleware-proxy
```

### Using Docker Compose

```bash
# Edit docker-compose.yml with your configuration
docker-compose up -d
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Server port | `3001` |
| `HOST` | Bind address | `0.0.0.0` |
| `ORBIT_ADAPTERS` | JSON array of adapter configs | Required |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins | `*` |
| `RATE_LIMIT_WINDOW_MS` | Rate limit window (ms) | `60000` |
| `RATE_LIMIT_MAX_REQUESTS` | Max requests per window | `100` |
| `LOG_LEVEL` | Log level (debug/info/warn/error) | `info` |
| `LOG_FORMAT` | Log format (json/pretty) | `json` |
| `LOG_REQUESTS` | Log all requests | `true` |
| `CONFIG_FILE` | Optional config file path | - |

### Adapter Configuration

Adapters are configured via the `ORBIT_ADAPTERS` environment variable (JSON array):

```json
[
  {
    "name": "Simple Chat",
    "apiKey": "orbit_xxxx",
    "apiUrl": "https://orbit-server.example.com"
  },
  {
    "name": "Advanced QA",
    "apiKey": "orbit_yyyy",
    "apiUrl": "https://orbit-server.example.com"
  }
]
```

### Optional Config File

You can also use a JSON config file:

```json
{
  "server": {
    "port": 3001,
    "host": "0.0.0.0"
  },
  "adapters": [
    {
      "name": "Simple Chat",
      "apiKey": "orbit_xxxx",
      "apiUrl": "https://orbit-server.example.com"
    }
  ],
  "cors": {
    "allowedOrigins": ["https://app.example.com"]
  },
  "rateLimit": {
    "windowMs": 60000,
    "maxRequests": 100
  }
}
```

## API Endpoints

### Health Check

```
GET /health
```

Returns server health status:

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime": 3600,
  "timestamp": "2024-01-15T10:30:00.000Z"
}
```

### Readiness Check

```
GET /ready
```

Returns readiness status with adapter info:

```json
{
  "status": "ready",
  "adapters": {
    "loaded": 2,
    "healthy": 2
  }
}
```

### List Adapters

```
GET /api/adapters
```

Returns available adapter names (no API keys or URLs exposed):

```json
{
  "adapters": [
    { "name": "Simple Chat" },
    { "name": "Advanced QA" }
  ]
}
```

### Proxy Requests

```
* /api/proxy/*
```

Proxies requests to ORBIT server. Requires `X-Adapter-Name` header:

```bash
curl -X POST https://middleware-proxy.example.com/api/proxy/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-Adapter-Name: Simple Chat" \
  -H "X-Session-ID: session-123" \
  -d '{"messages": [{"role": "user", "content": "Hello"}], "stream": true}'
```

## Client Integration

### chat-app / chat-widget

Point your client's `apiUrl` to the middleware proxy:

```javascript
// Before: Direct to ORBIT server
const apiUrl = 'https://orbit-server.example.com';

// After: Through middleware proxy
const apiUrl = 'https://middleware-proxy.example.com/api/proxy';
```

The client must include the `X-Adapter-Name` header with each request:

```javascript
fetch(`${apiUrl}/v1/chat`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-Adapter-Name': 'Simple Chat',
    'X-Session-ID': sessionId,
  },
  body: JSON.stringify({ messages, stream: true }),
});
```

## Architecture

```
┌─────────────────┐     ┌─────────────────────┐     ┌─────────────────┐
│   chat-app      │     │  middleware-proxy   │     │  ORBIT Server   │
│   chat-widget   │────▶│                     │────▶│                 │
│   (Browser)     │     │  - CORS protection  │     │  (API Keys)     │
│                 │     │  - Rate limiting    │     │                 │
│  X-Adapter-Name │     │  - API key inject   │     │  X-API-Key      │
└─────────────────┘     │  - SSE streaming    │     └─────────────────┘
                        │  - Request logging  │
                        └─────────────────────┘
```

## Development

```bash
# Install dependencies
npm install

# Run in development mode with hot reload
npm run dev

# Build for production
npm run build

# Start production server
npm start
```

## License

MIT
