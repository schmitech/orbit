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
  `pricing_source` in `request_summary` (and at the top level of the row). Rendered as the
  Tokens/Cost columns and the "Usage & cost" section of the record dossier
  in the admin panel's Audit tab.
- **Aggregated**: `GET /admin/observability/usage` (admin panel: the
  **Costs** tab) — token/cost totals, a time-bucketed series, and top-N
  groups by model/provider/adapter/user, over a configurable window. Backed
  by `AuditStorageStrategy.aggregate_usage()`, implemented per storage
  backend (SQLite, Postgres, MongoDB, Elasticsearch) in
  `server/services/audit/`. Both endpoints are gated by the existing
  `audit.read` permission — reading aggregate token counts is strictly less
  sensitive than the full query/response text `audit.read` already grants,
  so there's no separate permission for this.

## Outstanding: image/video/audio services aren't tracked yet

Everything above only covers **text inference** (`server/ai_services/implementations/inference/`).
None of the other AI service categories report usage or cost yet, even
though several of them are the actual bulk of provider spend per request —
a single image or video generation call routinely costs far more than a
text completion, and none of that shows up in the Audit table or the Costs
tab today:

- `server/ai_services/implementations/image/` — gemini, openai, xai, ollama
- `server/ai_services/implementations/video/` — gemini, xai
- `server/ai_services/implementations/audio/` — openai, elevenlabs,
  anthropic, cohere, gemini/google, coqui, supertonic, whisper, vllm, ollama
  (STT and TTS both live here)
- `server/ai_services/implementations/vision/` — anthropic, cohere, gemini,
  openai, llama_cpp, ollama, ollama_cloud, vllm
- `server/ai_services/implementations/ocr/` — gemini, mistral, vision-based

None of these go through `LLMInferenceStep`/`UsageReportingMixin` at all —
image/video generation is typically billed **per image/second/megapixel**,
not per token, so `config/pricing.yaml`'s `input_per_1m`/`output_per_1m`
shape and `PricingService.estimate()`'s token-based arithmetic don't apply
as-is. Extending this feature to these categories will need:

- A per-category usage unit (images generated, video seconds, audio
  seconds/characters) captured from each of the above services' responses,
  analogous to `usage_sink` but not token-shaped.
- A pricing shape in `config/pricing.yaml` (or a sibling file) keyed on that
  unit instead of tokens per 1M — the current `resolve()`/matching logic
  should still apply, just against a different rate shape per category.
- New `AuditRecord` fields (or a separate record type) for non-text spend,
  since `prompt_tokens`/`completion_tokens` don't mean anything for a video
  generation call.
- Corresponding columns/sections on the Audit dossier and a way to combine
  text + media cost in the Costs tab's totals (currently `cost_usd` there
  only sums text-inference audit rows).

This is a real gap, not a nice-to-have — flagging it here so it isn't lost
before the next round of work on this feature.

## Known limitations

- **MCP tool-calling loop**: a request that goes through the inline MCP
  tool-calling loop (`run_tool_calling_loop`) makes multiple provider calls,
  and usage is not currently summed across those calls — it's tagged
  `metadata["usage"]["partial"] = True` rather than silently under-reporting.
- **Cancelled/cached responses**: a cancelled stream never sees a final
  usage chunk, and a query-cache hit never calls the provider at all — both
  correctly leave usage unreported (`total_tokens: null`), not `0`.
- **Cost is always an estimate.** Even with an accurate, current rate, this
  is a locally-computed number, not what the provider will actually invoice
  (rounding, committed-use discounts, free tier credits, etc. are all
  invisible to this feature).
