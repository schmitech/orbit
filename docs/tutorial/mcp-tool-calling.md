# Example 10: Opportunistic MCP Tool Calling

Beyond the templated function-calling in [Example 8](agent-function-calling.md), any conversational adapter can let the model decide, turn by turn, whether to call an external MCP tool — no `skill` field, no adapter swap, same thread throughout. This example wires up the bundled sample CRM server and turns it on for `simple-chat`.

### How it works

1. ORBIT connects to configured MCP servers at startup and discovers their tools.
2. On each turn, if the adapter has `mcp_tools: true`, the model is offered those tools via the provider's native function-calling.
3. The model decides — call zero, one, or several tools — and ORBIT feeds tool results back until it has a final answer.
4. Ordinary questions that don't need a tool get a normal conversational answer; no tool is forced.

### 1. Start the sample MCP server

The repo ships a small synthetic CRM server (customers, opportunities, pipeline data) for testing:

```bash
cd examples/mcp-server
npm install
MCP_TOKEN=test-secret npm start
```

This listens at `http://127.0.0.1:9999/mcp`. Leave it running in its own terminal.

### 2. Point ORBIT at it

`config/mcp_client.yaml` already declares this server as `business-sample` with `mcp_client.enabled: true` and `allow_opportunistic: true` (the global gate — required in addition to the per-adapter flag below):

```yaml
mcp_client:
  enabled: true
  allow_opportunistic: true
  servers:
    - name: "business-sample"
      transport: "http"
      url: "http://127.0.0.1:9999/mcp"
      token: "${MCP_TOKEN}"
      enabled: true
```

Export the same token in the terminal where ORBIT runs:

```bash
export MCP_TOKEN=test-secret
```

### 3. Turn on the capability for an adapter

In [`config/adapters/passthrough.yaml`](../../config/adapters/passthrough.yaml), `simple-chat` already lists `business-sample` under `mcp_servers` — flip `mcp_tools` to `true` to actually let the model use it:

```yaml
capabilities:
  mcp_tools: true          # was false — set this to true
  mcp_servers:
    - "business-sample"
```

`simple-chat` uses `inference_provider: "openai"`, which supports native tool calling, so no provider change is needed. Restart ORBIT after saving.

### 4. Create an API key (or reuse your first-chat key)

If you already created a `simple-chat` key in [Your first chat](first-chat.md), reuse it. Otherwise, open `http://localhost:3000/admin` → **API Keys** → **+ Create**, pick `simple-chat`, name it, and save.

### 5. Try it

With no `skill` field:

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: orbit_YOUR_KEY" \
  -d '{"messages": [{"role": "user", "content": "List the top Enterprise customers in EMEA and summarize renewal risk."}]}'
```

Or from OrbitChat:

```bash
ORBIT_ADAPTER_KEYS='{"simple-chat":"orbit_YOUR_KEY"}' orbitchat --open
```

> "Find open Negotiation opportunities over $100k and group them by owner."

Confirm:
- The response includes tool-derived customer/opportunity data.
- `sources` contains an `mcp_tool_call` entry (e.g. `business-sample__search_opportunities`).
- A follow-up that doesn't need live data (e.g. "What is retrieval-augmented generation?") gets a plain conversational answer with no `sources` — the model isn't forced to call a tool every turn.

### What happens internally

1. The API key authenticates as `simple-chat`; the adapter's `mcp_tools`/`mcp_servers` capabilities are read.
2. Both gates are checked: `mcp_client.allow_opportunistic` (global) and the adapter's `mcp_tools` (per-adapter).
3. The model is offered the discovered tools from `business-sample` alongside the conversation.
4. If it calls a tool, the result is fed back and the loop continues (up to `max_tool_iterations`) until a final answer.
5. No adapter swap occurs — this is the same conversational thread throughout, unlike the explicit `mcp-agent` skill.

See [MCP Agent Skill: Opportunistic Mode](../adapters/mcp-agent.md#opportunistic-mode-mcp_tools-capability) for the full design, and [`docs/adapters/playbook-mcp-tool-loop.md`](../adapters/playbook-mcp-tool-loop.md) for multi-step tool chaining, error handling, the `mcp_servers` allowlist, and provider-fallback edge cases.

---

[Tutorial home](../tutorial.md) | [Previous: Example 9: Skills and Image Generation](skills-image-generation.md) | [Next: Example 11: Web Search and Automatic Skill Routing](auto-skill-routing.md)

---
