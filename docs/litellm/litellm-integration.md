# LiteLLM Integration Guide

This guide covers three ways to connect LiteLLM to ORBIT's OpenAI-compatible `/v1/chat/completions` endpoint:

1. **Standalone LiteLLM instance** — add ORBIT to an already-running LiteLLM proxy
2. **LiteLLM Python SDK** — quick scripted testing
3. **LiteLLM proxy via Docker** — spin up a fresh proxy that routes to ORBIT

---

## Prerequisites

- ORBIT running and accessible (default: `http://localhost:3000`)
- A valid ORBIT API key (`orbit_xxx...`) — create one with `./bin/orbit.sh key create`
- Docker installed (for the proxy approach)
- Python 3.8+ with `litellm` installed: `pip install litellm`

---

## Step 1 — Disable the X-Session-ID Requirement

ORBIT requires a `X-Session-ID` header on every request by default. LiteLLM does not send this header, so disable the requirement in `config/config.yaml`:

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

Restart ORBIT after saving. Each request that arrives without a session ID will receive an auto-generated UUID — LiteLLM calls work without any extra headers.

---

## Step 2 — Add ORBIT to a Running LiteLLM Instance

If you already have a LiteLLM proxy running (started with `litellm --config config.yaml` or via Docker), add ORBIT by editing the proxy's config file and reloading it.

### 2a. Edit your existing `config.yaml`

Add one entry per ORBIT adapter under `model_list`. The `api_base` must be reachable from wherever LiteLLM is running.

```yaml
model_list:
  # ... your existing models ...

  - model_name: orbit                        # name clients use when calling the proxy
    litellm_params:
      model: openai/orbit                    # "openai/" prefix tells LiteLLM to use OpenAI-compatible routing
      api_base: http://localhost:3000/v1     # ORBIT base URL (adjust if ORBIT is on another host)
      api_key: orbit_YOUR_API_KEY_HERE       # sent as Authorization: Bearer, accepted by ORBIT

  # Multiple adapters — give each a distinct model_name and API key:
  - model_name: orbit-hr
    litellm_params:
      model: openai/orbit
      api_base: http://localhost:3000/v1
      api_key: orbit_HR_KEY_HERE

  - model_name: orbit-legal
    litellm_params:
      model: openai/orbit
      api_base: http://localhost:3000/v1
      api_key: orbit_LEGAL_KEY_HERE
```

> **ORBIT on a different host?** Replace `localhost:3000` with the actual hostname or IP of your ORBIT server. If LiteLLM is inside Docker and ORBIT is on your laptop, use `host.docker.internal:3000` (Mac/Windows) or the host IP (Linux).

### 2b. Reload the config

LiteLLM supports hot-reloading via its admin API — no restart needed:

```bash
# Reload config without downtime (LiteLLM proxy must have --detailed_debug or admin routes enabled)
curl -X POST http://localhost:4000/config/update \
  -H "Authorization: Bearer YOUR_LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d @config.yaml
```

Or restart the proxy if hot-reload is not configured:

```bash
# If running as a process
pkill -f "litellm" && litellm --config config.yaml --port 4000

# If running via Docker
docker restart <litellm-container-name>
```

### 2c. Verify ORBIT appears in the model list

```bash
curl http://localhost:4000/v1/models \
  -H "Authorization: Bearer YOUR_LITELLM_MASTER_KEY"
```

You should see `orbit` (and any other ORBIT adapter names you added) in the response.

### 2d. Send a test request through the proxy

```bash
curl http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_LITELLM_MASTER_KEY" \
  -d '{
    "model": "orbit-chat",
    "messages": [{"role": "user", "content": "What is ORBIT?"}]
  }'
```

### 2e. Use the LiteLLM UI (if enabled)

If you started LiteLLM with the UI enabled (`litellm --config config.yaml --ui`), open `http://localhost:4000/ui`. ORBIT will appear in the model dropdown after the config reload. You can send test messages directly from the UI without any code.

---

## Step 3 — Quick Test with the LiteLLM Python SDK (no proxy)

```python
import litellm

response = litellm.completion(
    model="openai/orbit",                        # prefix must be "openai/"
    messages=[{"role": "user", "content": "What is ORBIT?"}],
    api_base="http://localhost:3000/v1",
    api_key="orbit_YOUR_API_KEY_HERE",
)

print(response.choices[0].message.content)
```

### Streaming

```python
response = litellm.completion(
    model="openai/orbit",
    messages=[{"role": "user", "content": "Explain RAG in one paragraph."}],
    api_base="http://localhost:3000/v1",
    api_key="orbit_YOUR_API_KEY_HERE",
    stream=True,
)

for chunk in response:
    print(chunk.choices[0].delta.content or "", end="", flush=True)
```

### Async

```python
import asyncio
import litellm

async def main():
    response = await litellm.acompletion(
        model="openai/orbit",
        messages=[{"role": "user", "content": "Hello"}],
        api_base="http://localhost:3000/v1",
        api_key="orbit_YOUR_API_KEY_HERE",
    )
    print(response.choices[0].message.content)

asyncio.run(main())
```

---

## Step 4 — LiteLLM Proxy via Docker (fresh instance)

The LiteLLM proxy exposes an OpenAI-compatible API that routes to ORBIT (and any other provider). Any tool that supports OpenAI can point at the proxy instead.

### 4a. Prepare the proxy config

A ready-to-use config is included at the repo root: [`litellm-config.yaml`](../litellm-config.yaml). Fill in your API keys, then use it directly with either run option below.

> **Note (Docker):** `host.docker.internal` resolves to your laptop from inside a Docker container on Mac and Windows. On Linux, replace it with the host IP (e.g. `172.17.0.1`) or use `--network host` (see below).

### 4b. Start the proxy

**Option 1 — Standalone process** (LiteLLM installed via `pip install 'litellm[proxy]'`):

```bash
# Run from the repo root
litellm --config litellm-config.yaml --port 4000
```

**Option 2 — Docker (Mac/Windows)**:

```bash
# Run from the repo root
docker run \
  -v $(pwd)/litellm-config.yaml:/app/config.yaml \
  -p 4000:4000 \
  ghcr.io/berriai/litellm:main-latest \
  --config /app/config.yaml --port 4000 --num_workers 1
```

**Option 2 — Docker (Linux)**, using host networking so `localhost:3000` resolves to ORBIT on the host:

```bash
# In litellm-config.yaml set api_base to: http://localhost:3000/v1
docker run \
  --network host \
  -v $(pwd)/litellm-config.yaml:/app/config.yaml \
  ghcr.io/berriai/litellm:main-latest \
  --config /app/config.yaml --port 4000
```

The proxy is now listening at `http://localhost:4000`.

### 4c. Test the proxy

```bash
# The model name must match model_name in litellm-config.yaml (e.g. "orbit-chat"), not the adapter name.

# curl
curl http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer anything" \
  -d '{
    "model": "orbit-chat",
    "messages": [{"role": "user", "content": "What is ORBIT?"}]
  }'

# streaming
curl http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer anything" \
  -d '{
    "model": "orbit-chat",
    "messages": [{"role": "user", "content": "Explain RAG briefly."}],
    "stream": true
  }'
```

The proxy accepts any string as the Bearer token unless you configure `general_settings.master_key` in `litellm_config.yaml`.

### 4d. Use the proxy from Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:4000/v1",
    api_key="anything",                  # proxy handles real auth
)

response = client.chat.completions.create(
    model="orbit",
    messages=[{"role": "user", "content": "Hello from the proxy!"}],
)
print(response.choices[0].message.content)
```

---

## Optional: Minimal ORBIT Configuration for Inference-Only Use

When ORBIT is used purely as an LLM inference gateway via LiteLLM — no RAG, no conversation history, no threaded datasets — several subsystems can be disabled. This reduces startup time, eliminates background database writes, and keeps the logs clean.

Edit `config/config.yaml` and apply these changes alongside the Step 1 session-ID settings:

```yaml
# Step 1 settings (required for LiteLLM)
general:
  session_id:
    required: false

chat_history:
  enabled: false          # LiteLLM manages its own conversation history
  session:
    auto_generate: true   # Still needed so session-less requests don't error
    required: true
    header_name: "X-Session-ID"

# Additional settings safe to disable for inference-only use
conversation_threading:
  enabled: false          # Dataset caching for multi-turn RAG — not needed for passthrough

autocomplete:
  enabled: false          # Query suggestions based on intent templates — not applicable

language_detection:
  enabled: false          # Auto-detects user language for RAG boosting — not used by LiteLLM
```

Restart ORBIT after saving. These settings have no effect on `/v1/chat/completions` response content — they only control backend side-effects that don't apply to a simple inference proxy.

> **Keep enabled**: `internal_services.audit` (compliance trail), `fault_tolerance.circuit_breaker` (protects downstream LLM providers), and `auth` (API key validation). These are lightweight and apply to every request regardless of use case.

---

## Endpoint Reference

| Detail | Value |
|--------|-------|
| Base URL | `http://localhost:3000/v1` |
| Chat endpoint | `POST /v1/chat/completions` |
| Required header | `X-API-Key: orbit_xxx` |
| Conditional header | `X-Session-ID: <uuid>` (required unless `auto_generate: true`) |
| Streaming | SSE (`"stream": true`) |
| LiteLLM model prefix | `openai/` |

---

## Troubleshooting

**`401 Invalid or missing API key` from ORBIT**
The key is wrong or inactive. Verify with `./bin/orbit.sh key status --key orbit_xxx`.

**`Connection refused` from inside Docker**
`localhost` inside a container points to the container itself, not your laptop. Use `host.docker.internal` (Mac/Windows) or `--network host` (Linux).

**Model field is ignored**
ORBIT ignores the `model` field in the request body — the actual model is determined by the adapter tied to your API key. The `openai/orbit` prefix is only needed by LiteLLM's routing logic.

**Responses include an `orbit` field**
ORBIT adds an `orbit` extension object to responses (sources, metadata, threading). LiteLLM and the OpenAI SDK ignore unknown fields, so this is harmless.
