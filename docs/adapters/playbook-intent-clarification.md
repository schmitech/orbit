# Manual/Integration Check: Intent Clarification (Graceful Degradation)

Steps to verify confidence-banded disambiguation and slot-fill clarification — first with `curl`, then in OrbitChat.

The feature is **off by default**. These steps turn it on for `intent-sql-postgres`
(`config/adapters/customer-orders.yaml`).

## 1. Enable it on the adapter

This is **not** a `capabilities:` entry — it's a set of `adapter_config` knobs read
by `IntentSQLRetriever`, alongside `confidence_threshold` and the Phase 3B query-guard
knobs. Add them to `intent-sql-postgres`'s existing `config:` block:

```yaml
# config/adapters/customer-orders.yaml
- name: "intent-sql-postgres"
  ...
  config:
    confidence_threshold: 0.5
    ...
    clarification_enabled: true          # ← turns on Phase 5 (default: false)
    clarification_high_threshold: 0.65   # >= this: execute directly
    clarification_ambiguity_gap: 0.05    # top-2 gap below this → disambiguate
    clarification_max_rounds: 2          # slot-fill re-asks before giving up
    clarification_ttl_seconds: 300       # how long a pending question survives
    # no_match_message: "Custom fallback text"   # optional
```

Resuming a clarification (answering "which one?" or filling in a missing
parameter on the *next* turn) requires the retriever to receive `session_id`.
`ContextRetrievalStep` forwards it automatically once `clarification_enabled: true`
is set — you do **not** need to also flip `capabilities.supports_session_tracking`
(that's a separate, unrelated capability, and every shipped intent adapter leaves
it `false`). Just make sure your client sends a stable `X-Session-ID` across turns
(OrbitChat already does this — one UUID per conversation).

## 2. Start the server and create an API key

```bash
python3 server/main.py
# in another shell:
./bin/orbit.sh key create --adapter intent-sql-postgres --name "Clarification test"
```

```bash
export ORBIT_KEY=<the-key-just-created>
export SID=clarify-test-1
```

## 3. Disambiguation — two similar templates, low gap

Ask something vague enough that two templates score close together in the
`[confidence_threshold, clarification_high_threshold)` band. The right phrasing
depends on your template library and embedding provider — start from a query in
`examples/intent-templates/sql-intent-template/postgres/customer-orders/*_test_queries.md`
and vague it up (drop specifics like an exact date range or customer name) until it's
ambiguous between two templates instead of a clean top match.

**Known-ambiguous pair on `intent-sql-postgres`:** `find_high_value_orders_time_period`
and `find_high_value_orders` (`customer_orders_templates.yaml`) share an `nl_example`
verbatim ("Find expensive orders above $1000") and differ only in whether a time
window is present — a query that states neither an amount nor a time period should
land both templates close together:

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $ORBIT_KEY" \
  -H "X-Session-ID: $SID" \
  -d '{"message": "show me expensive orders"}' | jq
```

A second pair to try if the first doesn't land ambiguous on your embedding model:
`find_order_by_customer_name` vs. `find_order_by_customer_name_recent` — ask
`"what did John Smith order?"` (no time window stated).

If neither lands in the ambiguous band as-is, check the actual candidate scores via
the Test Query panel (`POST /admin/adapters/intent-sql-postgres/test-query`, Phase 1B)
before troubleshooting further — score placement depends on your `embedding_provider`.

**Expected:** the `response` text lists 2–3 numbered candidate descriptions and asks
"which did you mean?" — not an executed query result. Server log shows the retriever
resolving to `clarify_disambiguate` (check `/metrics`, step 6).

Answer on the **same session** to resume:

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $ORBIT_KEY" \
  -H "X-Session-ID: $SID" \
  -d '{"message": "the first one"}' | jq
```

**Expected:** it executes the pinned template from the earlier candidate list
("1.", "first", "one", or the template's id/keyword in your answer all match —
see `_match_disambiguation_choice` in `intent_sql_base.py`) — a real result, not
another clarification question.

## 4. Slot-fill — missing a required parameter

Ask something that clearly matches one high-confidence template but omits a
required parameter (e.g. a query template that requires a date range or customer
identifier, asked without one).

**Known-working query on `intent-sql-postgres`:** stating the time window (which
`find_high_value_orders_time_period` needs to distinguish itself from
`find_high_value_orders`) pushes similarity `>= clarification_high_threshold`,
but omitting the required `min_amount` triggers slot-fill instead of executing:

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $ORBIT_KEY" \
  -H "X-Session-ID: $SID-slotfill" \
  -d '{"message": "show me high value orders from the last 30 days"}' | jq
```

**Expected:** a question naming the missing parameter(s) ("could you tell me:
the minimum order amount?"), not an error and not a fallback to a worse-matching
template.

Answer it on the same session (fills in `min_amount`):

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $ORBIT_KEY" \
  -H "X-Session-ID: $SID-slotfill" \
  -d '{"message": "500"}' | jq
```

**Expected:** it executes with `min_amount: 500` and the previously-stated 30-day
window merged in — a real result. If your answer is still ambiguous/unparseable
instead, it re-asks (bumping the internal round counter) up to
`clarification_max_rounds`, then gives up with a plain "I still couldn't get all
the information I need" message.

## 4b. Alternate adapter — HR SQLite (`intent-sql-sqlite-hr`)

If `intent-sql-postgres` doesn't reliably land in the ambiguous/missing-param
bands for you (real data + your LLM's parameter extraction can make it too good
a match), `config/adapters/hr.yaml`'s `intent-sql-sqlite-hr` has an even more
reliable setup: `examples/intent-templates/sql-intent-template/sqlite/hr/hr-templates.yaml`
has **four near-identical templates** that differ only by comparison word, all
requiring a numeric salary parameter with no default:

| Template id | `nl_examples` |
|---|---|
| `find_employees_earning_at_least` | "Who earns at least 100000?" |
| `find_employees_earning_exactly` | "Who earns $45000?" |
| `find_employees_earning_less_than` | "Who earns less than 50000?" |
| `find_employees_earning_more_than` | "Who earns more than 50000?" |

`hr.db` has real salary data (range $42,000–$282,000, average ≈$99,449) and
departments (Engineering, Sales, Marketing, Human Resources, Finance,
Operations) so follow-up answers resolve to real results.

```bash
./bin/orbit.sh key create --adapter intent-sql-sqlite-hr --name "Clarification test (HR)"
export HR_KEY=<the-key-just-created>
```

**Slot-fill — confirmed working (OrbitChat, `gpt-oss:120b` + `nomic-embed-text`):**

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $HR_KEY" \
  -H "X-Session-ID: hr-slotfill-1" \
  -d '{"message": "who earns a certain salary amount"}' | jq
```

This vague phrasing scored `>= clarification_high_threshold` against
`find_employees_earning_at_least` specifically (not a tie among the four —
its "at least" framing apparently reads as the generic default for an
unqualified salary question), so it went straight to slot-fill instead of
disambiguating: **"I can help with that — could you tell me: Minimum salary
amount?"**

Answer it (a dollar-formatted, comma-free amount works fine — parameter
extraction handles `"$100000"`):

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $HR_KEY" \
  -H "X-Session-ID: hr-slotfill-1" \
  -d '{"message": "$100000"}' | jq
```

**Expected:** resumes against the pinned template and returns real rows —
"Employees earning CAD $100,000 or more" with actual employee names,
departments, and salaries from `hr.db`. Verified end-to-end through OrbitChat
(not just curl): the clarifying question rendered as a normal streamed
assistant message, and the follow-up correctly resumed rather than
re-matching from scratch.

**Disambiguation** — the query above landed the top template *above*
`clarification_high_threshold`, so the ambiguity-gap check (which only
applies inside `[confidence_threshold, clarification_high_threshold)`) never
got a chance to fire. To reliably see disambiguation instead of slot-fill on
this exact query, temporarily raise the ceiling so the same vague phrasing
now falls *inside* that band:

```yaml
# config/adapters/hr.yaml, intent-sql-sqlite-hr's config: block — temporary, for this test only
clarification_high_threshold: 0.95
```

Restart the server, then re-run the same query on a fresh session:

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $HR_KEY" \
  -H "X-Session-ID: hr-clarify-1" \
  -d '{"message": "who earns a certain salary amount"}' | jq
```

**Expected:** now a disambiguation question listing 2–3 of the four salary
templates by description, since none clears the raised bar outright. Resume
it the same way as the customer-orders example:

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $HR_KEY" \
  -H "X-Session-ID: hr-clarify-1" \
  -d '{"message": "the first one"}' | jq
```

Set `clarification_high_threshold` back to `0.65` (or remove it to fall back
to the default) once you're done — the raised value is only useful for
forcing this demo, not a setting you want in a real deployment.

## 5. Round cap and TTL

- **Round cap:** on the slot-fill flow above, reply with nonsense
  (`"I don't know"`) `clarification_max_rounds` times in a row on the same
  session. **Expected:** after the last round it stops asking and returns the
  giveup message instead of looping forever.
- **TTL:** trigger a clarification, wait longer than `clarification_ttl_seconds`
  (or lower it to `5` temporarily for a fast check), then answer. **Expected:**
  the pending state has expired — the answer is treated as a fresh query
  (probably `no_matching_template`/`below_threshold`) instead of resuming.

## 6. Confirm it's non-streaming-safe

This exercises the P1 review fix — before it, a clarification response on
`/v1/chat` (non-streaming) crashed with an HTTP 500 instead of returning the
question. Confirm the JSON above has no `error` key and a normal 200 status
(`curl -i` to see the status line, or `-w '\n%{http_code}\n'`).

## 7. Metrics

```bash
curl -s http://localhost:3000/metrics | grep orbit_intent_template_matches_total
```

**Expected:** entries with `outcome="clarify_disambiguate"` and/or
`outcome="clarify_slot_fill"` after steps 3–4, alongside the existing
`executed`/`no_match`/etc. outcomes from Phase 4.

## 8. Backward-compatibility check

Set `clarification_enabled: false` (or remove it) and repeat the same vague/
missing-parameter queries from steps 3–4. **Expected:** the old behavior —
either the best-effort top template executes anyway, or a flat
`"I found potential matches but couldn't extract the required information"` /
`"...none met the confidence threshold"` fallback — never a clarifying question.
This is what the eval-harness regression check (`server/tests/intent_eval/`)
verifies: `clarification_enabled: false` leaves matching byte-identical to Phase 4.

## 9. OrbitChat UI

1. Point OrbitChat at an API key for `intent-sql-postgres` and open a new chat.
2. Send the same vague query from step 3. The assistant's reply should read as a
   clarifying question with numbered options — respond in the same conversation
   ("the first one" / "the second one") and confirm it answers with real data
   instead of asking again or re-running the original vague match.
3. Repeat with the slot-fill query from step 4 — answer with just the missing
   value (e.g. "500") and confirm it resolves.
4. Because OrbitChat streams over SSE and keeps one session ID per conversation
   automatically, no extra client-side setup is needed — this is really testing
   that the resume path (P2 fix) works with a real UI client, not just curl with
   a manually-repeated `X-Session-ID`.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| Never see a clarifying question, even for clearly ambiguous/incomplete queries | `clarification_enabled` not set (or `false`) on the adapter's `config:` block. |
| Clarification question appears, but the follow-up turn re-matches from scratch instead of resuming | Client isn't sending the same `X-Session-ID` on both turns, or `clarification_ttl_seconds` expired between them. |
| Non-streaming `/v1/chat` returns `{"error": ...}` for a clarification | You're on a build before the P1 fix in `services/pipeline_chat_service.py` — check `git log` for the "non-streaming clarification" fix, or verify `context.metadata["intent_clarification"]` is set by `IntentClarificationStep`. |
| Streaming client (OrbitChat, `/v1/chat` SSE) shows "No response received from the server" for a clarification | You're on a build before the `process_chat_stream` ordering fix — `context.has_error()` (true for any `is_blocked` context) used to `return` before the dedicated blocked-response handling ever ran. Verify the guard reads `if context.has_error() and not context.is_blocked:` in `pipeline_chat_service.py`. |
| Disambiguation never triggers, only slot-fill or flat fallback | Your test query doesn't land two templates close together in `[confidence_threshold, clarification_high_threshold)` — try lowering `clarification_ambiguity_gap`'s effective window by narrowing `clarification_high_threshold`, or pick a genuinely more ambiguous phrasing. |
| Slot-fill never triggers | The top template's similarity needs to be `>= clarification_high_threshold` — a query that's too vague lands in the low/mid band instead (executes with `low_confidence: true`, or disambiguates). |

## Unit tests

```bash
# From repo root:
venv/bin/python -m pytest server/tests/test_retrievers/test_intent_clarification.py -v
venv/bin/python -m pytest server/tests/test_services/test_pipeline_chat_service_clarification.py -v
venv/bin/python -m pytest server/tests/test_pipeline_steps/test_context_retrieval_clarification_session.py -v
```

Covers: confidence-band classification, disambiguation/slot-fill response
building, the pending-clarification store's TTL/round bookkeeping, resume with
a changed/removed template, the non-streaming blocked-response fix (P1),
`session_id` forwarding to a `clarification_enabled` retriever independent of
`supports_session_tracking` (P2), and the streaming blocked-response ordering
fix that made a clarification reach OrbitChat/SSE clients at all.
