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
        e. sends response.create
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

- `resolve_grounding_config(adapter_config) -> Optional[GroundingConfig]` — reads `config.grounding_adapter` (the name of an existing retriever adapter) plus optional `grounding_tool_name`, `grounding_tool_description`, `grounding_confidence_threshold`, `grounding_max_answer_chars`. Returns `None` when `grounding_adapter` isn't set, which is what keeps ungrounded `openai_realtime` adapters unaffected.
- `build_tool_schema(grounding) -> dict` — a neutral JSON-schema function-calling definition. OpenAI Realtime's `session.tools` accepts this shape directly; a future provider handler would translate the same dict into its own tool-declaration format instead of duplicating this logic.
- `execute_grounding_lookup(adapter_manager, grounding, query, api_key=None) -> str` — calls `adapter_manager.get_adapter(grounding.adapter_name)` then `adapter.get_relevant_context(query=...)` (the same ad-hoc, outside-the-pipeline entry point already used by `parallel_adapter_executor.py` and `file_routes.py`), then joins the top answers into a short, speakable plain-text string. Voice answers favor terse text over the markdown/toon table formatting used for LLM prompt injection — a table doesn't work well read aloud.

### `openai_realtime_websocket_handler.py`

- Constructor takes `adapter_manager` and `api_key`, and resolves `self._grounding = resolve_grounding_config(adapter_config)` once at construction.
- `_resolve_realtime_instructions()` appends a short instruction — *"call `<tool_name>` for factual questions, then answer naturally, don't read the lookup text verbatim"* — when grounding is configured. This composes with whatever base persona/system prompt (`system_prompt_id`) is already loaded; no separate persona mechanism is needed.
- `_build_session_update()` adds `tools`/`tool_choice` to the session payload only when `self._grounding` is set.
- `_map_openai_event()` handles `response.function_call_arguments.done` via `_handle_function_call()`, which parses the `query` argument, runs `execute_grounding_lookup()`, and replies with `conversation.item.create` (`function_call_output`) + `response.create`.

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
```

| Field | Required | Default | Purpose |
|---|---|---|---|
| `grounding_adapter` | Yes (to enable grounding) | — | Name of an existing retriever-type adapter to query per-turn. |
| `grounding_tool_name` | No | `lookup_answer` | Function name the model sees and calls. |
| `grounding_tool_description` | No | generic description | Shown to the model — write this to match the adapter's actual domain so the model knows when to call it. |
| `grounding_confidence_threshold` | No | retriever's own default | Overrides the retriever's configured `confidence_threshold` for this tool's calls. |
| `grounding_max_answer_chars` | No | `600` | Caps how much retrieved text gets spoken back per lookup. |

The `grounding_adapter` mechanism itself is generic — it works against any `type: "retriever"` adapter via the same `BaseRetriever.get_relevant_context()` interface, regardless of datasource. In practice, today it's only tuned for **QA-shaped** retrievers (`qa-sql`, `qa-vector-chroma`). See [Known Limitations](#known-limitations-intent-retriever-content-shape) before pointing it at an intent retriever (`intent-sql-postgres`, `intent-duckdb-analytics`, `intent-elasticsearch-app-logs`, `intent-mongodb-mflix`, ...).

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

## Known Limitations: Intent Retriever Content Shape

**Status: analyzed, not yet fixed.** Currently validated end-to-end only
against `qa-sql`/`qa-vector-chroma` (`config/adapters/qa.yaml`). This is
QA-only *by current tuning*, not by architectural necessity — the fix below
is scoped and not yet built.

### Why QA retrievers work cleanly today

QA domain adapters (`server/adapters/qa/base.py:36-48`, `format_document`)
set `item["answer"]` to a short, pre-formatted natural-language sentence
(e.g. *"Birth certificates can be requested from the Vital Records Office
for a fee of $20."*). `_format_answer()` in `realtime_grounding.py` prefers
`doc.get("answer")`, so the text handed to the model as `function_call_output`
is already voice-ready — truncating it at `grounding_max_answer_chars`
(default 600) rarely matters since these answers are short.

### Why intent retrievers (customer-orders, elasticsearch-logs, mongodb-mflix, business-analytics) need more work

Intent retrievers (`server/retrievers/base/intent_sql_base.py:770-831`,
mirrored in `intent_http_base.py`) never set `item["answer"]`. A single
`get_relevant_context()` call returns **one dict** (not one per row) whose
`content` field is a fully-rendered multi-row table — markdown/TOON/CSV
depending on `context_format`, built by `TableRenderer.render()`
(`intent_sql_base.py:786`) — covering up to `return_results` rows (e.g.
`return_results: 100` in `config/adapters/customer-orders.yaml`) folded
into one string that can run to several KB, prefixed with a line like
`"Found 47 results:"` or `"Showing 20 of 47 total results (truncated):"`.

`_format_answer()` falls back to `doc.get("content")` for these and
truncates at `grounding_max_answer_chars` on a raw character boundary. For
a multi-row table that means:
- Cutting mid-row or mid-table-syntax (stray `|` characters, broken TOON
  lines) rather than at a sentence boundary.
- Silently dropping the relevant row entirely if it falls past the
  first ~600 characters of the table.

This formatting happens *inside* `get_relevant_context()` itself (before
the pipeline's `context_format`/`context_max_tokens` capabilities are ever
applied — those only run later, in `ContextRetrievalStep._format_context`,
which this grounding path doesn't use), so there's no existing per-adapter
knob that produces a short spoken sentence instead of a table.

### Follow-up work (next session)

1. **Make truncation table-aware** in `_format_answer()` — detect
   table-formatted content (or just always truncate on line/row boundaries,
   not mid-string) so a cut-off table degrades to "fewer rows shown"
   instead of garbled syntax.
2. **Recommend/default a small `return_results`** (e.g. 1–3) for any
   retriever adapter used as a `grounding_adapter`, so the table is small
   by construction rather than relying on downstream truncation — a voice
   answer should describe one thing, not summarize 47 rows.
3. Optionally, let `execute_grounding_lookup()` ask the underlying LLM
   (or a cheap summarizer call) to condense a table result into a single
   spoken sentence, rather than truncating raw table text at all — closer
   to how the text pipeline lets the *main* LLM read structured `<context>`
   and phrase a natural answer, except here the *tool output* itself would
   need to already be terse since the Realtime model receives it as plain
   function-call output, not as `<context>` fed through the usual prompt
   builder.

---

## Testing

1. Set `OPENAI_API_KEY` and start the server.
2. Connect the existing node client (`clients/realtime-voice/`) to `ws://<host>:<port>/ws/voice/qa-realtime-voice` — no client-side changes needed.
3. Ask a factual question in the adapter's domain (e.g. *"How much is the birth certificate?"*, answered from `examples/city-qa-pairs.json` via `qa-sql`). Expect a tool call, a short pause for the lookup, then a natural spoken answer.
4. Ask an unrelated conversational question (small talk) and confirm the model does **not** call the tool for it.
5. Confirm an adapter with no `grounding_adapter` configured (e.g. `open-ai-real-time-voice-chat`) is unaffected — no `tools` in its session, no function-call handling triggered.
