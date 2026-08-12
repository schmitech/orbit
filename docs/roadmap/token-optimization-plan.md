# Reduce per-turn token consumption on paid APIs

## Status (updated after first implementation pass)

| Phase | Status | Notes |
|---|---|---|
| Phase 1 — Gate the chart formatting block | ✅ Done | `supports_charts` capability + hint/full split + intent gate shipped |
| Phase 2a — Stable prefix/tail split | ✅ Done | `build_system_message()` returns `(content, prefix_len)` |
| Phase 2b — Carry breakpoint to provider | 🟡 Partial | Anthropic only (explicit `cache_control`); OpenAI/Gemini need no code (benefit passively from 2a); Anthropic history/tool breakpoints (max 4) not added — single breakpoint only |
| Phase 2c — Extend caching to remaining providers (DeepSeek, xAI, Mistral, Cohere, Groq, etc.) | ⬜ Not started | New — audit each provider's actual caching support before wiring; several may already cache automatically and only need usage-extraction fixes (Phase 4.3) |
| Phase 3 — Relevance-filter MCP tools | ⬜ Not started | Biggest remaining win (20k–50k tokens/turn on MCP-enabled adapters) |
| Phase 4.1 — Fix history overhead constant | ✅ Done | `history.system_overhead_tokens` (default 1200), replaces hardcoded 700 |
| Phase 4.2 — Tokenizer-accurate estimate | ⬜ Not started (re-scoped) | Left `len//3` heuristic as-is — intentionally fast, real tokenizer already applied async; not a bug, decided not worth the risk |
| Phase 4.3 — Cache-token-aware pricing | ⬜ Not started | Anthropic cache reads still priced at full input rate in audit records |
| Phase 4.4 — Docs | ✅ Done | `docs/token-usage-and-cost-tracking.md` updated |

Also shipped, not in the original phase list: two post-review fixes — an
off-by-one in `_build_system_param` that silently skipped the cache
breakpoint when there was no volatile tail (the common case with
language/clock/RAG all disabled), and a missing `pytest.importorskip("anthropic")`
in the new caching test module so collection doesn't fail without the
optional Anthropic dependency installed.

Full regression suite as of this pass: `server/tests/test_inference/`,
`server/tests/test_pipeline_steps/`, `server/tests/test_services/test_pricing_service.py`,
`server/tests/test_adapters/` — **457 passed, 25 skipped**.

---

## Context

A trivial `"hello"` on the `simple-chat` passthrough adapter (`config/adapters/passthrough.yaml`) with
`examples/prompts/examples/default-conversational-adapter-prompt.md` (~450 tokens) currently sends
**~1,700 prompt tokens**, and grows linearly with history. Measured breakdown of what
`PromptInstructionBuilder.build_system_message_content()` emits every turn:

| Component | Source | Tokens |
|---|---|---|
| System prompt | `prompt_builder.py:45` | ~450 |
| Clock instruction | `prompt_builder.py:48`, `clock_service.py:103` | ~20 (**changes every second**) |
| Chart formatting rules | `prompt_builder.py:220-306` | **~1,200, unconditional** |
| Persona/context footer | `prompt_builder.py:78` | ~15 |
| MCP tool schemas (when `mcp_tools: true`) | `mcp_client_service.py:612-627` | **~20k–50k, re-sent per loop iteration** |

Three structural problems:

1. The chart block is appended for **every adapter on every turn**, chart-related or not, and is
   ~2.5× the size of the actual system prompt.
2. **No provider prompt caching exists anywhere** — `cache_control`, `prompt_cache_key`,
   `cached_content` have zero hits under `server/`. The static prefix is re-billed at full rate
   every turn. The clock instruction sitting at position 2 would bust any prefix cache even if one
   existed.
3. `MCPClientManager.get_all_tools()` returns **every tool from every enabled server** with no
   relevance selection; `config/mcp_clients.yaml` enables filesystem + business-sample + github
   (github alone is ~70-100 tools), and `run_tool_calling_loop` re-sends the full list on each of
   up to 8 iterations plus a final synthesis call.

Goal: cut the fixed per-turn cost by ~70% for conversational turns and make the remaining prefix
cacheable, without losing context fidelity.

---

## Phase 1 — Gate the chart formatting block ✅ Done

**Files:** `server/inference/pipeline/prompt_builder.py`, `server/adapters/capabilities.py`,
`config/adapters/*.yaml`

1. Add `supports_charts: bool = False` to `AdapterCapabilities` (`capabilities.py:31-41`) and parse
   it in `from_config` alongside `formatting_style` (`:134`). Set `supports_charts: true` only on
   adapters that genuinely produce visualizations (analytics/intent-SQL adapters); leave it off for
   `simple-chat` and other pure-passthrough entries.
2. Split `build_chart_instruction()` into two constants:
   - `CHART_HINT` (~120 tokens): the one-paragraph contract — "for a chart emit a ```chart fenced
     block; for a table use markdown; supported types: bar, line, pie, area, scatter, composed,
     radar, funnel, radialbar" plus a single FORMAT A example.
   - `CHART_FULL` — the existing ~84-line block verbatim (`prompt_builder.py:222-306`), unchanged so
     chart fidelity is not degraded when it matters.
3. Change `build_chart_instruction()` to take `context` and return:
   - `""` when the adapter does not declare `supports_charts`;
   - `CHART_FULL` when a cheap intent gate fires — a compiled regex over `context.message` plus the
     last ~2 turns of `context.context_messages` matching chart/graph/plot/visuali[sz]e/bar/pie/
     line chart/trend/histogram/breakdown-by, **or** a ```chart fence already present in history
     (a follow-up like "make it horizontal" must keep the full spec);
   - `CHART_HINT` otherwise.

**Saving:** ~1,200 → 0 tokens/turn on `simple-chat`; ~1,200 → ~120 on chart-capable adapters when
the turn isn't chart-related.

`supports_charts: true` is set on: `business-analytics`, `customer-orders`, `hr`, `ev`,
`billing-sla`, `elasticsearch-logs`, `intent`, `mongodb-mflix`, `composite`, and `qa`
(`qa-sql`/`qa-vector-chroma`/`qa-vector-qdrant-demo`) in both `config/adapters/` and
`install/default-config/adapters/` — every `retriever`-type adapter with `formatting_style: standard`,
i.e. the ones that return tabular/aggregate data a chart could visualize.

The gate is a generic capability, not restricted to retriever/intent adapters — it's also enabled on
the passthrough/multimodal adapters, since the ~120-token hint (or nothing, if the turn isn't
chart-related) makes it safe to turn on broadly: `simple-chat` (`config/adapters/passthrough.yaml`
and its `install/default-config/` counterpart) and every adapter in `multimodal.yaml`
(`simple-chat-with-files`, `simple-chat-with-files-audio`, plus `install/default-config/`'s
additional `local-voice-chat` and `math-teacher-quadratic-files`) — multimodal adapters commonly
take CSV/spreadsheet uploads a user may want visualized. Left off `web-search` in both directories
(pure search/citation adapter, no data to chart).

---

## Phase 2 — Make the prefix stable, then cache it 🟡 Partial

**Files:** `server/inference/pipeline/prompt_builder.py`,
`server/inference/pipeline/steps/llm_inference.py`, `anthropic_inference_service.py`,
`openai_inference_service.py`, `gemini_inference_service.py`

### 2a. Reorder for a stable prefix (benefits every provider passively) ✅ Done

In `build_system_message_content()` (`prompt_builder.py:41-80`) emit strictly:

```
[ static prefix ]  system prompt -> chart instruction (Phase 1) -> persona/answer-mode footer
[ volatile tail ]  language instruction -> time instruction -> <context> RAG block
```

The time instruction moves out of position 2 to the **end** of the system message (behind the cache
breakpoint). `formatted_context` (RAG/file content) is already per-turn volatile and belongs in the
tail. Return the split point alongside the string — add a small
`build_system_message(context) -> tuple[str, int]` (prefix length) and keep
`build_system_message_content()` as a thin wrapper returning the joined string, so the websocket
handlers and other callers are untouched.

### 2b. Carry the breakpoint to the provider 🟡 Partial — Anthropic only

Thread the prefix boundary through `_build_message_format()`
(`llm_inference.py:383-408`) as a structured system message the providers can split on. Minimal
shape that no existing provider breaks on: keep `messages[0]["content"]` a plain string, and set
`context.cacheable_prefix_len` (new field on `ProcessingContext`, `pipeline/base.py`), forwarded as
a `cache_prefix_len=` kwarg from `generate_tracked`/`generate_stream_tracked` at
`llm_inference.py:139` and `:213`. Providers that don't pop it must not receive it — reuse the same
capability-flag pattern already documented for `usage_sink` (`SUPPORTS_USAGE_REPORTING` in
`ai_services/services/inference_service.py`): add `SUPPORTS_PROMPT_CACHING = False` on the base and
flip it to `True` per migrated provider, so an unmigrated provider's SDK never sees the kwarg.

Per provider:

- **Anthropic** ✅ Done (single breakpoint) — `_build_system_param()` in
  `anthropic_inference_service.py` emits a content-block list with
  `cache_control: {"type": "ephemeral"}` on the prefix when `cache_prefix_len` is set (including
  the equal-length case, i.e. no volatile tail — fixed post-review off-by-one that originally
  skipped this common case). ⬜ Not done: the second breakpoint on the last trimmed-history message
  (incremental history caching) and the tool-list breakpoint ordering — still a single
  system-prefix breakpoint only.
- **OpenAI** ✅ Passive win from 2a, ⬜ `prompt_cache_key` not added — automatic prefix caching
  already benefits from the stable prefix with zero code change; the optional
  `(adapter_name, system_prompt_id, model)`-derived `prompt_cache_key` for better cache routing was
  not implemented.
- **Gemini** ✅ Passive win from 2a — implicit caching benefits from the stable prefix with no API
  change, as planned. Explicit `cachedContent` intentionally not wired (as scoped).

**Saving:** on Anthropic, ~90% off the repeated prefix (system prompt + chart block + tools +
history) after turn 1. On OpenAI, 50% off cached input tokens. Reported cost falls out of this
automatically only if usage extraction also reads the cache fields — see Phase 4.

### 2c. Extend caching/cache-usage extraction to the remaining providers ⬜ Not started

Phase 2a's stable prefix already benefits *every* provider passively wherever the underlying API
does automatic/implicit caching — no code required. This subtask is about the providers that need
either an explicit opt-in (like Anthropic's `cache_control`) or usage-extraction changes to surface
a cache hit that's already happening silently. Per-provider, based on each API's documented
caching behavior (verify against current provider docs before implementing — these mechanisms
change):

- **DeepSeek** — context caching is automatic (no request-side flag), and usage already reports
  `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` on `response.usage`. No `cache_prefix_len`
  wiring needed (same as OpenAI/Gemini in 2b); the gap is purely in usage extraction/pricing — see
  Phase 4.3, since `deepseek_inference_service.py`'s usage reporting doesn't yet read those fields.
- **xAI (Grok)** — OpenAI-compatible usage shape; check whether `usage.prompt_tokens_details.cached_tokens`
  is populated the way OpenAI's is. If so, same passive-caching / usage-extraction gap as DeepSeek,
  no explicit breakpoint needed.
- **Mistral** — confirm current support before doing anything; historically no documented
  prompt-caching mechanism (implicit or explicit). If still true, this provider gets no work item
  beyond the passive benefit of a stable prefix (fewer tokens sent, even without a cache discount).
- **Cohere** — confirm current support; historically no prompt-caching mechanism. Same fallback as
  Mistral if true.
- **Groq, Mistral, DeepInfra, Together, Fireworks, Cerebras, Moonshot, Minimax, Nebius, Scaleway,
  Perplexity, Venice** — all share the OpenAI-compatible `openai` python client per
  `docs/token-usage-and-cost-tracking.md`'s SDK-family table. Audit each provider's actual API docs
  for a caching mechanism (some proxy to upstream models that do support it, e.g. an
  OpenAI-compatible endpoint fronting a cached-capable backend) before assuming none exists —
  don't blanket-copy the Anthropic `cache_control` approach onto a provider that doesn't support it,
  since an unrecognized param can be rejected by the SDK call (see `SUPPORTS_PROMPT_CACHING` guard
  in `inference_service.py`, which exists precisely to prevent that).
- For any provider found to support automatic caching with reported cache-hit tokens: extend
  `_report_usage`/`UsageReportingMixin` (Phase 4.3) so the hit is priced at a discount instead of
  folded into the full-price prompt total, mirroring the Anthropic
  `cache_read_input_tokens` handling already planned there.

**Saving:** proportional to how many of these providers turn out to already do automatic caching
server-side — likely free wins once usage extraction is corrected, since 2a's stable prefix means
the discount silently applies today on any provider with implicit caching; ORBIT just isn't
pricing it correctly yet.

---

## Phase 3 — Relevance-filter MCP tools per turn ⬜ Not started

**Files:** `server/services/mcp_client_service.py`, `server/inference/pipeline/mcp_tool_loop.py`,
`config/mcp_clients.yaml`

Reuse the two-stage pattern already proven in `server/services/skill_intent_router.py`:

1. Add `MCPClientManager.get_relevant_tools(message, allowed_servers, opportunistic_only, top_n)`
   next to `get_all_tools()` (`mcp_client_service.py:244-258`). Build a per-`(provider, toolset)`
   embedding index over each tool's `name + description` — mirror `_build_phrase_index` /
   `_phrase_cache` (`skill_intent_router.py:188-240`), including the `embed_query_tracked` +
   `accumulate_usage_sink` path so the embedding cost lands on the audit record.
2. Score with the same `_cosine` helper, keep tools above `embedding_threshold`, cap at `top_n`
   (config `mcp_clients.tool_selection.max_tools`, default 15).
3. **Always union in** every tool already called in this thread (walk `messages` for
   `tool_calls[].function.name`), so a multi-step task cannot lose a tool it is mid-way through.
4. Call it from `llm_inference.py:285-289` (`_run_inline_mcp_tools`) instead of `get_all_tools()`,
   and keep the resulting list **fixed for the whole loop** in `run_tool_calling_loop`
   (`mcp_tool_loop.py:126-127`) — do not re-select per iteration, or the cache prefix breaks and
   the model loses tools mid-plan.
5. Config gate `mcp_clients.tool_selection.enabled` (default `true`) with fallback to the full list
   when no embedding provider is configured — log one warning, never fail the turn.

**Saving:** 20k–50k → ~2-4k tokens per iteration, multiplied by up to 9 calls per MCP turn.

---

## Phase 4 — Correct the accounting so the win is visible 🟡 Partial

**Files:** `server/services/chat_history_service.py`,
`server/ai_services/providers/usage_reporting.py`, provider services, `docs/token-usage-and-cost-tracking.md`

1. ✅ Done (re-scoped) — `_calculate_max_token_budget` (`chat_history_service.py:262-264`) reserved
   a hardcoded `overhead_tokens = 700`; replaced with a configurable
   `history.system_overhead_tokens` (default `1200`) read from config. Did **not** implement
   "measure the actual system-message length when available" — the constant-with-config-override
   was simpler and sufficient for the immediate under-reservation bug.
2. ⬜ Not started (decided against, for now) — `_estimate_token_count`'s `len(content) // 3`
   heuristic left as-is. On inspection it's intentionally a fast placeholder used only for immediate
   storage; accurate tokenization already happens asynchronously via the `_tokenization_queue`.
   Swapping it for the real tokenizer synchronously here risked adding latency to every message
   write for a marginal accuracy gain — revisit if the async path turns out not to backfill in
   practice.
3. ⬜ Not started — no `cached_prompt_tokens`/`cache_write_tokens` extraction, no
   `cached_input_per_1m`/`cache_write_per_1m` pricing tiers. **Consequence:** Anthropic cache reads
   (now happening thanks to Phase 2b) are still priced at the full input rate in audit
   records/cost reporting — the token savings are real on Anthropic's invoice but not yet reflected
   in ORBIT's own cost estimate.
4. ✅ Done — `docs/token-usage-and-cost-tracking.md` has a new "Reducing prompt-token cost per turn"
   section documenting the gating, prefix/tail split, and the two `⬜` gaps above.

---

## Also noted, not doing (mention only)

- `_build_prompt` (`llm_inference.py:352-360`) builds the `messages` array **and** a redundant
  `f"{system_content}\n\nUser: {message}"` string. Every provider pops `messages` and ignores
  `prompt`, so this is **not** double-billed — it's wasted work and a misleading `context.full_prompt`
  in debug logs. Left alone; it's outside the token-cost ask.
- `_uses_native_chat_format` (`:340-350`) returns True only for `passthrough` adapters and
  `ollama*` providers. Non-passthrough OpenAI/Anthropic adapters therefore flatten history into one
  `"Role: content"` string (`:369-381`). This costs role fidelity and blocks caching for those
  adapters, but changing it alters behavior for every intent/RAG adapter — worth a separate task.

---

## Verification

1. **Unit** — new tests:
   - `server/tests/test_pipeline_steps/` — chart gate: `supports_charts: false` → no chart text;
     `true` + "hello" → `CHART_HINT` only; `true` + "show me a bar chart of sales" → `CHART_FULL`;
     chart fence in history → `CHART_FULL`.
   - Prefix stability: build the system message twice ~1s apart with the clock enabled and assert
     the first `cacheable_prefix_len` chars are byte-identical.
   - Anthropic `system` param shape with/without `cache_prefix_len`; assert the kwarg never reaches
     an unmigrated provider (extend `server/tests/test_pipeline_steps/test_llm_inference_usage.py`'s
     existing "legacy provider" case, which already proves this for `usage_sink`).
   - MCP tool selection: asserts cap respected, already-called tools always present, and full-list
     fallback with no embedding provider.
2. **Regression** —
   `venv/bin/python -m pytest server/tests/test_inference/ server/tests/test_pipeline_steps/ server/tests/test_services/test_pricing_service.py -q`
3. **End-to-end measurement** — start the server, send `"hello"` on `simple-chat` against a paid
   provider, and read `GET /admin/audit/events`:
   - Before: ~1,700 prompt tokens. Target after Phase 1: **< 550**.
   - Turn 2 on Anthropic: `cache_read_input_tokens > 0` and `cost_usd` visibly below turn 1's
     per-token rate.
   - With `skill:"mcp-agent"` / an MCP-triggering message: prompt tokens per iteration should drop
     from tens of thousands to low single-digit thousands.
4. `ruff check server/`
