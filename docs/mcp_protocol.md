# MCP Protocol (ORBIT as an MCP Server)

ORBIT exposes its own REST API as an [MCP](https://modelcontextprotocol.io) server, so any MCP client (Claude Desktop, an IDE integration, another agent) can discover and call ORBIT's endpoints as tools — no separate integration code required.

> Looking for the other direction — ORBIT calling *external* MCP servers as a client? See [MCP Tool Calling](tutorial/mcp-tool-calling.md) and [MCP Agent Adapter](adapters/mcp-agent.md). This page is about ORBIT acting as the server.

## Endpoint

- **URL**: `POST /mcp` (Streamable HTTP transport)
- **Implementation**: [FastMCP](https://gofastmcp.com)'s `FastMCP.from_fastapi(...)`, which reflects every FastAPI route that declares an `operation_id` into an MCP tool. `POST /v1/chat` (`operation_id="chat"`) is exposed this way, so `chat` is always available as an MCP tool.
- **Advertised via A2A**: the [A2A](a2a-protocol.md) agent card includes `extensions.mcp_url` pointing at this endpoint.

## Connecting

```bash
# Handshake
curl -i -X POST http://localhost:3000/mcp \
  -H "Host: localhost" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2025-06-18",
      "capabilities": {},
      "clientInfo": {"name": "my-client", "version": "1.0"}
    }
  }'
```

A successful response includes an `mcp-session-id` header and a JSON-RPC result with the negotiated `protocolVersion` and server capabilities. Reuse the `mcp-session-id` header on subsequent requests in the same session (`tools/list`, `tools/call`, etc.), per the [MCP Streamable HTTP transport spec](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports).

## Capabilities

Currently only **tools** are exposed (one per `operation_id`-tagged FastAPI route). ORBIT does not define MCP resources, prompts, or sampling on this endpoint.

## Security

The `/mcp` mount bypasses ORBIT's normal `X-API-Key` middleware — MCP tool calls are unauthenticated at this layer. To guard against [DNS rebinding](https://github.com/modelcontextprotocol/typescript-sdk/security/advisories/GHSA-w48q-cv73-mx4w) (a malicious webpage using a hostname that resolves to `127.0.0.1` to reach a locally-running, unauthenticated MCP server through a victim's browser), ORBIT validates the `Host` and `Origin` headers on every `/mcp` request:

- Loopback hosts (`localhost`, `127.0.0.1`, `::1`) are always allowed.
- Any hostname listed in `security.cors.allowed_origins` (`config.yaml`) is allowed, for deployments that front `/mcp` with a real domain.
- Anything else is rejected with `400 Bad Request`.

This is implemented in `server/middleware/mcp_host_validation_middleware.py`.

## Conformance testing

ORBIT's `/mcp` endpoint can be validated against the official
[modelcontextprotocol/conformance](https://github.com/modelcontextprotocol/conformance)
suite — the same tool the MCP spec authors use to check SDK and server behavior
against the protocol (JSON-RPC framing, `initialize` handshake, capability
negotiation, `tools/list`/`tools/call` schemas, session headers, DNS-rebinding
protection, etc). It's a Node/TypeScript CLI, run via `npx` — no install step,
no changes to this repo's Python toolchain.

### Prerequisites

- Node.js (any recent LTS; the suite is fetched on demand via `npx`)
- A running ORBIT server reachable at its `/mcp` endpoint, e.g.:
  ```bash
  ./bin/orbit.sh start --config config/config.yaml
  ```

### Run the full server suite

```bash
npx @modelcontextprotocol/conformance server \
  --url http://localhost:3000/mcp \
  --expected-failures ./conformance-baseline.yml
```

- `server` — test mode; the suite also has a `client` mode for testing an MCP
  *client* implementation (not applicable here — see the note at the top of
  this page about ORBIT's client-side MCP support instead).
- `--url` — the endpoint under test.
- `--expected-failures ./conformance-baseline.yml` — see below.

### Run a single scenario (useful while debugging one failure)

```bash
npx @modelcontextprotocol/conformance server \
  --url http://localhost:3000/mcp \
  --scenario tools-list
```

### Other useful flags

| Flag | Purpose |
|---|---|
| `--suite active\|all\|draft\|pending` | Which scenario group to run (default `active`) |
| `--spec-version 2025-11-25\|2026-07-28\|draft` | Target a specific MCP spec revision |
| `--timeout <ms>` | Per-scenario timeout (default 30000) |

Results are written to `results/server-<scenario>-<timestamp>/checks.json` for each run — useful for diffing what changed between two invocations.

### The `conformance-baseline.yml` file (repo root)

This is an **expected-failures allowlist**, a feature built into the conformance CLI itself (`--expected-failures <file>`). Some of the suite's server scenarios assume you've hand-built an "everything server" exposing specific named fixtures — a resource at `test://static-text`, a tool called `test_image_content`, a prompt named `test_prompt_with_arguments`, and so on. ORBIT doesn't do this: its MCP tools are auto-generated by reflecting FastAPI routes (`FastMCP.from_fastapi`, see [Endpoint](#endpoint) above), so those fixture-specific scenarios fail — not because of a protocol violation, but because the fixture doesn't exist to test against.

Listing a scenario in this file tells the CLI "this is a known, explained gap — don't fail CI on it, but do tell me if a *new* scenario starts failing." Format:

```yaml
server:
  - some-scenario-name
client: []
```

Each entry in the checked-in file has an inline comment explaining why it's there. Two rules for maintaining it:

- **Never add a scenario to silence a genuine spec violation.** Investigate and fix the underlying bug instead — that's what happened with `dns-rebinding-protection`, which is deliberately *not* in this file (see [Security](#security) above).
- **Re-run without `--expected-failures` periodically.** If ORBIT ever adds real MCP resources/prompts, some baselined scenarios may start passing — remove them when they do, so the baseline doesn't quietly mask new capability.

### CI integration (not yet wired up)

There is no `.github/workflows/` in this repo today. If/when one is added, the conformance suite ships a ready-made GitHub Action:

```yaml
- uses: modelcontextprotocol/conformance@v0.1.16
  with:
    mode: server
    url: http://localhost:3000/mcp
    expected-failures: ./conformance-baseline.yml
```

(pin to whatever release is current at [github.com/modelcontextprotocol/conformance/releases](https://github.com/modelcontextprotocol/conformance/releases) — `v0.1.16` was latest as of this writing).
