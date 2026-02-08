# API Key Management Utilities

This package provides utilities for managing API keys and interacting with the chat server API. It includes:

1. `orbit.py` - A command-line tool for creating and managing API keys and system prompts
2. `api_client.py` - A client library for sending chat messages using API keys

## Installation

```bash
# Install required dependencies
pip install requests python-dotenv
```

## API Key Manager

The API Key Manager utility allows you to create, test, and manage API keys and system prompts from the command line.

### API Key Management

```bash
# Create a new API key with a system prompt
python orbit.py --url http://localhost:3000 key create\
  --collection city \
  --name "City Assistant" \
  --prompt-file .examples/prompts/examples/city/city-assistant-normal-prompt.txt \
  --prompt-name "Municipal Assistant Prompt"

# List all API keys
python orbit.py --url http://localhost:3000 list

# Test an API key
python orbit.py --url http://localhost:3000 test --key YOUR_API_KEY

# Deactivate an API key
python orbit.py --url http://localhost:3000 deactivate --key YOUR_API_KEY

# Delete an API key
python orbit.py --url http://localhost:3000 delete --key YOUR_API_KEY

# Get API key status
python orbit.py --url http://localhost:3000 status --key YOUR_API_KEY
```

### System Prompt Management

```bash
# Create a new system prompt
python orbit.py --url http://localhost:3000 prompt create \
  --name "Support Assistant" \
  --file prompts/support.txt \
  --version "1.0"

# List all prompts
python orbit.py --url http://localhost:3000 prompt list

# Get a specific prompt
python orbit.py --url http://localhost:3000 prompt get --id PROMPT_ID

# Update a prompt
python orbit.py --url http://localhost:3000 prompt update \
  --id PROMPT_ID \
  --file prompts/updated.txt \
  --version "1.1"

# Delete a prompt
python orbit.py --url http://localhost:3000 prompt delete --id PROMPT_ID

# Associate a prompt with an API key
python orbit.py --url http://localhost:3000 prompt associate \
  --key YOUR_API_KEY \
  --prompt-id PROMPT_ID
```

## API Client

The API Client provides a convenient interface for sending chat messages to the server using API keys. The project is located under
clients/python, however for your convenience there is a pre-built package available:
```bash
pip install schmitech-orbit-client
orbit-chat --url http://localhost:3000 # Type 'hello' to chat with Ollama. No chat history yet, coming soon...
```

### Usage

```python
from chat_client import stream_chat

# Stream a chat message
response, timing_info = stream_chat(
    url="http://localhost:3000",
    message="Hello, how are you?",
    api_key="your-api-key-here",
    session_id=None,  # Optional, will generate UUID if not provided
    debug=False  # Optional, for debugging
)

# Print response
print(response)

# Print timing information if needed
if timing_info:
    print(f"Total time: {timing_info['total_time']:.3f}s")
    print(f"Time to first token: {timing_info['time_to_first_token']:.3f}s")

```

## Testing admin endpoints from the browser

All admin routes live under `/admin` (see `server/routes/admin_routes.py`). They require either:

- **Admin auth:** `Authorization: Bearer <token>` (obtain a token via the auth login endpoint), or  
- **API key:** `X-API-Key: <your-api-key>` (any valid API key is accepted for admin access).

Default server URL: `http://localhost:3000` (override if your config uses a different port).

### 1. Swagger UI (recommended)

1. Open **http://localhost:3000/docs** in your browser.
2. Click **Authorize**.
3. Either:
   - Set **X-API-Key** to a valid API key (if your OpenAPI schema exposes it), or  
   - Set **Bearer** to an admin token from the auth service.
4. Use the **admin** tag to find and try endpoints (e.g. `GET /admin/info`, `GET /admin/api-keys`, `POST /admin/api-keys`, `GET /admin/prompts`).

Swagger sends the chosen auth header on every request, so you can exercise GET, POST, PATCH, PUT, and DELETE from the browser.

### 2. Browser DevTools console

For a one-off call (e.g. server info or list API keys), open DevTools (F12) → **Console** and run:

**With API key:**

```javascript
fetch('http://localhost:3000/admin/info', {
  headers: { 'X-API-Key': 'YOUR_API_KEY' }
}).then(r => r.json()).then(console.log);
```

**With Bearer token (after logging in via auth API):**

```javascript
fetch('http://localhost:3000/admin/api-keys', {
  headers: { 'Authorization': 'Bearer YOUR_ADMIN_TOKEN' }
}).then(r => r.json()).then(console.log);
```

**POST example (create API key):**

```javascript
fetch('http://localhost:3000/admin/api-keys', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': 'YOUR_API_KEY'
  },
  body: JSON.stringify({
    client_name: 'Test Client',
    notes: 'From browser'
  })
}).then(r => r.json()).then(console.log);
```

Replace `YOUR_API_KEY` or `YOUR_ADMIN_TOKEN` with a real value. Without valid auth you’ll get `401 Admin authentication or valid API key required`.

### Summary of admin routes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/info` | Server PID and status |
| GET | `/admin/api-keys` | List API keys (optional: `adapter`, `active_only`, `limit`, `offset`) |
| POST | `/admin/api-keys` | Create API key (body: `client_name`, `notes`, etc.) |
| GET | `/admin/api-keys/{api_key}/status` | Key status |
| PATCH | `/admin/api-keys/{old_api_key}/rename?new_api_key=...` | Rename key |
| POST | `/admin/api-keys/deactivate` | Deactivate key (body: `{"api_key": "..."}`) |
| DELETE | `/admin/api-keys/{api_key}` | Delete key |
| GET | `/admin/prompts` | List system prompts |
| POST | `/admin/prompts` | Create prompt |
| GET/PUT/DELETE | `/admin/prompts/{prompt_id}` | Get / update / delete prompt |
| POST | `/admin/reload-adapters` | Hot-reload adapters (optional `?adapter_name=...`) |
| POST | `/admin/reload-templates` | Hot-reload templates |
| GET | `/admin/quotas/usage-report` | Quota usage report |

Other admin routes (quotas, chat history, conversations, shutdown) are in `admin_routes.py`; use the same auth and base URL.

---

## Testing auth endpoints from the browser

Auth routes live under `/auth` (see `server/routes/auth_routes.py`). They use **Bearer token** auth only (no `X-API-Key`). Get a token via `POST /auth/login`, then send `Authorization: Bearer <token>` on subsequent requests.

Default server URL: `http://localhost:3000`.

### 1. Swagger UI

1. Open **http://localhost:3000/docs**.
2. Call **POST /auth/login** with body `{"username": "admin", "password": "your-password"}` (or your configured admin credentials). Copy the `token` from the response.
3. Click **Authorize**, set **Bearer** to that token, then use the **authentication** tag to call other auth endpoints.

### 2. Browser DevTools console

**Login (no auth; returns token):**

```javascript
fetch('http://localhost:3000/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'admin', password: 'admin123' })
}).then(r => r.json()).then(data => {
  console.log('Token:', data.token);
  window.orbitToken = data.token;  // optional: reuse below
});
```

**Current user (Bearer required):**

```javascript
fetch('http://localhost:3000/auth/me', {
  headers: { 'Authorization': 'Bearer ' + window.orbitToken }
}).then(r => r.json()).then(console.log);
```

**Logout (invalidates token):**

```javascript
fetch('http://localhost:3000/auth/logout', {
  method: 'POST',
  headers: { 'Authorization': 'Bearer ' + window.orbitToken }
}).then(r => r.json()).then(console.log);
```

**Change password (any authenticated user):**

```javascript
fetch('http://localhost:3000/auth/change-password', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ' + window.orbitToken
  },
  body: JSON.stringify({
    current_password: 'admin123',
    new_password: 'new-secure-password'
  })
}).then(r => r.json()).then(console.log);
```

**Admin-only examples (Bearer must be admin):**

```javascript
// List users
fetch('http://localhost:3000/auth/users', {
  headers: { 'Authorization': 'Bearer ' + window.orbitToken }
}).then(r => r.json()).then(console.log);

// Register new user (admin only)
fetch('http://localhost:3000/auth/register', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ' + window.orbitToken
  },
  body: JSON.stringify({ username: 'newuser', password: 'secret', role: 'user' })
}).then(r => r.json()).then(console.log);
```

### Summary of auth routes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/login` | None | Login; body `{"username","password"}` → returns `token` and `user` |
| GET | `/auth/me` | Bearer | Current user info (id, username, role, active, created_at, last_login) |
| POST | `/auth/logout` | Bearer | Invalidate current token |
| POST | `/auth/change-password` | Bearer | Change own password; body `{"current_password","new_password"}` |
| GET | `/auth/users` | Admin | List users (query: `role`, `active_only`, `limit`, `offset`) |
| GET | `/auth/users/by-username?username=...` | Admin | Get user by username |
| POST | `/auth/register` | Admin | Create user; body `{"username","password","role"}` (role: `user` or `admin`) |
| DELETE | `/auth/users/{user_id}` | Admin | Delete user (cannot delete self) |
| POST | `/auth/reset-password` | Admin | Reset another user's password; body `{"user_id","new_password"}` |
| POST | `/auth/users/{user_id}/deactivate` | Admin | Deactivate user (cannot deactivate self) |
| POST | `/auth/users/{user_id}/activate` | Admin | Activate user |

Without a valid Bearer token (or with wrong role for admin-only routes) you get `401` or `403` as appropriate.

## Security Notes

1. API keys are sensitive credentials and should be handled securely
2. Consider using environment variables or secure credential storage instead of hardcoding API keys
3. In production, always use HTTPS to encrypt API keys in transit