# AI Services Implementations Cleanup — Phased Follow-ups

## Summary

A `/simplify` pass (four parallel review angles — reuse, simplification,
efficiency, altitude) over `server/ai_services/implementations/` (~100
provider files across `audio/`, `decision/`, `embedding/`, `image/`,
`inference/`, `moderation/`, `ocr/`, `reranking/`, `video/`, `vision/`) plus
`server/ai_services/base.py` and `server/ai_services/providers/`. The
layering is generally good — API-key resolution, timeout/retry config, and
generic HTTP client setup are already centralized in `ProviderAIService` and
used consistently.

The safe, single-file findings were applied directly in that session:
`vllm_audio_service.py` lost a dead `_construct_tts_prompt` method and a
19-line commented-out shell-command block. Two findings that looked like
duplicate dead code (`_resolve_reasoning_effort` in `nvidia_inference_service.py`
and `vllm_inference_service.py`) turned out to be false positives on
inspection — neither `NVIDIABaseService` nor `VLLMBaseService` inherits from
`OpenAICompatibleBaseService`, and both overrides have deliberately different,
documented semantics — so they were left alone.

Everything below touches shared base classes or changes behavior across
multiple provider files, so it's phased for independent follow-up rather than
folded into the same-session cleanup pass, ordered by value vs. risk.

Reference: review findings were produced by four parallel agent passes
(reuse, simplification, efficiency, altitude) over
`server/ai_services/implementations/`, `server/ai_services/base.py`, and
`server/ai_services/providers/*.py` on 2026-10-24.

---

## Phase 1 — Low-risk, single-file fixes

Safe to do without touching shared services; each is contained to the file(s)
named. Good first bites.

- [x] **Remove duplicate double-logging on exception handling.** Only
      `openai_embedding_service.py:89` actually had the redundant generic
      `logger.error(f"Unexpected error...")` before calling `_handle_openai_error`
      — removed. Correction from the original finding: `cohere_embedding_service.py`
      and `mistral_embedding_service.py` do **not** have this pattern; their
      `embed_query`/`embed_documents` methods call `_handle_cohere_error`/
      `_handle_mistral_error` directly with no preceding generic log. Left
      untouched.
- [x] **Collapse vLLM TTS voice-resolution duplication.** Added
      `_resolve_tts_voice(voice)` (class-level `ORPHEUS_VOICES`/`OPENAI_VOICES`
      sets) to `vllm_audio_service.py`; both `text_to_speech` and
      `text_to_speech_streaming` now call it instead of duplicating the
      if/elif/elif/else.
- [x] **Factor shared Orpheus prompt/chunk-finalization helpers in
      `vllm_audio_service.py`.** Added `_build_orpheus_prompt(text, voice)`
      (used by both TTS methods) and `_finalize_audio_chunk(pcm_bytes,
      audio_format, wav_header_sent)` (used by `text_to_speech_streaming`'s
      per-chunk and flush paths, and by `_process_tts_response`'s final
      wrap-or-return-raw step).
- [ ] **vLLM's `_extract_provider_config` override.** Correction: this item
      was briefly marked done and the override deleted, on the mistaken
      premise that no `sounds:` config key exists anywhere in `config/` — that
      check missed `docs/audio/vllm-audio-service-guide.md`, which documents
      a `sounds.vllm` deployment path (also referenced at
      `docs/audio/vllm-audio-service-guide.md:109,464`) that real deployments
      may use instead of `tts_providers`/`stt_providers`. Deleting the
      override would have silently dropped those deployments back to default
      host/port/model/concurrency settings. **Reverted** — the override is
      restored as-is. Left open as a Phase 1 item: if the `sounds.vllm` path
      is still wanted, it could be made to compose with `config_section_key`
      instead of hand-rolling the fallback, but that requires confirming
      whether `sounds.vllm` is actually used by any deployment today before
      changing it — not done in this pass.
- [ ] **vLLM audio's broad-except boilerplate.** Not applied — skipped on
      inspection. The 14 `except Exception` blocks in `vllm_audio_service.py`
      have genuinely heterogeneous behavior (log-and-reraise, log-and-return-
      `False`, log-and-continue inside a loop, log-and-yield-fallback), so
      collapsing them into one decorator/helper risks silently changing
      control flow for at least one call site. Still a reasonable follow-up,
      but needs a per-site behavior audit, not a mechanical sweep.

## Phase 2 — Shared-infrastructure generalization

Each of these requires extending a shared base class or adding one new
helper, then updating multiple call sites together. Single coherent changes,
but each touches more than one file and deserves its own PR + test pass.

- [ ] **Centralize provider error classification behind `raise_sanitized`.**
      Investigated, not applied — the 8 `_handle_*_error` implementations
      diverge more than the finding assumed: `huggingface_base.py` and
      `anthropic_base.py` classify by `isinstance` against SDK exception
      classes (not string matching), and `azure_base.py`/`zai_base.py`/
      `google_base.py` log provider-specific categories (quota, deployment,
      permission) that a generic 4-bucket helper (auth/rate-limit/connection/
      timeout) would drop. A shared helper is still worth building, but it
      needs a category table expressive enough to keep each provider's
      diagnostic log detail, which is a design task on its own — deferred
      rather than forcing a lossy version through now.
      8 files under `server/ai_services/providers/*_base.py`
      (`cohere_base.py`, `mistral_base.py`, `zai_base.py`, `azure_base.py`,
      `huggingface_base.py`, `jina_base.py`, `google_base.py`,
      `anthropic_base.py`) hand-roll a `_handle_*_error` that lowercases the
      exception string and substring-matches
      `"api_key"`/`"unauthorized"`/`"rate limit"`/`"connection"`/`"timeout"`
      to pick a log level, before calling the already-robust
      `raise_sanitized` (which does real classification via HTTP status code
      extraction and exception-class-name matching in `errors.py`). The rest
      of the provider bases (`openai_base.py`, `aws_base.py`, `bitnet_base.py`,
      `tensorrt_base.py`, `replicate_base.py`, `openai_compatible_base.py`,
      `airllm_base.py`, `transformers_base.py`, `shimmy_base.py`,
      `llama_cpp_base.py`, `watson_base.py`, `nvidia_base.py`, `vllm_base.py`)
      already delegate straight to `raise_sanitized` with no pre-classification
      — don't touch those, they're the pattern to converge on, not duplicates
      of it. Add one shared `log_and_raise_sanitized(logger, error, provider,
      operation)` to `errors.py` that derives the log level/message from the
      same status-code/exception-name tables `errors.py` already has, and have
      the 8 affected `_handle_*_error` methods delegate to it instead of
      re-deriving classification from brittle substring matching. This also
      shrinks the Phase 1 double-logging pattern at its root for any provider
      among those 8, not just the three embedding files called out there.
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
- [ ] **Add a shared reasoning-model/temperature-support capability hook.**
      Not applied this pass — deferred alongside the error-classification item
      above since it's a similarly-scoped shared-base-class design task; also
      includes fixing real behavior drift (xAI's missing `effort` kwarg strip,
      Azure's unconditional `max_completion_tokens`), which deserves its own
      test pass rather than being bundled into this cleanup session.
      `openai_inference_service.py` (`_supports_reasoning_effort` +
      `_resolve_reasoning_effort` override), `mistral_inference_service.py`,
      `xai_inference_service.py`, `openai_vision_service.py`
      (`_supports_temperature`, `_get_token_parameter_name`), and
      `azure_vision_service.py` (`_supports_temperature`) each hand-maintain
      their own `model_name.startswith((...))` prefix tuple to detect
      reasoning-capable models, then re-implement the same pop/fallback
      resolution logic around that one boolean. Add a
      `_reasoning_effort_supported(model) -> bool` hook (default `True`) to
      `OpenAICompatibleBaseService._resolve_reasoning_effort`, and a
      `_supports_temperature(model)` / `_get_token_parameter_name(model)` pair
      on `OpenAIBaseService` (checking a config override first, then a shared
      prefix table), so provider/service-type subclasses override only the
      one hook instead of the whole resolution method. This also fixes an
      existing drift this duplication caused: xAI's resolver doesn't strip
      `effort` from kwargs on the unsupported path the way OpenAI's and
      Mistral's do, and `azure_openai_inference_service.py` hardcodes
      `max_completion_tokens` unconditionally where `openai_vision_service.py`
      gates on model name for the same quirk.
- [x] **Parallelize independent batch calls instead of sequential awaits.**
      `gemini_embedding_service.py`'s `embed_documents` now builds the batch
      list up front and runs them concurrently via `asyncio.gather`, bounded
      by a `Semaphore(3)` in place of the old sequential `await
      asyncio.sleep(0.5)` between batches. `openai_reranking_service.py`'s
      `rerank` does the same for `_score_batch` calls (also `Semaphore(3)`),
      merging each batch's usage into `usage_sink` as soon as that batch
      succeeds rather than after all batches finish. Both use explicit
      `asyncio.create_task` + `gather` instead of bare `gather`, and on
      failure cancel and await the remaining in-flight tasks before
      re-raising — review feedback caught that a bare `gather` lets batches
      still in flight keep making billable provider requests in the
      background after the failure is reported, and that collecting
      reranking usage only after `gather` returns would drop usage already
      earned by batches that *did* succeed when a later one failed. Further
      review feedback caught that cancelling an `asyncio.create_task` wrapping
      `await asyncio.to_thread(...)` doesn't stop the underlying synchronous
      SDK call once it's started — cancellation only interrupts the awaiting
      coroutine, not the thread-pool work item. `gemini_embedding_service.py`
      now uses a `failed` `asyncio.Event()` instead: a started batch always
      runs to completion, but once any batch fails the event is set and
      batches still waiting on the semaphore return early without making a
      request, then `gather(..., return_exceptions=True)` collects everything
      and the first exception found is re-raised.
- [x] **Cache long-lived clients instead of building them per request.**
      `google_audio_service.py`'s `translate()` now caches the
      `google.cloud.translate_v2.Client()` on `self._translate_client` (built
      once, lazily, on first use — matching the ImportError-fallback
      structure already there) instead of constructing one per call, and the
      synchronous `.translate()` call is wrapped in `asyncio.to_thread`.
- [x] **Wrap blocking file read in `vision/cohere_vision_service.py`.**
      Both call sites of `_image_to_base64` (`analyze_image`,
      `multimodal_inference`) now invoke it via `asyncio.to_thread` instead of
      awaiting the enclosing method directly over the synchronous file read.
- [x] **Move the video-generation poll loop off a borrowed thread-pool
      worker.** `gemini_video_service.py`'s `generate_video` now splits the
      single long-running `_run_sync` (with an in-thread `time.sleep(5)` poll
      loop) into three short `asyncio.to_thread` calls — `_submit`, `_poll`,
      `_finalize` — with `await asyncio.sleep(5)` between poll attempts in the
      async method itself. Each thread-pool borrow now lasts only as long as
      one network call, not the whole wait.
- [ ] **Migrate `bitnet_inference_service.py` onto
      `OpenAICompatibleBaseService`.** `bitnet_inference_service.py:116`
      constructs `AsyncOpenAI(...)` directly against its own ~285-line
      `providers/bitnet_base.py`, duplicating client construction, error
      handling, and `verify_connection` that `OpenAICompatibleBaseService`
      already provides to 19 sibling inference providers (groq, mistral,
      azure_openai, cerebras, deepseek, fireworks, nebius, openrouter,
      perplexity, together, venice, xai, scaleway, moonshot, nearai,
      deepinfra, minimax, zai). First confirm there's no genuine BitNet API
      incompatibility forcing the bespoke path; if none, migrate it like the
      others and delete `bitnet_base.py`. Not attempted this pass — the
      "confirm no incompatibility" step means reading and testing against
      BitNet's actual API surface, not a code-only change.

## Phase 3 — Opportunistic / low-urgency

Smaller wins, fine to fold into unrelated future PRs touching the same files
rather than scheduling dedicated work.

- [x] **Dedupe the repeated WAV-header-writing helper.** Added a shared
      `AudioService._wrap_pcm_in_wav(pcm_bytes, sample_rate, num_channels=1,
      sample_width=2)` static method (`services/audio_service.py`), and
      updated all six TTS files (`openai_audio_service.py`,
      `vllm_audio_service.py`, `gemini_audio_service.py`,
      `xai_audio_service.py`, `coqui_audio_service.py`,
      `supertonic_audio_service.py`) to call it instead of hand-rolling
      `wave.open(BytesIO(...), 'wb')`. Each file's own `_wrap_in_wav`/
      `_to_wav_bytes`/`_synthesize` wrapper method is kept where it existed
      (for its sample-rate default or call-site naming), now just delegating
      to the shared helper. Removed the `wave`/`BytesIO` imports that became
      unused in each file. Verified: all six files still parse; the four
      without optional native deps (openai, vllm, gemini, xai) still import
      cleanly; `pytest -k "audio or embedding or rerank or gemini or vllm"`
      shows the same pass/fail set before and after (13 pre-existing
      failures, unrelated — missing `vllm_provider` module, live-connection
      tests, and two already-failing config/placeholder tests untouched by
      this change).
- [ ] **Share one `genai.Client()` across Gemini-backed service types.**
      `inference/gemini_inference_service.py`, `embedding/gemini_embedding_service.py`,
      `ocr/gemini_ocr_service.py`, `vision/gemini_vision_service.py`,
      `image/gemini_image_service.py`, and `video/gemini_video_service.py`
      each lazily build and cache their own `genai.Client()` per service
      instance (fine on its own), but a deployment enabling multiple
      Gemini-backed capabilities gets a separate client/connection pool per
      capability. Not applied — left as-is per the item's own wording, since
      no deployment running several Gemini service types concurrently in one
      process has actually surfaced as a real pattern worth optimizing for.
- [x] **`vllm_audio_service.py` timeout/retry config overrides.** Added
      `default_connect`/`default_total`/`default_warmup` params to
      `ProviderAIService._get_timeout_config` and a `default_enabled` param to
      `_get_retry_config` (`base.py`), both defaulting to the prior hardcoded
      values so every other caller is unaffected. `vllm_audio_service.py`'s
      overrides now each shrink to a one-line `super()...(...)` call passing
      just the two/one numbers that actually differ (15s/120s timeouts, retry
      enabled by default) instead of recopying the dict-building logic. Note:
      the base's `_get_timeout_config` always includes a `warmup` key that the
      old vLLM override omitted — harmless, since the only consumer
      (`ConnectionManager`) only reads `timeout_config['total']`.

---

## Out of scope / accepted as-is

Noted by the review and explicitly judged not worth fixing:

- `nvidia_inference_service.py`'s and `vllm_inference_service.py`'s
  `_resolve_reasoning_effort` overrides look like dead duplicates of
  `OpenAICompatibleBaseService`'s version of the same name, but neither
  `NVIDIABaseService` nor `VLLMBaseService` inherits from
  `OpenAICompatibleBaseService` — both extend `ProviderAIService` directly,
  and both overrides have deliberately different, documented semantics
  (NVIDIA's is intentionally ungated by model name since NIM hosts many model
  families under one API; vLLM's is API-mode-only). Confirmed false positive;
  no action.
- No raw sync `requests`/`httpx.Client(` calls were found anywhere in
  `implementations/`. Direct `httpx.AsyncClient`/`aiohttp.ClientSession`
  construction does exist (e.g. `vllm_audio_service.py:92`,
  `xai_video_service.py`, `voyage_embedding_service.py`,
  `cohere_reranking_service.py`, and others), but these are async and were
  not flagged as a problem on their own — only worth revisiting case-by-case
  if a specific instance turns out to skip connection pooling/reuse that a
  shared client would give it for free.
- API-key resolution, base-URL/timeout/endpoint config helpers are already
  centralized in `ProviderAIService` (`base.py:115`) and used consistently;
  the one direct `os.environ.get` outside the shared helper
  (`moderation/presidio_moderation_service.py:87`) is a legitimate
  provider-specific override, not duplication. Actual HTTP/SDK client
  construction happens per provider base/implementation, not in
  `ProviderAIService` itself — see the `httpx.AsyncClient`/
  `aiohttp.ClientSession` note above.
