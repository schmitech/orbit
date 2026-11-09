# Pipeline Steps — Simplification/Altitude Roadmap

## Summary

A `/simplify` pass over `server/inference/pipeline/steps/` (21 files, ~6.7k
lines) found a quick-win layer already applied (see "Shipped" below) plus a
larger body of duplication and architectural drift that's riskier or wider
than a quick win — mostly concentrated in the four media-generation steps
(`image_generation.py`, `video_generation.py`, `audio_generation.py`,
`document_generation.py`) and in how steps decide "is this my adapter type?"
Tracked here as phased follow-up work, not urgent.

---

## Shipped (for reference — no longer tracked here)

- **`_get_adapter_type` dedup**: the identical module-level helper copied into
  `image_generation.py`, `video_generation.py`, `audio_generation.py`,
  `document_generation.py`, and `mcp_agent.py` now all import
  `_utils.get_adapter_type` instead (already the single implementation used by
  `fetch.py`/`web_search.py`).
- **`_resolve_provider` dedup**: `image_generation.py`, `video_generation.py`,
  `audio_generation.py`'s near-identical provider-resolution methods (runtime
  override → adapter-config key → global config section) now call one shared
  `_utils.resolve_media_provider(container, context, config, adapter_override_key,
  config_section)`.

---

## Phase 1 — Consolidate rewrite-provider resolution (quick-ish, needs care)

`_resolve_rewrite_provider` is duplicated (~50-60 lines each) across
`image_generation.py`, `video_generation.py`, `audio_generation.py`. Not
folded into Phase-0 because `audio_generation.py`'s version also threads an
`explicit_model_override=rewrite_model` parameter the other two don't have —
needs a careful look at whether that's intentional per-step behavior or a gap
in image/video, before picking one shared signature.

`document_generation.py`'s `_resolve_rewrite_providers` (plural) is **not** a
minor variant of this and should not be merged into the same helper: it
returns an ordered, de-duplicated list of candidate providers (ranked
rewrite_provider → original-adapter → skill-adapter → global), and
`_generate_spec` retries down that list when a candidate fails (e.g. a bad API
key), falling back to a bare fallback document only once the whole list is
exhausted. Any shared helper for the single-provider steps must stay separate
from — or be a thin wrapper feeding into — document generation's candidate-list
+ retry + dedup-by-provider/model logic, not a replacement for it.

- Land one `_utils.resolve_rewrite_provider(container, context, *, model_override=None)`
  helper for image/video/audio; decide the `rewrite_model` question first.
- Leave `document_generation.py`'s candidate-list resolver as its own function;
  revisit only if/when it can share the single-candidate resolution step
  without losing the ordered-list/retry/dedup behavior.

**Acceptance checks for this phase:**
- Provider precedence (rewrite_provider → original-adapter inference_provider →
  skill-adapter inference_provider → global) is unchanged for image/video/audio.
- `audio_generation.py`'s `explicit_model_override=rewrite_model` still reaches
  `get_overridden_provider` exactly as before.
- `document_generation.py` still retries the next candidate on a failed
  generation call and still de-dupes by provider/model (not just provider).

## Phase 2 — Adapter capability registry: express routing/behavior flags generically

`server/adapters/capabilities.py` (`AdapterCapabilities` /
`AdapterCapabilityRegistry`) is already used properly by
`context_retrieval.py`/`document_reranking.py`, but several other steps still
reach into raw `adapter_manager.get_adapter_config()` dicts and string-match
adapter type names instead:

- `llm_inference.py`'s `NO_LLM_ADAPTER_TYPES` (`_utils.py:13-24`) and
  `NO_INFERENCE_PROVIDER_ADAPTER_TYPES` (`_utils.py:30-36`) are hand-maintained
  frozensets of adapter-type strings that must be kept in sync by hand.
- `llm_inference.py:441-446`'s `_uses_native_chat_format` hardcodes
  `adapter_config.get('type') == 'passthrough'`.
- `REWRITABLE_GENERATION_ADAPTER_TYPES` + `adapter_bypasses_rewrite_provider`
  (`_utils.py:270-289`) re-derive rewrite-eligibility from adapter type string
  + raw config access, duplicating a per-adapter decision context_retrieval.py
  already models via capabilities for a different flag
  (`supports_followup_rewrite`).

Correction to an earlier draft of this doc: `NO_INFERENCE_PROVIDER_ADAPTER_TYPES`
**is** a subset of `NO_LLM_ADAPTER_TYPES` — not two independently-drifting
sets. `document_generation` is in `NO_LLM_ADAPTER_TYPES` (it never calls the
*main* inference LLM — `document_generation.py` is its own step) but
correctly absent from `NO_INFERENCE_PROVIDER_ADAPTER_TYPES`, because it still
needs a text-inference provider for spec generation (`_resolve_rewrite_providers`
above). So these are two distinct, intentional questions — "does this adapter
type call the main LLM step?" vs. "does this adapter type need a text
inference provider at all (for anything)?" — and must stay as separate
capability flags, not be collapsed into one.

Proposed direction: extend `AdapterCapabilities` with explicit, separately-named
flags:
- `calls_main_llm` — replaces `NO_LLM_ADAPTER_TYPES` membership.
- `needs_text_inference_provider` — replaces `NO_INFERENCE_PROVIDER_ADAPTER_TYPES`
  membership; used by provider preload/validation *before* a request is
  processed, so it must be derivable from static adapter config alone (no
  per-request state).
- `uses_native_chat_format` — replaces the `adapter_config.get('type') ==
  'passthrough'` check in `llm_inference.py:441-446`.
- `prompt_rewrite_enabled` — replaces `REWRITABLE_GENERATION_ADAPTER_TYPES` +
  `adapter_bypasses_rewrite_provider`. Keep this distinct from
  `supports_followup_rewrite` (already on `AdapterCapabilities` for
  `context_retrieval.py`/`intent_query_rewrite.py`) — that flag governs
  rewriting a *follow-up retrieval query*, a different feature from rewriting
  a *generation prompt*; they must not be merged even though the names are
  similar.

Registry/init semantics to pin down before implementing:
- `AdapterCapabilityRegistry` is keyed by adapter name and populated lazily
  (confirm against current `capabilities.py` behavior) — new flags need a
  defined default when an adapter's capabilities haven't been computed yet
  (e.g. at preload/validation time, before first request), not just an
  exception path.
- Each flag's value must come from adapter config with an explicit safe
  default (matching today's `.get(key, True/False)` defaults in `_utils.py`),
  not inferred from adapter type alone, so a future adapter type isn't
  silently miscategorized.
- Config reload: if adapters can be reloaded/edited at runtime, confirm
  whether the registry's cached capabilities get invalidated, and whether
  preload/validation re-runs against the new config or only at startup.

This is the highest-value fix but also the widest-blast-radius one (touches
`capabilities.py`, the registry, and every step currently doing ad hoc type
checks) — do it as its own reviewed change, not bundled with Phase 1.

**Acceptance checks for this phase:**
- Every adapter type currently in `NO_LLM_ADAPTER_TYPES` has `calls_main_llm =
  False`, and every type in `NO_INFERENCE_PROVIDER_ADAPTER_TYPES` has
  `needs_text_inference_provider = False`, with `document_generation` as the
  key differential case (False/True respectively).
- `uses_native_chat_format` is `True` only for `passthrough`, matching current
  behavior.
- `prompt_rewrite_enabled` and `supports_followup_rewrite` remain independently
  toggleable per adapter (test an adapter with one on and the other off).
- A capability lookup for an adapter not yet in the registry (pre-first-request,
  e.g. during preload/validation) returns the documented safe default rather
  than raising.
- After a config reload, capability flags reflect the new config (or, if reload
  isn't actually supported for adapter capabilities, that's stated explicitly
  rather than left silently stale).

## Phase 3 — Per-request efficiency

Checked against current code before listing — two items from an earlier draft
didn't hold up and are dropped (see "Not pursued" below):

- `_get_mcp_manager`/`_get_tool_skill_registry` logic is duplicated verbatim
  between `llm_inference.py` and `mcp_agent.py` — factor into one shared
  helper (natural fit once Phase 1/2 land, since both already touch `_utils.py`).
  This is a reuse/readability win, not a performance one.
- `adapter_manager.get_adapter_config(adapter_name)` is independently refetched
  5-8 times per request across `context_retrieval.py`, `document_reranking.py`,
  `llm_inference.py`, `mcp_agent.py`, `fetch.py`, `web_search.py`. Before
  changing anything: profile/measure what `get_adapter_config` actually costs
  (in-memory dict lookup vs. something heavier) — if it's already cheap, a
  per-request cache on `ProcessingContext` adds complexity for no measurable
  gain. If it does show up, sequence after Phase 2 settles what capability
  data looks like, since that's the natural place to cache it.
- `language_detection.py`'s `_detect_spans` awaits each span's
  `_detect_language_ensemble_async(piece)` sequentially in a loop for
  mixed-language messages. Only worth changing if profiling shows this path is
  hot (messages with 3+ qualifying spans) — if so, prefer bounded concurrency
  (e.g. `asyncio.gather` over the spans with a semaphore, or a small
  `asyncio.Semaphore`-gated gather) rather than unbounded `gather`, since each
  span call already fans out to multiple backends internally.

## Not pursued

- **`MCPToolSelector` per-request construction**: looked like a caching
  opportunity but isn't — `MCPToolSelector.__init__` only reads config values
  into instance attributes; the actual expensive state (`_embedding_clients`,
  `_phrase_cache`) is already class-level and shared across every instance and
  request (`services/mcp_tool_selector.py:40-45`). No caching needed.
- **`DocumentRenderer` per-request construction**: `DocumentRenderer.__init__`
  (`ai_services/services/document_generation_service/renderer.py:36-37`) only
  stores the config dict; it does no font/template loading. No caching needed.
- `_utils.py`'s `extract_reranking_usage`/`extract_embedding_usage` share a
  "partition by predicate, write back remainder" shape, but the predicates and
  output shapes differ enough (usage units vs plain tokens) that a forced
  shared helper looked like it would cost more readability than it saved —
  left as-is.
