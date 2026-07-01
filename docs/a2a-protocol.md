# A2A Protocol Integration

ORBIT implements the [Google Agent-to-Agent (A2A) protocol](https://google.github.io/A2A/), allowing AI agents and orchestration frameworks to discover and invoke ORBIT as a peer agent using a standard JSON-RPC interface.

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/.well-known/agent.json` | Agent Card — machine-readable capability declaration |
| `POST` | `/a2a` | JSON-RPC 2.0 task management |

---

## Agent Card

`GET /.well-known/agent.json` returns a JSON document describing ORBIT's capabilities. Other A2A agents use this for discovery without any authentication.

```json
{
  "name": "ORBIT",
  "description": "Open Retrieval-Based Inference Toolkit — AI gateway with RAG, intent-SQL retrieval, and 37+ LLM provider support.",
  "url": "https://your-orbit-host",
  "version": "1.0.0",
  "capabilities": {
    "streaming": true,
    "pushNotifications": false,
    "stateTransitionHistory": false
  },
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "skills": [
    {
      "id": "hr",
      "name": "HR",
      "description": "HR queries",
      "inputModes": ["text/plain"],
      "outputModes": ["text/plain"]
    }
  ],
  "authentication": { "schemes": ["Bearer"] }
}
```

Skills are built dynamically from adapters that have `expose_as_skill: true` in their capabilities config. See [Skills](adapters/skills.md).

---

## Authentication

All task endpoints require a valid ORBIT API key passed as a Bearer token:

```
Authorization: Bearer <your-orbit-api-key>
```

The API key is resolved to an adapter name using the same mechanism as the REST and OpenAI-compatible endpoints. An invalid or revoked key returns `401`/`403`. If API-key enforcement is disabled in your deployment (no `api_key_service` configured), requests are accepted without a token and routed to the default adapter.

---

## JSON-RPC Methods

All requests to `POST /a2a` follow the JSON-RPC 2.0 envelope:

```json
{
  "jsonrpc": "2.0",
  "id": "request-id",
  "method": "tasks/send",
  "params": { ... }
}
```

### `tasks/send` — blocking

Sends a message and waits for the complete response.

**Request**

```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "method": "tasks/send",
  "params": {
    "id": "optional-task-id",
    "message": {
      "role": "user",
      "parts": [{ "type": "text", "text": "How many open positions do we have?" }]
    },
    "metadata": {
      "adapter": "hr"
    }
  }
}
```

`params.metadata.adapter` (or `metadata.skill`) overrides the adapter resolved from the API key for this task. Omit it to use the key's default adapter.

**Response**

```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "result": {
    "id": "optional-task-id",
    "status": { "state": "completed" },
    "history": [
      { "role": "user", "parts": [{ "type": "text", "text": "How many open positions do we have?" }] },
      { "role": "agent", "parts": [{ "type": "text", "text": "There are 12 open positions." }] }
    ],
    "artifacts": [
      {
        "name": "response",
        "parts": [{ "type": "text", "text": "There are 12 open positions." }],
        "metadata": { "sources": [ ... ] }
      }
    ]
  }
}
```

RAG sources are attached under `artifacts[0].metadata.sources` when the adapter performs retrieval.

---

### `tasks/sendSubscribe` — streaming SSE

Sends a message and streams back artifact chunks as Server-Sent Events. Each event is a JSON-RPC result frame.

**Request** — same shape as `tasks/send`.

**SSE event stream**

```
data: {"jsonrpc":"2.0","id":"1","result":{"id":"t1","status":{"state":"working"},"final":false}}

data: {"jsonrpc":"2.0","id":"1","result":{"id":"t1","artifact":{"name":"response","parts":[{"type":"text","text":"There are "}],"append":true,"lastChunk":false},"final":false}}

data: {"jsonrpc":"2.0","id":"1","result":{"id":"t1","artifact":{"name":"response","parts":[{"type":"text","text":"12 open positions."}],"append":true,"lastChunk":false},"final":false}}

data: {"jsonrpc":"2.0","id":"1","result":{"id":"t1","status":{"state":"completed"},"final":true}}
```

If the pipeline emits an error, the stream closes with a JSON-RPC error frame and the task is marked `failed`:

```
data: {"jsonrpc":"2.0","id":"1","error":{"code":-32000,"message":"Pipeline failed: ..."}}
```

---

### `tasks/get`

Retrieve a task by ID (tasks are stored in-memory per process).

```json
{ "jsonrpc": "2.0", "id": "2", "method": "tasks/get", "params": { "id": "t1" } }
```

Returns the full task object or `{"error": {"code": -32001, "message": "Task not found"}}`.

---

### `tasks/cancel`

Mark a task as canceled.

```json
{ "jsonrpc": "2.0", "id": "3", "method": "tasks/cancel", "params": { "id": "t1" } }
```

Returns the updated task with `status.state = "canceled"`.

---

## Task States

| State | Meaning |
|-------|---------|
| `submitted` | Task accepted, not yet started |
| `working` | Being processed |
| `completed` | Response ready |
| `failed` | Processing error — check the error frame or `status.message` |
| `canceled` | Canceled via `tasks/cancel` |

---

## Error Codes

| Code | Meaning |
|------|---------|
| `-32700` | Parse error — request body is not valid JSON |
| `-32600` | Invalid request — `jsonrpc` field missing or not `"2.0"` |
| `-32601` | Method not found |
| `-32602` | Invalid params — e.g. no text content in message parts |
| `-32001` | Task not found |
| `-32000` | Task execution error — LLM or pipeline failure |

---

## Relation to Other ORBIT Protocols

| Protocol | Endpoint | Use case |
|----------|----------|----------|
| REST | `POST /v1/chat` | Direct chat from your own clients |
| OpenAI-compatible | `POST /v1/chat/completions` | Drop-in replacement for OpenAI SDK |
| MCP | `/mcp` | Tool calls from MCP-aware agents |
| **A2A** | `/a2a` | Peer-to-peer agent orchestration |

All four protocols share the same adapter resolution and API-key authentication. An API key that grants access to the `hr` adapter works identically across all four.
