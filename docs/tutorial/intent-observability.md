# Example 14: Intent Adapter Observability — Metrics & Misses

**Level 5 · Advanced / production**

Everything so far has been about getting an intent adapter to answer correctly. Once it's live, you need a different question answered: *what is it failing on, right now, in production* — without babysitting logs or guessing which query to test next. This example wires up the two pieces that answer that: Prometheus metrics for every match attempt, and a running "Misses" list of the queries that didn't match, both surfaced in the admin panel.

This walks through it against the Postgres customer-orders example (`examples/intent-templates/sql-intent-template/postgres/customer-orders/`), configured as the `intent-sql-postgres` adapter in `config/adapters/customer-orders.yaml` — but everything here applies to any intent adapter (SQL, HTTP, GraphQL, MongoDB, Elasticsearch, Firecrawl, Agent, or Composite).

### How it works

- **On demand:** the [Test Query](../template-diagnostics.md) panel you may already know from earlier tutorials — pick one query, see exactly how it matched, right now.
- **Passive, from real traffic:** every chat request against an intent adapter reports its outcome (matched, below threshold, no match, parameter extraction failed, query guard rejected...) to two places automatically, no extra config:
  1. Prometheus counters/histograms under `orbit_intent_*`, exposed at the existing `/metrics` endpoint.
  2. An in-memory "misses" store, surfaced as a **Misses** panel in the admin panel's Adapters tab, next to Test Query.

Neither requires the adapter to do anything special — this is instrumentation on the shared intent-retrieval code path, not a per-adapter setting.

### 1. Confirm the adapter is running

Make sure your Postgres connection details are set (`.env` or environment) and the adapter is enabled, then start the server:

```bash
./bin/orbit.sh start
```

Confirm it loaded:

```bash
curl -s http://localhost:3000/admin/adapters/info -H "Authorization: Bearer <admin-token>" | jq '.[] | select(.name=="intent-sql-postgres")'
```

See [Template Diagnostics → Getting the Admin Token](../template-diagnostics.md#getting-the-admin-token) if you don't have `<admin-token>` yet.

### 2. Ask a question that should match

Open **Admin Panel → Adapters → `intent-sql-postgres` → Test Query**, and run one of the example questions from `demo-questions.md`, e.g. *"Show me orders above $500 in the last 30 days."*

<!-- MEDIA: screenshot | intent-observability/test-query-match | Test Query panel showing a matched template, similarity score, and rendered SQL for a customer-orders question -->
> 🖼️ **Screenshot placeholder:** Test Query panel showing a matched template and rendered SQL.
> _(To be added — see [`_media-todo.md`](_media-todo.md))_

### 3. Trigger a miss, then check the Misses panel

Ask something clearly outside the domain — *"What's the weather like in Paris?"* — either through the same Test Query box, or as a real chat message against a key bound to this adapter. It should come back as a `no_match`/`below_threshold` result rather than a matched template.

Open the **Misses** panel (next to Test Query, same adapter). Your off-domain question should appear, most recent first, along with the reason and the closest candidates it considered.

<!-- MEDIA: screenshot | intent-observability/misses-panel | Misses panel listing an off-domain query with its reason and candidate scores -->
> 🖼️ **Screenshot placeholder:** Misses panel showing a recorded miss with candidates and a "Test in diagnostics" button.
> _(To be added — see [`_media-todo.md`](_media-todo.md))_

Click **Test in diagnostics** on that row — it jumps back to the Test Query panel with the exact query prefilled and re-run, so you can iterate on a fix (a new `nl_example`, a lower threshold, a new template) without retyping anything. Reopening the Misses panel later refreshes the list, so anything recorded while it was closed shows up too.

> The misses store is in-memory and process-local — it resets on server restart. It's for "what's been happening since I last looked," not a durable audit log.

### 4. Check the Prometheus metrics

```bash
curl -s http://localhost:3000/metrics | grep orbit_intent
```

You should see, among others:

```
orbit_intent_template_matches_total{adapter="intent-sql-postgres",template_id="orders_above_amount",outcome="executed"} 1
orbit_intent_template_matches_total{adapter="intent-sql-postgres",template_id="none",outcome="below_threshold"} 1
orbit_intent_confidence_bucket{adapter="intent-sql-postgres",le="0.9"} 1
orbit_intent_rows_returned_sum{adapter="intent-sql-postgres",template_id="orders_above_amount"} 12
```

`outcome` is what you'd alert or dashboard on — a rising `no_match`/`below_threshold` rate for one adapter is a signal to go add `nl_examples` or a new template, well before a user complains. See [Template Diagnostics → Production Observability](../template-diagnostics.md#production-observability-metrics--misses) for the full metric reference, including the row-cap and query-guard-rejection counters.

### 5. (Optional) Record feedback to grow the eval corpus

If you've reviewed a miss and know which template *should* have matched, record that verdict via the API:

```bash
curl -X POST "http://localhost:3000/admin/adapters/intent-sql-postgres/feedback" \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"verdict": "no_match_expected", "expected_template_id": null}'
```

There's no submission UI for this yet — see [Template Diagnostics → `POST .../feedback`](../template-diagnostics.md#post-adminadaptersadapter_namefeedback) for the full field reference and how this feeds the `server/tests/intent_eval/` corpus.

### What this doesn't cover

- No sampled per-request trace persisted to the audit database yet — for deep per-request detail, use Test Query on demand.
- No per-pipeline-stage timing metric in production (only Test Query's `timing` block has that).
- Feedback is recorded but not yet auto-applied to the eval corpus — a human still reviews it and hand-adds entries.

---

[Tutorial home](../tutorial.md) | [Previous: Example 13: Customer 360 — Cross-Adapter Composition](customer-360-cross-adapter.md) | [Next: Example 15: Intent Clarification](intent-clarification.md)

---
