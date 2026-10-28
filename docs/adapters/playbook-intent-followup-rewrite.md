# Manual/Integration Check: Follow-up Query Rewriting

Steps to verify follow-up question rewriting for intent retrievers — first with `curl`, then in OrbitChat.

The feature is **off by default**. These steps use `intent-duckdb-analytics`
(`config/adapters/business-analytics.yaml`), which already ships with
`supports_followup_rewrite: true`, and cross-check with `intent-sql-postgres`
(`config/adapters/customer-orders.yaml`).

See `docs/sql-retriever-architecture.md` and
`docs/adapters/capabilities/adapter-capability-architecture.md` ("Follow-up
Query Rewriting") for the design. This feature composes with — and always
defers to — the clarification feature covered in
`docs/adapters/playbook-intent-clarification.md`; step 6 below exercises that
interaction directly.

## 1. Confirm it's enabled

It **is** a `capabilities:` entry, unlike clarification's `config:`-block knobs:

```yaml
# config/adapters/business-analytics.yaml
- name: "intent-duckdb-analytics"
  ...
  capabilities:
    ...
    supports_followup_rewrite: true   # ← turns this on (default: false)
```

Resuming a follow-up (rewriting "what about east" using the previous turn's
resolved query) requires the retriever to receive `session_id`.
`ContextRetrievalStep` forwards it automatically once
`supports_followup_rewrite: true` is set — the same special case already used
for `clarification_enabled`, independent of `capabilities.supports_session_tracking`.
Just make sure your client sends a stable `X-Session-ID` across turns
(OrbitChat already does this — one UUID per conversation).

Optionally, add a cheaper rewrite model so the per-turn rewrite LLM call isn't
on the same model as the main query:

```yaml
# config/adapters/business-analytics.yaml, alongside inference_provider/model
rewrite_provider: "ollama_cloud"
rewrite_model: "gpt-oss:20b"
```

## 2. Start the server and create an API key

```bash
python3 server/main.py
# in another shell:
./bin/orbit.sh key create --adapter intent-duckdb-analytics --name "Follow-up rewrite test"
```

```bash
export ORBIT_KEY=<the-key-just-created>
export SID=followup-test-1
```

## 3. Basic chain — same template, parameter swap

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $ORBIT_KEY" \
  -H "X-Session-ID: $SID" \
  -d '{"message": "what is the total sales amount for the west region"}' | jq
```

**Expected:** executes `total_sales_amount` with `region: "west"` directly — a
real number, not a clarifying question (no ambiguity here).

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $ORBIT_KEY" \
  -H "X-Session-ID: $SID" \
  -d '{"message": "what about east"}' | jq
```

**Expected:** the total for the **east** region, not an error or an
unfiltered total — the rewrite step turned "what about east" into something
like "What's the total sales amount for the east region" before template
matching ran. Check the server log at debug level for
`Rewrote follow-up query: 'what about east' -> '...'` (from
`inference/pipeline/steps/intent_query_rewrite.py`).

## 4. Chained follow-ups — building on the latest resolved turn, across templates

Continue the same session with a message that switches to a different
template (category instead of region) but should still be understood as a
sales-filter follow-up:

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $ORBIT_KEY" \
  -H "X-Session-ID: $SID" \
  -d '{"message": "and just for Electronics"}' | jq
```

**Expected:** resolves to `find_sales_by_category` (or a similarly-filtered
result) for Electronics — not a re-run of the east-region total and not a
"missing parameter" failure. This confirms the stored `effective_query`
chains forward from the *second* turn (east), not the first (west) — see the
"chaining" note in `docs/sql-retriever-architecture.md`.

## 5. Non-follow-up — must pass through unchanged

On a **fresh session**, send a message that has nothing to do with any prior
turn:

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $ORBIT_KEY" \
  -H "X-Session-ID: $SID-unrelated" \
  -d '{"message": "how many products do we have?"}' | jq
```

**Expected:** executes `count_products` normally (no prior turn exists for
this session, so `maybe_rewrite_followup_query` returns immediately without
an LLM call — check the log for the absence of any "Rewrote follow-up query"
line). Then, still in a session with prior state (reuse `$SID` from step 3),
ask something clearly unrelated to sales filtering:

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $ORBIT_KEY" \
  -H "X-Session-ID: $SID" \
  -d '{"message": "how many products do we have?"}' | jq
```

**Expected:** still resolves to `count_products` with no region/category
filter leaking in — the rewrite prompt is instructed to return the message
verbatim when it isn't actually a follow-up.

## 6. Clarification takes priority over rewriting

Enable clarification on the same adapter (see
`docs/adapters/playbook-intent-clarification.md` step 1) and trigger a
disambiguation or slot-fill question on a **new** session. Answer it with a
short fragment (e.g. "the first one", or just a bare value for slot-fill) —
**not** a rewrite target:

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $ORBIT_KEY" \
  -H "X-Session-ID: $SID-clarify" \
  -d '{"message": "<a vague query that triggers clarification on this adapter>"}' | jq

curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $ORBIT_KEY" \
  -H "X-Session-ID: $SID-clarify" \
  -d '{"message": "the first one"}' | jq
```

**Expected:** the answer resolves the clarification directly — the server log
must **not** show a "Rewrote follow-up query" line for this turn (confirm via
debug logging, or by temporarily breaking the rewrite LLM provider and
checking nothing errors/falls back oddly). This is the
`has_pending()` peek in `context_retrieval.py` short-circuiting the rewrite
step. Then send one more follow-up after the clarification resolves (e.g.
switch to a different region/category) and confirm it correctly builds on the
clarification's resolved query, not something stale from before
clarification started.

## 7. HTTP intent adapter

The feature works the same way on HTTP-based intent retrievers (no
clarification support there, so step 6 doesn't apply — the pending-check is
always false). Try it on `intent-http-glassdoor` or `intent-http-jsearch`
(`config/adapters/http-glassdoor.yaml`, `config/adapters/http-jsearch.yaml`),
both already enabled:

```bash
./bin/orbit.sh key create --adapter intent-http-jsearch --name "Follow-up rewrite test (HTTP)"
export JSEARCH_KEY=<the-key-just-created>

curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $JSEARCH_KEY" \
  -H "X-Session-ID: jsearch-followup-1" \
  -d '{"message": "find software engineer jobs in Toronto"}' | jq

curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $JSEARCH_KEY" \
  -H "X-Session-ID: jsearch-followup-1" \
  -d '{"message": "what about in Ottawa"}' | jq
```

**Expected:** the second call's results are for Ottawa, not Toronto or an
unfiltered search — same mechanism, HTTP template instead of SQL.

## 8. TTL

Trigger a follow-up chain like step 3, then wait longer than
`followup_rewrite_ttl_seconds` (default 300s) before sending the next turn.
To check this quickly, lower it temporarily in the adapter's `config:` block
(same place as `clarification_ttl_seconds`, not `capabilities:`):

```yaml
# config/adapters/business-analytics.yaml, intent-duckdb-analytics's config: block — temporary, for this test only
followup_rewrite_ttl_seconds: 5
```

**Expected:** after the TTL elapses, the stored turn is gone, so the next
message is treated as fresh (matched/extracted from scratch) instead of being
rewritten — no error either way, just no rewrite.

## 9. Usage accounting

```bash
curl -s http://localhost:3000/metrics | grep -i intent_rewrite
```

**Expected:** the rewrite LLM call's token usage shows up under the
`intent_rewrite` usage component (added via `add_usage_component` in
`context_retrieval.py`) rather than being invisible — confirm it only appears
on turns that actually triggered a rewrite call (i.e. not step 5's first,
state-free request).

## 10. OrbitChat UI

1. Point OrbitChat at an API key for `intent-duckdb-analytics` and open a new chat.
2. Ask "what is the total sales amount for the west region", confirm a real
   number comes back.
3. Ask "what about east" in the same conversation — confirm the answer is for
   east, not west and not an error.
4. Ask "and just for Electronics" — confirm it switches to the category
   filter rather than repeating the region total.
5. Because OrbitChat streams over SSE and keeps one session ID per
   conversation automatically, no extra client-side setup is needed — this
   exercises the real end-to-end path, not just curl with a manually-repeated
   `X-Session-ID`.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| Follow-up ("what about east") is matched/extracted as its own standalone query and fails or returns something unrelated | `supports_followup_rewrite` not set (or `false`) in the adapter's `capabilities:` block. |
| Follow-up resolves correctly on turn 2 but turn 3 reverts to the original (first) query instead of building on turn 2 | Check that `_store_followup_turn()` is storing the *rewritten* effective query, not the raw message, after each turn — see `docs/sql-retriever-architecture.md`'s chaining note. |
| Rewriting happens even when answering a pending clarification question | `has_pending()` peek in `context_retrieval.py` isn't being checked before the rewrite call, or clarification state was stored under a different adapter key than the rewrite lookup uses — both must use the resolved `retrieval_adapter_name`/`audit_adapter_name`, not `context.adapter_name`, for skill-routed requests. |
| Rewrite never triggers, even on a clear follow-up within the TTL window | No prior turn stored for this (adapter, session) — confirm the *previous* turn actually resolved a template (a `no_matching_template`/`below_threshold` turn stores nothing), and confirm `session_id` is actually being forwarded (debug-log `retriever_kwargs`). |
| Rewrite call errors or times out | Falls back silently to the original message by design — check `inference/pipeline/steps/intent_query_rewrite.py` logs for "Failed to rewrite follow-up query" / "Intent follow-up rewrite timed out"; verify `rewrite_provider`/`rewrite_model` (if set) actually resolve, or that the adapter's `inference_provider` fallback is reachable. |
| Follow-up state leaks across unrelated sessions or adapters | Confirm `(adapter_key, session_id)` isolation in `services/intent_followup_state.py` — each session/adapter pair must have its own entry. |

## Unit tests

```bash
# From repo root:
venv/bin/python -m pytest server/tests/test_services/test_intent_followup_state.py -v
venv/bin/python -m pytest server/tests/test_pipeline_steps/test_intent_query_rewrite.py -v
venv/bin/python -m pytest server/tests/test_pipeline_steps/test_context_retrieval_followup_rewrite.py -v
venv/bin/python -m pytest server/tests/test_retrievers/test_intent_clarification.py -v -k Followup
```

Covers: the TTL store's get/store/expiry and per-(adapter, session) isolation;
the rewrite step's no-op fast path, successful rewrite, and fallback on
LLM error/timeout/empty/malformed output; `session_id` forwarding and the
pending-clarification peek in `ContextRetrievalStep`; and — in the
clarification test file — storing the originating effective query across a
clarification round and two chained follow-ups after it resolves.
