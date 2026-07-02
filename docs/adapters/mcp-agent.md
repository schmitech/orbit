# MCP Agent Skill

## Overview

The **MCP agent** skill (`mcp-agent`) lets ORBIT connect *outward* to external [Model Context Protocol](https://modelcontextprotocol.io) (MCP) servers, discover their tools, and let the LLM call them in a multi-step agentic loop — all within a single request.

Concretely: the user asks a question, the model decides to call an MCP tool (e.g. a GitHub server's `search_issues`, a filesystem server's `read_file`), ORBIT executes it, feeds the result back to the model, and repeats until the model produces a final answer. Tool invocations are surfaced in the `sources` array of the response for transparency.

This is the inverse of ORBIT's existing MCP *server* role (which exposes ORBIT's own tools to external clients). The MCP agent skill makes ORBIT an MCP *client*.

Key properties:

- **Agentic loop** — the model may call multiple tools across several rounds before answering (bounded by `max_tool_iterations`).
- **Provider-agnostic** — works with any inference provider that supports native tool calling: `openai`, `anthropic`, `gemini`, `xai`, `ollama`, `ollama_cloud`, `llama_cpp`, and `vllm` (see [Supported Inference Providers](#supported-inference-providers)).
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

## Supported Inference Providers

The tool-calling loop works with any provider that implements `generate_with_tools`. A provider that doesn't will raise a clear `generate_with_tools not implemented` error at request time.

| Provider | Tool calling | Notes |
|----------|--------------|-------|
| `openai` | ✅ | `chat.completions` with `tools` + `tool_choice="auto"` |
| `anthropic` | ✅ | Messages API; OpenAI↔Anthropic message conversion handled internally |
| `gemini` | ✅ | `FunctionDeclaration`; strips JSON-Schema meta-fields and preserves thinking signatures across rounds |
| `xai` | ✅ | OpenAI-compatible (Grok) |
| `ollama` | ✅ | `/api/chat` with `tools=`. Requires a **tool-capable model** — e.g. `qwen2.5`, `qwen3`/`qwen3.5`, `llama3.1+`, `mistral-nemo`, or `functiongemma`. Models without a tool template just return plain text (the loop exits cleanly). |
| `ollama_cloud` | ✅ | Managed Ollama Cloud via the `ollama` SDK. Same tool-capable-model requirement; `gpt-oss` works well. |
| `llama_cpp` | ✅ API · ⚠️ direct | **API mode** (llama-server, OpenAI-compatible) recommended. **Direct mode** (in-process GGUF) only works for chat formats that implement function calling; with a plain `chatml` format the model ignores tool schemas. |
| `vllm` | ✅ API only | **API mode** requires the vLLM server be started with `--enable-auto-tool-choice --tool-call-parser <parser>` (e.g. `hermes`, `llama3_json`, `mistral`). **Direct/in-process mode is not supported** and raises `NotImplementedError`. |

> **Model capability matters as much as provider support.** Tool selection is a reasoning task. The hosted frontier models (`gpt-4.1`, `claude-sonnet-4-6`, `gemini-3.1-pro`) are the most reliable at picking the right tool and chaining calls. Small local models (functiongemma, Gemma 4 E2B, 1–4B Ollama models) work but are less reliable when many tools are visible or the query is ambiguous — scope them with `mcp_servers` (see [Scoping tools](#scoping-tools-with-the-mcp_servers-allowlist)).

---

## Prerequisites

1. **ORBIT version** — requires the `mcp_agent` adapter type, `MCPAgentStep`, and `generate_with_tools` provider methods (see [Implementation Reference](#implementation-reference)).
2. **Inference provider** — the `mcp-agent-chat` adapter must point to a provider with native tool calling: `openai`, `anthropic`, `gemini`, `xai`, `ollama`, `ollama_cloud`, `llama_cpp` (API mode), or `vllm` (API mode). See [Supported Inference Providers](#supported-inference-providers).
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

    - name: "my-http-server"
      transport: "http"
      url: "http://127.0.0.1:9999/mcp"
      token: "${MCP_TOKEN}"          # shorthand for Authorization: Bearer <value>
      enabled: true
```

Each server entry supports three transports:

| Transport | When to use | Required fields |
|-----------|-------------|-----------------|
| `stdio` | Local subprocess (npx, uvx, python -m …) | `command`, optionally `args`, `env` |
| `sse` | Remote SSE endpoint | `url`, optionally `headers` |
| `http` | Remote Streamable HTTP endpoint (MCP spec §4.2) | `url`, optionally `token` or `headers` |

**`http` transport specifics** — uses the MCP Streamable HTTP protocol (POST + optional SSE response). ORBIT automatically adds `Accept: application/json, text/event-stream`. Bearer-token auth can be configured with the `token` shorthand instead of writing out a full `Authorization` header:

```yaml
- name: "my-http-server"
  transport: "http"
  url: "http://127.0.0.1:9999/mcp"
  token: "${MCP_TOKEN}"          # shorthand → Authorization: Bearer <value>
  enabled: true
```

`token` and explicit `headers` can coexist; explicit `headers` are applied after and can override the `Authorization` set by `token`.

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
    inference_provider: "openai"    # openai | anthropic | gemini | xai | ollama | ollama_cloud | llama_cpp | vllm
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

> **The skill always uses `mcp-agent-chat`'s own model, not the invoking
> adapter's.** When a client sends `skill: "mcp-agent"`, the request is
> routed to `mcp-agent-chat`, which has its own `inference_provider`/`model`
> above. Any per-request `"model"` override the client also sent (resolved
> against the *invoking* adapter's `allowed_models`, e.g. `simple-chat`) is
> discarded — the tool-calling loop always runs on `mcp-agent-chat`'s
> configured model, regardless of which model the conversation was otherwise
> using. For example, sending `{"model": "claude", "skill": "mcp-agent"}` to
> an adapter whose `allowed_models` includes `claude` still runs the tool
> loop on `mcp-agent-chat`'s `openai`/`gpt-4.1-mini` — not Claude. If you
> want the skill to run on a different model, change `inference_provider`/
> `model` here, not the invoking adapter's `allowed_models`.
>
> (This only applies because `mcp-agent-chat` has its own configured LLM.
> Skills with no LLM of their own, like `fetch`, instead keep using the
> invoking adapter's resolved provider/model.)

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

## Opportunistic Mode (mcp_tools capability)

### Overview

Everything above requires the client to explicitly send `skill: "mcp-agent"`,
which swaps the whole request to a dedicated `mcp-agent-chat` adapter for that
one turn. **Opportunistic mode** lets an ordinary conversational/passthrough
adapter (e.g. `simple-chat-with-files`) decide, on any turn, whether an MCP
tool is needed — no `skill` field, no adapter swap, same adapter and thread
throughout the conversation. This is the same native tool-calling loop
described above (`generate_with_tools`), just running inline inside
`LLMInferenceStep`'s normal call instead of inside the dedicated
`MCPAgentStep`.

Because it removes the per-request client opt-in, opportunistic mode is
gated by **two** switches that must both be true — a global admin gate and a
per-adapter capability flag — rather than the skill mechanism's single
`skill:` field.

> **Why "opportunistic"?** The name describes *when* a tool gets called: the
> tools are made available on every turn, but the **model** decides, turn by
> turn, whether the current question presents an actual *opportunity* to use
> one — it isn't forced to, and the client never signals it in advance. Ask a
> question it can answer directly and it just answers (no tool, no `sources`);
> ask something that needs live data and it seizes the opportunity and calls
> the tool. This is the middle ground between the two other possible modes:
> **explicit/on-demand** (the `mcp-agent` skill — the *client* decides up
> front by sending `skill: "mcp-agent"`) and a hypothetical **forced** mode
> (a tool call on every turn regardless of need). The term follows the
> established computing sense — as in "opportunistic encryption" or
> "opportunistic locking" — meaning *do it when conditions make it useful,
> but don't require or force it*. It's the same per-turn, model-decides
> behavior ChatGPT and Claude exhibit natively.

### How It Works

```
Client: POST /v1/chat
  { "messages": [...] }              ← no "skill" field
  X-API-Key: <key for simple-chat-with-files>

   1. API key authenticates → adapter = "simple-chat-with-files"
   2. Adapter capabilities: mcp_tools=true, mcp_servers=[...]
   3. mcp_client.allow_opportunistic must also be true, or mcp_tools is ignored
   4. LLMInferenceStep runs the same tool-calling loop MCPAgentStep uses:
        a. Discover tools from the adapter's mcp_servers allowlist
        b. Call provider.generate_with_tools(messages, tools)
        c. If tool_calls → execute each via MCP, append results → go to b
        d. If final text → done (model chose not to use any tool)
   5. Response: { "response": "...", "sources": [...] }   ← sources only
      present if a tool was actually invoked this turn
```

### Configuration

| Field | Location | Default | Description |
|-------|----------|---------|--------------|
| `mcp_client.allow_opportunistic` | `config/mcp_client.yaml` | `false` | Global admin gate; must be `true` for any adapter's `mcp_tools: true` to take effect |
| `capabilities.mcp_tools` | adapter YAML | `false` | Per-adapter opt-in: run the tool-calling loop inline on every turn |
| `capabilities.mcp_servers` | adapter YAML | `null` (all servers) | Allowlist of MCP servers whose tools are exposed; shared with the `mcp-agent` skill mechanism |

```yaml
# config/mcp_client.yaml
mcp_client:
  enabled: true
  allow_opportunistic: true   # required in addition to the per-adapter flag
  servers:
    - name: "filesystem"
      transport: "stdio"
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/docs"]
      enabled: true
```

```yaml
# config/adapters/multimodal.yaml
- name: "simple-chat-with-files"
  ...
  capabilities:
    ...
    mcp_tools: true
    mcp_servers:
      - "filesystem"
```

### Examples

A plain message, no `skill` field, that triggers a tool call:

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <key for simple-chat-with-files>" \
  -H "X-Session-ID: <session-id>" \
  -d '{"messages":[{"role":"user","content":"What files are in the docs directory?"}]}'
```

```json
{
  "response": "The docs directory contains: adapters/, prototypes/, ...",
  "sources": [
    {"type": "mcp_tool_call", "tool": "filesystem__list_directory", "arguments": {"path": "..."}, "result_preview": "..."}
  ]
}
```

A plain message that does *not* need a tool — the model declines to call one,
`sources` is absent, and the response looks exactly like a normal
conversational answer:

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <key for simple-chat-with-files>" \
  -H "X-Session-ID: <session-id>" \
  -d '{"messages":[{"role":"user","content":"What is retrieval-augmented generation?"}]}'
```

### Model/Provider Requirements

Same requirement as the explicit skill — see
[Supported Inference Providers](#supported-inference-providers). ORBIT logs a
startup warning (not a hard failure) if an adapter sets `mcp_tools: true`
while its `inference_provider` isn't in that known-capable set, since some
providers' support is mode-dependent (e.g. vLLM API vs. direct).

Unlike the explicit skill — where tool schemas are only sent on requests the
client already opted into — opportunistic mode sends tool schemas on **every**
conversational turn for that adapter, including turns that never call a
tool. Keep `mcp_servers` narrow; in opportunistic mode this is closer to a
requirement than an optimization tip.

### Runtime model overrides and tool support

The provider requirement above applies to whichever provider is **actually
resolved for the request**, not just the adapter's static `inference_provider`.
If the adapter defines `allowed_models` and the client sends a `"model"`
field that maps to a provider without `generate_with_tools` support (e.g.
`openrouter`, `deepseek`, `cohere` — not in the
[Supported Inference Providers](#supported-inference-providers) table), the
tool loop is skipped for that request even though the adapter's default
provider fully supports it:

```yaml
# config/adapters/multimodal.yaml
allowed_models:
  - name: "gemini"
    provider: "gemini"          # ✅ tool calling works
  - name: "nemotron-3-ultra"
    provider: "openrouter"      # ❌ falls back to plain generation
```

**This fallback is silent to the client.** The response still returns
`200 OK` with normal-looking text and no error field — there is no `sources`
array and nothing in the JSON response tells the caller that tools were
skipped. The model still answers the question, but without ever calling a
tool, so it may fabricate plausible-looking data (fake customer records,
invented metrics, etc.) instead of saying it lacks the information. The only
visible signal is a server-side log line:

```
WARNING - Adapter '<adapter>' has mcp_tools enabled but provider '<provider>'
does not support generate_with_tools; falling back to plain generation.
```

If responses seem to be inventing data instead of reflecting real tool
results, check this log line first, and confirm which provider the request
actually resolved to (the adapter's default, or a `"model"` override) before
assuming the MCP server or tool discovery is broken.

### Interaction with the `mcp-agent` skill

`mcp_tools` (opportunistic) and `"mcp-agent"` in `available_skills` (explicit)
are independent, non-conflicting access paths to the same MCP servers — they
never fire on the same request, since skill routing fully swaps
`context.adapter_name` before the pipeline runs. They can coexist on the same
adapter: use `mcp_tools: true` for lightweight, narrowly-scoped tools you
want available with zero client-side ceremony (e.g. a filesystem allowlist
for a docs assistant); keep the `mcp-agent` skill for heavier, broader, or
cost-sensitive tool access you want the client to explicitly request per
message (e.g. a GitHub server you don't want queried on every casual chat
turn).

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

A single request may involve several tool-calling rounds, all resolved server-side within that one request/response cycle — the client never has to make a follow-up call to "continue" a chain. Each round appends the tool result to the conversation before the next model call. The loop is bounded by `max_tool_iterations` (default 5); if that limit is reached without a final answer, one last model call is made (with an empty tool list, forcing text output) to synthesize a response from the accumulated context.

The model handles tool errors gracefully — if a tool call fails (access denied, network error, invalid arguments, etc.), the error message is injected into the conversation and the model can retry with corrected arguments or explain the limitation in its final answer.

### No external agent framework — plain Python loop over native tool calling

The entire chaining mechanism is implemented as a single, bounded Python loop —
`run_tool_calling_loop()` in `server/inference/pipeline/mcp_tool_loop.py`.
There is **no LangChain, AutoGen, CrewAI, or any other agent-orchestration
library** involved, and none is required to get multi-step behavior. The
function has zero framework dependencies beyond `asyncio`/`logging`/`typing`:

```python
for iteration in range(max_iterations):
    result = await provider.generate_with_tools(messages, tools)   # native provider API
    if not result.tool_calls:
        return result.text                                         # done — final answer
    messages.append(result.assistant_message)
    for tool_call in result.tool_calls:
        tool_result = await mcp_manager.call_tool(tool_call.name, tool_call.arguments)
        messages.append({"role": "tool", "content": tool_result})  # fed back for next round
# iterations exhausted → one final call with tools=[] forces a text answer
```

(Simplified for illustration — the real implementation additionally handles
cancellation, per-tool error wrapping, and result truncation; see the linked
file for the exact code.) Everything the loop needs — the ability to describe
tools as JSON schemas and have the model request calls against them — is
already native to each supported provider's own API (OpenAI `tools`,
Anthropic `tool_use`, Gemini `FunctionDeclaration`, etc.). ORBIT's own code
is just the glue: build the tool list, call the provider, execute whatever
the model asks for via MCP, append the result, repeat.

This same loop is used **identically** by both invocation paths, so
multi-step chaining behaves the same way regardless of how the request got
there:

- the explicit `mcp-agent` skill (`MCPAgentStep`, `skill: "mcp-agent"`)
- [opportunistic mode](#opportunistic-mode-mcp_tools-capability) (`LLMInferenceStep`'s inline path, no `skill` field)

The only other dependency involved is the official [`mcp`](https://pypi.org/project/mcp/) Python SDK, which is a thin client for the Model Context Protocol itself (session/transport handling, tool discovery, `call_tool`) — not an agent framework, and it was already a project dependency before this feature existed.

### Real example: self-correcting multi-step chain

This is not just a theoretical loop — it self-corrects in practice. A live
test against the sample CRM server in `examples/mcp-server` produced this
sequence for a single user turn (server log, timestamps trimmed):

```
Round 1 → business-sample__search_opportunities(limit=100)
          ← MCP error: "Invalid arguments for tool search_opportunities:
             limit: too_big, maximum 25"
Round 2 → business-sample__search_opportunities(limit=25)   ← self-corrected
          ← success
Round 3 → final answer, synthesized from the returned opportunities
```

The model's first attempt used an out-of-range `limit`; the tool's
validation error was fed back as the tool result (wrapped in `<tool_result>`
tags to reduce prompt-injection risk), and the model corrected its own
argument on the very next round — no retry logic, no error-recovery code, no
external framework involved. This is the same self-correcting behavior
already shown in [Exploratory behaviour](#exploratory-behaviour) with the
filesystem server, just triggered by a tool-side validation error instead of
an access-denied error.

Two other useful multi-tool examples with the sample CRM server:

- *"Find the EMEA customer with the lowest health score and build a
  renewal-save account plan for them."* — requires `list_customers` to find
  the customer, then `build_account_plan` with that customer's id; two
  **different** tools chained in one turn based on reasoning over the first
  tool's result.
- *"Summarize the pipeline for EMEA and separately for APAC."* — may produce
  two `summarize_pipeline` calls (one per region) in the same turn.

See `examples/mcp-server/README.md` to run this server locally, and
`playbook-mcp-conversation.md` at the repo root for a fuller set of
multi-step, error-handling, and edge-case scenarios to test against it.

### Verifying it yourself

- Unit tests: `server/tests/test_inference/test_mcp_tool_loop.py` —
  `TestRunToolCallingLoop::test_single_tool_call_then_final_answer` and
  `test_exhaustion_forces_final_call_without_tools` assert the loop chains
  multiple rounds and correctly forces a final answer when
  `max_tool_iterations` is reached.
- Live check: any multi-step response includes one `sources` entry
  per tool call (see [Multi-step issue investigation](#github--multi-step-issue-investigation)
  for the shape), so you can count rounds directly from the response without
  reading server logs.

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
| Local via Ollama (CPU/GPU) | `ollama` / `qwen3.5-4b-cpu` or `qwen2.5-3b-cpu` *(good balance)*, `functiongemma-cpu` *(fastest tool selection, thin final answers)* |
| Self-hosted GPU server, high throughput | `vllm` (API mode, server started with `--enable-auto-tool-choice --tool-call-parser <parser>`) |
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
- **Opportunistic mode widens exposure.** It moves from per-request opt-in (client sends `skill: "mcp-agent"`) to per-adapter default-on for every conversational turn. Keep `mcp_client.allow_opportunistic: false` (the default) until deliberately enabled.
- **Always pair `mcp_tools: true` with a narrow `mcp_servers` allowlist** — in opportunistic mode, tool schemas are sent on every message the adapter receives, not only on messages that end up invoking a tool.

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

The configured `inference_provider` does not support native tool calling. Use one of: `openai`, `anthropic`, `gemini`, `xai`, `ollama`, `ollama_cloud`, `llama_cpp` (API mode recommended), or `vllm` (API mode). Note `vllm` in **direct/in-process mode** raises this error on purpose — switch it to API mode. See [Supported Inference Providers](#supported-inference-providers).

### Tool results look wrong / server errors

The MCP server returns `isError: true`. The error message is passed back to the model as the tool result, so the model can acknowledge the failure in its final answer. Check the server-side logs for the underlying cause.

### `mcp_tools` capability has no effect / model never calls tools opportunistically

Opportunistic mode is disabled by default even if the adapter sets
`mcp_tools: true` — check that `mcp_client.allow_opportunistic: true` is also
set in `config/mcp_client.yaml`. Both switches are required (see
[Opportunistic Mode](#opportunistic-mode-mcp_tools-capability)).

### Every response is slower / costs more, even when no tool is used

In opportunistic mode, tool schemas are sent to the model on every
conversational turn, not only turns that end up calling a tool. Narrow the
adapter's `mcp_servers` allowlist, or consider whether the explicit
`mcp-agent` skill (client opts in per-request) is a better fit than
always-on opportunistic mode for this adapter.

### HTTP transport: 401 Unauthorized

- Verify `token` or `headers.Authorization` in `mcp_client.yaml` matches what the server expects.
- Use `${ENV_VAR}` syntax and confirm the variable is set in the environment before starting ORBIT.
- For servers that require a specific scheme, use `headers` directly instead of `token`:
  ```yaml
  headers:
    Authorization: "ApiKey ${MY_API_KEY}"
  ```

### HTTP transport: connection refused or timeout

- Confirm the server is reachable at the configured `url`.
- The HTTP transport (`streamable_http_client`) uses POST requests — ensure the endpoint accepts POST, not GET.
- Some servers require the path to end in `/mcp` or a specific route; check the server's documentation.

---

## Testing the HTTP Transport

A self-contained FastMCP test server ships at `server/tests/test_services/mcp_http_test_server.py`. It exposes three tools over HTTP (`echo`, `add`, `fail_always`) and optionally enforces Bearer-token auth. Use it to verify the `http` transport end-to-end without needing an external service.

### Start the test server

```bash
# No auth
python server/tests/test_services/mcp_http_test_server.py --port 9999

# With Bearer-token enforcement
python server/tests/test_services/mcp_http_test_server.py --port 9999 --token test-secret
```

### Run the built-in smoke test

The `--smoke-test` flag connects to a running server via `MCPClientManager`, discovers tools, calls each one, and asserts on the results:

```bash
python server/tests/test_services/mcp_http_test_server.py --smoke-test --port 9999 --token test-secret
```

Expected output:

```
Discovering tools …
  Found: ['test-server__echo', 'test-server__add', 'test-server__fail_always']
Calling echo …
  Result: 'hello MCP'
Calling add …
  Result: '10'
Calling fail_always (expect Tool error) …
  Result: 'Tool error: intentional test failure'

All smoke tests passed.
```

### Point an ORBIT adapter at the test server

```yaml
# config/mcp_client.yaml
servers:
  - name: "test-server"
    transport: "http"
    url: "http://127.0.0.1:9999/mcp"
    token: "test-secret"
    enabled: true
```

Then send requests through ORBIT with `"skill": "mcp-agent"` — the model will pick from `test-server__echo`, `test-server__add`, and `test-server__fail_always`:

```bash
# Triggers test-server__echo
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -H "X-Session-ID: test-1" \
  -d '{"messages":[{"role":"user","content":"Echo back the message: hello from orbit"}],"skill":"mcp-agent"}'
```

```bash
# Triggers test-server__add
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -H "X-Session-ID: test-2" \
  -d '{"messages":[{"role":"user","content":"What is 42 plus 58?"}],"skill":"mcp-agent"}'
```

```bash
# Triggers test-server__fail_always (tests error-path handling)
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -H "X-Session-ID: test-3" \
  -d '{"messages":[{"role":"user","content":"Call the fail_always tool and tell me what happened"}],"skill":"mcp-agent"}'
```

A successful `add` response will include a `sources` entry showing the tool call and its result:

```json
{
  "response": "42 + 58 = 100",
  "sources": [
    {
      "type": "mcp_tool_call",
      "tool": "test-server__add",
      "arguments": {"a": 42, "b": 58},
      "result_preview": "100"
    }
  ]
}
```

> Make sure `MCP_TOKEN=test-secret` is set in the environment where ORBIT is running, and that `test-server` is listed in the `mcp_servers` allowlist of the `mcp-agent-chat` adapter.

### Unit tests

Transport selection and header construction are covered by the unit-test suite:

```bash
# From repo root:
/path/to/venv/bin/python -m pytest server/tests/test_services/test_mcp_client_service.py -v
```

Key test classes:

| Class | What it verifies |
|-------|-----------------|
| `TestExpandHeaders` | `token` → `Authorization: Bearer`, env-var expansion, header override precedence |
| `TestOpenSessionTransportSelection` | `sse` routes to `sse_client`, `http` routes to `streamable_http_client`, correct `Accept` header injected, `token` wired to `Authorization`, unknown transport raises |

---

## Implementation Reference

| Component | File | Role |
|-----------|------|------|
| MCP client manager | `server/services/mcp_client_service.py` | Singleton; connects to servers, caches tool schemas, executes `call_tool`; `allow_opportunistic` property gates opportunistic mode |
| Shared tool-calling loop | `server/inference/pipeline/mcp_tool_loop.py` | `run_tool_calling_loop()`; used by both `MCPAgentStep` and `LLMInferenceStep`'s inline path |
| Agent pipeline step | `server/inference/pipeline/steps/mcp_agent.py` | `MCPAgentStep`; explicit-skill entry point, delegates to `run_tool_calling_loop()` |
| LLM step guard | `server/inference/pipeline/steps/llm_inference.py` | Skips LLM for `type == mcp_agent` (line ~78); `_should_run_mcp_tools`/`_run_inline_mcp_tools` implement opportunistic mode |
| Pipeline registration | `server/inference/pipeline/pipeline.py` | `MCPAgentStep` added before `ImageGenerationStep`; streaming `done` payloads include `sources` for both the explicit and opportunistic paths |
| `AdapterCapabilities.mcp_tools` / `.mcp_servers` | `server/adapters/capabilities.py` | Opportunistic-mode capability flags; `mcp_servers` allowlist shared with the `mcp-agent` skill |
| `ToolCallingResult` | `server/ai_services/services/inference_service.py` | Normalized result type returned by `generate_with_tools` |
| OpenAI tool calling | `server/ai_services/implementations/inference/openai_inference_service.py` | `generate_with_tools` via `chat.completions` |
| Anthropic tool calling | `server/ai_services/implementations/inference/anthropic_inference_service.py` | `generate_with_tools` + OpenAI↔Anthropic message conversion |
| Gemini tool calling | `server/ai_services/implementations/inference/gemini_inference_service.py` | `generate_with_tools` via `FunctionDeclaration` |
| xAI tool calling | `server/ai_services/implementations/inference/xai_inference_service.py` | `generate_with_tools` (OpenAI-compatible) |
| Ollama tool calling | `server/ai_services/implementations/inference/ollama_inference_service.py` | `generate_with_tools` via `/api/chat`; `_normalize_messages_for_ollama` for loop history |
| Ollama Cloud tool calling | `server/ai_services/implementations/inference/ollama_cloud_inference_service.py` | `generate_with_tools` via the `ollama` SDK; reuses `_normalize_messages_for_ollama` |
| llama.cpp tool calling | `server/ai_services/implementations/inference/llama_cpp_inference_service.py` | `generate_with_tools` for API and direct modes |
| vLLM tool calling | `server/ai_services/implementations/inference/vllm_inference_service.py` | `generate_with_tools` (API mode only; direct mode raises `NotImplementedError`) |
| Skill adapter config | `config/adapters/mcp-agent.yaml` | `mcp-agent-chat` adapter; exposes as `mcp-agent` skill |
| Server config template | `config/mcp_client.yaml` | Example server definitions |
| Adapter registry | `config/adapters.yaml` | Imports `mcp-agent.yaml` |
| Design document | `docs/adapters/mcp-client-skill.md` | Original architecture design and phased plan |

### `ProcessingContext` additions

| Field | Type | Description |
|-------|------|-------------|
| `sources` | `List[Dict]` | Populated by `MCPAgentStep` (or `LLMInferenceStep`'s opportunistic path) with one entry per tool call: `{type, tool, arguments, result_preview}` |
| `mcp_tools` | `bool` | Opportunistic-mode capability flag, resolved from the (possibly skill-swapped) adapter's `capabilities.mcp_tools` |
| `mcp_servers_allowlist` | `Optional[List[str]]` | Opportunistic-mode server allowlist, resolved from `capabilities.mcp_servers` |

### `ToolCallingResult` fields

| Field | Type | Description |
|-------|------|-------------|
| `text` | `Optional[str]` | Final model answer (`None` when the model made tool calls) |
| `tool_calls` | `Optional[List[Dict]]` | Parsed tool calls: `[{id, name, arguments}]` |
| `assistant_message` | `Dict` | OpenAI-format message to append to the conversation history |
| `finish_reason` | `str` | Provider stop reason (`"stop"`, `"tool_calls"`, etc.) |

---

## Future Work

- **Persistent MCP connections** — the current implementation opens a fresh connection per tool call (per-request for SSE/HTTP, per-call subprocess for stdio). A persistent connection pool with reconnect logic would eliminate subprocess startup overhead.
- **Human-in-the-loop approval** — annotate tools as read-only vs. write, and surface a confirmation step for state-changing calls.
- **Resources and prompts** — v1 supports tools only. `list_resources` and `list_prompts` are future additions.
- **User-supplied MCP servers** — v1 restricts server configuration to admins. Allowing trusted users to supply their own servers at request time is a future capability.
- **Streaming tool-call progress events** — emit an SSE event for each tool invocation so the client can show "Calling github__search_issues…" in the UI before the final answer arrives.
