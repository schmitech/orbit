# Reduce per-turn token consumption on paid APIs

## Status — roadmap complete

Every phase below is done or deliberately closed. The two `⬜` rows (Phase 2b's incremental
history/tool cache breakpoints, and Phase 4.2's synchronous tokenizer swap) are conscious
decisions not to implement, not deferred work — see each phase's detail section for the reasoning.
Manually verified end-to-end against a live server + OrbitChat per
`docs/qa/token-optimization-regression-playbook.md`, including the audit-ledger cost math for
Anthropic (with cache reads), xAI (with reasoning + cached tokens), and the MCP-tools path.

| Phase | Status | Notes |
|---|---|---|
| Phase 1 — Gate the chart formatting block | ✅ Done | `supports_charts` capability + hint/full split + intent gate shipped |
| Phase 2a — Stable prefix/tail split | ✅ Done | `build_system_message()` returns `(content, prefix_len)` |
| Phase 2b — Carry breakpoint to provider | 🟡 Partial | Anthropic only (explicit `cache_control`); OpenAI/Gemini need no code (benefit passively from 2a); Anthropic history/tool breakpoints (max 4) not added — single breakpoint only |
| Phase 2c — Extend caching to remaining providers (DeepSeek, xAI, Mistral, Cohere, Groq, etc.) | ✅ Done (DeepSeek, xAI, Anthropic usage) | DeepSeek `prompt_cache_hit_tokens` and xAI `prompt_tokens_details.cached_tokens` now extracted; Anthropic's own usage now also folds `cache_read_input_tokens`/`cache_creation_input_tokens` into prompt_tokens. Mistral/Cohere/Groq/other OpenAI-compatible providers audited — no documented caching mechanism found, left untouched (would need re-checking if a provider adds one) |
| Phase 3 — Relevance-filter MCP tools | ✅ Done | New `MCPToolSelector` (`server/services/mcp_tool_selector.py`), wired into both `LLMInferenceStep._run_inline_mcp_tools` and `MCPAgentStep._run_agent_loop`; gated by `mcp_clients.tool_selection` (default `enabled: true`, `max_tools: 15`) |
| Phase 4.1 — Fix history overhead constant | ✅ Done | `history.system_overhead_tokens` (default 1200), replaces hardcoded 700 |
| Phase 4.2 — Tokenizer-accurate estimate | ⬜ Not started (re-scoped) | Left `len//3` heuristic as-is — intentionally fast, real tokenizer already applied async; not a bug, decided not worth the risk |
| Phase 4.3 — Cache-token-aware pricing | ✅ Done | `cached_prompt_tokens` threaded through `usage_sink`/`accumulate_usage_sink`/`record_usage`; `PricingService` prices it at optional `cached_input_per_1m` (configured for Anthropic + DeepSeek in `config/pricing.yaml`), falls back to full input rate when no discount tier is configured (xAI: no confirmed discount, so full rate) |
| Phase 4.4 — Docs | ✅ Done | `docs/token-usage-and-cost-tracking.md` updated |

Also shipped, not in the original phase list: two post-review fixes — an
off-by-one in `_build_system_param` that silently skipped the cache
breakpoint when there was no volatile tail (the common case with
language/clock/RAG all disabled), and a missing `pytest.importorskip("anthropic")`
in the new caching test module so collection doesn't fail without the
optional Anthropic dependency installed.

Full regression suite as of this pass: `server/tests/test_inference/`,
`server/tests/test_pipeline_steps/`, `server/tests/test_services/`, `server/tests/test_adapters/` —
**1053 passed, 38 skipped, 1 pre-existing unrelated failure** (`test_chat_history_service.py`'s
`test_runtime_provider_selects_its_own_history_budget_without_param_overrides`, a stale expected
constant predating this pass, not caused by it).

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

  **Post-review fix (found during manual QA, not code review):** the breakpoint above was only ever
  reachable from the plain `generate()`/`generate_stream()` path. `generate_with_tools()` — the path
  every MCP-tools turn actually takes, whether the opportunistic inline loop (`mcp_tools: true`) or
  the explicit `mcp-agent` skill — accepted no `cache_prefix_len` at all and always sent `system` as
  a bare string, so **any adapter with tools enabled never got a cache hit on any turn**, including
  turns that didn't call a tool (the loop still sends the full tool schema on every call). Manual
  regression testing against `simple-chat-with-files` (`mcp_tools: true`) surfaced this as
  `cached_prompt_tokens: 0` on every turn despite the plain-generation path working correctly in
  isolation. Fixed by threading `cache_prefix_len` through the same `SUPPORTS_PROMPT_CACHING` gate
  the plain path uses, at every layer: `InferenceService.generate_with_tools_tracked()` (base gate),
  `UnifiedProviderAdapter`/`LLMProvider.generate_with_tools_tracked()` (pipeline layer),
  `AnthropicInferenceService.generate_with_tools()` (now calls `_build_system_param()` too),
  `mcp_tool_loop.py`'s `_call_with_tools()`/`run_tool_calling_loop()` (new `cache_prefix_len` param,
  forwarded to every iteration *and* the final no-tools synthesis call, since the system message
  doesn't change mid-loop), and both callers —
  `LLMInferenceStep._run_inline_mcp_tools` (already had `context.cacheable_prefix_len` computed, just
  never forwarded it) and `MCPAgentStep._run_agent_loop`/`_build_initial_messages` (was calling the
  prefix-losing `build_system_message_content()` wrapper instead of `build_system_message()`, so it
  had no prefix length to forward in the first place).
- **OpenAI** ✅ Passive win from 2a, ⬜ `prompt_cache_key` not added — automatic prefix caching
  already benefits from the stable prefix with zero code change; the optional
  `(adapter_name, system_prompt_id, model)`-derived `prompt_cache_key` for better cache routing was
  not implemented.
- **Gemini** ✅ Passive win from 2a — implicit caching benefits from the stable prefix with no API
  change, as planned. Explicit `cachedContent` intentionally not wired (as scoped).

**Saving:** on Anthropic, ~90% off the repeated prefix (system prompt + chart block + tools +
history) after turn 1. On OpenAI, 50% off cached input tokens. Reported cost falls out of this
automatically only if usage extraction also reads the cache fields — see Phase 4.

### 2c. Extend caching/cache-usage extraction to the remaining providers ✅ Done

Phase 2a's stable prefix already benefits *every* provider passively wherever the underlying API
does automatic/implicit caching — no code required. This subtask covers providers that need
usage-extraction changes to surface a cache hit that's already happening silently, and folds in
the pricing side of the gap (originally slated as a separate Phase 4.3 item — implemented together
since one is meaningless without the other):

- **DeepSeek** ✅ Done — `deepseek_inference_service.py`'s `generate`/`generate_stream` now read
  `usage.prompt_cache_hit_tokens` and pass it through `_report_usage(..., cached_prompt_tokens=...)`.
  No request-side flag needed; caching is automatic. `config/pricing.yaml`'s `deepseek-chat*` entry
  gets a `cached_input_per_1m: 0.028` tier (~1/10th of the input rate, matching DeepSeek's published
  cache-hit price).
- **xAI (Grok)** ✅ Done — confirmed `usage.prompt_tokens_details.cached_tokens` is populated
  (OpenAI-compatible shape); extracted in `generate`/`generate_stream`/`generate_with_tools` via a
  new `_extract_cached_prompt_tokens()` helper. No `cached_input_per_1m` tier added to
  `pricing.yaml` — xAI's docs don't confirm a discounted cache rate, so cached tokens fall back to
  the full input rate rather than guessing a discount (see `PricingService.estimate()` below).
  `_extract_cached_prompt_tokens()` also checks `input_tokens_details.cached_tokens` (the Responses
  API's shape for the same field), so the `web_search=True` branches in `generate`/`generate_stream`
  — which route through `client.responses.create` instead of `chat.completions` — now report
  cached tokens too (post-review fix; originally shipped only checking the chat.completions shape).
- **Anthropic usage accounting** ✅ Done (bonus, found while wiring the above) — Anthropic's
  `usage.input_tokens` excludes `cache_read_input_tokens` and `cache_creation_input_tokens` (both
  billed separately by Anthropic). All three `_report_usage()` call sites now sum all three into
  `prompt_tokens` via a new `_total_input_tokens()` helper, and pass `cache_read_input_tokens` as
  `cached_prompt_tokens` via `_cache_read_tokens()` — previously prompt_tokens silently undercounted
  actual billed input whenever a cache breakpoint (Phase 2b) hit.
- **Mistral** ⬜ Confirmed no work needed — no documented prompt-caching mechanism (implicit or
  explicit) as of this pass. Gets the passive benefit of Phase 2a's stable prefix only.
- **Cohere** ⬜ Confirmed no work needed — same as Mistral.
- **Groq, DeepInfra, Together, Fireworks, Cerebras, Moonshot, Minimax, Nebius, Scaleway,
  Perplexity, Venice** ⬜ Not individually re-audited this pass — all share the OpenAI-compatible
  `openai` python client; none currently extract cached-token usage. Revisit per-provider (some may
  proxy to upstream models that do support caching) rather than blanket-copying the
  DeepSeek/xAI pattern, since an unpopulated `prompt_tokens_details` is a silent no-op, not a bug.

**Pricing plumbing** (was Phase 4.3): `UsageReportingMixin._report_usage()`/`accumulate_usage_sink()`
now carry an optional `cached_prompt_tokens` field end-to-end through `usage_sink` ->
`record_usage()`'s line items -> `PricingService.estimate(..., cached_prompt_tokens=...)`.
`ModelRate` gained an optional `cached_input_per_1m`; when configured, the cached subset of
`prompt_tokens` is priced at that rate and the remainder at the normal `input_per_1m` rate; when not
configured (e.g. xAI, or any provider with no known discount), the entire `prompt_tokens` total is
priced at the full rate exactly as before — cached tokens are never left unpriced, only un-discounted.

**Saving:** DeepSeek and xAI cache hits are now priced accurately (DeepSeek at a real discount;
xAI at parity, ready for a discount once one is confirmed). Anthropic's prompt_tokens total is now
correct rather than undercounted, which also fixes `total_tokens`/`cost_usd` on any turn that hits
the Phase 2b cache breakpoint.

**Post-review fix (audit trail visibility):** `cached_prompt_tokens` was computed and priced
correctly by `record_usage()`/`PricingService`, but never actually persisted — `AuditService.log_conversation()`
only forwarded the fields `reasoning_tokens` and older were already whitelisted for, so
`context.metadata["usage"]["cached_prompt_tokens"]` was silently dropped before it reached the audit
record, and the admin panel's Audit tab had no way to show it during manual QA (see
`docs/qa/token-optimization-regression-playbook.md`, Section 3). Fixed by threading
`cached_prompt_tokens` through the same path `reasoning_tokens` already takes: `AuditRecord`
dataclass (`audit_storage_strategy.py`) → `log_conversation()` → the SQLite/Postgres `audit_logs`
table schema (auto-migrated onto existing installs via each service's `_migrate_table_schema`) →
each strategy's row-to-dict field whitelist → the Elasticsearch explicit type mapping → a new
"Cached prompt tokens" row in the Audit tab's detail dossier (`admin_panel/tabs/audit.js`), shown
only when the provider actually reported one.

---

## Phase 3 — Relevance-filter MCP tools per turn ✅ Done

**Files:** `server/services/mcp_tool_selector.py` (new), `server/inference/pipeline/steps/llm_inference.py`,
`server/inference/pipeline/steps/mcp_agent.py`, `config/mcp_clients.yaml`

Implemented as a standalone `MCPToolSelector` (single-stage embedding filter, no LLM-confirm stage
— a false positive here just offers the model one extra tool, not a wrong action, so the cheaper
approach is enough) rather than a new method on `MCPClientManager` itself — this keeps
`mcp_client_service.py` (which has no `adapter_manager` reference) unchanged, and lets the selector
be constructed cheaply per call while its embedding-client/phrase-index caches stay at class level
across requests:

1. ✅ `MCPToolSelector.select_tools(message, tools, adapter_name, context_messages, usage_sink)` —
   builds a per-`(embedding_provider, frozenset of tool names)` phrase index over each tool's
   `name + description`, mirroring `_build_phrase_index`/`_phrase_cache` from
   `skill_intent_router.py`, including the `embed_query_tracked`/`embed_documents_tracked` +
   `accumulate_usage_sink` path so embedding cost lands on the same `usage_sink` the tool-calling
   loop already reports into (and therefore on the audit record).
2. ✅ Scores with the same `_cosine` helper, keeps tools scoring `>= embedding_threshold` among the
   top `max_tools` by score (config `mcp_clients.tool_selection.max_tools`, default `15`;
   `embedding_threshold`, default `0.3`).
3. ✅ **Always unions in** every tool already called earlier in the thread — scans `context_messages`
   for `tool_calls[].function.name` — added on top of the capped selection, never dropped even if
   it pushes the returned list past `max_tools`. Post-review fix: this scan was originally a no-op
   for every ordinary stored-session follow-up, because `ChatHistoryService.get_context_messages()`
   only ever reconstructs `role`/`content` from the database — a persisted turn's message dict never
   carries a `tool_calls` key regardless of what tools it actually called. Fixed by having
   `response_processor.py` reduce a turn's `mcp_tool_call` sources to a flat `mcp_tools_used` name
   list and record it in that turn's stored metadata, and having `get_context_messages()` surface
   that field back onto the reconstructed message; `MCPToolSelector._called_tool_names()` now scans
   both `tool_calls` (the shape of a live in-memory tool-calling loop) and `mcp_tools_used` (the
   shape of a reloaded, persisted turn).
4. ✅ Called from `LLMInferenceStep._run_inline_mcp_tools` and `MCPAgentStep._run_agent_loop`
   (both via a shared `_select_relevant_tools` helper) right after `get_all_tools()`, before
   `run_tool_calling_loop` starts — the returned list is then passed into the loop once and stays
   fixed for every iteration (the loop was already structured this way; no change needed there).
5. ✅ Gated by `mcp_clients.tool_selection.enabled` (default `true`); no embedding provider
   configured, embedding-client init failure, tool count already at/under `max_tools`, or any
   internal exception all fall back to the unfiltered tool list rather than blocking the turn —
   the "no provider configured" case logs one warning (class-level flag, not per-request).

**Saving:** 20k–50k → ~2-4k tokens per iteration on adapters/servers with a large tool count,
multiplied by up to `max_tool_iterations` calls per MCP turn. No change on requests already at or
under `max_tools` tools — the selector skips embedding entirely in that case.

---

## Phase 4 — Correct the accounting so the win is visible ✅ Done (4.2 deliberately not implemented)

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
3. ✅ Done (moved into, and completed under, Phase 2c above) — `cached_prompt_tokens` extraction and
   `cached_input_per_1m` pricing tier implemented for Anthropic, DeepSeek, and xAI. ⬜ Not done:
   `cache_write_tokens`/`cache_write_per_1m` (Anthropic cache-creation writes are folded into
   `prompt_tokens` at the full input rate rather than their own ~1.25x premium tier — a known,
   accepted approximation, not a silent gap).
4. ✅ Done — `docs/token-usage-and-cost-tracking.md` has a new "Reducing prompt-token cost per turn"
   section documenting the gating, prefix/tail split, and cache pricing.

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
