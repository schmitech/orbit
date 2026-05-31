# Design: MCP Client Skill (tool-calling agent)

> **Status:** Proposed (design only — not yet implemented). Tracking issue: _TBD_. Label: `new feature`.

## Context & Motivation

ORBIT today exposes an **MCP server** (FastMCP, wired in `server/inference_server.py`) that lets external clients call ORBIT's tools. This proposal is the inverse: an **MCP client** that lets ORBIT connect *out* to one or more external MCP servers, discover their tools, and let the LLM call them within a conversation — a true tool-calling agent loop — exposed as a **skill** (`mcp-agent`) so any adapter can opt in via `available_skills`.

Concretely: a user asks a question, the model decides to call an MCP tool (e.g. a GitHub server's `search_issues`, a filesystem server's `read_file`), ORBIT executes it against the MCP server, feeds the result back to the model, and repeats until the model produces a final answer.

This follows the same skill mechanics already used by `web-search`, `image-generation`, and `video-generation` (see [skills.md](./skills.md)).

## Relationship to the existing `IntentAgentRetriever`

There is already function-calling code: `IntentAgentRetriever` (`server/retrievers/implementations/intent/intent_agent_retriever.py`, config `intent-agent-example` in `config/adapters/intent.yaml`). It is **similar but not the same**, and the differences are exactly what this feature must add:

| Aspect | `IntentAgentRetriever` (existing) | MCP Client Skill (proposed) |
|--------|-----------------------------------|------------------------------|
| Tool source | Tools defined **statically in YAML** templates (`function_schema` + `execution`) | Tools **discovered dynamically** from external MCP servers (`list_tools`) |
| Tool transport | Built-in (calculator/date/json) or HTTP call | MCP protocol (stdio / SSE / streamable-HTTP) via the `mcp` SDK |
| Control flow | **Single-shot**: pick one function → execute once → return as retrieval context | **Agentic loop**: model may call multiple tools across several turns before answering |
| Pipeline role | A *retriever* (`get_relevant_context`) feeding context into the normal LLM step | A *skill step* that owns the LLM loop and bypasses the standard `LLMInferenceStep` |
| Provider tool-calling | Probes for `generate_with_tools`/`chat_with_tools`, but **no provider implements it** → falls back to prompt-based JSON parsing | Requires **real native tool-calling** on the inference services |

**Reuse, don't rewrite.** The following are directly reusable:
- `server/retrievers/implementations/intent/agent/tool_definitions.py` — `ToolDefinition`, `.to_openai_tool()` (schema → OpenAI tool format). MCP tool schemas map cleanly onto this.
- `server/retrievers/implementations/intent/agent/tool_executor.py` — `ToolExecutor` execution/result-status conventions (`ToolResultStatus`).
- `server/retrievers/implementations/intent/agent/response_synthesizer.py` — `ResponseSynthesizer` for turning structured tool output into natural language (optional final-synthesis fallback).

## Goals / Non-Goals

**Goals**
- Connect to one or more configured MCP servers and discover their tools at startup (and/or per-request).
- Run a bounded multi-step tool-calling loop with native provider tool-calling.
- Expose it as the `mcp-agent` skill, reusing all existing skill plumbing.
- Provider-agnostic across the tool-calling-capable providers (OpenAI, Anthropic, Gemini, xAI).
- Stream the final answer; surface tool invocations as metadata/sources.

**Non-Goals (v1)**
- Human-in-the-loop tool approval UI (note it as a future enhancement; see Security).
- Arbitrary user-supplied MCP servers at request time (servers are admin-configured).
- Resources/prompts from MCP (v1 = **tools** only; `list_resources`/`prompts` later).

## Architecture Overview

```
Client → POST /v1/chat { messages, skill: "mcp-agent" }
  1. Skill swap → adapter_name = "mcp-agent-chat", web_search-style routing
     (runtime model override cleared — skill uses its own provider/model)
  2. Pipeline runs; MCPAgentStep.should_execute() true for type == "mcp_agent"
     → LLMInferenceStep is skipped (same guard pattern as image/video)
  3. MCPAgentStep:
       a. get MCPClientManager (singleton service) → discovered tools (OpenAI schema)
       b. loop (max_iterations):
            response = provider.generate_with_tools(messages, tools)
            if response has tool_calls:
                for each call: result = mcp_manager.call_tool(server, name, args)
                append assistant tool_call + tool result messages
                continue
            else: final_text = response.text ; break
       c. context.response = final_text
          context.sources = [tool invocations + results]   (for transparency)
  4. Response: { "response": "...", "sources": [ {tool, server, args, ...} ] }
```

## Components to Build

### 1. `MCPClientManager` service (`server/services/mcp_client_service.py`)
A singleton service (registered in the service factory, lifecycle tied to the FastAPI lifespan like other services) that:
- Reads MCP server definitions from config (see §Config).
- Opens and **persists** client sessions using the `mcp` SDK:
  - stdio transport: `mcp.client.stdio` (spawns a local command).
  - SSE / streamable-HTTP transport: `mcp.client.sse` (remote URL + auth headers).
  - `mcp.client.session.ClientSession` for the session handshake.
- On init (and on a refresh interval), calls `list_tools()` per server and caches a unified tool registry, namespacing tool names by server (e.g. `github__search_issues`) to avoid collisions.
- Converts each MCP tool's JSON-Schema `inputSchema` → OpenAI tool schema (reuse `ToolDefinition`/`to_openai_tool` where possible).
- Exposes `get_tools(allowed_servers) -> list[openai_tool]` and `call_tool(namespaced_name, args) -> ToolResult`.
- Handles reconnects, per-call timeouts, and a circuit breaker per server (mirror the `fault_tolerance` pattern already used by intent adapters).

### 2. Provider native tool-calling (the biggest net-new piece)
Add an optional method to the inference service base (`server/ai_services/services/inference_service.py`) and implement it for the tool-calling-capable providers:

```python
async def generate_with_tools(self, messages, tools, **kwargs) -> ToolCallingResult
# ToolCallingResult: { text: str | None, tool_calls: list[{id, name, arguments}] | None, finish_reason }
```

- **OpenAI / xAI** (`openai`-SDK based): `chat.completions.create(tools=..., tool_choice="auto")` and parse `message.tool_calls`; feed results back as `role:"tool"` messages. (Or the Responses API with function tools.)
- **Anthropic**: `messages.create(tools=...)`; parse `tool_use` blocks; return results as `tool_result` content blocks.
- **Gemini**: `tools=[Tool(function_declarations=...)]`; parse `functionCall` parts; return `functionResponse` parts.

This is the same multi-format problem `_call_function_model` in `IntentAgentRetriever` already grapples with — but here it must be **real** (not prompt-based) and support the **loop** (multiple rounds). Keep the per-provider translation inside each inference service, returning the normalized `ToolCallingResult`.

> **Fast-path note (optional):** OpenAI's Responses API also supports a *hosted* `mcp` tool type (OpenAI connects to the MCP server itself). That is provider-specific and bypasses ORBIT's broker/loop. It could be offered as an optimization for OpenAI-only setups, but the **ORBIT-brokered loop above is the primary, provider-agnostic design** and the one this issue should deliver.

### 3. `MCPAgentStep` (`server/inference/pipeline/steps/mcp_agent.py`)
Mirror `ImageGenerationStep`:
- `should_execute(context)` → true when adapter `type == "mcp_agent"` (and not blocked).
- Add the guard to `LLMInferenceStep.should_execute` so it defers (it already defers for `image_generation`/`video_generation` — add `mcp_agent` to that tuple).
- Register it in the pipeline builder (`server/inference/pipeline/pipeline.py`) alongside the other skill steps.
- Implement the bounded loop (`max_tool_iterations`, default ~5). Stream the final assistant text via `process_stream`; non-streaming via `process`.
- On each tool call, append structured entries to `context.sources` for transparency (tool name, server, arguments, truncated result).

### 4. Capability + context plumbing (reuse existing)
- `AdapterCapabilities` (`server/adapters/capabilities.py`): no new flag strictly required — the adapter `type: "mcp_agent"` drives the step (like image/video). Optionally add `mcp_servers: list[str]` under capabilities to scope which configured servers this adapter may use.
- Skill exposure uses the **existing** fields: `expose_as_skill`, `skill_name`, `skill_description`, and consumers' `available_skills`. No change to `request_context_builder.py` beyond what already exists — the skill-swap + runtime-override-clearing we already ship covers it (the agent uses the skill adapter's own provider/model).

### 5. Config

New `config/mcp_client.yaml` (servers), imported by `config.yaml`:
```yaml
mcp_client:
  enabled: true
  servers:
    - name: "github"
      transport: "stdio"               # stdio | sse
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-github"]
      env:
        GITHUB_TOKEN: ${GITHUB_TOKEN}
      enabled: true
    - name: "docs-search"
      transport: "sse"
      url: "https://mcp.internal.example.com/sse"
      headers:
        Authorization: "Bearer ${INTERNAL_MCP_TOKEN}"
      enabled: true
  tool_timeout: 30
  max_tool_iterations: 5
```

New skill adapter `config/adapters/mcp-agent.yaml` (registered in `config/adapters.yaml` import list):
```yaml
adapters:
  - name: "mcp-agent-chat"
    enabled: true
    type: "mcp_agent"                  # triggers MCPAgentStep; LLM step skipped
    datasource: "none"
    adapter: "conversational"
    implementation: "implementations.passthrough.conversational.ConversationalImplementation"
    inference_provider: "openai"       # must support native tool-calling
    model: "gpt-5.4-mini"
    capabilities:
      expose_as_skill: true
      skill_name: "mcp-agent"
      skill_description: "Use external MCP server tools to answer (agentic tool calling)"
      retrieval_behavior: "none"
      formatting_style: "standard"
      requires_api_key_validation: false
      mcp_servers:                     # optional allowlist; omit = all enabled servers
        - "github"
        - "docs-search"
```
Then add `"mcp-agent"` to consumer adapters' `capabilities.available_skills` (e.g. `simple-chat`).

## Request / Response

Request (same shape as any skill):
```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "X-API-Key: <key for an adapter that allows mcp-agent>" \
  -d '{"messages":[{"role":"user","content":"Find open issues labeled bug in repo X"}],
       "skill":"mcp-agent"}'
```
Response:
```json
{
  "response": "There are 3 open bugs: ...",
  "sources": [
    {"type": "mcp_tool_call", "server": "github", "tool": "search_issues",
     "arguments": {"repo": "X", "labels": ["bug"], "state": "open"}}
  ]
}
```
Streaming yields the final answer tokens; tool calls happen server-side between the request and the first answer token (optionally emit progress events like the image skill's `request_id` chunk).

## Security Considerations

MCP servers execute commands (stdio) or reach networks (SSE) — treat them as privileged:
- **Admin-configured only.** No request-time server URLs/commands in v1.
- **Per-adapter allowlist** (`mcp_servers`) so a skill can only reach intended servers.
- **Secrets via env** (`${VAR}`), never inline; redact tool arguments/results in logs.
- **Timeouts + circuit breakers** per server; cap `max_tool_iterations` to bound cost/loops.
- **Output sanitization**: tool results are untrusted text injected into the model context — keep them clearly delimited (prompt-injection risk). Consider a result size cap.
- Future: human-in-the-loop approval for state-changing tools (annotate tools as read-only vs write).

## Phased Implementation Plan

1. **MCPClientManager (read-only spike)** → verify: connect to one stdio server (e.g. filesystem), `list_tools()`, `call_tool()` round-trip via a unit/integration test. _No pipeline yet._
2. **Provider tool-calling** → add `generate_with_tools` to the base + implement for OpenAI first; unit-test tool_call parsing and the tool-result message round-trip.
3. **MCPAgentStep + pipeline wiring** → new adapter type, step, `LLMInferenceStep` guard, pipeline registration. Verify a full single-tool loop end-to-end (non-streaming).
4. **Skill exposure + config** → `mcp-agent.yaml`, register in `adapters.yaml`, add to a consumer's `available_skills`; verify `GET /admin/skills` lists it and the skill routes correctly (reusing existing skill tests as a template).
5. **Multi-iteration loop + streaming + sources** → bounded loop, stream final answer, populate `context.sources`.
6. **Remaining providers** → Anthropic, Gemini, xAI `generate_with_tools`.
7. **Hardening** → timeouts, circuit breakers, redaction, result caps, docs in [skills.md](./skills.md).

Each phase is independently testable; phases 1–2 carry the real risk and should be spiked first.

## Open Questions / Decisions

- **Tool-calling normalization layer**: add `generate_with_tools` per inference service (recommended, keeps provider quirks isolated) vs a separate `ToolCallingAdapter` wrapper. _Lean: per-service method returning a normalized `ToolCallingResult`._
- **Session lifecycle**: persistent sessions held by the singleton manager (faster, but long-lived subprocesses) vs per-request connect/teardown (simpler, safer). _Lean: persistent with health checks + lazy reconnect._
- **Tool name collisions across servers**: namespacing scheme (`server__tool`). Confirm provider tool-name charset limits.
- **Should this reuse `intent_agent`'s code by extracting the agent loop into a shared module?** Worth considering so both the (future) native intent-agent and the MCP agent share one loop implementation.

## Reference Map

| Concern | Existing code to study / reuse |
|---------|--------------------------------|
| Skill swap, runtime-override clearing | `server/services/chat_handlers/request_context_builder.py` |
| Skill step pattern (bypass LLM step) | `server/inference/pipeline/steps/image_generation.py` |
| `LLMInferenceStep` skip guard | `server/inference/pipeline/steps/llm_inference.py` (`should_execute`) |
| Pipeline registration | `server/inference/pipeline/pipeline.py` (`build_standard_pipeline`) |
| Tool schema + execution conventions | `server/retrievers/implementations/intent/agent/{tool_definitions,tool_executor,response_synthesizer}.py` |
| Multi-format tool-call parsing (prior art) | `IntentAgentRetriever._call_function_model` |
| Inference service base | `server/ai_services/services/inference_service.py` |
| Provider services to extend | `server/ai_services/implementations/inference/{openai,anthropic,gemini,xai}_inference_service.py` |
| MCP server (mirror for client lifecycle) | `server/inference_server.py`, `server/routes/routes_configurator.py` |
| MCP client SDK | `mcp` 1.27.1 — `mcp.client.session.ClientSession`, `mcp.client.stdio`, `mcp.client.sse` |
| Skill docs to update | `docs/adapters/skills.md` |
