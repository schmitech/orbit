# MCP Agent Skill

## Overview

The **MCP agent** skill (`mcp-agent`) lets ORBIT connect *outward* to external [Model Context Protocol](https://modelcontextprotocol.io) (MCP) servers, discover their tools, and let the LLM call them in a multi-step agentic loop — all within a single request.

Concretely: the user asks a question, the model decides to call an MCP tool (e.g. a GitHub server's `search_issues`, a filesystem server's `read_file`), ORBIT executes it, feeds the result back to the model, and repeats until the model produces a final answer. Tool invocations are surfaced in the `sources` array of the response for transparency.

This is the inverse of ORBIT's existing MCP *server* role (which exposes ORBIT's own tools to external clients). The MCP agent skill makes ORBIT an MCP *client*.

Key properties:

- **Agentic loop** — the model may call multiple tools across several rounds before answering (bounded by `max_tool_iterations`).
- **Provider-agnostic** — works with any inference provider that supports native tool calling: `openai`, `anthropic`, `gemini`, `xai`.
- **Skill-based routing** — exposed as the `mcp-agent` skill; any adapter that lists it in `available_skills` can invoke it.
- **Admin-configured servers** — MCP server URLs/commands are set in `config/mcp_client.yaml`, never supplied at request time.

---

## How It Works

```
Client: POST /v1/chat
  { "messages": [...], "skill": "mcp-agent" }
  X-API-Key: <key for an adapter with mcp-agent in available_skills>

   1. API key authenticates → adapter = "simple-chat"
   2. RequestContextBuilder detects skill="mcp-agent"
   3. Checks: "mcp-agent" ∈ simple-chat's available_skills  ✓
   4. Skill swap: context.adapter_name = "mcp-agent-chat"
   5. Pipeline runs as "mcp-agent-chat":
        MCPAgentStep executes (adapter type = mcp_agent)
        LLMInferenceStep is skipped
   6. MCPAgentStep loop:
        a. Discover tools from configured MCP servers
        b. Call provider.generate_with_tools(messages, tools)
        c. If tool_calls → execute each via MCP, append results → go to b
        d. If final text → done
   7. Response: { "response": "...", "sources": [{...}] }
```

Tool names are namespaced as `<server_name>__<tool_name>` (e.g. `github__search_issues`) to avoid collisions across servers.

---

## Prerequisites

1. **ORBIT version** — requires the `mcp_agent` adapter type, `MCPAgentStep`, and `generate_with_tools` provider methods (see [Implementation Reference](#implementation-reference)).
2. **Inference provider** — the `mcp-agent-chat` adapter must point to a provider with native tool calling: `openai`, `anthropic`, `gemini`, or `xai`.
3. **`mcp` Python SDK** — already a dependency (`mcp` ≥ 1.27.1).
4. **MCP server runtime** — for stdio servers (e.g. `@modelcontextprotocol/server-github`), `npx` or the appropriate runtime must be on `$PATH`.

---

## Configuration

### Step 1 — Enable MCP and configure servers (`config/mcp_client.yaml`)

```yaml
mcp_client:
  enabled: true

  tool_timeout: 30          # seconds before a tool call is aborted
  max_tool_iterations: 5    # maximum tool-calling rounds per request

  servers:
    - name: "github"
      transport: "stdio"
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-github"]
      env:
        GITHUB_TOKEN: "${GITHUB_TOKEN}"   # expanded at runtime from environment
      enabled: true

    - name: "docs-search"
      transport: "sse"
      url: "https://mcp.example.com/sse"
      headers:
        Authorization: "Bearer ${INTERNAL_MCP_TOKEN}"
      enabled: true
```

Each server entry supports two transports:

| Transport | When to use | Required fields |
|-----------|-------------|-----------------|
| `stdio` | Local subprocess (npx, uvx, python -m …) | `command`, optionally `args`, `env` |
| `sse` | Remote HTTP/SSE endpoint | `url`, optionally `headers` |

Secret values should always use `${ENV_VAR}` syntax — they are expanded at startup and never written to logs.

> **Import into main config** — if `mcp_client.yaml` is a standalone file, import it from `config/config.yaml`:
>
> ```yaml
> import:
>   - "mcp_client.yaml"
> ```

### Step 2 — Choose inference provider (`config/adapters/mcp-agent.yaml`)

Edit the pre-shipped adapter file to point at the provider and model you want to use for the tool-calling loop:

```yaml
adapters:
  - name: "mcp-agent-chat"
    enabled: true
    type: "mcp_agent"
    datasource: "none"
    adapter: "conversational"
    implementation: "implementations.passthrough.conversational.ConversationalImplementation"
    inference_provider: "openai"    # openai | anthropic | gemini | xai
    model: "gpt-4.1-mini"

    capabilities:
      expose_as_skill: true
      skill_name: "mcp-agent"
      skill_description: "Use external MCP server tools to answer (agentic tool calling)"
      retrieval_behavior: "none"
      formatting_style: "standard"
      requires_api_key_validation: false
      # Optional: restrict which servers this adapter may call.
      # Omit to allow all enabled servers.
      # mcp_servers:
      #   - "github"
```

The `mcp_servers` allowlist under `capabilities` is optional. When present, the step only passes tools from those servers to the model — useful if you have multiple skill adapters that should each access a different subset of servers.

### Step 3 — Register the adapter (`config/adapters.yaml`)

The import is already added:

```yaml
import:
  - "adapters/mcp-agent.yaml"
```

### Step 4 — Allow the skill on consumer adapters

Add `"mcp-agent"` to the `available_skills` list of any adapter whose users should be able to invoke it:

```yaml
- name: "simple-chat"
  ...
  capabilities:
    available_skills:
      - "image-generation"
      - "web-search"
      - "mcp-agent"       # ← add this
```

---

## Examples

### Filesystem — list the repo root

The simplest test. Requires `@modelcontextprotocol/server-filesystem` configured in `mcp_client.yaml`.

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -H "X-Session-ID: <session-id>" \
  -d '{
    "messages": [
      {"role": "user", "content": "What files are in the root of the orbit repo?"}
    ],
    "skill": "mcp-agent"
  }'
```

**Response:**

```json
{
  "response": "The root of the orbit repo contains the following files and directories:\n\nFiles:\n- .env\n- .gitignore\n- CHANGELOG.md\n- CLAUDE.md\n- README.md\n- ruff.toml\n...\n\nDirectories:\n- bin\n- config\n- docs\n- server\n- ...",
  "sources": [
    {
      "type": "mcp_tool_call",
      "tool": "filesystem__list_directory",
      "arguments": {"path": "/Users/youruser/orbit"},
      "result_preview": "[DIR] bin\n[DIR] config\n[FILE] README.md\n..."
    }
  ]
}
```

> **Note on self-correction:** If the model first attempts `path: "/"` (outside the allowed directory), the MCP server returns an access-denied error. The model receives this as a tool result and automatically retries with the correct absolute path. This is normal agentic behaviour — errors from tools are fed back into the loop rather than surfacing as API errors.

---

### Filesystem — read and summarize a file

Two-step: the model first lists the directory to confirm the file exists, then reads it.

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -H "X-Session-ID: <session-id>" \
  -d '{
    "messages": [
      {"role": "user", "content": "What does CONTRIBUTING.md say about running tests?"}
    ],
    "skill": "mcp-agent"
  }'
```

The `sources` array will show a `filesystem__read_file` call:

```json
"sources": [
  {
    "type": "mcp_tool_call",
    "tool": "filesystem__read_file",
    "arguments": {"path": "/Users/youruser/orbit/CONTRIBUTING.md"},
    "result_preview": "# Contributing to ORBIT\n\n## Running Tests\n\n```bash\n..."
  }
]
```

---

### Filesystem — multi-step exploration

The model can chain directory listings and file reads autonomously.

```bash
-d '{
  "messages": [
    {"role": "user", "content": "Find all YAML files in the config directory and tell me which adapters are enabled"}
  ],
  "skill": "mcp-agent"
}'
```

Typical loop:
```
Round 1 → filesystem__list_directory(path=".../config")
Round 2 → filesystem__list_directory(path=".../config/adapters")
Round 3 → filesystem__read_file(path=".../config/adapters/passthrough.yaml")
Round 4 → final answer
```

---

### Filesystem — compare two files

```bash
-d '{
  "messages": [
    {"role": "user", "content": "Compare the adapter configs for web-search and mcp-agent. What are the key differences?"}
  ],
  "skill": "mcp-agent"
}'
```

The model reads both files in separate tool calls and synthesizes a comparison.

---

### GitHub — list open bugs (requires `GITHUB_TOKEN`)

Once the GitHub MCP server is configured and `GITHUB_TOKEN` is set:

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -H "X-Session-ID: <session-id>" \
  -d '{
    "messages": [
      {"role": "user", "content": "How many open issues labeled bug are in the schmitech/orbit repo?"}
    ],
    "skill": "mcp-agent"
  }'
```

**Response:**

```json
{
  "response": "There are 3 open issues labeled 'bug' in schmitech/orbit: ...",
  "sources": [
    {
      "type": "mcp_tool_call",
      "tool": "github__search_issues",
      "arguments": {"owner": "schmitech", "repo": "orbit", "labels": ["bug"], "state": "open"},
      "result_preview": "[{\"number\": 42, \"title\": \"Fix streaming timeout\"}, ...]"
    }
  ]
}
```

---

### GitHub — multi-step issue investigation

```bash
-d '{
  "messages": [
    {"role": "user", "content": "Find open bugs in schmitech/orbit and check if any of them reference issue #100"}
  ],
  "skill": "mcp-agent"
}'
```

```
Round 1 → github__search_issues(owner=schmitech, repo=orbit, labels=[bug], state=open)
Round 2 → github__get_issue(owner=schmitech, repo=orbit, issue_number=100)
Round 3 → final answer
```

---

### Streaming response

All of the above work with `"stream": true`. Tool calls still happen server-side before the first text chunk.

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -H "X-Session-ID: <session-id>" \
  -d '{
    "messages": [{"role": "user", "content": "Summarize the README.md"}],
    "skill": "mcp-agent",
    "stream": true
  }'
```

```
data: {"response": "ORBIT (Open Retrieval-Based Inference Toolkit) is", "done": false}
data: {"response": " a self-hosted AI gateway...", "done": false}
data: {"done": true, "sources": [{"type": "mcp_tool_call", "tool": "filesystem__read_file", ...}]}
```

The `sources` array appears in the final `{"done": true}` chunk.

---

## Multi-step Tool Calls

A single request may involve several tool-calling rounds. Each round appends the tool result to the conversation before the next model call. The loop is bounded by `max_tool_iterations` (default 5); if that limit is reached without a final answer, one last model call is made to synthesize a response from the accumulated context.

The model handles tool errors gracefully — if a tool call fails (access denied, network error, etc.), the error message is injected into the conversation and the model can retry with corrected arguments or explain the limitation in its final answer.

---

## How Tool Selection Works

There is no hardcoded routing or keyword matching in ORBIT. The model receives every available tool schema and decides on its own which tool to call, what arguments to pass, and whether to chain tools across multiple rounds.

### What the model sees

On every call to `generate_with_tools`, ORBIT sends the full list of available tool schemas alongside the conversation messages:

```json
{
  "messages": [...],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "filesystem__list_directory",
        "description": "Get the contents of a directory at the specified path...",
        "parameters": {
          "type": "object",
          "properties": {
            "path": { "type": "string", "description": "Absolute path to the directory" }
          },
          "required": ["path"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "filesystem__read_file",
        "description": "Read the complete contents of a file at the specified path...",
        ...
      }
    },
    {
      "type": "function",
      "function": {
        "name": "github__search_issues",
        ...
      }
    }
  ]
}
```

The model reads the descriptions and parameter schemas and selects the best-fitting tool — or no tool, if it can answer directly. ORBIT executes the selection and feeds the result back. All reasoning happens inside the model.

### What drives good (or bad) tool selection

| Factor | Impact |
|--------|--------|
| **Tool description quality** | The MCP server's description is what the model reads. Vague descriptions lead to wrong picks or missed tools — this is the single biggest lever and it's set by the MCP server, not ORBIT |
| **Number of tools visible** | More tools = more tokens consumed per round + higher chance of confusion when tools overlap. Use the `mcp_servers` allowlist to scope what the model sees |
| **Model capability** | GPT-4.1, Claude Sonnet, and Gemini Pro reliably select correct tools in complex multi-step scenarios. Smaller models (GPT-4.1-mini, Gemma 4 E2B, llama.cpp direct) are less reliable when many tools are available or the query is ambiguous |
| **System prompt** | You can guide tool preference in the adapter's system prompt: *"When asked about files, use the filesystem tools. When asked about code, use the GitHub tools."* |
| **Query specificity** | `"List files in /config"` → deterministic single-tool call. `"Tell me about the project"` → the model may explore with multiple tools across several rounds |

### Exploratory behaviour

The model often uses one tool to orient itself before calling a more targeted one. This is intentional and expected — it mirrors how a developer would navigate an unfamiliar codebase. In the live test earlier:

```
Query: "What files are in the root of the orbit repo?"

Round 1 → filesystem__list_directory(path="/")          ← access denied
Round 2 → filesystem__list_directory(path="/Users/.../orbit")  ← correct
Round 3 → final answer
```

The model received the access-denied error as a tool result and corrected its own argument on the next round, without any intervention from ORBIT.

### Scoping tools with the `mcp_servers` allowlist

If you have multiple servers configured, every tool from every server is visible to the model by default. For a query like *"what's in the config directory?"* the model will likely pick the right tool, but it's burning tokens on irrelevant GitHub and Slack schemas.

Scope what the model sees using `mcp_servers` in the adapter config:

```yaml
# config/adapters/mcp-agent.yaml
capabilities:
  mcp_servers:
    - "filesystem"   # model only sees filesystem tools for this adapter
```

You can run multiple skill adapters with different scopes and expose each one as a separate skill:

```yaml
# filesystem-only skill adapter
- name: "mcp-files-chat"
  type: "mcp_agent"
  capabilities:
    skill_name: "mcp-files"
    mcp_servers: ["filesystem"]

# GitHub-only skill adapter
- name: "mcp-github-chat"
  type: "mcp_agent"
  capabilities:
    skill_name: "mcp-github"
    mcp_servers: ["github"]
```

This keeps context windows lean and makes tool selection more deterministic.

### Model recommendations by use case

| Use case | Recommended provider/model |
|----------|---------------------------|
| Complex multi-server, multi-step tasks | `openai` / `gpt-4.1`, `anthropic` / `claude-sonnet-4-6` |
| Single-server tasks, cost-sensitive | `openai` / `gpt-4.1-mini`, `gemini` / `gemini-3.1-flash` |
| Private / offline, API mode (llama-server) | `llama_cpp` / `gemma4-e2b-api` |
| Private / offline, direct mode | `llama_cpp` / `gemma4-e2b-direct-cpu` *(less reliable on complex tool selection)* |

---

## Security Considerations

MCP servers can execute arbitrary commands (stdio) or reach external networks (SSE). ORBIT treats them as privileged:

- **Admin-only configuration.** Server URLs and commands are set in YAML, never accepted from request bodies.
- **Per-adapter allowlist.** The `mcp_servers` capability limits which servers a given skill adapter can reach.
- **Secrets via environment variables.** Use `${VAR}` — values are never logged or included in responses.
- **Timeouts and iteration cap.** `tool_timeout` aborts hung calls; `max_tool_iterations` bounds cost and loop risk.
- **Result truncation.** Tool result previews in `sources` are capped at 2 000 characters to prevent leaking large payloads.
- **Prompt-injection risk.** Tool results are untrusted text injected into the model context. Keep MCP servers narrowly scoped and consider result size limits for production deployments.

---

## Troubleshooting

### "MCP client is not enabled"

Set `mcp_client.enabled: true` in `config/mcp_client.yaml` (or wherever `mcp_client` is configured).

### "No MCP tools available"

- Check that at least one server entry has `enabled: true`.
- For stdio servers, verify the command is on `$PATH` (e.g. `which npx`).
- Check server startup logs — the manager logs `MCP server '<name>': discovered N tools` on first use.

### Tool calls time out

Increase `tool_timeout`. For stdio servers using `npx -y`, the first call may be slow due to npm package download; subsequent calls (with a warm npm cache) are faster.

### Model calls the wrong tool or ignores tools entirely

- **Too many tools:** scope the adapter to fewer servers with `mcp_servers` in capabilities.
- **Weak tool descriptions:** the MCP server's `description` field drives selection — nothing in ORBIT can compensate for a vague description. Check what `list_tools()` returns from the server.
- **Model too small:** switch to a larger model. Tool selection is a reasoning task — GPT-4.1-mini and Gemma 4 E2B struggle when multiple tools have overlapping descriptions.
- **System prompt:** add tool-use hints to the adapter's system prompt to steer the model.

### "generate_with_tools not implemented" error

The configured `inference_provider` does not support native tool calling. Use one of: `openai`, `anthropic`, `gemini`, `xai`, or `llama_cpp` (api mode recommended).

### Tool results look wrong / server errors

The MCP server returns `isError: true`. The error message is passed back to the model as the tool result, so the model can acknowledge the failure in its final answer. Check the server-side logs for the underlying cause.

---

## Implementation Reference

| Component | File | Role |
|-----------|------|------|
| MCP client manager | `server/services/mcp_client_service.py` | Singleton; connects to servers, caches tool schemas, executes `call_tool` |
| Agent pipeline step | `server/inference/pipeline/steps/mcp_agent.py` | `MCPAgentStep`; runs bounded tool-calling loop, streams final answer |
| LLM step guard | `server/inference/pipeline/steps/llm_inference.py` | Skips LLM for `type == mcp_agent` (line ~78) |
| Pipeline registration | `server/inference/pipeline/pipeline.py` | `MCPAgentStep` added before `ImageGenerationStep` |
| `ToolCallingResult` | `server/ai_services/services/inference_service.py` | Normalized result type returned by `generate_with_tools` |
| OpenAI tool calling | `server/ai_services/implementations/inference/openai_inference_service.py` | `generate_with_tools` via `chat.completions` |
| Anthropic tool calling | `server/ai_services/implementations/inference/anthropic_inference_service.py` | `generate_with_tools` + OpenAI↔Anthropic message conversion |
| Gemini tool calling | `server/ai_services/implementations/inference/gemini_inference_service.py` | `generate_with_tools` via `FunctionDeclaration` |
| xAI tool calling | `server/ai_services/implementations/inference/xai_inference_service.py` | `generate_with_tools` (OpenAI-compatible) |
| Skill adapter config | `config/adapters/mcp-agent.yaml` | `mcp-agent-chat` adapter; exposes as `mcp-agent` skill |
| Server config template | `config/mcp_client.yaml` | Example server definitions |
| Adapter registry | `config/adapters.yaml` | Imports `mcp-agent.yaml` |
| Design document | `docs/adapters/mcp-client-skill.md` | Original architecture design and phased plan |

### `ProcessingContext` additions

| Field | Type | Description |
|-------|------|-------------|
| `sources` | `List[Dict]` | Populated by `MCPAgentStep` with one entry per tool call: `{type, tool, arguments, result_preview}` |

### `ToolCallingResult` fields

| Field | Type | Description |
|-------|------|-------------|
| `text` | `Optional[str]` | Final model answer (`None` when the model made tool calls) |
| `tool_calls` | `Optional[List[Dict]]` | Parsed tool calls: `[{id, name, arguments}]` |
| `assistant_message` | `Dict` | OpenAI-format message to append to the conversation history |
| `finish_reason` | `str` | Provider stop reason (`"stop"`, `"tool_calls"`, etc.) |

---

## Future Work

- **Persistent MCP connections** — the current implementation opens a fresh connection per tool call (per-request for SSE, per-call subprocess for stdio). A persistent connection pool with reconnect logic would eliminate subprocess startup overhead.
- **Human-in-the-loop approval** — annotate tools as read-only vs. write, and surface a confirmation step for state-changing calls.
- **Resources and prompts** — v1 supports tools only. `list_resources` and `list_prompts` are future additions.
- **User-supplied MCP servers** — v1 restricts server configuration to admins. Allowing trusted users to supply their own servers at request time is a future capability.
- **Streaming tool-call progress events** — emit an SSE event for each tool invocation so the client can show "Calling github__search_issues…" in the UI before the final answer arrives.
