# Automatic Skill Intent Detection (Hybrid Router)

> **Status:** Implemented. Code: `server/services/skill_intent_router.py`,
> wired in `server/services/pipeline_chat_service.py`. Config gate:
> `skill_routing` in `config/config.yaml` + `capabilities.auto_skill_routing`
> per adapter. Manual validation steps: `playbook-auto-skill-routing.md`.

## Context

Today ORBIT skills (PDF, Image, Video, Audio, Word, Excel, PowerPoint, web-search,
Fetch, …) are only invoked when the client explicitly sends `skill: "<name>"` —
in OrbitChat, the user must type `/` and pick the skill every time. The goal is
to let ORBIT infer intent from natural language ("can you turn this into a PDF",
"read this out loud", "search the web for X") and auto-route to the right skill,
the way ChatGPT/Claude do — without the user reaching for `/`.

This mirrors the **opportunistic mode** philosophy already shipped for MCP tools
([`mcp-agent.md`](mcp-agent.md#opportunistic-mode-mcp_tools-capability), commit
d0e9af78): the client sends a plain message, and ORBIT decides per-turn whether a
specialized capability applies — gated by an opt-in switch, backward compatible
when off.

**Decisions locked with the user:**
- **Mechanism**: Hybrid — a cheap embedding pre-filter for recall, then a small
  LLM confirm for precision (LLM only fires when the pre-filter finds a candidate).
- **Scope (initial)**: generation skills (image/video/document/audio — incl. PDF,
  Word, Excel, PowerPoint, Markdown) **plus** web-search and Fetch. Retrieval
  skills (HR, business-analytics, customer-orders) and mcp-agent are excluded for now.
- **Enablement**: opt-in via a two-switch gate (global + per-adapter); an explicit
  `skill` from the `/` picker always overrides auto-detection.

## Why this approach fits

- **Reuses 100% of the skill machinery.** Auto-detection only computes a skill
  *name*; feeding it into the existing `build_context(skill=...)` argument runs the
  same allowlist check, adapter swap, provider resolution, and step gating that the
  `/` picker uses. No pipeline step or generation step changes.
- **Native tool-calling (opportunistic-MCP style) was rejected for generation**
  because the shared `run_tool_calling_loop` feeds *string* tool results back to the
  LLM — but PDF/image/video/audio produce binary artifacts that need the skill's
  native response shape (`context.image` / `context.document` / …). The loop can't
  cleanly represent a "terminal" artifact-producing tool.
- **Pure embedding was rejected** because generation skills have no `nl_examples`
  and single-turn phrase matching is brittle for negation / mixed intent / similar
  skills (PDF vs Word vs Markdown). The **LLM confirm** stage resolves exactly those
  ambiguities; the **embedding pre-filter** keeps the common "normal chat" turn cheap
  (no LLM call when nothing matches).

## Key existing code (reused, not rewritten)

- Injection point — `server/services/pipeline_chat_service.py`
  `process_chat` (~line 647) and `process_chat_stream` (~line 808), immediately
  before `build_context(..., skill=skill)`. `adapter_name`, `message`, and
  `context_messages` are all in hand here.
- Skill swap (unchanged) — `server/services/chat_handlers/request_context_builder.py:202-244`.
- Skill registry — `server/services/config/adapter_config_manager.py`
  `get_all_skills()` (name + `skill_description` + backing adapter) and
  `get_skill_adapter()`.
- Embedding primitive — `server/embeddings/base.py`
  `EmbeddingServiceFactory.create_embedding_service(config)` (cached singleton) +
  `embed_query` / `embed_documents`. Non-retriever call-site precedents:
  `server/utils/chunk_manager.py`, `server/services/cache/embedding_cache_manager.py`.
- Cosine — `server/vector_stores/base/base_vector_store.py:217` `calculate_similarity`
  (or a trivial numpy dot-product; no Chroma / vector store needed).
- Confirm-LLM provider resolution — mirror the `rewrite_provider` pattern in
  `server/inference/pipeline/steps/document_generation.py:127-211`
  (`adapter_manager.get_overridden_provider(provider, adapter_name, explicit_model_override=...)`).
- Capabilities — `server/adapters/capabilities.py` (`available_skills`,
  `expose_as_skill`, `skill_name`, `skill_description`).

## Implementation

### 1. New service: `SkillIntentRouter`
File: `server/services/skill_intent_router.py`

`async detect(message, context_messages, adapter_name) -> Optional[str]`:

1. **Candidate set** = the adapter's `auto_routable_skills` (falling back to
   `available_skills` when unset) ∩ the *routable* set (skills whose backing
   adapter `type` is in
   `{image_generation, video_generation, document_generation, audio_generation, fetch}`
   or that carry `web_search: true`). Pull metadata from `get_all_skills()`.
   Return `None` if empty. (Splitting the source from `available_skills` lets an
   admin allow auto-routing while forbidding explicit user invocation — set
   `available_skills: []` and list skills under `auto_routable_skills`.)
2. **Stage 1 — embedding pre-filter** (recall-oriented, permissive threshold):
   - Provider resolution: the consumer adapter's `embedding_provider` override
     when set, otherwise the global `embedding.provider`. The phrase cache is
     keyed by `(provider, candidate-set)` so multiple adapters stay correct.
   - Per candidate, embed a phrase set once and memoize (keyed by candidate set):
     default source is `skill_description` + the `skill_name` token; an optional
     `routing_examples: [..]` list on the skill adapter's capabilities augments it
     when present (works out of the box, tunable later).
   - `embed_query(message)`, compute max cosine per skill via `calculate_similarity`,
     keep the top candidate(s) above `embedding_threshold`. If none → return `None`
     (cheap fast-path; no LLM call).
3. **Stage 2 — LLM confirm** (precision): one small constrained call over the last
   N history turns + the top candidate(s) and their descriptions: "Which of these
   skills, if any, does this turn want? Reply with the exact skill name or NONE."
   Resolve the provider via `router_provider`/`router_model` config (fallback: the
   adapter's own `inference_provider`), `max_tokens` small. Parse to a candidate
   name or `None`; anything not in the candidate set → `None`.

### 2. Wire into the service layer
`server/services/pipeline_chat_service.py`, both `process_chat` and
`process_chat_stream`, just before `build_context(..., skill=skill)`:

```python
if skill is None and self._auto_skill_routing_enabled(adapter_name):
    try:
        skill = await self.skill_router.detect(message, context_messages, adapter_name)
    except Exception:
        skill = None   # never break a normal turn on router failure
```

- `if skill is None` guarantees the `/` picker always wins ("manual still wins").
- `_auto_skill_routing_enabled` requires **both** the global gate and the
  per-adapter flag (below).
- Construct `self.skill_router` where other services are wired (service factory /
  `PipelineChatService.__init__`), passing `adapter_manager`, config, and the
  embedding factory.

### 3. Config + capability flags (two-switch gate)
- `server/adapters/capabilities.py`: add `auto_skill_routing: bool = False`
  (consumer-adapter opt-in), optional `auto_routable_skills: List[str]` (router
  candidate source; falls back to `available_skills`), and optional
  `routing_examples: List[str]` (skill-adapter phrase overrides). Parse all in
  `from_config`. An auto-detected skill is validated in `build_context` against
  `auto_routable_skills` (via `skill_auto_detected=True`); explicit user skills
  stay restricted to `available_skills`.
- Global gate + router settings in `config/config.yaml` (new block), e.g.:
  ```yaml
  skill_routing:
    auto_detect: false          # global gate (default off = backward compatible)
    embedding_threshold: 0.35   # permissive pre-filter
    router_provider: cohere     # small/fast confirm LLM
    router_model: command-r7b-12-2024
    history_turns: 4
  ```
- Enable on the target consumer adapter — `config/adapters/multimodal.yaml`
  `simple-chat-with-files` (it already lists the generation + web/fetch skills and
  is `supports_threading: false`): set `capabilities.auto_skill_routing: true`.
  Note in docs that auto-routing is intended for conversational/multimodal
  (non-threading) adapters, consistent with how the `/` picker is suppressed for
  threading adapters.

### 4. Docs
Add an "Automatic Intent Detection" section to `docs/adapters/skills.md`
(cross-linking `mcp-agent.md`'s opportunistic mode): the two-switch gate, the
hybrid flow, scope, the `/`-override precedence, and the cost note (embedding every
turn, LLM only on a hit).

### 5. (Optional) UI transparency
No UI change is required for the happy path — OrbitChat already sends no `skill`
for plain messages and already renders `image` / `document` responses. Optional
nicety: return `requested_skill` in the response so OrbitChat can show an
"auto: PDF" badge. Defer unless wanted.

## Verification

- **Unit** (`server/tests/test_services/test_skill_intent_router.py`): mock the
  embedding service + confirm-LLM and assert — positive ("make a pdf of this" →
  `PDF`), negative ("what is retrieval-augmented generation?" → `None`, and assert
  the confirm-LLM was **not** called), disambiguation ("put this in a spreadsheet"
  → `Excel`, not `PDF`), and out-of-scope skill filtered out of candidates.
- **Regression**: with `auto_detect` off (default) or `auto_skill_routing` unset,
  `detect` is never invoked and existing behavior is byte-for-byte unchanged; an
  explicit `skill` from the request still routes and overrides.
- **Integration (manual, venv python)**: with both switches on for
  `simple-chat-with-files`, `POST /v1/chat` with **no** `skill` field and
  `{"content":"create a PDF summarizing our conversation"}` → response contains
  `document` + `document_format` and no LLM text; the same message with
  `auto_detect` off → normal conversational text response.
- Run existing skill tests to confirm no break:
  `venv/bin/python -m pytest server/tests/chat_handlers/test_request_context_builder.py::TestSkillRouting server/tests/test_config/test_config_management.py::TestSkillRegistry -v`.

## Out of scope (initial)
- Auto-routing retrieval skills (HR, analytics, customer-orders) and mcp-agent.
- Native tool-calling representation of generation skills.
- Multi-skill per turn (e.g. "make a PDF *and* an image") — router returns one skill.

## Interaction with opportunistic MCP tool calling

Auto-skill routing and [opportunistic MCP](mcp-agent.md#opportunistic-mode-mcp_tools-capability)
coexist cleanly and are fully independent. They are gated by **separate** switch
pairs, so enabling one never affects the other:

| Feature | Global gate | Per-adapter flag |
|---------|-------------|------------------|
| Auto-skill routing | `skill_routing.auto_detect` | `capabilities.auto_skill_routing` |
| Opportunistic MCP | `mcp_client.allow_opportunistic` | `capabilities.mcp_tools` |

**They never both fire on the same turn**, and there is a clear precedence.
Skill detection runs **first** (`_maybe_detect_skill`, before `build_context`):

1. **A skill is detected** → `build_context` swaps `context.adapter_name` to the
   skill adapter (exactly like an explicit `/` pick). From there:
   - **Generation/fetch skills** (PDF, Image, Video, Audio, Fetch) are in
     `NO_LLM_ADAPTER_TYPES`, so `LLMInferenceStep` is skipped — and since the
     opportunistic MCP loop lives *inside* `LLMInferenceStep`, it does not run.
   - **web-search skill** runs `LLMInferenceStep`, but `mcp_tools` is resolved
     from the *swapped* adapter (the web-search adapter, where it's `false`), so
     MCP still doesn't fire.
   - Net: the skill wins that turn; MCP stands down.
2. **No skill is detected** → no swap. The turn stays on the consumer adapter and
   opportunistic MCP behaves exactly as before (runs if `mcp_tools: true` +
   `allow_opportunistic: true`).

This is the same "skill routing swaps the adapter before the pipeline runs, so
the two paths never collide" property the MCP docs already describe for the
explicit `mcp-agent` skill — auto-routing just fills in the skill name for you.

**Two things worth knowing:**

- **Precedence when both are enabled on one adapter.** For a turn where a skill
  matches, the auto-detected skill preempts opportunistic MCP. (Today this is
  moot — `simple-chat-with-files` ships `mcp_tools: false`.) If you enable MCP
  there too and want a web-fetch MCP server to handle e.g. "search the web"
  instead of the `web-search` skill, drop `web-search`/`Fetch` from that
  adapter's `available_skills` so routing won't claim those turns.
- **`mcp-agent` is deliberately excluded** from auto-routing (its adapter type
  isn't in `ROUTABLE_ADAPTER_TYPES` and it carries no `web_search` flag), so
  auto-detection never hijacks it — the explicit `mcp-agent` skill and
  opportunistic `mcp_tools` both keep working untouched.

## Follow-ups / possible enhancements

Optional improvements deferred from the initial build — none required for the
feature to work, listed here so they're easy to pick back up.

- **Multilingual `routing_examples`.** The confirm LLM already handles other
  languages, and OpenAI `text-embedding-3-*` is multilingual, but the
  pre-filter is more reliable for non-English (esp. Audio / web-search / Fetch,
  whose trigger words *translate* rather than being shared tokens like "PDF")
  when each skill adapter lists native-language phrases, e.g.:
  ```yaml
  # audio-generator.yaml
  routing_examples:
    - "read this out loud"
    - "lis ça à voix haute"        # fr
    - "léelo en voz alta"          # es
  ```
  Requires a multilingual embedding provider (avoid `cohere` `embed-english-v3.0`).

- **UI "auto: PDF" badge.** Surface which skill was auto-invoked so OrbitChat can
  show *why* a skill response appeared (vs. an explicit `/` pick). Return
  `requested_skill` in the chat response (`response_processor.build_result` →
  `server/models/schema.py`) and render a small badge in OrbitChat. Purely
  additive; no server-side behavior change.

- **Tune `embedding_threshold` against real traffic.** Default `0.35` is
  permissive (recall-oriented, since the confirm LLM adds precision). Raise it if
  ordinary chat ever mis-fires a skill; lower it if a genuine request occasionally
  fails to trigger. Set in `config/config.yaml` under `skill_routing`.

- **Widen scope if wanted.** Currently generation + web-search/fetch only. Retrieval
  skills and `mcp-agent` were excluded (see *Out of scope*); revisit if there's a
  clear use case, keeping mis-routing risk for normal questions in mind.
