# Plan: Decision-model ("System One" / Jev-style) adapter + providers (Ollama, TypeSafe)

## Context
Jev-style decision models (nimble 9B, tev1 4B/0.8B, TypeSafe `jev-latest`) don't write chat replies. They take `state` plus typed `questions` (`choice`, `noul`, `score`) and return typed answers with probabilities and confidence, in about 100 ms per decision. That makes them a good fit for fast, real-time triage, moderation and routing in ORBIT.

Both backends use the same wire protocol:
- **Ollama (local):** `POST http://localhost:11434/v1/systemone`, no auth. ORBIT calls it over plain HTTP, so there is no extra dependency.
- **TypeSafe (hosted):** `POST https://api.typesafe.ai/v1/systemone` with a Bearer key. ORBIT calls it through the official `typesafe-sdk` (`AsyncTypeSafeClient`).

The request is `{model, state:{...}, questions:{name:{type, instructions, criteria?}}}`. The response is `{model, answers:{name:{type, choice|noul|score, probabilities?, legend?, confidence?}}, usage:{input_tokens, output_tokens}}`.

ORBIT has no decision service type today. Non-LLM adapter types (image, video, fetch) each get a dedicated pipeline step that skips `LLMInferenceStep`, and this plan follows that pattern.

**Confirmed with the user:**
- Questions are defined in the adapter YAML, with an optional per-request override.
- `response` holds the answers JSON, and a new typed `decision` field goes on every terminal output.
- Three example adapters.
- The plan also folds in the user's review feedback.

## Design

### 1. AI service type `decision`
- `ai_services/base.py`: add `ServiceType.DECISION = "decision"`.
- `ai_services/services/decision_service.py`: abstract `DecisionService(ProviderAIService)`.
  - Set `config_section_key = "decision_models"`. This matters: the registry's `config_section` only filters registration, and `_extract_provider_config()` (`base.py:160`) reads this attribute.
  - Define `async decide(state: dict, questions: dict, model: str | None = None, **kw) -> dict`. It returns the normalized `{model, answers, usage}`.
  - Model it on `services/video_generation_service.py` and export it from `services/__init__.py`.
- New directory `ai_services/implementations/decision/`, with the lazy-import `__init__.py` loop copied from `implementations/image/__init__.py`.
  - `ollama_decision_service.py`, `OllamaDecisionService(DecisionService)`:
    - Does **not** extend `OllamaBaseService`. That base resolves config through `OllamaConfig` / `_get_service_type_name`, which only knows the existing sections, and it warms up via `/api/generate`.
    - Instead it owns a `ConnectionManager` and `RetryHandler` from `ai_services/connection.py`, built from `base_url`, `timeout` and `retry`.
    - The POST path is relative, because `ConnectionManager` already builds its `ClientSession` with `base_url`:
      ```python
      session = await self.connection_manager.get_session()
      async with session.post("/v1/systemone", json=payload) as response: ...
      ```
    - **Timeout:** build `ConnectionManager(base_url=..., timeout_ms=int(timeout["total"]))`. The YAML value is already an integer in milliseconds; never pass the YAML dict.
    - **Retries are restricted.** Build `RetryHandler(..., retry_on=(aiohttp.ClientConnectionError, asyncio.TimeoutError, DecisionRetryableError))`, where `DecisionRetryableError(status, body)` is raised only for HTTP 429/5xx. It stores `.status` and `.body`, and its message includes both. If the step still sees one after retries run out (e.g. a 503), it reports `Decision model failed: HTTP 503: <provider body>`.
    - Other non-200 responses (400/401/404/422) raise `ValueError` straight away with the provider's error body verbatim, so an invalid request fails once and keeps its useful detail. A missing `answers` also raises `ValueError`.
    - `close()` closes the connection manager. `verify_connection` is a cheap `GET /api/tags`.
  - `typesafe_decision_service.py`, `TypeSafeDecisionService(DecisionService)`:
    - A lazily created, cached `AsyncTypeSafeClient(api_key=..., base_url=..., timeout=...)`. `close()` calls `await client.aclose()`.
    - **Timeout:** convert the YAML `timeout.total` (ms) to the SDK's expected form, float seconds (`total / 1000`) or the SDK's timeout object if that's what it takes. The SDK inspection in step 1 confirms which. Never pass the YAML dict.
    - Converts YAML questions to SDK objects: `choice` → `Choice(instructions, criteria)`, `noul` → `Noul(instructions[, criteria])`, `score` → `Score(instructions, criteria)`.
    - Normalizes the SDK response to `{model, answers, usage}`, using `model_dump()` if it exists, else `.choices`, `.nouls`, `.scores`, `.usage` and `.model`.
    - Retries are left to the SDK. SDK exceptions are re-raised as `ValueError` with the provider's message and details intact.
    - The SDK is imported lazily. If the import fails, the `__init__` loop skips the provider with a debug log.
  - **Model handling:** services are cached per provider (configured default model). The per-call `model` argument to `decide()` carries adapter or runtime overrides, so no cache-key changes are needed.
- `ai_services/registry.py`:
  - Add `register_decision_services(config)`. It skips everything when `decision.enabled` is false, and uses `config_section='decision_models'` and `default_enabled=False`, mirroring `register_video_generation_services` (`:245`).
  - Call it from `register_all_services` (~`:287`).
- **Caching:**
  - New `services/cache/decision_cache_manager.py` `DecisionCacheManager`, a copy of `video_cache_manager.py`, exported in `services/cache/__init__.py`.
  - `services/dynamic_adapter_manager.py`: add `self.decision_cache` (`:81`) and `get_decision_service(provider, adapter_name)` (`:525`). Add its size and keys to the diagnostics dict (`:734`, `:744`).
  - `DynamicAdapterManager.close()` (`:853`) closes provider, embedding, reranker, vision and audio caches today, but not image or video. Add `await self.decision_cache.close()`, and while there add the missing `image_cache.close()` and `video_cache.close()` calls.

### 2. Config (`base_url` used everywhere)
- New `config/decision.yaml`:
  ```yaml
  decision:
    provider: "ollama"          # default provider: ollama | typesafe
    enabled: true
  decision_models:
    ollama:
      enabled: true
      base_url: "http://localhost:11434"
      model: "nimble"           # nimble | tev1 | tev1:0.8b
      timeout: { connect: 5000, total: 30000 }
      retry: { enabled: true, max_retries: 2, initial_wait_ms: 500, max_wait_ms: 5000, exponential_base: 2 }
    typesafe:
      enabled: true
      api_key: ${TYPESAFE_API_KEY}
      base_url: "https://api.typesafe.ai"
      model: "jev-latest"
      timeout: { total: 30000 }
  ```
- `config/config.yaml`: add `"decision.yaml"` to the imports, after `video.yaml` (~line 17).
- Repo-root `env.example`: add `TYPESAFE_API_KEY=`.
- `install/dependencies.toml` `[profiles.default]`: add `"typesafe-sdk>=0.7.2,<0.8"` next to `xai-sdk` (line 24), and follow the `generate_requirements.py` convention if one applies.

### 3. Adapter type `decision_model`
- `adapters/__init__.py:99-126`: add it to the `(type, "none", "multimodal")` registration loop.
- Add it to these type lists:
  - `adapter_sdk/validator.py:22` `KNOWN_TYPES` and `:34` `NO_INFERENCE_PROVIDER_TYPES`
  - `inference/pipeline/steps/_utils.py:12-34` `NO_LLM_ADAPTER_TYPES` and `NO_INFERENCE_PROVIDER_ADAPTER_TYPES`
  - `adapter_sdk/specs.py:156,217` and `routes/discovery_routes.py:221`, but only where they enumerate generation-style types (check each one)
- **Adapter fields:**
  - `decision_provider`
  - `model` (optional)
  - `config.questions`, `config.state_key` (default `"input"`) and `config.allow_question_override` (default false)
- **Client model selection:** out of scope for v1. `allowed_models` is **not** reused. A dedicated `allowed_decision_models` resolution in `request_context_builder.py` can come later.

### 4. Pipeline step: `inference/pipeline/steps/decision_model.py` `DecisionModelStep`
- `should_execute`: not blocked, and `get_adapter_type(...) == 'decision_model'` (`_utils.py:234`). `supports_streaming() -> False`.
- **Input parsing:**
  - If `context.message` is a JSON object with a `state` object, use that state.
  - Its `questions` replace the adapter's questions only if `allow_question_override` is set. Otherwise they are ignored and a warning is logged.
  - Any other message becomes `state = {state_key: message}`.
- **Validation** (`_validate_questions`, returns clear error text):
  - The questions mapping is non-empty. Each name is a non-empty string and each definition is a dict.
  - `type` is one of `choice`, `noul`, `score`, and `instructions` is a non-empty string.
  - `choice` needs a non-empty `criteria` dict. `score` needs a `criteria` list of at least 2 levels. For `noul`, `criteria` is optional.
  - On failure, call `context.set_error(...)`.
- **Provider and model resolution:**
  - Provider: `context.runtime_provider`, then the adapter's `decision_provider`, then the global `decision.provider`.
  - Model: `context.runtime_model_name`, then the adapter's `model`, then the provider default. The model is passed to `decide(model=...)`.
- **Output:**
  - `context.decision = result`
  - `context.response = json.dumps(result["answers"], indent=2)`
  - `context.runtime_provider` and `context.runtime_model_name = result["model"]`, which is the resolved model, e.g. `jev-1.13.0`
  - Token usage is recorded with the existing usage helper in `_utils.py`.
  - Provider errors go to `context.set_error(f"Decision model failed: {e}")` with the detail preserved.
- Export it in `steps/__init__.py`, and insert it in `pipeline.py` (~`:422`) before `LLMInferenceStep`.

### 5. `decision` on every terminal output
- `inference/pipeline/base.py` `ProcessingContext`: add `decision: Optional[dict[str, Any]] = None`.
- `services/chat_handlers/streaming_events.py`:
  - `DoneEvent`: add optional `decision`.
  - `parse_stream_payload()` (`:197`): set `DoneEvent(..., decision=payload.get("decision"))`.
  - `stream_event_to_dict()` (`:270`): emit `payload["decision"]` when it is set.
- `streaming_handler.build_done_event` (`:622`): add a `decision` kwarg and forward it into `DoneEvent`.
- `services/chat_handlers/response_processor.py` `ResponseProcessor.build_result()` (`:380`): add a `decision` parameter and put it in the returned result dict.
- `services/pipeline_chat_service.py`:
  - Pass `context.decision` to `build_done_event` (~`:1413-1438`).
  - Pass it to `build_result()` in `process_chat()`.
- `inference/pipeline/pipeline.py` `process_stream`: add `decision` to the non-streaming fallback payload (`:340`, next to `sources`). Also audit the media short-circuit branches (`:185-214`) and the non-stream `process` path so that every public route surfaces `decision` when it is set. Trace how the pipeline's JSON chunks become `DoneEvent`s in `pipeline_chat_service`, so the field goes through the one canonical builder and isn't dropped.

### 6. Example adapters: `config/adapters/decision.yaml`
Each adapter uses `type: decision_model`, `datasource: none`, `adapter: multimodal`, `implementation: implementations.passthrough.multimodal.MultimodalImplementation` and `capabilities: {retrieval_behavior: none, formatting_style: clean, supports_threading: false}`. Each also sets `decision_provider` explicitly.

1. **`ticket-triage`** (`decision_provider: ollama`, `model: nimble`, `allow_question_override: true`)
   - `team`: choice of billing / technical / account / other
   - `refund_requested`: noul
   - `urgency`: score, Routine / Soon / Urgent
2. **`content-moderation`** (`decision_provider: typesafe`, `model: jev-latest`)
   - `category`: choice of safe / harassment / hate / self_harm / sexual / violence / spam
   - `needs_human_review`: noul
   - `severity`: score, None / Low / Medium / High
3. **`skill-router`** (`decision_provider: ollama`, `model: tev1:0.8b`)
   - `skill`: choice of chat / image / video / document / web_search / sql_analytics
   - `needs_retrieval`: noul
   - This is config only. It is not wired into `skill_intent_router.py`; that's a follow-up.

Finally, add `adapters/decision.yaml` to `config/adapters.yaml` `import:`.

## Implementation order
1. Install `typesafe-sdk` into the venv and inspect it (`AsyncTypeSafeClient.__init__`, `system_one`, the response model, exceptions, close). Write the SDK contract test first, then code against the confirmed API.
2. Service type, base class, Ollama and TypeSafe services, registry, and cache manager, with their unit tests.
3. Config files and dependency.
4. Adapter type lists and the step, with step tests.
5. `decision` output plumbing, with the streaming and non-streaming tests.
6. Example adapters, then end-to-end verification.

## Tests (`server/tests/`)
- `test_ai_services/test_typesafe_sdk_contract.py`: import `typesafe_sdk`, then assert that `AsyncTypeSafeClient`, `Choice`, `Noul` and `Score` exist, that the constructor accepts `api_key`, `base_url` and `timeout`, and that `system_one` and `aclose` exist. Skip if the SDK isn't installed.
- `test_ai_services/test_decision_services.py`:
  - **Ollama:** mocked session.
    - The request goes to the relative path `/v1/systemone`, with the expected payload shape and the per-call `model` override.
    - A 422 raises once, with no retry and the provider detail preserved.
    - A 503 and a connection error are retried. When a 503 exhausts its retries, the error keeps the status and body.
    - `timeout.total` in ms reaches `ConnectionManager(timeout_ms=...)`.
    - `close()` closes the connection manager.
  - **TypeSafe:** monkeypatched client.
    - Questions are converted to SDK objects, and `api_key` and `base_url` are passed through.
    - The response is normalized, and error mapping keeps the detail.
    - The `model` override is applied.
    - `close()` awaits `client.aclose()`.
    - The ms timeout is converted to the SDK's timeout form.
  - **Config:** `_extract_provider_config()` reads `decision_models.<provider>`.
- `test_ai_services/test_decision_registry.py`:
  - Registration is skipped when `decision.enabled: false` or `decision_models.<p>.enabled: false`.
  - A missing SDK skips typesafe but still registers ollama.
- `test_pipeline_steps/test_decision_model.py`, patterned on `test_image_generation.py` `_make_container`:
  - gating on adapter type
  - plain-text state mapping
  - JSON override, allowed and ignored
  - each validation rule
  - provider and model resolution order
  - `context.decision` and `context.response` populated
  - provider error surfaced
- Output tests:
  - `process_stream` fallback payload includes `decision`
  - `build_done_event` / `DoneEvent` serializes `decision`
  - `parse_stream_payload` → `stream_event_to_dict` round-trips `decision`
  - `ResponseProcessor.build_result(decision=...)`, so the non-streaming `process_chat` result includes `decision`
  - `DynamicAdapterManager.close()` closes the decision, image and video caches
- Validator: `decision_model` is accepted without `inference_provider`.
- Run: `/Users/remsyschmilinsky/Downloads/orbit/venv/bin/python -m pytest server/tests/ -q -k "decision or typesafe"`, then the full suite, then `ruff check server/`.

## End-to-end verification
1. Run `ollama pull nimble && ollama pull tev1:0.8b`, then run the blog's curl directly against Ollama.
2. Set `TYPESAFE_API_KEY` in `.env`, start `python3 server/main.py`, and create API keys bound to each example adapter.
3. On `ticket-triage`, send "I was charged twice, please refund", once streaming and once not. Expect `team=billing` and `refund_requested`≈1, with `decision` present in both outputs.
4. On the same adapter, send the JSON `{"state":{...},"questions":{...}}` override and confirm the custom questions are answered.
5. On `content-moderation`, confirm the TypeSafe call goes through the SDK and reports the resolved model (e.g. `jev-1.13.0`).
6. Stop Ollama and send a request. The error should surface cleanly with the provider detail, and the server should not crash.
