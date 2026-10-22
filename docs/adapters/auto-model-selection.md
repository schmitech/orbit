# Automatic Model Selection ("Auto" Routing)

Lets a client pick a reserved `model: "auto"` entry instead of naming a
specific `allowed_models` entry. ORBIT asks a small [decision
model](decision-models.md) how much capability the turn needs, and routes to
the `allowed_models` entry tagged for that tier — before the normal chat LLM
call runs. This is the same idea as GitHub Copilot's "Auto" model option:
cheap/fast models handle simple turns, expensive/capable models are reserved
for turns that actually need them.

If routing is disabled, fails, or can't resolve a tier, ORBIT silently falls
back to the adapter's normal default model — "auto" never blocks a request. A
client that names a specific `allowed_models` entry always bypasses routing
entirely.

## Setup

### 1. Tag `allowed_models` entries with a `routing_tier`

`routing_tier` is **separate from `effort`** — `effort` controls a provider's
reasoning-effort parameter (Claude's `output_config.effort`, OpenAI/Mistral/xAI
`reasoning_effort`, Gemini `thinking_level`); `routing_tier` ranks the
model's overall capability/speed/price for routing purposes. An adapter may
set at most one `allowed_models` entry per tier (`low`/`medium`/`high`):

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
    effort: "low"           # unrelated to routing_tier
    routing_tier: "high"
```

### 2. Enable `auto_model_selection` on the adapter's capabilities

```yaml
capabilities:
  auto_model_selection:
    enabled: true
    decision_provider: "ollama"        # optional; defaults to decision.provider (see decision-models.md)
    decision_model: "tev1:0.8b"        # optional; defaults to the provider's configured model
    instructions: "How much capability does this request need to answer well: simple lookup/chat, moderate reasoning, or complex/multi-step reasoning?"
    criteria: ["low", "medium", "high"]   # must match the routing_tier values used on allowed_models
    min_confidence: 0.4                   # below this, a routing decision is treated as failed (see below)
    state_key: "input"
    context_messages: 0                   # how many recent turns to include when judging a follow-up
```

A client can then discover and request `"auto"`:

```bash
curl -H "X-API-Key: <key>" http://localhost:3000/adapters/<adapter_name>/models
# {"adapter_name": "...", "has_restrictions": true,
#  "models": [{"name": "auto", "provider": null, "model": null, "auto": true}, ...]}

curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" -H "X-API-Key: <key>" \
  -d '{"messages":[{"role":"user","content":"..."}], "model": "auto"}'
```

The response includes `auto_selected_model` (the `allowed_models` `name` that
was actually picked) alongside `model`, both for `/v1/chat` and the
OpenAI-compatible `/v1/chat/completions` (`orbit.auto_selected_model`).

## How the tier is chosen

`ModelSelectionStep` asks a single `score` question with your `criteria` as
the ordered levels. The answer's `score` (a fractional expected level) is
rounded to the nearest index to pick a tier — e.g. with three levels
`[low, medium, high]`, a score of 1.4 rounds to `medium`, 1.6 rounds to
`high`.

A routing decision is treated as **failed** — falling back to the adapter's
normal default model — when any of the following holds:
- The decision provider isn't configured or the call errors.
- The answer is missing, malformed, or `refused` (a documented possibility
  for the `openai` decision provider).
- `confidence` is below `min_confidence`.
- No `allowed_models` entry on the adapter carries the resolved tier (no
  nearest-tier substitution — an adapter that only defines `low`/`high` will
  never silently route a `medium` decision to either).

## Known v1 limitations

- **Skills with their own LLM don't support "auto".** Conversation history
  for a turn is always fetched against the *calling* adapter, before skill
  detection ever runs — so there's no static budget to validate a skill's own
  `routing_tier` entries against at config-load time (see the guard below).
  `"auto"` silently degrades to that skill's normal default model, and the
  `"auto"` entry isn't advertised in skill-scoped discovery for such skills.
  A skill with **no** LLM of its own (e.g. Fetch) still supports "auto" via
  the calling adapter's own `allowed_models`.
- **History sizing happens before routing runs.** For the branches where
  "auto" is supported, ORBIT validates at config-load time (and on every
  config reload) that every `routing_tier` entry's effective history budget
  (context window minus its own `max_tokens`/reasoning reservation, minus
  `history.system_overhead_tokens`) is at least as large as the adapter's own
  baseline budget — the budget conversation history was already sized
  against before `ModelSelectionStep` runs. An adapter that fails this check
  has `auto_model_selection` disabled automatically at load, with an error
  logged naming the offending tier.

## Cost tracking

The routing decision call's own token usage and cost are folded into the
*same* audit row as the main chat call — not a separate row — so the
Costs tab total for a request already includes both. The two aren't broken
out separately in the stored record, so you can't currently see, after the
fact, how much of a given row's cost came from routing versus the chat call
itself. In practice this is a small, fairly fixed overhead per routed
request (one short decision-model call), negligible next to the chat call it
precedes — worth revisiting only if you're using an unusually chatty decision
model or very cheap chat models where that overhead stops being negligible.

## Implementation Reference

| Component | File |
|-----------|------|
| Pipeline step | `server/inference/pipeline/steps/model_selection.py` |
| Shared question validation | `server/inference/pipeline/steps/_decision_support.py` |
| Pipeline wiring | `server/inference/pipeline/pipeline.py` (between `DecisionModelStep` and `LLMInferenceStep`) |
| `"auto"` resolution + branch logic | `server/services/chat_handlers/request_context_builder.py` |
| Config-load-time validation | `server/services/config/adapter_config_manager.py` |
| Capability declaration | `server/adapters/capabilities.py` |
| Discovery (`"auto"` entry) | `server/routes/discovery_routes.py` |
