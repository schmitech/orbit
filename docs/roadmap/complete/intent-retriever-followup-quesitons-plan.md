# Follow-up Query Rewriting for Intent Retrievers

## Context

Intent retrievers (SQL/HTTP) match a natural-language query against templates and extract
parameters purely from the current message — `DomainParameterExtractor.extract_parameters()`
(`server/retrievers/implementations/intent/domain/extraction/extractor.py:65`) has no notion of
prior turns. So a sequence like:

1. "How many customers bought in Toronto" → answered
2. "What about Ottawa" → template matching/parameter extraction sees only "What about Ottawa",
   which likely fails to match a template or extracts no location parameter.

The ask is a new, generic capability — not the existing "conversation thread" feature (which
replays a cached dataset) and not full chat-history injection into the LLM prompt. Instead,
before template matching, detect whether the new message is a follow-up to the *previous intent
query* and, if so, use a cheap LLM call to rewrite it into a standalone, fully-specified question
(e.g. "How many customers bought in Ottawa"), similar in spirit to the existing
image/video/audio/document generation rewriters (`config/rewriters-prompts.yaml`) but dynamic
rather than hardcoded to one domain, and scoped to intent retrievers only.

The closest existing architectural precedent is the intent **clarification** feature
(`server/services/intent_clarification_state.py`), which pins per-(adapter, session) state across
turns in a TTL-bounded in-memory store. This plan reuses that pattern for storing "last resolved
intent turn" instead of "pending clarification," and is careful to compose correctly with
clarification rather than race it.

## Approach

### 1. New per-(adapter, session) "last turn" store

Add `server/services/intent_followup_state.py`, structurally mirroring
`intent_clarification_state.py` (TTL default 300s, configurable via a new
`followup_rewrite_ttl_seconds` adapter config key, same cap/eviction approach, same
`(adapter_key, session_id)` keying via the existing `_clarification_adapter_key()`-style helper).

Store: `{"effective_query": str, "template_id": str, "parameters": dict}` where `effective_query`
is the *standalone* resolved question for that turn (the rewritten text if a rewrite happened,
otherwise the original message) — not the raw user utterance. This is what makes chaining work:
"Toronto" → "What about Ottawa" (rewrites to, and stores, "How many customers bought in Ottawa")
→ "and last month" rewrites against *that* stored effective query, producing "How many customers
bought in Ottawa last month", so each turn builds on the latest resolved request rather than the
original one.

API: `store_last_turn(adapter_key, session_id, payload)`, `get_last_turn(adapter_key, session_id)`.
No change to `chat_history_service` / `ConversationHistoryHandler` — this is adapter-scoped
ephemeral state for rewriting, not conversation history or threading, and losing it just disables
the rewrite for that turn (safe fallback, not a correctness issue).

### 2. Populate the store on every successful resolution — including clarification

In `intent_sql_base.py` and `intent_http_base.py`, call `store_last_turn()` at **every** point a
turn ends with a concrete resolved template + parameter set, specifically:

- The normal path: right after a template is matched, parameters extracted, and the query executed
  (near `_format_execution_response()` in `intent_sql_base.py:885`).
- The clarification-resume path: inside `_resume_pending_clarification()`
  (`intent_sql_base.py:1096`), *after* it successfully merges the newly-extracted parameters and
  executes — i.e. once a disambiguation/slot-fill round completes successfully. Earlier draft of
  this plan skipped this case, which would leave follow-up state anchored to a stale pre-
  clarification query (or missing entirely) for the next turn. Do not store on a clarification
  round that itself re-asks (still pending).

  **The resume case needs the originating standalone question, not the answer fragment.** The
  clarification payload stored by `store_pending()` (`_build_disambiguation_response()` /
  `_build_slot_fill_clarification()`) currently holds `template_id`/`template_hash`/`extracted`/
  `missing_params`/`round`, but not the question that triggered clarification — so on resume,
  `context.message` is just the short answer ("Ottawa", "the second one"), not something safe to
  store as `effective_query`. Extend the clarification payload to also carry
  `originating_effective_query`: always the *current turn's own* rewritten/effective query — i.e.
  whatever string was actually passed as `query` into `get_relevant_context()` for the turn that
  triggered clarification (after follow-up rewriting already ran on it, if applicable) — never a
  value re-fetched from `intent_followup_state`. For example, if a follow-up rewrite turns "what
  about last month" into "Ottawa last month" and *that* triggers clarification (e.g. an ambiguous
  region match), the preserved question must be "Ottawa last month", not the older stored "Toronto"
  query — otherwise the newly-introduced "last month" constraint would be lost on resume. Carry
  this field forward unchanged across multiple clarification rounds (slot-fill can re-ask more than
  once before resolving, `clarification_max_rounds`). When `_resume_pending_clarification()`
  finally succeeds, store `effective_query = originating_effective_query` (not the raw answer
  fragment) together with the final merged parameters into `intent_followup_state`. This is what
  lets a *second* follow-up after a clarification round build on the right question.

### 3. Priority: pending clarification wins over follow-up rewrite

Rewriting must never run while a clarification is pending for that (adapter, session), because an
answer like "the second one" or "Ottawa" is meant to resolve the clarification prompt directly and
would otherwise be rewritten against stale prior-turn context instead. In the pipeline step (point
6 below), before invoking the rewrite step, check whether clarification is pending for this
adapter/session — reuse the existing `pop_pending()`/peek-style check from
`intent_clarification_state.py` as a non-destructive peek (add a `has_pending(adapter_key,
session_id)` helper there if one doesn't already exist, so checking doesn't consume the entry) —
and skip rewriting entirely if so, passing `context.message` through unchanged so the retriever's
own `_resume_pending_clarification()` handles it as today.

### 4. New rewrite prompt in `config/rewriters-prompts.yaml`

Add a `rewriters.intent_query` entry alongside `image`/`video`/`audio`/`document`, with its own
`template`, `max_tokens` (small, e.g. 150), `temperature` (low, e.g. 0.1). Prompt inputs: the
previous *effective* query + previously resolved parameters (rendered as plain text), and the new
user message. Instructions: if the new message is a follow-up that implicitly reuses/replaces
parameters from the previous query (e.g. "what about X", "and for last month"), output a single
standalone rewritten question; otherwise output the new message unchanged, verbatim. Output
contract: plain text only (no JSON) — if the LLM returns empty text or something pathological
(e.g. far longer than a reasonable question, or multi-line/contains a refusal), the rewrite step
must treat that as a failure and fall back to the original message rather than passing malformed
text into template matching.

### 5. New pipeline step: `server/inference/pipeline/steps/intent_query_rewrite.py`

Mirrors the **audio/document** rewrite-provider pattern specifically (not image), since those are
the ones that actually forward `rewrite_model`:
`_resolve_rewrite_provider()` in `audio_generation.py:103-129` (`explicit_model_override=rewrite_model`
passed into `get_overridden_provider()`, `server/services/dynamic_adapter_manager.py:303`).
Read `rewrite_provider`/`rewrite_model` off the adapter config the same way; fall back to the
adapter's own `inference_provider` if unset.

Call `llm_provider.generate_tracked(prompt, usage_sink=rewrite_sink, max_tokens=..., temperature=...)`
(`server/inference/pipeline/providers/llm_provider.py:146`) under a short bounded timeout (e.g.
`asyncio.wait_for(..., timeout=5.0)`) — a hung rewrite call must not stall the whole turn; on
timeout or any exception, fall back to the original message. Record the rewrite call's token usage
into the context's usage accounting the same way the generation steps do with `rewrite_sink`
(so it shows up in billing/telemetry, not as a free hidden LLM call).

Entry point: `maybe_rewrite_followup_query(context, adapter_name, session_id) -> str`. Looks up
`get_last_turn()`; if none, returns `context.message` unchanged without an LLM call.

**Cost note (corrects an earlier draft assumption):** the "no LLM call" fast path only applies to
the *first* turn in a session (or any turn after the follow-up state has expired/been evicted).
Once a last-turn entry exists, **every subsequent turn within the TTL window calls the rewrite
LLM** — including turns that aren't actually follow-ups — since the whole point is to let the LLM
decide. This is an accepted cost of the first version (mitigated by using a small/cheap
`rewrite_model` and tight `max_tokens`), not something to optimize away now; document this plainly
in the code comment and in adapter docs so it isn't mistaken for a free optimization.

### 6. New capability flag

In `server/adapters/capabilities.py`, add `supports_followup_rewrite: bool = False` to
`AdapterCapabilities` (next to `supports_charts`, line ~56) and read it in `from_config()`
(line ~166).

### 7. Wire into `context_retrieval.py`, with session_id forwarded

In `server/inference/pipeline/steps/context_retrieval.py`, extend the existing special-case block
at lines 303-308 (currently forwarding `session_id` only when `clarification_enabled`) to also
forward it when the retriever/capability has `supports_followup_rewrite` enabled:

```python
if (
    'session_id' not in retriever_kwargs
    and context.session_id
    and (
        getattr(retriever, 'clarification_enabled', False)
        or getattr(capabilities, 'supports_followup_rewrite', False)
    )
):
    retriever_kwargs['session_id'] = context.session_id
```

(`getattr(capabilities, ...)` guards against `capabilities` being `None`/absent for adapters with
no declared capabilities block, consistent with how `clarification_enabled` is already read via
`getattr` on the retriever rather than assumed present.)

This is the fix for the gap where HTTP adapters and SQL adapters with clarification disabled would
otherwise never get a `session_id`, so follow-up state would never populate or be read for them.

**Adapter identity consistency.** The context_retrieval step already resolves a
`retrieval_adapter_name` distinct from `context.adapter_name` for skill-swapped requests (see the
log line at `context_retrieval.py:280`, "Retrieving via original adapter ... for skill-swapped
adapter ..."). All follow-up-rewrite state must key off that same resolved `retrieval_adapter_name`
(via the existing `_clarification_adapter_key()`-style helper) — consistently for: the
`intent_followup_state` store/lookup, the pending-clarification peek, and resolving the rewrite
LLM provider (`rewrite_provider`/`rewrite_model` read from that adapter's config, not
`context.adapter_name`'s). Using the wrong identity on any one of these would silently split a
single conversation's follow-up state across two keys (or read/write the wrong adapter's config)
whenever a skill-routed request is in play.

Then, just before the retriever call (~line 316), when
`getattr(capabilities, 'supports_followup_rewrite', False)` is true and `context.session_id` is
present:
1. Peek for pending clarification (point 3) — if pending, skip rewriting, use `context.message` as-is.
2. Otherwise call `maybe_rewrite_followup_query(...)` and pass its result as `query=` instead of
   `context.message`.

No change needed to `_build_retriever_kwargs()` itself beyond the session_id condition above —
the rewrite only changes what string is sent as `query`.

### 8. Config

Enable per-adapter via existing capabilities block, e.g. in `config/adapters/customer-orders.yaml`:

```yaml
capabilities:
  supports_followup_rewrite: true
```

Optionally add `rewrite_provider` / `rewrite_model` at the adapter level for a cheaper model than
the adapter's main `inference_provider` (same keys the generation adapters already use), and
`followup_rewrite_ttl_seconds` to override the default TTL.

## Files to touch

- `server/services/intent_followup_state.py` — new, TTL store (pattern: `intent_clarification_state.py`, plus a non-destructive `has_pending`-style peek helper added to the clarification store if missing)
- `server/retrievers/base/intent_sql_base.py`, `server/retrievers/base/intent_http_base.py` — store last-turn state on both the normal success path and the clarification-resume success path
- `config/rewriters-prompts.yaml` — new `intent_query` rewriter entry
- `server/inference/pipeline/steps/intent_query_rewrite.py` — new, rewrite step (pattern: `audio_generation.py`'s `_resolve_rewrite_provider`/rewrite call, with `explicit_model_override`, bounded timeout, and usage-sink accounting)
- `server/adapters/capabilities.py` — new `supports_followup_rewrite` flag
- `server/inference/pipeline/steps/context_retrieval.py` — forward `session_id` for this capability too; peek-and-skip on pending clarification; call the rewrite step before `get_relevant_context`
- `config/adapters/customer-orders.yaml` (and other intent adapters, opt-in) — enable the capability

## Verification

1. Unit: `intent_followup_state` store/get/TTL expiry, and `(adapter, session)` isolation (two
   different sessions or adapters never see each other's last-turn state).
2. Unit: `maybe_rewrite_followup_query` — no-op when no last turn stored; calls the LLM and returns
   rewritten text when a last turn exists; falls back to original message on LLM error, timeout,
   empty output, or malformed/oversized output.
3. Unit: pending-clarification peek correctly short-circuits rewriting without consuming the
   pending entry (a subsequent clarification resume still works normally).
4. Integration: enable `supports_followup_rewrite` on `intent-sql-postgres`
   (`config/adapters/customer-orders.yaml`), run the server, and with a fixed `X-Session-ID` drive
   a **chained** sequence — "How many customers bought in Toronto" → "What about Ottawa" → "and
   last month" — confirming each turn's rewritten/effective query and resulting SQL incorporate the
   latest resolved parameters (Ottawa + last month on the third turn, not Toronto).
5. Integration: with clarification enabled on the same adapter, trigger a disambiguation/slot-fill
   question, answer it ("the second one"), and confirm the answer resolves the clarification
   (rewriting was skipped) and that the next follow-up turn after that correctly builds on the
   clarification's resolved query/parameters.
5a. Unit/integration: clarification followed by two chained follow-ups — trigger a clarification
   round, resolve it, then send two more follow-up turns in sequence (e.g. resolve to "revenue by
   region for Q3" → "and Q4" → "just Ontario"), asserting each turn's stored `effective_query` and
   resulting parameters correctly carry forward the clarification's originating question plus each
   successive follow-up's edits, not the raw clarification answer fragment.
6. Confirm a brand-new session's first turn, a turn unrelated to any prior query (should pass
   through unchanged), and an HTTP intent adapter (e.g. `intent-http-glassdoor`) all behave
   correctly with the capability enabled.
