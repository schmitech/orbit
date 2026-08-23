# Using ORBIT from Claude

There are two supported ways to connect Claude to ORBIT, depending on which side is driving:

| | Claude calls ORBIT | ORBIT and Claude as peer agents |
|---|---|---|
| **Protocol** | [MCP](mcp_protocol.md) | [A2A](a2a-protocol.md) |
| **Use when** | You want Claude (Desktop, Code, or an SDK-based agent) to call ORBIT's `chat` endpoint as a tool mid-conversation | You're building a Claude-based agent that delegates whole tasks to ORBIT and lets it run independently (multi-turn, streaming, cancellable) |
| **Direction** | Claude → ORBIT, synchronous tool call | Claude's agent ↔ ORBIT, JSON-RPC task lifecycle |
| **Auth** | None at the `/mcp` mount (see caveat below) | `Authorization: Bearer <api-key>` |

If you're not sure which you need: MCP is the simpler, faster path for "let Claude ask ORBIT things." A2A is for when ORBIT needs to be addressable as its own agent — with its own task IDs, streaming, and cancellation — inside a larger multi-agent system.

---

## Option 1: MCP — ORBIT as a tool Claude calls

ORBIT mounts a full MCP server at `/mcp` (see [MCP Protocol](mcp_protocol.md) for the underlying implementation). Any MCP client, including Claude Desktop and Claude Code, can connect to it directly — no example code required.

### Claude Desktop / Claude Code

Add ORBIT to your MCP server config (Claude Desktop: `claude_desktop_config.json`; Claude Code: `.mcp.json` or via `claude mcp add`):

```json
{
  "mcpServers": {
    "orbit": {
      "url": "http://localhost:3000/mcp",
      "type": "http"
    }
  }
}
```

Or from the Claude Code CLI:

```bash
claude mcp add --transport http orbit http://localhost:3000/mcp
```

Once connected, Claude can call ORBIT's `chat` tool (and any other `operation_id`-tagged route) directly in the conversation — ask it something that needs ORBIT's RAG/retrieval, and it will route the call through MCP automatically.

### Important caveats

- **No authentication at this layer.** The `/mcp` mount bypasses ORBIT's normal `X-API-Key` middleware entirely. Only point Claude at an ORBIT instance you trust on your network — see [Security](mcp_protocol.md#security) for the DNS-rebinding protections that are in place instead.
- **Won't start with `auth.require_authenticated_user` enabled.** If your `config.yaml` requires authenticated users everywhere, ORBIT refuses to mount `/mcp` at startup (there's no request-scoped identity to check at that layer) and logs a warning instead.
- Only `chat` is exposed as a tool today — MCP resources, prompts, and sampling are not implemented.

---

## Option 2: A2A — ORBIT as a peer agent

Use this when a Claude-based agent needs to hand off a task to ORBIT and treat it as another agent in the system, rather than a single tool call. ORBIT implements Google's [A2A protocol](https://google.github.io/A2A/) at `POST /a2a`, with discovery at `GET /.well-known/agent.json`. Full protocol details, the Agent Card schema, and authentication are in [A2A Protocol Integration](a2a-protocol.md).

Working clients are in [`examples/a2a-protocol/`](../examples/a2a-protocol/):

- `a2a_client.py` / `a2a_client.js` — dependency-free clients covering discovery, blocking and streaming task submission, task lookup, and cancellation.
- `python_a2a_client.py` — the same, built on the [`python-a2a`](https://pypi.org/project/python-a2a/) package's typed `A2AClient`/`Message` API and Agent Card discovery.

A Claude agent (via the Agent SDK, a custom tool, or a subprocess call) can drive any of these to:

1. Discover ORBIT's skills: `python a2a_client.py --discover`
2. Submit a task, optionally to a specific skill/adapter: `python a2a_client.py "..." --adapter hr`
3. Stream the response as it's produced: `python a2a_client.py "..." --stream`
4. Check status or cancel by task ID: `python a2a_client.py --get <task-id>` / `--cancel <task-id>`

Set `ORBIT_API_URL` and `ORBIT_API_KEY` (and `ORBIT_USER_TOKEN` if the key is restricted to a specific user) as shown in [`examples/a2a-protocol/README.md`](../examples/a2a-protocol/README.md).

Unlike MCP, every A2A call is authenticated with a real ORBIT API key, so this path is appropriate for exposing ORBIT to agents outside your own trusted network.
