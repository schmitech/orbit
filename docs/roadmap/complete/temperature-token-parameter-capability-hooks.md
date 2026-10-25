# Temperature / Token-Parameter Capability Hooks

## Summary

Split off from `docs/roadmap/complete/ai-services-implementations-cleanup-deferred.md`'s
"Add a shared reasoning-model/temperature-support capability hook" item once
its reasoning-effort half was done (see that doc's completed entry). This
plan covers the remaining half: the duplicated model-capability checks that
decide (a) which token-count kwarg a request uses
(`max_tokens`/`max_completion_tokens`/`max_output_tokens`) and (b) whether a
custom `temperature` can be sent at all, versus a reasoning-style model that
rejects anything but its default.

Unlike the reasoning-effort hook, this does **not** collapse into one shared
base. Two unrelated hierarchies each have their own duplication:

- `OpenAIBaseService` → `OpenAIInferenceService`, `OpenAIVisionService`
- `AzureBaseService` → `AzureVisionService`, `AzureOpenAIInferenceService`
  (sibling of `OpenAIBaseService`, extends `ProviderAIService` directly —
  shares no base with it)

So this is two separate extractions, not one.

## Current state (verified against code, not assumed)

### OpenAI side

`openai_inference_service.py` and `openai_vision_service.py` each define
their own copies of `_get_token_parameter_name`, `_resolve_token_value`, and
`_supports_temperature` — **byte-for-byte identical** in all three methods
(confirmed by diff, not just similar shape). Both classes inherit
`OpenAIBaseService`, so a straight lift-to-base-class works with no semantic
reconciliation needed:

```python
def _get_token_parameter_name(self) -> str:
    # config override (token_parameter_name / token_parameter) first,
    # then self.model prefix check: gpt-4.1/gpt-4o/gpt-5/o1/o2/o3 ->
    # max_completion_tokens, else max_tokens

def _resolve_token_value(self, token_param, kwargs) -> int:
    # pops max_tokens/max_completion_tokens/max_output_tokens out of kwargs,
    # returns whichever was given (preferring token_param's own key),
    # else self.max_tokens

def _supports_temperature(self) -> bool:
    # self.model prefix check: gpt-5/o1/o2/o3 -> False, else True
```

### Azure side

`azure_vision_service.py` defines the same three methods, but **richer**
than the OpenAI versions, not just a renamed copy:

- `_get_token_parameter_name` and `_supports_temperature` key off
  `self.deployment` (not `self.model` — Azure deployment names are
  user-defined and can't be sniffed as reliably as OpenAI's own model ids).
- `_supports_temperature` additionally accepts a `supports_temperature`
  boolean config override before falling back to the deployment-name prefix
  check — the OpenAI version has no equivalent config override.
- `azure_vision_service.py` also overrides `verify_connection` itself, to
  route the health-check's own request through `_get_token_parameter_name`/
  `_supports_temperature` instead of `AzureBaseService`'s unconditional
  `temperature=0, max_completion_tokens=16` — otherwise a
  temperature-restricted deployment (e.g. a GPT-5.6-class Foundry Catalog
  model) fails its own connection check.

**`azure_openai_inference_service.py` has none of these three methods at
all.** Its `generate`/`generate_stream` send `temperature=...` and
`max_completion_tokens=...` unconditionally (hardcoded parameter name, no
capability gating). This means:

- It already assumes every Azure OpenAI deployment accepts
  `max_completion_tokens` — no `max_tokens` fallback for older deployments.
- It has no guard against reasoning-restricted deployments rejecting a
  non-default `temperature`, the same failure mode `azure_vision_service.py`'s
  `verify_connection` override exists specifically to avoid.

This is a **pre-existing gap** in `azure_openai_inference_service.py`, not
something introduced by this plan — call it out explicitly rather than
silently "fixing" it as a side effect of a refactor; confirm with whoever
owns Azure OpenAI deployments whether it's actually been hit before deciding
whether closing it is in scope here or its own bug ticket.

## Proposed approach

Two independent extractions, each should land (and be tested) separately:

1. **`OpenAIBaseService`**: move `_get_token_parameter_name`,
   `_resolve_token_value`, `_supports_temperature` up from
   `openai_inference_service.py`/`openai_vision_service.py` verbatim (they're
   already identical) onto `OpenAIBaseService`. Delete the two duplicate
   copies. Lowest risk of the two — purely a lift, no behavior reconciliation.

2. **`AzureBaseService`**: move `azure_vision_service.py`'s versions (the
   richer ones, with the config override and deployment-name sniffing) up
   onto `AzureBaseService`. Delete `azure_vision_service.py`'s copies.
   Decide, as a separate explicit decision (not bundled silently): should
   `azure_openai_inference_service.py` start using the lifted hooks too? That
   would change its live request construction (parameter name could switch
   for some deployments, temperature could get dropped for reasoning-style
   ones) — real behavior change, not a pure refactor, and needs sign-off plus
   its own test coverage before being folded in. If not adopted now, leave
   `azure_openai_inference_service.py` as-is and note the gap stays open.

   Also worth deciding whether `AzureBaseService.verify_connection`'s own
   default probe (the unconditional `temperature=0, max_completion_tokens=16`
   call noted in `azure_base.py`) should route through the lifted hooks too,
   now that they're available on the base class — `azure_vision_service.py`
   only overrides `verify_connection` today because the hooks weren't
   reachable from the base. If they move up, that override may become
   unnecessary. **This is not an isolated cleanup**: `AzureBaseService` is
   `AzureOpenAIInferenceService`'s base too, so changing the shared probe
   changes Azure *inference*'s connection check as well, even if
   `azure_openai_inference_service.py`'s `generate`/`generate_stream` keep
   their hardcoded parameters per the decision above. Fold this into the same
   explicit sign-off, not a separate "just the health check" change.

## Why this needs its own test pass

Moving the identical OpenAI helpers (extraction 1) onto `OpenAIBaseService`
is a pure lift — request construction for `openai_inference_service.py`/
`openai_vision_service.py` is unchanged. The live-behavior risk is
concentrated in extraction 2's explicit decisions: whether
`azure_openai_inference_service.py` adopts the lifted hooks (which
token-kwarg name gets sent, whether `temperature` is included at all for its
`generate`/`generate_stream` calls), and whether
`AzureBaseService.verify_connection`'s shared probe starts routing through
them — which changes Azure *inference*'s connection-check request
(`AzureOpenAIInferenceService` has no `verify_connection` override, so it
uses the base probe directly); it only reaches Azure *vision* too if
`azure_vision_service.py`'s own `verify_connection` override is also removed
as part of this work, since that override exists specifically to bypass the
base probe's unconditional parameters. A regression in either surfaces as a 400 from the provider for specific
deployed models/deployments (e.g. gpt-5.x, o-series, or a Foundry Catalog
reasoning model), not as a test failure, unless tests actually cover those
names. Before merging:

- Enumerate the model/deployment names currently configured for OpenAI
  (`config/inference.yaml` / `config/vision.yaml`) and for Azure — the two
  Azure configs name their deployment differently, so check both: Azure
  *inference*'s deployment name lives in `config/azure.yaml`'s
  `azure_presets` (e.g. `config/azure.yaml:15`), referenced from
  `config/inference.yaml` via `use_preset: "..."` (`config/inference.yaml:343`);
  Azure *vision*'s deployment name is inline as `deployment_name` directly in
  `config/vision.yaml`'s own `azure` section (`config/vision.yaml:196`), no
  preset indirection. Make sure each falls on the expected side of the prefix
  checks after the move (no accidental behavior change from a typo during the
  lift).
- Add or confirm test coverage for at least one "modern" (reasoning/4o-class)
  and one "legacy" model name per provider, covering both the token-parameter
  name chosen and whether `temperature` is sent — ideally via recorded
  request assertions (what params `client.chat.completions.create` was
  called with) rather than live API calls.
- If `azure_openai_inference_service.py` adopts the hooks, specifically test
  a reasoning-restricted deployment name to confirm `temperature` is no
  longer sent unconditionally.

## Scope / out of scope

- In scope: `openai_inference_service.py`, `openai_vision_service.py`,
  `OpenAIBaseService`, `azure_vision_service.py`, `AzureBaseService`, and the
  explicit decision (not silent change) on whether
  `azure_openai_inference_service.py` adopts the lifted Azure hooks.
- Out of scope: any other provider's temperature/token-parameter handling —
  this duplication is specific to these two hierarchies, confirmed by the
  original survey in `ai-services-implementations-cleanup-deferred.md`.
