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

- [ ] **Remove duplicate double-logging on exception handling.** Several
      `embedding/*.py` files (`openai_embedding_service.py:85-90`,
      `cohere_embedding_service.py:82-84`, `mistral_embedding_service.py:76-78`)
      log the exception once generically (`logger.error(f"Unexpected error...")`)
      immediately before calling `_handle_*_error`, which logs it again with
      its own classification. Drop the redundant generic log at each call
      site; keep the classified log from `_handle_*_error`.
- [ ] **Collapse vLLM TTS voice-resolution duplication.**
      `vllm_audio_service.py`'s `text_to_speech` (lines ~557-576) and
      `text_to_speech_streaming` (lines ~678-687) duplicate the
      voice-resolution if/elif/elif/else almost verbatim, including a branch
      that's unreachable as a distinct case by the time it's reached. Extract
      one `_resolve_tts_voice(voice)` helper used by both methods.
- [ ] **Factor shared Orpheus prompt/chunk-finalization helpers in
      `vllm_audio_service.py`.** `text_to_speech` and
      `text_to_speech_streaming` (lines ~528-759) duplicate prompt
      construction (voice resolution + START/END token wrapping) and the
      "wrap final bytes in WAV depending on format" logic (lines ~737-744,
      ~754-757, and `_process_tts_response` lines ~838-844). Factor a shared
      `_build_orpheus_prompt(text, voice)` and `_finalize_audio_chunk(pcm_bytes,
      audio_format, wav_header_sent)`.
- [ ] **vLLM audio's broad-except boilerplate.** 10+ near-identical
      `except Exception as e: # noqa: BLE001` blocks in `vllm_audio_service.py`
      (log-and-reraise or log-and-return-`False`) could collapse to one
      `@log_and_reraise(...)` decorator or small helper. Scope this to the one
      file; don't widen it into the Phase 2 error-handling item below.
- [ ] **vLLM's `_extract_provider_config` override duplicates the
      `config_section_key` fallback pattern.** `vllm_audio_service.py:173-188`
      re-implements the "try this key, then fall back to `super()`" logic that
      `base.py`'s `config_section_key` hook already generalizes. Set
      `self.config_section_key = 'sounds'` before calling `super().__init__()`
      instead, and delete the override. (Do **not** touch
      `_compute_provider_config`/`_extract_provider_config` themselves — see
      Out of scope below; `AudioService._compute_provider_config` overrides it
      to merge `tts_providers`/`stt_providers`, so the two-method split is
      load-bearing, not redundant indirection.)

## Phase 2 — Shared-infrastructure generalization

Each of these requires extending a shared base class or adding one new
helper, then updating multiple call sites together. Single coherent changes,
but each touches more than one file and deserves its own PR + test pass.

- [ ] **Centralize provider error classification behind `raise_sanitized`.**
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
- [ ] **Parallelize independent batch calls instead of sequential awaits.**
      `embedding/gemini_embedding_service.py:92-116` (`embed_documents`) loops
      over batches sequentially with a hardcoded `await asyncio.sleep(0.5)`
      between each; `reranking/openai_reranking_service.py:100-105` awaits
      `_score_batch` one batch at a time. Both are independent I/O calls per
      batch — replace with `asyncio.gather` (bounded by a `Semaphore` if the
      provider's rate limits require it).
- [ ] **Cache long-lived clients instead of building them per request.**
      `audio/google_audio_service.py:230`'s `translate()` builds a new
      `google.cloud.translate_v2.Client()` on every call and invokes its
      synchronous `.translate()` directly on the event loop. Build the client
      once in `initialize()` (matching how `_speech_client`/`_tts_client`
      already work in the same file) and wrap the blocking call in
      `asyncio.to_thread`.
- [ ] **Wrap blocking file read in `vision/cohere_vision_service.py`.**
      `cohere_vision_service.py:44-48` uses synchronous `open(image, 'rb')`
      inside an async method, blocking the event loop during disk I/O for
      local file-based requests. Wrap in `asyncio.to_thread` or switch to
      `aiofiles`.
- [ ] **Move the video-generation poll loop off a borrowed thread-pool
      worker.** `video/gemini_video_service.py:93`'s polling loop
      (`while not operation.done: time.sleep(5); ...`) runs inside
      `asyncio.to_thread`, pinning a default-executor worker thread for the
      full poll duration (video gen can take minutes); concurrent requests
      can exhaust the thread pool and serialize unrelated async work.
      Investigate the async Gemini operations API, or poll with
      `await asyncio.sleep(5)` directly in an async method instead of a
      blocking sync thread.
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
      others and delete `bitnet_base.py`.

## Phase 3 — Opportunistic / low-urgency

Smaller wins, fine to fold into unrelated future PRs touching the same files
rather than scheduling dedicated work.

- [ ] **Dedupe the repeated WAV-header-writing helper.** Six TTS provider
      files (`openai_audio_service.py:168`, `vllm_audio_service.py:406`,
      `gemini_audio_service.py:104`, `xai_audio_service.py:490`,
      `coqui_audio_service.py:431`, `supertonic_audio_service.py:165`) each
      build a WAV file via `wave.open(io.BytesIO(...), 'wb')` with the same
      ~10-line header-writing logic. Not a perf issue (in-memory), just
      maintenance duplication — factor into one shared helper when next
      touching any of these files.
- [ ] **Share one `genai.Client()` across Gemini-backed service types.**
      `inference/gemini_inference_service.py`, `embedding/gemini_embedding_service.py`,
      `ocr/gemini_ocr_service.py`, `vision/gemini_vision_service.py`,
      `image/gemini_image_service.py`, and `video/gemini_video_service.py`
      each lazily build and cache their own `genai.Client()` per service
      instance (fine on its own), but a deployment enabling multiple
      Gemini-backed capabilities gets a separate client/connection pool per
      capability. Low urgency — revisit only if running several Gemini
      service types concurrently in one process becomes a real deployment
      pattern worth optimizing for.
- [ ] **`vllm_audio_service.py` timeout/retry config overrides.**
      `_get_timeout_config`/`_get_retry_config` overrides (lines ~981-1000)
      re-implement the base's dict-building logic verbatim just to change two
      default numbers. Low urgency since it's one file — if `base.py`'s
      methods are touched for another reason, add
      `default_connect`/`default_total` parameters so this override can
      shrink to passing two numbers instead of recopying the method body.

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
