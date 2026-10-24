# AI Services Implementations Cleanup — Deferred Items

## Summary

`docs/roadmap/complete/ai-services-implementations-cleanup.md` worked through
a `/simplify` pass over `server/ai_services/implementations/`,
`server/ai_services/base.py`, and `server/ai_services/providers/` in three
phases. Most items were applied directly; the items below were investigated
but deliberately **not** applied, because each is either a multi-file
shared-base-class redesign that needs its own design/test pass, or requires
confirming something outside the codebase (a live API's behavior, actual
deployment usage of a config path) before it's safe to change. This doc
collects them so they aren't lost now that the original plan has moved to
`docs/roadmap/complete/`.

None of these are urgent — pick them up independently, whenever there's
appetite for the one that's most valuable at the time.

---

## Items

- [x] **Centralize provider error classification behind `raise_sanitized`.**
      Done — added `ErrorCategory` and `log_and_raise_sanitized(logger, error,
      provider, operation, category, message=None, error_text=None,
      message_fields=None, level=None)` to `errors.py`, and migrated all 12
      files that actually duplicated classification (`anthropic_base.py`,
      `openai_base.py`, `openai_compatible_base.py`, `shimmy_base.py`,
      `azure_base.py`, `cohere_base.py`, `jina_base.py`, `mistral_base.py`,
      `zai_base.py`, `google_base.py`, `huggingface_base.py`, `aws_base.py`)
      onto it — each keeps its own classification logic, only the log-level/
      message/`raise_sanitized` tail is shared. The 9 pure one-line delegators
      (`airllm`, `bitnet`, `llama_cpp`, `nvidia`, `replicate`, `tensorrt`,
      `transformers`, `vllm`, `watson`) were left untouched, nothing to
      centralize there. Caught and fixed during review: a format-string
      injection bug (provider error text, error codes, or a configured base
      URL containing literal `{`/`}` could crash `.format()` instead of
      raising the sanitized error — fixed via `error_text`/`message_fields`
      substitution args instead of baking dynamic text into templates), an
      Azure quota severity regression (now explicit `level=logging.ERROR`),
      and two branding regressions (OpenAI/Hugging Face capitalization).
      8 files under `server/ai_services/providers/*_base.py`
      (`cohere_base.py`, `mistral_base.py`, `zai_base.py`, `azure_base.py`,
      `huggingface_base.py`, `jina_base.py`, `google_base.py`,
      `anthropic_base.py`) hand-roll a `_handle_*_error` that classifies the
      exception (mostly by lowercasing and substring-matching
      `"api_key"`/`"unauthorized"`/`"rate limit"`/`"connection"`/`"timeout"`)
      to pick a log level and message, before calling the already-robust
      `raise_sanitized` (which does real classification via HTTP status code
      extraction and exception-class-name matching in `errors.py`).

      **Correction:** the original wording claimed the other 13 provider bases
      "already delegate straight to `raise_sanitized` with no
      pre-classification." That's not accurate — at least `openai_base.py:73`
      (`_handle_openai_error`), `aws_base.py:245` (`_handle_aws_error`),
      `openai_compatible_base.py:411` (`_handle_openai_compatible_error`), and
      `shimmy_base.py:144` (`_handle_shimmy_error`) also classify the error
      (mostly via `isinstance` against SDK/boto exception types, or AWS error
      codes) before calling `raise_sanitized`, purely to pick a log
      level/message — functionally the same duplicated-logging problem as the
      8 called out above, just via `isinstance` instead of string matching.
      Scope this item by **which behavior is actually duplicated** (classify
      error → pick log level/message → call `raise_sanitized`), not by an
      assumed clean split between "8 that classify" and "13 that don't" — the
      real list of classifying handlers needs a fresh audit of all ~23 files
      before scoping the fix, not reuse of the original 8-file list.

      **Why deferred:** the implementations diverge more than a first look
      suggests. `huggingface_base.py` and `anthropic_base.py` (string-matching
      group) and `openai_base.py`/`shimmy_base.py`/`openai_compatible_base.py`
      (isinstance group) classify by `isinstance` against SDK exception
      classes in some cases and substring matching in others, and
      `azure_base.py`/`zai_base.py`/`google_base.py`/`aws_base.py` log
      provider-specific categories (quota, deployment, permission, AWS error
      codes) beyond a generic auth/rate-limit/connection/timeout four. A
      shared `log_and_raise_sanitized(logger, error, provider, operation)`
      helper is still worth building, but it needs a category table
      expressive enough to preserve each provider's diagnostic log detail —
      that's a small design task on its own, not a mechanical find-and-replace.
      Doing it without that design step would either lose diagnostic log
      fidelity or require one-off category tables per provider anyway,
      defeating the point.

- [ ] **Share the `verify_connection` try/log/return-bool scaffolding across
      provider bases — but keep each provider's actual probe logic intact.**
      All 23 files in `server/ai_services/providers/*.py` reimplement the same
      surrounding try/log/return-bool skeleton, but the probe itself varies in
      more than just "which cheap call" — e.g.
      `openai_compatible_base.py:248`'s `verify_connection` falls back from
      listing models to issuing an actual completion request when listing
      isn't supported, it isn't a single cheap probe call. A shared
      `_verify_connection_via(coro)` helper should wrap only the common
      try/log/return-bool shell and accept an arbitrary async probe callable
      (including multi-step fallback logic like OpenAI-compatible's), not
      assume every provider reduces to one `await probe()`.

      **Why deferred:** needs a full survey of all 23 files' actual probe
      logic (not just the one example above) before the helper's shape can be
      pinned down — some probes may have other fallback patterns, different
      exception handling needs, or side effects (like resetting cached state)
      that a generic wrapper would need to account for. That survey plus the
      helper plus the 23-site migration is a full PR on its own.

- [ ] **Add a shared reasoning-model/temperature-support capability hook.**
      Inheritance, checked against the actual code:
      `OpenAIInferenceService`/`OpenAIVisionService` inherit `OpenAIBaseService`;
      `MistralInferenceService`/`XAIInferenceService` inherit
      `OpenAICompatibleBaseService` directly (`OpenAIBaseService` is itself a
      subclass of `OpenAICompatibleBaseService`); `AzureVisionService`/
      `AzureOpenAIInferenceService` inherit `AzureBaseService`, a sibling that
      extends `ProviderAIService` directly and shares no base with either of
      the above.

      `openai_inference_service.py` (`_supports_reasoning_effort` +
      `_resolve_reasoning_effort` override), `mistral_inference_service.py`,
      and `xai_inference_service.py` each hand-maintain their own
      `model_name.startswith((...))` prefix tuple to detect reasoning-capable
      models, then re-implement the same pop/fallback resolution logic around
      that one boolean. Add a `_reasoning_effort_supported(model) -> bool`
      hook (default `True`) to
      `OpenAICompatibleBaseService._resolve_reasoning_effort` — this correctly
      covers all three, since `OpenAIBaseService` inherits from
      `OpenAICompatibleBaseService`.

      Separately, `openai_vision_service.py` (`_supports_temperature`,
      `_get_token_parameter_name`) and `azure_vision_service.py`
      (`_supports_temperature`) duplicate a similar model-prefix check for
      temperature/token-parameter support, but they **don't share a base** —
      a single hook on `OpenAIBaseService` would cover
      `openai_vision_service.py` but not reach `azure_vision_service.py` or
      `azure_openai_inference_service.py` at all. This needs two separate
      hooks: `_supports_temperature(model)` / `_get_token_parameter_name(model)`
      on `OpenAIBaseService` (covering `openai_inference_service.py`/
      `openai_vision_service.py`), and an equivalent pair on `AzureBaseService`
      (covering `azure_vision_service.py`/`azure_openai_inference_service.py`),
      each checking a config override first, then its own shared prefix table.
      Not one extraction — two, on two unrelated base classes.

      **Why deferred:** a shared-base-class redesign spanning two unrelated
      hierarchies rather than one, and it changes real request-construction
      behavior (token-parameter naming, which kwargs get sent) for live model
      calls. Deserves its own test pass (ideally against real or recorded API
      responses for each affected provider/model combination) rather than
      being bundled into a cleanup session.

- [ ] **Migrate BitNet's API mode onto `OpenAICompatibleBaseService`
      (direct mode stays as-is).** `bitnet_inference_service.py:116`
      constructs `AsyncOpenAI(...)` directly against its own ~285-line
      `providers/bitnet_base.py`, duplicating client construction, error
      handling, and `verify_connection` that `OpenAICompatibleBaseService`
      already provides to 19 sibling inference providers (groq, mistral,
      azure_openai, cerebras, deepseek, fireworks, nebius, openrouter,
      perplexity, together, venice, xai, scaleway, moonshot, nearai,
      deepinfra, minimax, zai) — but only for API mode.
      `BitNetBaseService` (`providers/bitnet_base.py:18`) also supports a
      **direct mode** (`mode == "direct"` branches through
      `_setup_direct_mode`, `_load_direct_model`, and local-model cleanup in
      `close()`) that has no equivalent in `OpenAICompatibleBaseService`,
      which only ever talks to an OpenAI-compatible HTTP endpoint — so this
      is not a drop-in replacement for the whole service, and
      `providers/bitnet_base.py` can't simply be deleted. Direct mode's local
      model loading, execution, and cleanup logic needs a home either way
      (a slimmed-down `bitnet_base.py` that only handles direct mode, or
      moved into `bitnet_inference_service.py` itself) — that split is a
      design decision of its own, separate from the API-mode migration.

      **Why deferred:** the API-mode client construction/error-handling/
      `verify_connection` duplication is still real and likely worth fixing,
      but it needs the direct-mode/API-mode split decided first, on top of
      confirming that API mode has no genuine BitNet-specific incompatibility
      forcing the bespoke client path — both need a maintainer with BitNet
      access to weigh in before implementation.

- [ ] **vLLM's `_extract_provider_config` override — confirm whether the
      `sounds.vllm` config path is still used.** `vllm_audio_service.py`'s
      `_extract_provider_config` override checks a `sounds` top-level config
      key before falling back to the standard `tts_providers`/`stt_providers`
      lookup. This path is documented
      (`docs/audio/vllm-audio-service-guide.md:109,464`), so the override must
      stay — a prior pass in this cleanup briefly deleted it on the mistaken
      belief that no `sounds:` key exists anywhere in `config/`, and had to
      revert that.

      **Why deferred:** the override itself hand-rolls the same "try this key,
      then fall back to `super()`" pattern that `base.py`'s
      `config_section_key` hook already generalizes, so it could in principle
      shrink to `self.config_section_key = 'sounds'`. But composing it that
      way would reorder precedence relative to `AudioService`'s
      `tts_providers`/`stt_providers` merge (see
      `services/audio_service.py:_compute_provider_config`), which is a real
      behavior change for anyone currently relying on `sounds.vllm`. Needs
      confirmation of whether that config path is actually used by any
      current deployment before changing how it's resolved.

- [ ] **vLLM audio's broad-except boilerplate.** 14 near-identical
      `except Exception as e:  # noqa: BLE001` blocks in
      `vllm_audio_service.py` could collapse to a decorator or small helper.

      **Why deferred:** the blocks have genuinely heterogeneous behavior
      (log-and-reraise, log-and-return-`False`, log-and-continue inside a
      loop, log-and-yield-fallback-audio), so a mechanical sweep risks
      silently changing control flow at one or more call sites. Needs a
      per-site behavior audit — list out what each block actually needs to do
      on failure — before a shared helper's shape can be designed.

- [ ] **Share one `genai.Client()` across Gemini-backed service types.**
      `inference/gemini_inference_service.py`,
      `embedding/gemini_embedding_service.py`, `ocr/gemini_ocr_service.py`,
      `vision/gemini_vision_service.py`, `image/gemini_image_service.py`, and
      `video/gemini_video_service.py` each lazily build and cache their own
      `genai.Client()` per service instance (fine on its own), but a
      deployment enabling multiple Gemini-backed capabilities gets a separate
      client/connection pool per capability.

      **Why deferred:** low urgency, not complexity — genuinely fine to leave
      until a deployment running several Gemini service types concurrently in
      one process actually surfaces this as a real cost worth optimizing for.
      Listed here mainly so it isn't forgotten entirely.

---

## Out of scope / accepted as-is

Carried over from the completed plan — still true, no action needed:

- `nvidia_inference_service.py`'s and `vllm_inference_service.py`'s
  `_resolve_reasoning_effort` overrides look like dead duplicates of
  `OpenAICompatibleBaseService`'s version of the same name, but neither
  `NVIDIABaseService` nor `VLLMBaseService` inherits from
  `OpenAICompatibleBaseService` — both extend `ProviderAIService` directly,
  and both overrides have deliberately different, documented semantics
  (NVIDIA's is intentionally ungated by model name since NIM hosts many model
  families under one API; vLLM's is API-mode-only). Confirmed false positive;
  no action.
- Direct `httpx.AsyncClient`/`aiohttp.ClientSession` construction exists in
  several files (e.g. `vllm_audio_service.py:92`, `xai_video_service.py`,
  `voyage_embedding_service.py`, `cohere_reranking_service.py`, and others),
  but these are async and were not flagged as a problem on their own — only
  worth revisiting case-by-case if a specific instance turns out to skip
  connection pooling/reuse that a shared client would give it for free.
- API-key resolution, base-URL/timeout/endpoint config helpers are already
  centralized in `ProviderAIService` (`base.py:115`) and used consistently;
  the one direct `os.environ.get` outside the shared helper
  (`moderation/presidio_moderation_service.py:87`) is a legitimate
  provider-specific override, not duplication.
