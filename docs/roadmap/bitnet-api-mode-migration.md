# Migrate BitNet's API Mode onto `OpenAICompatibleBaseService`

## Summary

Carried forward from `docs/roadmap/complete/ai-services-implementations-cleanup-deferred.md`,
which collected it as an item needing a maintainer with BitNet access before
implementation. Investigation in that doc's session went further than the
original item anticipated and found the inherited base class isn't even the
real duplication — see below.

`bitnet_inference_service.py` constructs `AsyncOpenAI(...)` directly for its
API mode, duplicating client construction, error handling, and
`verify_connection` that `OpenAICompatibleBaseService` already provides to 19
sibling inference providers (groq, mistral, azure_openai, cerebras, deepseek,
fireworks, nebius, openrouter, perplexity, together, venice, xai, scaleway,
moonshot, nearai, deepinfra, minimax, zai).

## Current state (verified against code, not assumed)

`BitNetInferenceService` (`implementations/inference/bitnet_inference_service.py`)
inherits `BitNetBaseService` (`providers/bitnet_base.py`), but **does not use
any of its inherited behavior**:

- `BitNetInferenceService.__init__` calls `ProviderAIService.__init__`
  directly, bypassing `BitNetBaseService.__init__` entirely.
- It fully reimplements `initialize`, `close`, `verify_connection`,
  `generate`, and `generate_stream` itself.
- Grepping the codebase confirms nothing else references `BitNetBaseService`
  except `bitnet_inference_service.py`'s own import and class declaration.

So `BitNetBaseService`'s `_setup_api_mode`, `_setup_direct_mode`,
`initialize`, `_load_direct_model`, `verify_connection`, and `close` are all
**dead code** — never invoked at runtime. The real API-mode duplication (a
manual `AsyncOpenAI(...)` construction and a manual `verify_connection`) lives
directly in `bitnet_inference_service.py`, not in the inherited base. The
original item's premise (duplication hiding in an inherited base class) was
half-right: the duplication is real, but it's not where it looked.

This also means a straightforward class-level migration onto
`OpenAICompatibleBaseService` doesn't fit cleanly: `BitNetInferenceService`
picks its mode (`direct` by default, or `api`) at **runtime** via config, not
via separate subclasses. `OpenAICompatibleBaseService.__init__` eagerly:

- Requires a resolved API key, raising `ValueError` if none is found
  (`_setup_openai_compatible_config`). BitNet's API mode is typically a
  self-hosted, unauthenticated server — its own client construction defaults
  to `self.api_key or "not-needed"` rather than requiring one.
- Builds a full `AsyncOpenAI` client with an `httpx.AsyncClient` and kicks off
  async connection verification — fine for API mode, but would need to be
  skipped entirely for direct mode (no HTTP endpoint to verify).

So subclassing `OpenAICompatibleBaseService` directly would break direct-mode
instantiation (the default) unless gated very carefully.

## Decision made so far

Discussed during the investigation: migrate via **composition**, not
inheritance — in API mode, `BitNetInferenceService` would hold an
`OpenAICompatibleBaseService` (or equivalent) instance and delegate client
construction, error handling, and `verify_connection` to it; direct mode
stays untouched, using its own local-model loading path. This direction
wasn't implemented — the investigation was paused before writing code.

Still open, discovered mid-investigation and not yet resolved:

- **Missing/optional API key.** `OpenAICompatibleBaseService._setup_openai_compatible_config`
  raises `ValueError` when no API key resolves. BitNet API mode doesn't
  require one (self-hosted). A composition approach needs to inject a
  default (e.g. `"not-needed"`, matching the current client's fallback)
  into the config handed to the composed instance when no real key is
  configured — without touching the 19 other providers' shared
  `_setup_openai_compatible_config` behavior, which should keep requiring a
  key.
- **`provider_name` metadata.** `OpenAICompatibleBaseService.DEFAULT_BASE_URLS`/
  `API_KEY_ENV_VARS` don't have a `"bitnet"` entry, so it would fall back to
  the generic `https://api.bitnet.com/v1` default and `BITNET_API_KEY` env
  var naming — neither matters in practice since BitNet's config always
  supplies an explicit `base_url` (self-hosted), but worth confirming no
  existing deployment relies on the generic fallback.
- **Direct-mode split.** `BitNetBaseService`'s direct-mode logic
  (`_setup_direct_mode`, `_load_direct_model`, GGUF path resolution,
  thread-pool cleanup in `close()`) is all dead code today (see above) —
  `bitnet_inference_service.py` has its own independent direct-mode
  implementation already. Once API mode moves to composition,
  `providers/bitnet_base.py` can likely be deleted outright rather than
  slimmed down, since nothing uses it. Confirm this before deleting it,
  in case something outside this codebase imports it directly.

## Why this needs a maintainer with BitNet access

The composition approach above is a design sketch, not a verified plan — it
hasn't been tested against a live BitNet inference server. In particular:
does a real BitNet OpenAI-compatible server support `/v1/models` the way
`OpenAICompatibleBaseService.verify_connection`'s probe expects, or does it
only support `/v1/chat/completions` (forcing the fallback-to-test-request
path on every verification)? That can only be confirmed by someone who runs
BitNet in API mode.

## Scope / out of scope

- In scope: `bitnet_inference_service.py` (API-mode path only),
  `providers/bitnet_base.py` (candidate for deletion once confirmed dead).
- Out of scope: BitNet's direct-mode logic — stays exactly as-is in
  `bitnet_inference_service.py`.
