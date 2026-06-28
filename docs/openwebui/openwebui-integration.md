# Open WebUI Integration Guide

This guide covers two ways to connect Open WebUI to ORBIT:

1. **OpenAI-compatible connection** — point Open WebUI at ORBIT's `/v1/chat/completions` endpoint (recommended starting point)
2. **MCP tools connection** — expose ORBIT's MCP tool server to Open WebUI so models can invoke ORBIT tools inline

Both approaches can be used together.

---

## Prerequisites

- ORBIT running and accessible (default: `http://localhost:3000`)
- A valid ORBIT API key (`orbit_xxx...`) — create one with `./bin/orbit.sh key create`
- Open WebUI running (default: `http://localhost:8080`) — see the [Open WebUI quick-start](https://docs.openwebui.com/getting-started/quick-start/)
- Admin access to Open WebUI

---

## Step 1 — Disable the X-Session-ID Requirement

ORBIT requires an `X-Session-ID` header on every request by default. Open WebUI does not send this header, so disable the requirement in `config/config.yaml`:

```yaml
general:
  session_id:
    header_name: "X-Session-ID"
    required: false          # was: true

chat_history:
  session:
    auto_generate: true      # was: false
    required: true
    header_name: "X-Session-ID"
```

Restart ORBIT after saving. Each request that arrives without a session ID will receive an auto-generated UUID.

---

## Step 2 — Connect Open WebUI via OpenAI-Compatible Endpoint

Open WebUI treats any server that implements `/v1/chat/completions` as an OpenAI-compatible provider. ORBIT satisfies this requirement out of the box.

### 2a. Add the connection in Open WebUI

1. Open Open WebUI and sign in as an admin.
2. Navigate to **⚙️ Admin Settings** → **Connections** → **OpenAI**.
3. Click **➕ Add Connection**.
4. Fill in the fields:

| Field | Value |
|-------|-------|
| **URL** | `http://localhost:3000/v1` |
| **API Key** | `orbit_YOUR_API_KEY_HERE` |
| **Model IDs (Filter)** | *(see note below)* |

> **ORBIT on a different host?** Replace `localhost:3000` with the actual hostname or IP. If Open WebUI is inside Docker and ORBIT is on your laptop, use `host.docker.internal:3000` (Mac/Windows) or the host IP (Linux).

5. Click **Save**.

### 2b. Model IDs

ORBIT does not expose a `/v1/models` endpoint, so Open WebUI's auto-detection will fail. Add each adapter name manually in the **Model IDs (Filter)** field. Use the adapter names defined in `config/adapters.yaml`, for example:

```
hr-assistant
legal-assistant
procurement-assistant
```

Each adapter name you add becomes a selectable model in the Open WebUI chat dropdown.

### 2c. Verify the connection

Open the Open WebUI chat interface, open the model selector, and confirm your ORBIT adapter names appear. Send a test message — you should get a response routed through ORBIT.

### 2d. Multiple adapters as separate connections

Each ORBIT API key is scoped to one adapter. To expose multiple adapters in Open WebUI, add a separate connection per adapter:

| Connection | URL | API Key | Model ID |
|-----------|-----|---------|----------|
| ORBIT HR | `http://localhost:3000/v1` | `orbit_HR_KEY` | `hr-assistant` |
| ORBIT Legal | `http://localhost:3000/v1` | `orbit_LEGAL_KEY` | `legal-assistant` |
| ORBIT Procurement | `http://localhost:3000/v1` | `orbit_PROC_KEY` | `procurement-assistant` |

---

## Step 3 — Connect ORBIT's MCP Tools to Open WebUI

ORBIT ships a built-in MCP server (exposed via FastMCP) that gives Open WebUI models direct access to ORBIT tools — datasource queries, adapter lookups, and custom tools defined in `server/tools/`.

Open WebUI supports external MCP/OpenAPI servers over HTTP. ORBIT's MCP server is accessible at:

```
http://localhost:3000/mcp
```

### 3a. Add the MCP server in Open WebUI

1. Navigate to **⚙️ Admin Settings** → **Tools**.
2. Click **➕ Add Tool Server** (or **Add OpenAPI/MCP Server**, depending on your Open WebUI version).
3. Enter the URL:

```
http://localhost:3000/mcp
```

4. Set the authentication header:

```
Authorization: Bearer orbit_YOUR_API_KEY_HERE
```

5. Click **Save** and confirm the tool list populates.

> **Note:** Open WebUI natively supports Streamable HTTP MCP servers. ORBIT's FastMCP integration is served over HTTP, so no additional translation proxy (e.g. `mcpo`) is needed.

### 3b. Enable tools for a model

Once the MCP server is saved, enable it for the models that should be able to call ORBIT tools:

1. In a chat session, click the **Tools** icon in the message toolbar.
2. Toggle on the ORBIT tools you want available.
3. The model can now invoke ORBIT tools inline — datasource queries, retrieval, and anything registered in `server/tools/`.

---

## Step 4 — Quick Verification

After completing Steps 2 and 3, run these checks:

```bash
# Confirm ORBIT is up and accepting requests
curl http://localhost:3000/health

# Confirm a chat completion round-trip
curl http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer orbit_YOUR_API_KEY_HERE" \
  -d '{
    "model": "hr-assistant",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

Open WebUI should show a successful response in the chat UI.

---

## Optional: Minimal ORBIT Configuration for Inference-Only Use

When ORBIT is used purely as an LLM inference gateway — no RAG, no conversation history, no threaded datasets — several subsystems can be disabled. Edit `config/config.yaml` alongside the Step 1 session-ID settings:

```yaml
# Step 1 settings (required for Open WebUI)
general:
  session_id:
    required: false

chat_history:
  enabled: false          # Open WebUI manages its own conversation history
  session:
    auto_generate: true
    required: true
    header_name: "X-Session-ID"

# Additional settings safe to disable for inference-only use
conversation_threading:
  enabled: false          # Dataset caching for multi-turn RAG — not needed for passthrough

autocomplete:
  enabled: false          # Query suggestions — not used by Open WebUI

language_detection:
  enabled: false          # Auto-detects user language for RAG boosting — not used here
```

Restart ORBIT after saving. These settings have no effect on response content — they only disable backend side-effects that don't apply to a simple inference proxy.

> **Keep enabled**: `internal_services.audit` (compliance trail), `fault_tolerance.circuit_breaker` (protects downstream LLM providers), and `auth` (API key validation). These are lightweight and apply to every request.

---

## Endpoint Reference

| Detail | Value |
|--------|-------|
| Base URL | `http://localhost:3000/v1` |
| Chat endpoint | `POST /v1/chat/completions` |
| MCP server | `http://localhost:3000/mcp` |
| Required header | `Authorization: Bearer orbit_xxx` |
| Conditional header | `X-Session-ID: <uuid>` (required unless `auto_generate: true`) |
| Streaming | SSE (`"stream": true`) |
| Model IDs | Adapter names from `config/adapters.yaml` |

---

## Troubleshooting

**Open WebUI shows "Connection failed" when saving the connection**
ORBIT may not be reachable from the Open WebUI host. Confirm ORBIT is running (`curl http://localhost:3000/health`) and adjust the host if Open WebUI is inside Docker (`host.docker.internal` on Mac/Windows).

**No models appear in the chat dropdown**
ORBIT does not implement `/v1/models`. Open the connection in **Admin Settings** → **Connections** and add model names manually in the **Model IDs (Filter)** field. Use the adapter names from `config/adapters.yaml`.

**`401 Invalid or missing API key`**
The key is wrong or inactive. Verify with `./bin/orbit.sh key status --key orbit_xxx`.

**`400` or `422` errors on chat completions**
Check that `X-Session-ID` is no longer required (`auto_generate: true` is set and ORBIT was restarted).

**MCP tools don't appear after adding the server URL**
Confirm the MCP server is reachable at `http://localhost:3000/mcp` and that the API key has permission to access MCP tools. Check the ORBIT server logs for connection attempts.

**Responses include an `orbit` field**
ORBIT adds an `orbit` extension object to responses (sources, metadata, threading). Open WebUI ignores unknown fields, so this is harmless.
