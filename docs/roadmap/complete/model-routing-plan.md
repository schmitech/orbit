# Automatic Model Selection ("Auto" routing) — Implementation Plan

## Context

ORBIT adapters can already declare a client-selectable `allowed_models` list
(`config/adapters/multimodal.yaml`), and the project already ships System One
decision models (`docs/adapters/decision-models.md`,
`server/ai_services/services/decision_service.py`) — small, ~100ms classifier
models that return typed answers instead of generated text. Today these two
features are unconnected: a client must always pick a specific model by name,
and decision models can only answer questions, never steer which chat model
runs.

Many users have asked whether ORBIT can auto-select the cheapest/fastest model
capable of handling a given prompt (the way GitHub Copilot's "Auto" model
option works), instead of always calling an expensive model or forcing the
client to guess. This plan wires a decision model in as a lightweight router:
when a client picks the reserved `model: "auto"` entry on an adapter that opts
in, ORBIT asks a `score` decision question ("how much capability does this
request need?"), maps the answer to a routing tier, and picks that tier's
designated `allowed_models` entry — before the normal LLM call runs. If
routing is skipped, disabled, or fails for any reason, resolution falls back
to the adapter's normal default model, unchanged. A client that names a
specific `allowed_models` entry always bypasses routing entirely.

This is the second revision after two rounds of review. Round 1 caught:
discovery would silently drop the "auto" entry, `effort` was the wrong field
to route on, the score→tier mapping was underspecified, and routing's own
usage would be overwritten by the main chat call. Round 2 caught: the usage
fix still needed a concrete, non-duplicating consumer; the context-window
caveat needed an actual guard, not just a docs note; and a skill with no LLM
of its own could silently lose "auto" because the flag and the candidate
adapter config disagreed on which adapter's `allowed_models` mattered. All are
addressed below.

## Design

### 1. Reserved `"auto"` name + new `routing_tier` field (not `effort`)

`effort` on an `allowed_models` entry already means something else today — a
reasoning-effort parameter passed to the provider (Claude's `output_config.effort`,
OpenAI/Mistral/xAI `reasoning_effort`, Gemini `thinking_level`), not a ranking
of the model's capability/speed/price. Reusing it for routing would be wrong:
e.g. `multimodal.yaml`'s `claude` entry has `effort: "low"` (a cheap reasoning
setting) while being one of the more expensive, more capable models in the
list. Routing needs its own field.

Add an optional `routing_tier` to `allowed_models` entries (`"low"` |
`"medium"` | `"high"`, same three tiers the decision question will choose
among) and allow only exactly one entry per tier to avoid ambiguous "first
match" picking:

```yaml
allowed_models:
  - name: "gemma4-e2b"
    provider: "ollama"
    model: "gemma4-e2b-cpu"
    routing_tier: "low"
  - name: "minimax-m2.7"
    provider: "ollama_cloud"
    model: "minimax-m2.7:cloud"
    routing_tier: "medium"
  - name: "claude"
    provider: "anthropic"
    model: "claude-sonnet-4-5-20250929"
    effort: "low"
    routing_tier: "high"
```

Validate at config-load time, in `AdapterConfigManager` (see §4b) — not in
`request_context_builder.py`, which has no load/reload lifecycle — that at
most one entry per `routing_tier` value exists per adapter, and log/disable
`auto_model_selection` if it's enabled on an adapter with zero tiered
entries.

`"auto"` is a reserved pseudo-entry, written as a plain string sentinel, not a
real `allowed_models` row with empty `provider`/`model` — the discovery
endpoint (`server/routes/discovery_routes.py:229-244`) only includes rows
when `allowed_models` is truthy and maps `{name, provider, model}` without
filtering empties, so a bare `{"name": "auto"}` row would reach clients with
blank `provider`/`model` fields, which is confusing for a model picker.
Instead:

- Discovery (`server/routes/discovery_routes.py:131+`, `list_adapter_models`)
  explicitly prepends a synthetic `{"name": "auto", "provider": null, "model":
  null, "auto": true}` entry to the returned `models` list whenever the
  **resolved** `adapter_config` (after the function's existing `skill=`
  resolution at lines 187-227, which may swap `adapter_config`/`resolved_name`
  to the skill's own backing adapter) has
  `capabilities.auto_model_selection.enabled`. Since `"auto"` is excluded at
  request time for a skill with its own LLM (§1/§4c), it must not be
  advertised there either — so this check explicitly uses
  `skill_has_own_llm` (already computed at line 212 in that function) to
  suppress the synthetic entry: only add it when `not skill` or
  `not skill_has_own_llm`, i.e. exactly the two branches where
  `auto_select_requested` can actually become `True`. A UI can special-case
  the `auto: true` flag to render it as "Auto" rather than a concrete model.
- `resolve_runtime_model_override()` (`request_context_builder.py:87-157`)
  gets one new branch, checked before the `allowed_models` list lookup: if
  `requested_model == "auto"` and the adapter's capability has
  `auto_model_selection.enabled`, return `(None, None, None)` same as a
  no-op override (never a real provider/model pair) — it must NOT raise
  `ValueError` as an unrecognized name would. This function only returns a
  tuple and runs before a `ProcessingContext` exists (it's called standalone
  at `pipeline_chat_service.py:887`, ahead of context building, purely for
  the conversation-history token budget), so it cannot set a context flag
  itself.
- The actual `auto_select_requested` flag is set in `build_context()`
  (`request_context_builder.py:426-619`), next to each of the two branches
  that call `resolve_runtime_model_override()` for a chat-style adapter:
  - The `skill_inference_provider` branch (602-610), where the skill has its
    own LLM — **`auto_select_requested` is unconditionally `False` here**,
    regardless of `requested_model` or the skill adapter's capability. This
    is a deliberate v1 exclusion: conversation history for this turn was
    already fetched (`pipeline_chat_service.py:893-901`) against the
    *calling* adapter, before skill detection/swap ever runs, so there is no
    static baseline the load-time budget guard (§4c) can validate this
    branch's `allowed_models` tiers against. See §4c for the full reasoning.
  - The final `else` branch (611-619), where there's no skill or the skill
    has no LLM of its own — resolution runs against
    `original_adapter_name or adapter_name` (the **calling** adapter), since
    that's whose `allowed_models` was actually validated. This is the branch
    an earlier draft got wrong, by checking `final_cfg` (the skill's own,
    possibly LLM-less, config) instead.

  To avoid ModelSelectionStep re-deriving (and risking disagreeing with) this
  same branch logic later in the pipeline, `build_context()` also records
  **which** adapter name was used for resolution into a new
  `ProcessingContext` field, `model_routing_adapter_name: Optional[str]`,
  set in the *second* branch only (see below). `auto_select_requested` is
  computed **separately per branch** — there is deliberately no single shared
  expression, so the exclusion in the first branch can't be accidentally
  reintroduced by a future edit that generalizes the snippet:

  ```python
  # Branch 1: skill_inference_provider (602-610) — skill has its own LLM.
  # v1 exclusion (§4c): always False, regardless of requested_model or this
  # skill adapter's own auto_model_selection capability.
  auto_select_requested = False
  model_routing_adapter_name = None  # ModelSelectionStep never runs for this branch

  # Branch 2: the final `else` (611-619) — no skill, or a skill with no LLM
  # of its own. This is the ONLY branch where "auto" is honored in v1.
  model_routing_adapter_name = original_adapter_name or adapter_name
  routing_cfg = self.get_adapter_config(model_routing_adapter_name)
  auto_select_requested = (
      requested_model == "auto"
      and bool(routing_cfg.get('capabilities', {}).get('auto_model_selection', {}).get('enabled'))
  )
  ```
  Both `auto_select_requested` and `model_routing_adapter_name` (from
  whichever branch ran) are passed into the `ProcessingContext(...)`
  constructor call (line 628+).
  `ModelSelectionStep` (§3) then resolves `allowed_models` and the
  `auto_model_selection` config from
  `context.model_routing_adapter_name or context.adapter_name` — never from
  `context.adapter_name` alone — so it always agrees with what
  `resolve_runtime_model_override()` already validated. (This mirrors, but is
  distinct from, the existing `context.original_adapter_name` field used by
  `image_generation.py`/`context_retrieval.py`/`intent_no_match.py` for a
  different purpose — retrieval capabilities always follow the *caller*, but
  model routing must follow whichever adapter's `allowed_models` was
  resolved, which is the caller in one branch and the skill itself in the
  other.)

### 2. New capability block: `auto_model_selection`

Add to `AdapterCapabilities` (`server/adapters/capabilities.py`):

```python
auto_model_selection: Optional[dict[str, Any]] = None
```

Parsed in `from_config()` from `capabilities_config.get('auto_model_selection')`
verbatim (small dict, no dedicated dataclass needed). Example:

```yaml
capabilities:
  auto_model_selection:
    enabled: true
    decision_provider: "ollama"        # optional; defaults to decision.provider
    decision_model: "tev1:0.8b"        # optional; defaults to the provider's configured model
    instructions: "How much capability does this request need to answer well: simple lookup/chat, moderate reasoning, or complex/multi-step reasoning?"
    criteria: ["low", "medium", "high"]   # must match the routing_tier values used on allowed_models
    min_confidence: 0.4                   # below this, treat as a failed decision (see §3)
    state_key: "input"
    context_messages: 2                   # how many recent turns of context to include in state (see §4)
```

### 3. New pipeline step: `ModelSelectionStep`

New file `server/inference/pipeline/steps/model_selection.py`, reusing the
provider/service resolution pattern from `decision_model.py`:

- `should_execute(context)`: `False` if blocked, if
  `not context.auto_select_requested` (this alone already excludes clients
  that picked a specific model, and excludes `decision_model`-type adapters
  since `"auto"` is only ever set for a resolvable chat-style final adapter).
- `process(context)`:
  1. Build a single `score` question from the capability config
     (`instructions`, `criteria`). Reuse `validate_questions()` — extracted
     from `decision_model.py` into a shared helper
     `server/inference/pipeline/steps/_decision_support.py` so both steps
     import the same validation logic instead of duplicating it.
  2. State includes the current message plus, when
     `auto_model_selection.context_messages > 0`, that many of the most
     recent `context.context_messages` entries (joined/truncated) under an
     additional state key — so a short follow-up like "and for Spanish too?"
     is judged with its preceding turn in view, not in isolation. Default
     `context_messages: 0` (message-only) to keep the common case cheap;
     adapters with heavy multi-turn use can opt in.
  3. Resolve the decision provider/model: `decision_config.get('decision_provider')
     or config['decision']['provider']`, `decision_config.get('decision_model')`
     — same precedence `DecisionModelStep` uses. Get the service via
     `adapter_manager.get_decision_service(...)`.
  4. Call `service.decide(state, {"capability": question}, model=...)`.
  5. **Score interpretation** (precise rule, replacing the earlier
     under-specified version): the question has 3 ordered `criteria` levels
     (indices 0/1/2 = low/medium/high). `answer.score` is a fractional
     expected-level value in `[0, len(criteria)-1]`
     (`docs/adapters/decision-models.md`'s documented shape). Map it to a
     tier by **rounding to the nearest index** (`round(score)`, clamped to
     valid range) rather than floor/ceil, so a borderline 1.4 rounds to
     "medium" and 1.6 rounds to "high". Treat the following as a **failed
     decision** (go to step 7, degrade): `answer` missing or malformed
     (no `score`/`legend`), `answer.get("refused")` is true (OpenAI
     provider's documented refusal case), or `answer.get("confidence", 0) <
     auto_model_selection.min_confidence` (default `0.4` if unset) — a
     low-confidence router pick is worse than just using the adapter's
     normal default.
  6. Map the resolved tier label (e.g. `"medium"`) to the `allowed_models`
     entry on the *chat* adapter whose `routing_tier` equals that label
     (exact match only — §1 guarantees at most one per tier; no nearest-tier
     fallback, since an adapter might legitimately only define `low` and
     `high` and silently substituting a wrong tier is worse than just
     falling through to the adapter's configured default).
  7. **On any failure** (no decision provider configured, service error,
     invalid/low-confidence/refused answer, or no `allowed_models` entry for
     the resolved tier): log a warning (`logger.warning`, not `exception`,
     to avoid noisy stack traces for an expected degrade path) and return
     `context` unchanged — never call `context.set_error(...)`. This is the
     explicit "optimization, not requirement" contract: `LLMInferenceStep`
     then falls through to its existing precedence (`context.inference_provider`
     → global default), exactly as if `"auto"` had never been requested.
  8. On success, set `context.runtime_provider`, `context.runtime_model_name`,
     and `context.runtime_param_overrides` from the matched entry (the same
     fields `LLMInferenceStep._resolve_llm_provider()` reads first,
     `llm_inference.py:40-57` — no change needed there) and
     `context.auto_selected_model = match.get('name')` (new `ProcessingContext`
     field, default `None`) so later response/usage code can report what
     "auto" actually picked.
  9. Record the decision call's own usage via the **existing, already-correct
     mechanism** for exactly this situation — `add_usage_component(context,
     usage_sink, source="model_routing")` (`_utils.py:39-53`) — instead of
     `record_media_generation_usage`. This is the same helper
     `LLMInferenceStep`/`MCPAgentStep` use for every independently-priceable
     side call (embeddings, reranking) that precedes the main generation
     call. Critically, `record_usage()` (`_utils.py:332-454`) only special-cases
     components whose `source` is `"embedding"` or `"reranking"` — those get
     detached into their own separate audit rows via
     `extract_embedding_usage`/`extract_reranking_usage`. Any other `source`
     value (lines 391-408) is left in `_usage_components` and gets folded
     in as an extra **line item** inside the single chat usage row that
     `LLMInferenceStep` writes for this same request — each line item keeps
     its own `provider`/`model`/`source` and is priced independently
     (`_utils.py:456-467`) before the row's `cost_usd` is summed. So tagging
     the routing call's `usage_sink` with `source="model_routing"`
     automatically produces **one chat audit row whose cost includes the
     routing call, broken out as a labeled line item** — no separate
     `model_routing` audit row, no double counting, and no change needed to
     `record_usage()`, `record_media_generation_usage()`, or the
     observability `call_type` filter. `ModelSelectionStep` only needs to
     build a usage_sink dict in the shape `add_usage_component` expects
     (`{"reported": True, "provider", "model", "prompt_tokens",
     "completion_tokens", "total_tokens"}`) from the decision service's
     returned `usage`, and call `add_usage_component(context, sink,
     source="model_routing")` right after a successful `decide()` call —
     before the success/failure branch in step 7, so a routing call that
     succeeded but then found no matching tier still gets costed. On a
     decision-service error (no `decide()` result at all), nothing is added,
     consistent with "we only had the one chat call" in that case.

### 4. Conversation-history / context-window ordering — enforced guard, not just a caveat

`pipeline_chat_service.py:872-901` resolves `runtime_param_overrides` and
fetches conversation history via
`ChatHistoryService._get_token_budget_for_adapter()`
(`chat_history_service.py:259-310`) **before** `ModelSelectionStep` runs.
For `"auto"`, `resolve_runtime_model_override()` returns `(None, None, None)`
at that point, so the budget is computed from the adapter's own static
`context_window`/`inference_provider` default (or the global default) — call
this the **baseline context window**. If `ModelSelectionStep` later routes to
a tier whose model has a *smaller* context window than that baseline (e.g.
`multimodal.yaml`'s `gemma4-e2b` low-tier entry, `context_window: 8192`, vs. a
much larger adapter default), history already fetched against the baseline
budget could overflow the selected model's real limit. A doc note alone does
not prevent this, so v1 enforces it structurally instead of trimming twice:

**Load-time guard** (precise comparison in §4c, below — it must compare
*effective history budgets*, not raw context windows, since two tiers can
share a context window but reserve different output-token space): for any
adapter with `auto_model_selection.enabled`, every `allowed_models` entry
carrying a `routing_tier` must leave at least as much room for conversation
history as the adapter config that history was actually fetched against for
this request. A violation disables `auto_model_selection` for that adapter at
load (log an error naming the offending tier/model) rather than crashing
startup — consistent with `auto_model_selection` being an optional
optimization. This guarantees no tier `ModelSelectionStep` can route to ever
has a smaller usable window than what conversation history was already
budgeted against, without needing to re-fetch or re-trim history mid-pipeline.

### 4b. Config-load-time validation lives in `AdapterConfigManager`, shared by both load paths

Both the `routing_tier`-uniqueness check (§1) and the context-window/budget
guard above belong in `AdapterConfigManager` (`server/services/config/
adapter_config_manager.py`) — the actual config loader — not in
`request_context_builder.py`, which only reads already-loaded adapter configs
per-request and has no load/reload lifecycle. **`reload_from_config()`
(lines 129-183) does not call `_load_configs()`** — it independently builds
`new_adapter_configs` inline (lines 143-149) and diffs it against the current
map. So the checks must live in one new method, e.g.
`_validate_auto_model_selection(adapter_configs: dict[str, dict])`, called
from **both** `_load_configs()` (after it populates `self._adapter_configs`,
around line 63) **and** `reload_from_config()` (after line 149, against
`new_adapter_configs`, before line 171's reassignment) — the same pattern
already used for change detection (`ConfigChangeDetector.configs_differ`)
being called from the reload path independently of the initial-load path.
On a violation for a given adapter, mutate that adapter's in-memory
`capabilities.auto_model_selection` to disabled (or drop the key) and log an
error naming the adapter and the offending tier/model, in whichever dict
(`self._adapter_configs` or `new_adapter_configs`) is being validated — never
raise and abort the whole load, consistent with `auto_model_selection` being
an optional, best-effort feature.

### 4c. The guard compares usable history budgets, not raw context windows

A raw `context_window` comparison (as drafted in §4) is insufficient:
`ChatHistoryService._calculate_max_token_budget()`
(`chat_history_service.py:178-252`) reserves `max_output_tokens` (the
model's own `max_tokens`/`num_predict`, which varies per `allowed_models`
entry) plus a fixed `overhead_tokens` (`history.system_overhead_tokens`,
default 1200) before computing `available_tokens = context_window -
reserved_tokens`. Two tiers can share the same `context_window` but leave
very different space for history if their `max_tokens` differ — a higher-tier
entry with `max_tokens: 65536` reserves far more output budget than a
low-tier entry with `max_tokens: 2048`. The guard must therefore compare
**effective history budgets**, using the same formula, not bare
`context_window` values.

Critically, the helper must resolve each side using the **same inheritance
chain the real request path uses**, not just the bare entry — a `routing_tier`
entry that omits `context_window` or `max_tokens` inherits from the adapter's
own config, which in turn inherits from `inference.yaml`'s provider defaults
(resolved through any `use_preset`), exactly as
`DynamicAdapterManager.get_overridden_provider()`
(`dynamic_adapter_manager.py:303-334`, "runtime > adapter >
inference.yaml") and `_calculate_max_token_budget()`
(`chat_history_service.py:192-220`, which already layers `adapter_config`
over `inference_config` and resolves presets via `_resolve_preset_config()`)
both do. A helper that only inspects the bare `allowed_models` entry would
wrongly treat a missing `max_tokens` as "no reservation" and overstate that
tier's effective budget, making the guard pass when the real request would
actually reserve more and have less room for history. So:

```python
def _effective_history_budget(
    provider_name: str,
    overrides: dict,           # the allowed_models entry's own temperature/max_tokens/
                                # context_window/effort, or {} for the adapter's own baseline
    adapter_config: dict,      # the adapter's own config (for its context_window/max_tokens)
    global_config: dict,       # for inference.yaml + presets + history.system_overhead_tokens
) -> int:
    # Same layering as _calculate_max_token_budget(), applied with `overrides`
    # (a routing_tier entry) standing in for the per-request runtime override:
    # overrides > adapter_config > inference.yaml (presets resolved) — i.e.
    # effective_config = {**inference_config, **adapter_overrides, **overrides}.
    # Then: available = effective_context_window - (effective_max_tokens + overhead_tokens).
    ...
```

For the adapter's own baseline (used on the comparison's right-hand side),
call this with `overrides={}`, `provider_name=adapter_config.get('inference_provider')` —
i.e. exactly what `_calculate_max_token_budget(adapter_config)` already
computes today, so the guard can simply reuse
`ChatHistoryService._calculate_max_token_budget()` directly for the baseline
rather than reimplementing it, and only needs the new
`_effective_history_budget()` helper for the `routing_tier` entry side (where
the entry's own `provider`/`context_window`/`max_tokens` must be layered over
the *adapter's* config, not the global default, since an entry without its
own override still runs under the adapter's settings for anything it omits).

The baseline to compare against is **whichever adapter config conversation
history was actually fetched against** for this turn. Checking the actual
call order in `pipeline_chat_service.py` settles this precisely: history is
fetched at lines 893-901 (`get_context(session_id, adapter_name, ...)`)
**before** skill detection (`_maybe_detect_skill`, lines 904-910) and before
`build_context()` (line 913+, where the skill→backing-adapter swap actually
happens). So `adapter_name` at the history-fetch call site is **always the
original calling adapter**, in every case — there is no branch where history
is fetched against a skill's own config, even when that skill has its own
`inference_provider`/`allowed_models` and ends up as the final adapter the
chat call runs against.

This means the load-time guard (comparing a `routing_tier` entry's effective
budget against a *statically known* baseline) is only sound for the two
branches where **the routing adapter and the history-fetch adapter are the
same adapter**:
- The no-skill case: `model_routing_adapter_name == adapter_name` (the single
  calling adapter) — baseline is that adapter's own static config. Guard
  applies.
- The no-own-LLM-skill case: `model_routing_adapter_name ==
  original_adapter_name or adapter_name` — i.e. the **calling** adapter,
  which is exactly the adapter history was fetched against. Guard applies.
- The skill-with-its-own-LLM case: `model_routing_adapter_name == adapter_name`
  is the **skill's own backing adapter**, but history was fetched against the
  unrelated **calling** adapter, whose static config the skill's config has
  no fixed relationship to (many different calling adapters can route to the
  same skill, each with a different history budget). A load-time check
  against the skill's own config alone cannot bound this; it would need the
  actual caller at request time, which the config loader doesn't have.

**v1 decision: exclude "auto" on skill adapters with their own LLM.** In
`build_context()`'s `skill_inference_provider` branch (602-610, §1),
`auto_select_requested` is unconditionally forced to `False` regardless of
the capability or `requested_model` value — the same silent-degrade
philosophy as a failed routing call, just decided earlier. `"auto"` is only
honored for the no-skill and no-own-LLM-skill branches, where the guard in
§4c is sound. This is documented as a known v1 scope limit in §7; a later
iteration could lift it by re-fetching/re-trimming history after
`ModelSelectionStep` runs for that one branch, but that's follow-on work, not
part of this plan.

For the two branches `"auto"` *does* support, the correct baseline is simply
`ChatHistoryService._calculate_max_token_budget(adapter_config)` for
`adapter_config = get_adapter_config(model_routing_adapter_name)` (per §4c's
note that the baseline side reuses that existing method directly). The
per-adapter validation then requires, for every `routing_tier`-tagged
`allowed_models` entry:
```python
_effective_history_budget(
    provider_name=entry.get('provider') or adapter_config.get('inference_provider'),
    overrides=entry,
    adapter_config=adapter_config,
    global_config=config,
) >= baseline
```
— entirely config-shape-driven, no runtime context needed, since
`model_routing_adapter_name` is, by construction, the same adapter whose
config is passed through `_load_configs()`/`reload_from_config()`.

### 5. Pipeline wiring

In `InferencePipelineBuilder.build_standard_pipeline()`
(`server/inference/pipeline/pipeline.py:372-438`), insert `ModelSelectionStep`
immediately after `DecisionModelStep` and before `LLMInferenceStep`. No change
to `process_stream()`'s step-skipping logic is needed — streaming already
runs all non-LLM/non-MCP steps normally before specially driving the LLM
call, so `ModelSelectionStep` runs there too and its `runtime_*` writes are
visible to the subsequent streamed `LLMInferenceStep` call.

### 6. Output plumbing

Surface `context.auto_selected_model` alongside `model`/`decision` at the
same three call sites `docs/adapters/decision-models.md` already documents
for `decision`, plus the two additional sites review flagged that also
construct response payloads directly:

- `server/services/chat_handlers/streaming_events.py`, `streaming_handler.py`,
  `response_processor.py` — non-streaming body, final streaming event.
- `server/services/pipeline_chat_service.py` (~line 887 area's surrounding
  `process_chat` result dict) — add `auto_selected_model` to the result dict
  wherever `decision`/`model` are already placed, so it flows into
  `routes_configurator.py`'s consumption of `result`.
- `server/routes/routes_configurator.py:734-742` — the OpenAI-compatible
  completion builder already special-cases `extra={"decision": ...}`; extend
  the same `extra` dict with `"auto_selected_model": result["auto_selected_model"]`
  when set, so it reaches the `orbit.*` block the same way `orbit.decision`
  does today.

### 6b. OrbitChat client support (optional, scoped as a follow-on)

`clients/orbitchat/src/types/index.ts:67-71` types `AllowedModel` with
`provider: string` and `model: string` (non-nullable), and
`ModelPickerButton.tsx`/`modelsService.ts`/`MessageInput.tsx` consume that
shape to render the model picker. The synthetic `"auto"` discovery entry (§1)
has `provider: null, model: null`, which doesn't fit the current type. If
OrbitChat should display an "Auto" option (recommended, since it's the
reference first-party client and this feature is explicitly modeled on
Copilot's "Auto" UX), this plan includes:
- `clients/orbitchat/src/types/index.ts`: widen `AllowedModel.provider`/
  `.model` to `string | null`, add `auto?: boolean`.
- `clients/orbitchat/src/services/modelsService.ts`: pass the `auto` flag
  through unchanged.
- `clients/orbitchat/src/components/ModelPickerButton.tsx`: render the
  `auto: true` entry distinctly (e.g. an "Auto" label/icon instead of a
  provider/model pair), and
- `clients/orbitchat/src/components/MessageInput.tsx`: ensure selecting it
  sends `model: "auto"` like any other picker entry (no special-casing needed
  there if the existing send path already forwards the picked `name`
  verbatim — confirm during implementation).
This is scoped as part of this plan (not a separate follow-up) since without
it the only visible result of §1 is an API-level capability with no UI to
exercise it in ORBIT's own reference client.

### 7. Documentation

Add `docs/adapters/auto-model-selection.md` (cross-linked from
`docs/adapters/decision-models.md`'s comparison table), covering: the
reserved `"auto"` name and how it differs from a normal `allowed_models`
entry, the `routing_tier` field (and why it's separate from `effort`), the
`auto_model_selection` capability block, the exact score→tier rounding and
confidence/refusal degrade rules from §3, the usage/cost component behavior
from §3.9, the context-window ordering caveat from §4, and a worked example
using `config/adapters/multimodal.yaml`.

## Files touched

| File | Change |
|---|---|
| `server/inference/pipeline/base.py` | Add `auto_select_requested: bool = False`, `auto_selected_model: Optional[str] = None`, and `model_routing_adapter_name: Optional[str] = None` to `ProcessingContext` |
| `server/services/chat_handlers/request_context_builder.py` | `resolve_runtime_model_override()`: treat `"auto"` + capability enabled as a no-op override (no `ValueError`); `build_context()`: compute `model_routing_adapter_name` and `auto_select_requested` per-branch (§1) and pass both into `ProcessingContext(...)` |
| `server/services/config/adapter_config_manager.py` | New shared `_validate_auto_model_selection()` (routing_tier uniqueness + effective-history-budget guard, §4/§4b/§4c), called from both `_load_configs()` and `reload_from_config()`; disables `auto_model_selection` with a logged error on violation |
| `server/routes/discovery_routes.py` | Prepend a synthetic `{"name": "auto", "provider": null, "model": null, "auto": true}` row when `auto_model_selection.enabled` |
| `server/adapters/capabilities.py` | Add `auto_model_selection: Optional[dict]` field + `from_config()` wiring |
| `server/inference/pipeline/steps/_decision_support.py` (new) | Shared `validate_questions()` extracted from `decision_model.py` |
| `server/inference/pipeline/steps/decision_model.py` | Import `validate_questions` from the new shared module |
| `server/inference/pipeline/steps/model_selection.py` (new) | `ModelSelectionStep` as designed in §3, using `add_usage_component(..., source="model_routing")` from `_utils.py` (no changes needed to `_utils.py` itself) |
| `server/inference/pipeline/pipeline.py` | Register `ModelSelectionStep` between `DecisionModelStep` and `LLMInferenceStep` |
| `server/services/pipeline_chat_service.py` | Surface `auto_selected_model` in the `process_chat` result dict |
| `server/services/chat_handlers/streaming_events.py`, `streaming_handler.py`, `response_processor.py` | Surface `auto_selected_model` alongside `model`/`decision` |
| `server/routes/routes_configurator.py` | Add `auto_selected_model` to the OpenAI-compatible completion's `extra` dict (~line 741) |
| `docs/adapters/auto-model-selection.md` (new) | User-facing docs |
| `docs/adapters/decision-models.md` | Cross-reference the new doc |
| `clients/orbitchat/src/types/index.ts` | Widen `AllowedModel.provider`/`.model` to `string \| null`, add `auto?: boolean` (§6b) |
| `clients/orbitchat/src/services/modelsService.ts`, `components/ModelPickerButton.tsx`, `components/MessageInput.tsx` | Render and select the "Auto" entry (§6b) |
| `server/tests/test_model_selection/` (new) | Unit tests (see Verification) |

## Verification

1. **Unit tests** (new `server/tests/test_model_selection/test_model_selection_step.py`):
   - `should_execute` is `False` without `auto_select_requested`.
   - A mocked decision service returning `score≈1.4`/`confidence=0.8` resolves
     to the `"medium"`-tier `allowed_models` entry; `score≈1.6` resolves to
     `"high"` (boundary rounding behavior from §3.5).
   - `confidence` below `min_confidence`, a `refused: true` answer, and a
     missing/malformed answer all leave `context` unchanged with no error set
     and `context.auto_selected_model is None`.
   - No `allowed_models` entry carries the resolved `routing_tier` → falls
     through unchanged (no nearest-tier substitution).
   - Decision-service exception → `context` returned unchanged,
     `is_blocked`/`has_error()` both false.
   - Usage: after a successful routing decision, a `source="model_routing"`
     component is present in `context.metadata["_usage_components"]`; after a
     subsequent (simulated) `record_usage()` call for the main chat
     generation, the resulting single usage row's `line_items` includes the
     `model_routing` entry and the row's `cost_usd` reflects both the routing
     and chat costs summed (no separate `model_routing`-call-type row is
     created).
   - A skill with no LLM of its own: `context.adapter_name` is the skill
     adapter, `context.model_routing_adapter_name` is the calling adapter;
     `ModelSelectionStep` resolves `allowed_models`/`auto_model_selection`
     from the calling adapter's config, matching what
     `resolve_runtime_model_override()` validated against, per §1.
   - A skill **with its own LLM**: even with `requested_model == "auto"` and
     `auto_model_selection.enabled` on the skill's backing adapter,
     `context.auto_select_requested` is `False` and `ModelSelectionStep`
     never runs — confirms the v1 exclusion from §1/§4c.
2. **Config validation tests** (`AdapterConfigManager`, per §4b/§4c): two
   `allowed_models` entries sharing the same `routing_tier` on an adapter with
   `auto_model_selection.enabled` disables it with a logged error, both via
   `AdapterConfigManager(config)` (initial load) and via
   `reload_from_config(new_config)` on an existing instance (separate test for
   each path, since they don't share code today). Same for a tiered entry
   whose effective history budget (context window minus its own `max_tokens`
   and the configured overhead) is smaller than the baseline adapter's — and a
   case proving two tiers with equal `context_window` but different
   `max_tokens` are correctly distinguished (the scenario a raw
   context-window comparison would miss). Add a case where a `routing_tier`
   entry omits `max_tokens`/`context_window` entirely and confirm
   `_effective_history_budget()` resolves them by inheriting from the
   adapter's own config (then the provider/preset defaults), not by treating
   the omission as zero reservation — i.e. prove the guard would still catch
   a real mismatch for an entry that only overrides `provider`/`model`. Add a dedicated case for the §4c
   exclusion: a calling adapter with a large context window (e.g. 1M tokens)
   invoking a skill whose own backing adapter has `auto_model_selection`
   enabled with a small-window low tier (e.g. 8K) — assert this configuration
   is accepted at load time (no guard violation, since the skill-with-its-own-LLM
   branch is excluded from the budget guard entirely, per §4c) and that the
   protection instead comes from the request-time exclusion verified in
   item 1's skill-with-its-own-LLM test above.
3. **Existing test suites must still pass**: run
   `/Users/remsyschmilinsky/Downloads/orbit/venv/bin/python -m pytest server/tests/test_decision/` and the
   broader `server/tests/` suite from `server/`, confirming
   `resolve_runtime_model_override` and `DecisionModelStep` behavior for
   non-`"auto"` requests, and discovery-route tests for adapters without
   `auto_model_selection`, are unaffected.
4. **End-to-end manual check**: enable `auto_model_selection` on a copy of
   `simple-chat-with-files` with `routing_tier` added to 2-3 of its existing
   `allowed_models` entries (sized so all pass the context-window guard),
   start the server, call `GET /adapters/<adapter_name>/models` (the
   adapter-scoped discovery endpoint, `discovery_routes.py:131`) and confirm
   the synthetic `"auto"` entry appears, then send `model: "auto"` requests of
   varying complexity and confirm via the response's `auto_selected_model`
   field that different tiers are chosen, and via the admin Costs tab that
   the request's single chat-call usage row's cost includes the routing
   call's tokens. Confirm a request naming a specific `allowed_models` entry
   still bypasses routing entirely.
