# Token usage & cost tracking

ORBIT records per-request token usage and an **estimated** cost on every
inference audit record, and surfaces both on the admin panel's Audit table
and its "Costs" tab (`/admin/observability/usage`). Cost is derived from a
local, hand-maintained rate table (`config/pricing.yaml`) — it is not pulled
from any provider billing API, and will not match an invoice to the cent.
See the plan's "Key design constraint" rationale for why: only a handful of
providers expose a usage API at all, each needs a separate admin credential,
the data is aggregate and hours-delayed, and none of them can attach a cost
to an individual request the way a local rate table can.

This doc covers the two things you'll actually need to touch as new
providers/models show up: wiring a provider into usage extraction, and
keeping `config/pricing.yaml` current.

## How it fits together

```
provider SDK response
  -> <provider>_inference_service.py  (reads response.usage / usage_metadata / etc.)
  -> UsageReportingMixin._report_usage(usage_sink, prompt_tokens, completion_tokens)
  -> LLMInferenceStep._record_usage()  (server/inference/pipeline/steps/llm_inference.py)
       - looks up cost via PricingService (server/services/pricing_service.py)
       - writes context.metadata["usage"]
  -> ResponseProcessor.log_conversation() -> AuditService.log_conversation()
  -> AuditRecord (prompt_tokens, completion_tokens, total_tokens, cost_usd,
     input_rate_per_1m, output_rate_per_1m, pricing_source)
  -> audit_logs table / collection / index
  -> GET /admin/audit/events (per-record) and GET /admin/observability/usage (aggregated)
```

Two things are deliberately decoupled:

- **Usage extraction** (did the provider tell us how many tokens this request used) is a
  per-provider, per-SDK concern — Section "Adding a new provider" below.
- **Pricing** (what those tokens cost) is a single flat-file lookup, keyed on
  `(provider, model)` — Section "Updating pricing" below.

A provider can report usage with no price configured (shows as tokens with
`cost: —` / "unpriced" in the UI), and a provider can be priced with no
usage reporting wired up yet (shows as `—` tokens, no cost). Neither blocks
the other.

## Adding a new provider

This only applies to **paid, hosted API providers**. Local/self-hosted
providers (`ollama`, `llama_cpp`, `vllm`, `sglang`, `lmstudio`, `shimmy`,
`transformers`, `tensorrt`, `bitnet`, `airllm`, `fugu`, `huggingface`)
intentionally report `$0.00` cost, not extracted usage — see their entries
in `config/pricing.yaml`.

Every inference implementation lives under
`server/ai_services/implementations/inference/<provider>_inference_service.py`
and defines its own `generate()`/`generate_stream()` — there is no shared
"generate" method to hook once for all providers, because roughly half of
them are on genuinely different SDKs (Anthropic's, Google's `genai`, Cohere,
Ollama's raw HTTP API, `azure-ai-inference`, `ZaiClient`, the native
`openrouter` client) even where they superficially look OpenAI-shaped. Wire
each provider by hand:

1. **Mix in `UsageReportingMixin`.** Add it as the *first* base class:

   ```python
   from ...providers.usage_reporting import UsageReportingMixin

   class YourProviderInferenceService(UsageReportingMixin, InferenceService, YourBaseService):
       ...
   ```

   This flips `SUPPORTS_USAGE_REPORTING` to `True` for the class. That flag is
   what gates whether `usage_sink` is ever forwarded to `generate()`/
   `generate_stream()` at all — see "Why the capability flag" below before
   skipping this step.

2. **Pop the sink as the first line of `generate()` and `generate_stream()`:**

   ```python
   async def generate(self, prompt: str, **kwargs) -> str:
       usage_sink = self._take_usage_sink(kwargs)
       ...
   ```

   This must run *before* any other `kwargs` handling. Most implementations
   do `params.update(kwargs)` or `**kwargs` straight into the provider SDK
   call — if `usage_sink` isn't popped first, it leaks into that call and the
   provider's SDK will reject the request with an unrecognized-parameter
   error.

3. **After the response comes back, extract usage and report it:**

   ```python
   response = await self.client.chat.completions.create(**params)

   usage = getattr(response, "usage", None)
   if usage is not None:
       self._report_usage(
           usage_sink,
           getattr(usage, "prompt_tokens", None),
           getattr(usage, "completion_tokens", None),
       )
   ```

   Always use `getattr(..., None)` guards — never assume the field exists.
   Some providers omit `usage` entirely on certain response shapes (e.g. a
   tool-call turn), and an unreported request must stay `reported: False`,
   not silently become `0`. See `server/ai_services/providers/usage_reporting.py`
   for the exact contract.

   Where to find the field names, by SDK family (see the migrated providers
   for working examples of each):

   | SDK family | Non-streaming usage | Streaming usage |
   |---|---|---|
   | OpenAI-compatible (`openai` python client pointed at a compatible endpoint) — groq, mistral, deepseek, together, xai, fireworks, deepinfra, cerebras, moonshot, minimax, nebius, scaleway, perplexity, venice, cohere | `response.usage.prompt_tokens` / `.completion_tokens` | Add `"stream_options": {"include_usage": True}` to the request params; the final chunk has `choices == []` and a populated `.usage` — see `openai_inference_service.py` |
   | Anthropic | `response.usage.input_tokens` / `.output_tokens` | Only available via `stream.get_final_message().usage` after the stream is exhausted — Anthropic's `message_delta.usage.output_tokens` is cumulative, so take the final value, never sum deltas. See `anthropic_inference_service.py` |
   | Google (`google-genai`) — gemini, vertexai | `response.usage_metadata.prompt_token_count` / `.candidates_token_count`, **plus** `.thoughts_token_count` for reasoning-enabled models (billed as output but reported separately — see `_billed_completion_tokens()`) | Track the *last* chunk's `usage_metadata` across the stream (it's cumulative per-chunk, not incremental) |
   | Ollama (raw HTTP, both local and `ollama_cloud`) | `data["prompt_eval_count"]` / `data["eval_count"]` from the JSON response (or the Pydantic response object for `ollama_cloud`) | Same fields on the final NDJSON line where `done: true` |
   | Anything else (a distinct SDK — Azure AI Inference, Z.AI, the native `openrouter` client, etc.) | Check that SDK's response object for a `usage`-shaped attribute and wire it the same way | Only add a streaming `stream_options`-style extraction if you've confirmed that SDK actually supports it — don't guess at an unconfirmed param shape. It's fine to ship non-streaming extraction only and leave streaming unreported (see `azure_openai_inference_service.py`, `zai_inference_service.py`, `openrouter_inference_service.py` for this exact tradeoff, each with a `noqa` comment explaining why) |

   `_report_usage()` also takes an optional `reasoning_tokens=` kwarg — the
   subset of completion tokens spent on reasoning/thinking, when a provider
   breaks it out separately (OpenAI's `usage.completion_tokens_details.reasoning_tokens`
   / Responses API `output_tokens_details.reasoning_tokens`, exposed via
   `UsageReportingMixin._extract_reasoning_tokens()`; Gemini/Vertex's
   `usage_metadata.thoughts_token_count`). It's purely informational and
   already folded into the `completion_tokens` total passed as the second
   positional arg — never treat it as an addition to make yourself, and
   never let its absence (most providers don't break it out) affect cost.

4. **Add pricing** for that provider's models — see "Updating pricing" below.
   A provider with usage extraction wired but no pricing entry shows tokens
   with cost `—` ("unpriced"), which is a safe intermediate state, not a bug.

5. **Test it.** `server/tests/test_usage_extraction.py` is table-driven over
   mocked SDK response objects (no real API calls) — add a case there for the
   new provider's response shape. Also run the pipeline-level regression
   guard:

   ```bash
   venv/bin/python -m pytest server/tests/test_usage_extraction.py server/tests/test_pipeline_steps/test_llm_inference_usage.py -q
   ```

   The pipeline test's "legacy provider" case is the one that actually
   proves step 2 above matters — it asserts `usage_sink` never reaches a
   provider that hasn't opted in.

### Why the capability flag (don't skip this)

`InferenceService.generate_tracked()`/`generate_stream_tracked()`
(`server/ai_services/services/inference_service.py`) are the only things the
pipeline calls — never `generate()`/`generate_stream()` directly. They only
forward `usage_sink=` to the underlying `generate()` when
`SUPPORTS_USAGE_REPORTING` is `True` on that instance. Every provider you
*haven't* migrated yet still works today because that flag defaults to
`False` on the base class — the sink is silently dropped and the request
proceeds exactly as before. This is what lets usage tracking roll out
provider-by-provider without a flag day.

## Updating pricing

`config/pricing.yaml` is a flat rate table, loaded once at startup by
`PricingService` (`server/services/pricing_service.py`). Rates are USD per
1,000,000 tokens:

```yaml
pricing:
  currency: "USD"
  updated: "2026-07-29"      # bump this whenever you touch a rate
  stale_after_days: 120       # admin panel flags the pricing as stale past this

  providers:
    openai:
      "gpt-5.4-mini":  { input_per_1m: 0.25, output_per_1m: 2.00 }   # exact model match
      "gpt-5*":        { input_per_1m: 1.25, output_per_1m: 10.00 }  # glob, matches any gpt-5 variant/date suffix
    ollama:
      "*": { input_per_1m: 0.0, output_per_1m: 0.0 }                # explicit "known free"
```

**Matching order**, for a given `(provider, model)`:

1. An exact key match (`"gpt-5.4-mini"`).
2. The **longest** matching glob pattern (`fnmatch` syntax), so a specific
   pattern like `"gpt-4o-mini*"` wins over a more general `"gpt-4o*"` on the
   same provider. This is why a versioned/dated model name like
   `claude-sonnet-4-6-20250929` still resolves correctly against a pattern
   like `"claude-sonnet-4*"`.
3. The provider's bare `"*"` fallback, if present.
4. No match at all → **unpriced**, not `$0.00`.

That last distinction matters and is enforced end-to-end: an explicit
`{input_per_1m: 0.0, output_per_1m: 0.0}` rate (used for local/self-hosted
providers) is tagged `pricing_source: "local_zero"` and shows `$0.00` in the
UI. A model with genuinely no rate configured is tagged `"unpriced"` and
shows `—`. Conflating the two would make a forgotten pricing entry silently
read as "this is free," which is the wrong failure mode for a cost feature.
`PricingService` logs one deduplicated warning per unseen `(provider, model)`
pair so a gap doesn't stay silent forever.

### Adding/refreshing a rate

1. Find (or add) the provider's block under `pricing.providers` in
   `config/pricing.yaml`.
2. Add a key for the model. Prefer a glob over the exact dated model string
   when a provider ships frequent date-suffixed releases of the same tier
   (e.g. `"claude-sonnet-4*"` rather than pinning every snapshot) — but use an
   exact key when a specific model needs to override a broader glob (see
   `openai.gpt-4o-mini*` next to `openai.gpt-4o*` for the general "specific
   beats generic" pattern).
3. Bump `pricing.updated` to today's date. The admin panel's Costs tab reads
   this and flags the whole pricing table as stale once it's older than
   `stale_after_days`.
4. Restart the server (or hot-reload config, if enabled) — `PricingService`
   parses the file once at startup.
5. Sanity-check the resolution before trusting it in the UI:

   ```bash
   cd server && ../venv/bin/python -c "
   from services.pricing_service import PricingService
   import yaml
   cfg = yaml.safe_load(open('../config/pricing.yaml'))
   svc = PricingService(cfg)
   print(svc.estimate('<provider>', '<model-name>', prompt_tokens=1_000_000, completion_tokens=1_000_000))
   "
   ```

   Confirm `pricing_source` is what you expect (`exact`/`pattern`/
   `provider_default`) and `cost_usd` is not `None` for a model you meant to
   price.
6. Run `venv/bin/python -m pytest server/tests/test_pricing_service.py -q`
   — it covers exact-vs-glob precedence, the longest-pattern-wins rule, and
   the unpriced-vs-local-zero distinction, so a malformed entry that breaks
   one of those invariants gets caught before it reaches the admin panel.

### Where rates currently come from (today: manual)

There is no automated sync yet — every rate in `config/pricing.yaml` was
typed in from each provider's public pricing page at the time it was added.
That means the table **will drift** as providers change prices; the
`stale_after_days`/`updated` staleness flag exists specifically to surface
that drift in the admin panel rather than let stale numbers look
authoritative forever.

If you're keeping rates current by hand: check the provider's official
pricing page (not a rate limit page or model card — these frequently quote
different numbers), record both input and output per-1M rates, and re-run
the verification steps above.

**Planned follow-up (not yet built):** an automated tool/script to populate
`config/pricing.yaml` from a canonical pricing source instead of hand-editing
it — either a small scraper/fetcher per provider, or adopting an existing
open-source LLM-pricing dataset if one has an acceptable license and
coverage of ORBIT's provider list. Whatever that ends up being, it should
write to this same `pricing.providers.<provider>.<model-pattern>` shape so
the matching/precedence rules above don't change, and it should preserve the
`updated`/`stale_after_days` fields (or set `updated` itself on every run).

## Auditing / observability surfaces

- **Per-record**: `GET /admin/audit/events` — each inference-source row
  carries `prompt_tokens`, `completion_tokens`, `total_tokens`,
  `reasoning_tokens` (informational, only set for providers that break it
  out — see above), `cost_usd`, `input_rate_per_1m`, `output_rate_per_1m`,
  `pricing_source`, `usage_unit`, `usage_quantity` (the latter two only set
  for discrete-unit media requests — see below) in `request_summary` (and at
  the top level of the row). Rendered as the Tokens/Cost columns and the
  "Usage & cost" section of the record dossier in the admin panel's Audit
  tab.
- **Aggregated**: `GET /admin/observability/usage` (admin panel: the
  **Costs** tab) — token/cost totals, a time-bucketed series, and top-N
  groups by model/provider/adapter/user, over a configurable window. Backed
  by `AuditStorageStrategy.aggregate_usage()`, implemented per storage
  backend (SQLite, Postgres, MongoDB, Elasticsearch) in
  `server/services/audit/`. Both endpoints are gated by the existing
  `audit.read` permission — reading aggregate token counts is strictly less
  sensitive than the full query/response text `audit.read` already grants,
  so there's no separate permission for this.

## Media services: image/video/audio/vision/OCR

Non-text AI services are tracked using one of three billing shapes, all
resolved through `PricingService` and landing on the same `AuditRecord`:

| Shape | Unit | Where | Pricing |
|---|---|---|---|
| Text tokens | tokens | `inference/`, all of `vision/`, gemini OCR, gemini/openai (gpt-image-1) image | `pricing.providers.<provider>.<model>.{input_per_1m,output_per_1m}` — same table/matching as text |
| Tiered tokens | text + audio tokens | realtime voice sessions (`gpt-realtime*`) | `pricing.providers` gains optional `audio_input_per_1m`/`audio_output_per_1m`; `PricingService.estimate()` takes optional `audio_prompt_tokens`/`audio_completion_tokens` and reports `unpriced` (never silently text-priced) if audio tokens are present without a configured audio tier |
| Discrete units | images, video seconds, TTS characters, STT seconds, OCR pages | image/video/audio(TTS+STT)/mistral-OCR | new `pricing.media` section (same provider/model matching), `PricingService.estimate_media(provider, model, unit, quantity)` |

Two new `AuditRecord`/audit_logs columns carry the discrete-unit case:
`usage_unit` (e.g. `"images"`, `"audio_seconds"`) and `usage_quantity`.
`cost_usd` stays the **one** summable cost column across both shapes, so the
Costs tab's totals need no changes to include media spend.

**Reporting mechanism**, mirroring text inference:
- Media services that return a `Dict` (`generate_image`, `generate_video`,
  `extract_document`) put a `"usage"` (token-shaped, e.g. gpt-image-1) or
  `"media_usage"` (`{"unit", "quantity"}`) key directly in their return value
  — no `usage_sink` needed, since the return value is already a dict.
  DALL-E/Imagen/xai/ollama images report `images` count (the actual `n`
  requested); xAI video reports `seconds` (the actual duration requested,
  never guessed from output bytes); Mistral OCR reports `pages` (already
  computed for `page_count`); Gemini's Imagen branch and OpenAI's DALL-E
  branch report no token usage at all (no `usage_metadata`/`response.usage`
  on those SDK calls) — only the unit.
- Services that return a bare `str`/`bytes` (vision's `analyze_image` etc.,
  audio's `speech_to_text`) accept an explicit `usage_sink` kwarg and mix in
  `UsageReportingMixin`, exactly like text `generate()`. TTS characters are
  the one exception needing no service change at all — the caller already
  has the exact text being spoken (`len(text)`), so the pipeline step
  computes it directly rather than reading it back from the service.
- `server/inference/pipeline/steps/_utils.py`'s `record_media_generation_usage()`
  combines a generation call's usage with its **separate prompt-rewrite LLM
  call** (image/video/audio-generation adapters resolve a natural-language
  prompt via a rewrite LLM before the actual generation call — that LLM
  spend was previously untracked entirely) into one `context.metadata["usage"]`
  — both are real spend for the same request and belong on one audit row.
  The two cost components are priced independently against their own
  provider/model and summed; a missing/unpriced component contributes `$0`
  rather than blocking the other.
- File-upload STT/vision/OCR (`file_processing_service.py`,
  `ai_document_processor.py`) had **no audit record at all** before this —
  unlike chat requests, uploads never flow through
  `response_processor.log_conversation()`. `FileProcessingService._log_extraction_usage()`
  writes a new, separate audit record when a call reports usage, reached via
  `self.app_state.audit_service` (lazily fetched — it may not be wired yet
  when the service is constructed).
- Realtime voice sessions (OpenAI Realtime, Gemini Live) accumulate usage
  across every `response.done`/`usageMetadata` event — including cancelled
  and tool-call-only turns, which still bill tokens — into a per-session
  `BaseRealtimeWebSocketHandler._usage_accumulator`, flushed as **one** audit
  record in `cleanup()` (not per-turn; a session can produce hundreds of
  turns, which would flood the Costs tab).

**Not yet covered** (explicit scope reduction, not silently dropped):
- Cohere and the local vision providers (ollama, ollama_cloud, vllm,
  llama_cpp) — token usage extraction for `vision/*` only reached Anthropic,
  OpenAI, and Gemini.
- STT duration is only captured for OpenAI (`response_format="verbose_json"`
  gives an authoritative `duration`); other STT providers (ElevenLabs,
  Gemini/Google, Cohere) report no usage at all yet.
- Inline chat TTS (`return_audio`/`tts_voice` on a normal chat request, via
  `services/chat_handlers/audio_handler.py`) is not wired — the audit record
  for that request is written by `response_processor.process_response()`
  *before* the TTS audio is generated, so merging TTS cost into the same row
  would require reordering that call sequence in `pipeline_chat_service.py`.
- `openai_realtime_translation_websocket_handler.py` does not extend
  `BaseRealtimeWebSocketHandler` (it's a standalone class with no response
  lifecycle), so it has no usage accumulator either.

## Known limitations

- **Cancelled/cached responses**: a cancelled stream never sees a final
  usage chunk, and a query-cache hit never calls the provider at all — both
  correctly leave usage unreported (`total_tokens: null`), not `0`.
- **Cost is always an estimate.** Even with an accurate, current rate, this
  is a locally-computed number, not what the provider will actually invoice
  (rounding, committed-use discounts, free tier credits, etc. are all
  invisible to this feature).
