# Grounded Real-Time Voice (OpenAI Realtime + Retriever Adapters)

## Overview

ORBIT's OpenAI Realtime bridge (`OpenAIRealtimeWebSocketHandler`) proxies a client to OpenAI's Realtime API for full speech-to-speech conversation — no cascaded STT → LLM → TTS round trip. By default that bridge is a pure proxy: it builds a static `instructions` string once when the session opens and otherwise just relays audio both ways.

**Grounded real-time voice** adds live RAG lookups on top of that proxy so the assistant can correctly answer factual questions ("How much is the birth certificate?") in natural speech, without falling back to the slower cascade path. It works by registering an existing **retriever adapter** (`qa-sql`, `intent-sql-postgres`, `intent-duckdb-analytics`, etc.) as an OpenAI Realtime **function-calling tool**. When the user asks something factual, the model calls the tool mid-conversation, ORBIT runs the retriever synchronously, and the result is fed back so the model can speak the grounded answer in its own words.

Key properties:

- **Live, per-turn grounding** — retrieval runs fresh for each question the model decides needs it, the same way `retrieval_behavior: "always"` retrieval works for text adapters. Nothing is baked into the prompt at connect time.
- **Reuses existing retriever adapters as-is** — no new adapter type, no changes to `server/adapters/capabilities.py`, `server/inference/pipeline/steps/*`, or the retriever implementations themselves. Any `type: "retriever"` adapter (SQL, DuckDB, vector, HTTP, ...) can be pointed at.
- **Provider-agnostic core** — the tool schema and the retrieval call live in a small shared module independent of OpenAI's wire protocol, so a future Gemini/Mistral/local realtime handler can reuse them; only the event-mapping layer is OpenAI-specific.
- **Zero client changes** — the ORBIT client protocol (`audio_chunk`, `transcription`, `assistant_transcript_delta`, `done`, ...) is unchanged. Grounding happens entirely between ORBIT and OpenAI; `clients/realtime-voice/` needs no changes.
- **Backward compatible** — an `openai_realtime` adapter with no `grounding_adapter` configured behaves exactly as before (e.g. `open-ai-real-time-voice-chat` in `config/adapters/audio.yaml`).

---

## How It Works

```
Client: WS /ws/voice/qa-realtime-voice
  {"type": "audio_chunk", "data": "<base64 pcm16>"}

   1. voice_routes.py resolves adapter "qa-realtime-voice" (type: openai_realtime)
   2. OpenAIRealtimeWebSocketHandler.__init__ resolves grounding config from
      config.grounding_adapter → GroundingConfig(adapter_name="qa-sql", tool_name="lookup_answer", ...)
   3. session.update sent to OpenAI includes:
        instructions: "<persona/base prompt> + grounding-usage guidance"
        tools: [ { type: function, name: lookup_answer, parameters: {query: string} } ]
        tool_choice: "auto"
   4. User speaks: "How much is the birth certificate?"
   5. OpenAI transcribes + decides to call the tool:
        response.function_call_arguments.done { call_id, name: "lookup_answer", arguments: '{"query": "..."}' }
   6. Handler._handle_function_call:
        a. adapter_manager.get_adapter("qa-sql") → the qa-sql retriever instance
        b. retriever.get_relevant_context(query=...) → ranked QA docs
        c. execute_grounding_lookup() formats the top answer(s) into short spoken text
        d. sends conversation.item.create { type: function_call_output, call_id, output: "<answer text>" }
        e. waits for the tool-call response's response.done, then sends response.create
   7. OpenAI speaks the grounded answer in the model's own words (audio streamed back as usual)
```

Everything after step 3 is invisible to the ORBIT client — it just keeps receiving `audio_chunk` / `assistant_transcript_delta` events as normal; the tool round-trip happens purely between ORBIT and OpenAI.

---

## Implementation Reference

| Piece | File |
|---|---|
| Grounding config, tool schema, retrieval call (provider-agnostic) | `server/services/chat_handlers/realtime_grounding.py` |
| OpenAI wire-protocol integration (session.tools, function-call event handling) | `server/services/chat_handlers/openai_realtime_websocket_handler.py` |
| Gemini Live wire-protocol integration (google-genai SDK, tool-call handling) | `server/services/chat_handlers/gemini_live_websocket_handler.py` |
| Passes `adapter_manager`/`api_key` into the handler | `server/routes/voice_routes.py` |
| Demo adapters | `config/adapters/qa.yaml` → `qa-realtime-voice`, `qa-gemini-realtime-voice` |

### `realtime_grounding.py`

- `resolve_grounding_config(adapter_config) -> Optional[GroundingConfig]` — reads `config.grounding_adapter` (the name of an existing retriever adapter) plus optional `grounding_tool_name`, `grounding_tool_description`, `grounding_confidence_threshold`, `grounding_max_answer_chars`, and `grounding_max_rows`. Returns `None` when `grounding_adapter` isn't set, which is what keeps ungrounded `openai_realtime` adapters unaffected.
- `build_tool_schema(grounding) -> dict` — a neutral JSON-schema function-calling definition. OpenAI Realtime's `session.tools` accepts this shape directly; a future provider handler would translate the same dict into its own tool-declaration format instead of duplicating this logic.
- `execute_grounding_lookup(adapter_manager, grounding, query, api_key=None) -> str` — calls `adapter_manager.get_adapter(grounding.adapter_name)` then `adapter.get_relevant_context(query=...)` (the same ad-hoc, outside-the-pipeline entry point already used by `parallel_adapter_executor.py` and `file_routes.py`), then joins the top answers into a short, speakable plain-text string. Voice answers favor terse text over the markdown/toon table formatting used for LLM prompt injection — a table doesn't work well read aloud.

### `openai_realtime_websocket_handler.py`

- Constructor takes `adapter_manager` and `api_key`, and resolves `self._grounding = resolve_grounding_config(adapter_config)` once at construction.
- `_resolve_realtime_instructions()` appends a short instruction — *"call `<tool_name>` for factual questions, then answer naturally, don't read the lookup text verbatim"* — when grounding is configured. This composes with whatever base persona/system prompt (`system_prompt_id`) is already loaded; no separate persona mechanism is needed.
- `_build_session_update()` adds `tools`/`tool_choice` to the session payload only when `self._grounding` is set.
- `_map_openai_event()` handles `response.function_call_arguments.done` via `_handle_function_call()`, which parses the `query` argument, runs `execute_grounding_lookup()`, and replies with `conversation.item.create` (`function_call_output`). It sends `response.create` only after OpenAI emits `response.done` for the tool-call-only response; creating the follow-up earlier is rejected as a concurrent active response.

None of this fires when `self._grounding` is `None` — the branch is simply never reached, and no new fields are added to the session payload.

---

## Configuration

Point any existing retriever adapter at a new `openai_realtime` adapter via `config.grounding_adapter`:

```yaml
# config/adapters/qa.yaml
- name: "qa-realtime-voice"
  enabled: true
  type: "openai_realtime"
  datasource: "none"
  adapter: "conversational"
  implementation: "implementations.passthrough.conversational.ConversationalImplementation"
  capabilities:
    retrieval_behavior: "none"      # this adapter doesn't retrieve directly; grounding_adapter does
    supports_realtime_audio: true
    supports_interruption: true
  config:
    realtime_model: "gpt-realtime"
    realtime_voice: "marin"
    enable_input_transcription: true
    grounding_adapter: "qa-sql"                # name of any retriever-type adapter
    grounding_tool_name: "lookup_answer"
    grounding_tool_description: "Look up factual answers (fees, hours, procedures) from the city knowledge base."
    # grounding_confidence_threshold: 0.3       # optional override
    # grounding_max_answer_chars: 600           # optional override (default 600)
    # grounding_max_rows: 3                     # optional override (default 3)
```

| Field | Required | Default | Purpose |
|---|---|---|---|
| `grounding_adapter` | Yes (to enable grounding) | — | Name of an existing retriever-type adapter to query per-turn. |
| `grounding_tool_name` | No | `lookup_answer` | Function name the model sees and calls. |
| `grounding_tool_description` | No | generic description | Shown to the model — write this to match the adapter's actual domain so the model knows when to call it. |
| `grounding_confidence_threshold` | No | retriever's own default | Overrides the retriever's configured `confidence_threshold` for this tool's calls. |
| `grounding_max_answer_chars` | No | `600` | Caps how much retrieved text gets spoken back per lookup. |
| `grounding_max_rows` | No | `3` | For structured intent results, exposes at most this many complete rows to the realtime model. |

The `grounding_adapter` mechanism works against any `type: "retriever"` adapter via the same `BaseRetriever.get_relevant_context()` interface, regardless of datasource. QA retrievers contribute their `answer` text directly. Intent retrievers (`intent-sql-postgres`, `intent-duckdb-analytics`, `intent-elasticsearch-app-logs`, `intent-mongodb-mflix`, and HTTP-backed intent adapters) contribute their structured `metadata.formatted_data` instead: ORBIT converts each selected result row to field/value text before it reaches the realtime model. This avoids passing markdown, CSV, or TOON table syntax into a spoken response.

---

## Gemini Live Provider

`GeminiLiveWebSocketHandler` (`server/services/chat_handlers/gemini_live_websocket_handler.py`) is a second real-time speech-to-speech provider, registered under adapter `type: "gemini_live"`. It proves the provider-agnostic design: it reuses `realtime_grounding.py` **unchanged** and speaks the identical ORBIT client wire protocol (`audio_chunk`/`transcription`/`assistant_transcript_delta`/`done`/`error`), so `clients/realtime-voice/` works against it with no changes — just point `VITE_ADAPTER_NAME` at a `gemini_live` adapter.

Implementation notes:

- Uses the `google-genai` SDK (`client.aio.live.connect`), not a raw WebSocket — the SDK owns the Gemini `setup`/tool-call/tool-response wire protocol.
- **Sample rate**: Gemini Live requires **16 kHz PCM16** input; the ORBIT client always sends **24 kHz**. The handler resamples every inbound `audio_chunk` from 24 kHz → 16 kHz server-side (`_resample_pcm16`, linear interpolation via numpy) before forwarding to Gemini. Output audio is already 24 kHz PCM16, matching the client's expected output rate, so no output resampling is needed.
- **Tool calling**: `build_tool_schema(grounding)`'s neutral JSON-schema dict is passed directly into `google.genai.types.FunctionDeclaration(parameters_json_schema=...)` — no manual translation into the SDK's `Schema` object graph. Incoming `response.tool_call.function_calls[]` are resolved via `execute_grounding_lookup()` (same as OpenAI) and replied to via `session.send_tool_response(function_responses=[FunctionResponse(id, name, response={"result": ...})])`.
- **No tool-call-only `done` suppression needed** (unlike the OpenAI handler): Gemini signals turn completion via `server_content.turn_complete`, which only fires once the spoken answer has actually streamed, not on the tool-call round-trip itself.
- **Auth**: `GOOGLE_API_KEY` (or `GEMINI_API_KEY`) env var, else `inference.gemini.api_key` in `config/inference.yaml` (already used by the existing Gemini vision/video/embedding services).
- **Custom tools vs. Google Search grounding**: Gemini Live can't combine a custom `function_declarations` tool with built-in `googleSearch` grounding in the same session — this handler only wires up custom tools (the `grounding_adapter` pattern), so it's unaffected, but don't add `googleSearch` alongside `grounding_adapter` in the same adapter config.

Demo adapters: `gemini-live-voice-chat` (ungrounded, `config/adapters/audio.yaml`) and `qa-gemini-realtime-voice` (grounded against `qa-sql`, `config/adapters/qa.yaml`) — direct Gemini counterparts of `open-ai-real-time-voice-chat` and `qa-realtime-voice`.

---

## Intent Retriever Grounding

Intent retrievers return a structured `formatted_data` payload alongside
their normal text `content`. Realtime grounding uses the structured payload
when it contains a table: it sends a short result count followed by complete
`Column: value` rows. `grounding_max_rows` defaults to 3 and is applied
independently of the retriever's `return_results`, so enabling voice does not
change a shared adapter's behavior for text clients.

For a dedicated voice-only retriever, set `return_results` to 1–3 as well to
reduce query work and keep the source result set aligned with what can be
spoken. For a shared adapter such as `intent-sql-postgres` in
`config/adapters/customer-orders.yaml`, `intent-duckdb-analytics` in
`config/adapters/business-analytics.yaml`, or `intent-elasticsearch-app-logs`
in `config/adapters/elasticsearch-logs.yaml`, leave its existing
`return_results` intact and configure the voice adapter separately:

```yaml
- name: "customer-orders-realtime-voice"
  enabled: true
  type: "openai_realtime"
  datasource: "none"
  adapter: "conversational"
  implementation: "implementations.passthrough.conversational.ConversationalImplementation"
  capabilities:
    retrieval_behavior: "none"
    supports_realtime_audio: true
    supports_interruption: true
  config:
    realtime_model: "gpt-realtime"
    realtime_voice: "marin"
    grounding_adapter: "intent-sql-postgres"
    grounding_tool_name: "lookup_customer_orders"
    grounding_tool_description: "Look up customer order facts, statuses, and totals."
    grounding_max_rows: 3
    grounding_max_answer_chars: 600
```

The same configuration works with `gemini_live` by changing only `type`, the
Gemini model, and voice fields. The realtime model still turns the returned
facts into a natural answer; ORBIT does not add a second LLM summarization
call or a second source of truth.

---

## Known Limitation: MCP Agent Adapters Not Groundable (Future Task)

**Status: analyzed, not yet fixed.** `grounding_adapter` does **not** currently
work against `type: "mcp_agent"` adapters (e.g. `mcp-agent-chat` in
`config/adapters/mcp-agent.yaml`) — it fails silently rather than erroring.

**Why:** `execute_grounding_lookup()` calls
`adapter.get_relevant_context(query=...)`, the `BaseRetriever` interface.
`mcp_agent` is registered under the same conversational-passthrough factory
as `openai_realtime`/`gemini_live` themselves (`server/adapters/__init__.py`),
which resolves to `ConversationalImplementation` — its
`get_relevant_context()` is an explicit no-op that always returns `[]`. So
pointing `grounding_adapter` at an MCP agent adapter would always fall
through to `execute_grounding_lookup()`'s empty-result branch and answer
"I don't have information about that.", regardless of what the MCP tools
could actually answer.

MCP tool-calling instead runs through `MCPAgentStep`
(`server/inference/pipeline/steps/mcp_agent.py`), a full pipeline step that
replaces `LLMInferenceStep` and runs its own multi-turn
`run_tool_calling_loop()` / `generate_with_tools()` against the configured
MCP servers — a different call shape than "give me a query, get back ranked
docs."

**Candidate fixes (pick one to scope out):**
1. Add an MCP-specific branch to `execute_grounding_lookup()` that detects
   a `type: "mcp_agent"` grounding adapter and calls
   `run_tool_calling_loop()` directly instead of `get_relevant_context()`,
   formatting its final answer the same way QA/intent results are formatted
   today.
2. Give `MCPAgentStep`'s tool-calling loop a retriever-shaped wrapper (a thin
   adapter whose `get_relevant_context()` runs the MCP loop internally and
   returns its answer as a single doc), so `execute_grounding_lookup()` needs
   no MCP-specific logic at all — closer to how QA/intent grounding works
   today.

Option 2 keeps `realtime_grounding.py` fully provider- and adapter-type
agnostic (the stated design goal); option 1 is more direct but reintroduces
a type-specific branch into the shared module.

---

## Testing

1. Set `OPENAI_API_KEY` and start the server.
2. Connect the existing node client (`clients/realtime-voice/`) to `ws://<host>:<port>/ws/voice/qa-realtime-voice` — no client-side changes needed.
3. Ask a factual question in the adapter's domain (e.g. *"How much is the birth certificate?"*, answered from `examples/city-qa-pairs.json` via `qa-sql`). Expect a tool call, a short pause for the lookup, then a natural spoken answer.
4. Ask an unrelated conversational question (small talk) and confirm the model does **not** call the tool for it.
5. Confirm an adapter with no `grounding_adapter` configured (e.g. `open-ai-real-time-voice-chat`) is unaffected — no `tools` in its session, no function-call handling triggered.
