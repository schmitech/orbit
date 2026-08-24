# Example 15: Intent Clarification — Disambiguation & Slot-Filling

**Level 5 · Advanced / production**

By default, an intent adapter does its best with whatever it's given: if two templates
are a close match, it silently picks one; if a required piece of information is
missing, it either falls back to a flat "couldn't extract the required information"
message or, in some cases, just tries the next-best template instead. That's fine for
a clean demo query, but real users are vague. This example turns on **graceful
degradation** — the adapter asks a clarifying question instead of guessing wrong or
giving up, and resumes correctly when you answer it on the next turn.

This walks through it against the HR SQLite example (`examples/intent-templates/sql-intent-template/sqlite/hr/`),
configured as the `intent-sql-sqlite-hr` adapter in `config/adapters/hr.yaml` — the
same adapter used in [SQL Database (SQLite)](sql-database-sqlite.md). Everything here
also applies to `intent-sql-postgres`, `intent-duckdb-analytics`, and any other adapter
built on the SQL/DuckDB intent retriever family (see the note at the end for which
adapters don't support this yet).

### How it works

Two situations trigger a clarifying question instead of a normal answer:

- **Disambiguation** — the top two candidate templates score close together, and
  neither clearly wins. Instead of guessing, the adapter lists the top few candidates
  and asks which one you meant.
- **Slot-filling** — one template clearly wins, but a required parameter (an amount,
  a date, a name) wasn't in your message. Instead of failing outright, the adapter
  asks for just that missing piece.

In both cases, the question streams back as a normal assistant message — no error, no
partial guess. Answer it on the **same conversation** and the adapter resumes against
the exact template it was already leaning toward, merging in whatever you already
said, instead of re-matching your answer from scratch.

This is off by default. Turning it on is a handful of `config:` keys on the adapter —
no code changes, no new endpoints.

### 1. Enable it on the adapter

`config/adapters/hr.yaml`'s `intent-sql-sqlite-hr` already ships with it configured:

```yaml
config:
  confidence_threshold: 0.4
  ...
  clarification_enabled: true          # ← turns this feature on (default: false)
  clarification_high_threshold: 0.65    # confidence needed to execute directly
  clarification_ambiguity_gap: 0.05     # how close the top two candidates must be to disambiguate
  clarification_max_rounds: 2           # slot-fill re-asks before giving up
  clarification_ttl_seconds: 300        # how long a pending question stays resumable
```

These are the same kind of retriever-level setting as `confidence_threshold` — plain
keys under the adapter's `config:` block, not `capabilities:`. If you're setting this
up on your own adapter, that's the only thing to add.

Resuming across turns needs one more thing: a stable session id from your client.
OrbitChat already sends one UUID per conversation automatically, so nothing to do
there. If you're testing with `curl`, reuse the same `X-Session-ID` on both requests.

### 2. Start the server and create an API key

```bash
./bin/orbit.sh start
./bin/orbit.sh key create --adapter intent-sql-sqlite-hr --name "Clarification example"
```

```bash
export ORBIT_KEY=<the-key-just-created>
export SID=clarify-example-1
```

### 3. Trigger slot-filling

`hr-templates.yaml` has four salary-lookup templates that differ only by comparison
word — "at least," "exactly," "less than," "more than" — each requiring a numeric
salary parameter with no default. Ask a vague version of one of them, with no number:

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $ORBIT_KEY" \
  -H "X-Session-ID: $SID" \
  -d '{"message": "who earns a certain salary amount"}' | jq -r '.response'
```

**Expected:** a clarifying question naming what's missing, e.g. *"I can help with
that — could you tell me: Minimum salary amount?"* — not an error, and not a guess.

<!-- MEDIA: screenshot | intent-clarification/slot-fill-question | OrbitChat showing the slot-fill clarifying question asking for a minimum salary amount -->
> 🖼️ **Screenshot placeholder:** OrbitChat showing the slot-fill clarifying question.
> _(To be added — see [`_media-todo.md`](_media-todo.md))_

Answer it on the **same session** — the amount can be loosely formatted:

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $ORBIT_KEY" \
  -H "X-Session-ID: $SID" \
  -d '{"message": "$100000"}' | jq -r '.response'
```

**Expected:** a real, executed result — employees earning $100,000 or more, with
names, departments, and salaries from `hr.db`. Nothing was re-matched from scratch;
the adapter resumed the exact template it had already picked and merged in the amount
you just gave it.

<!-- MEDIA: screenshot | intent-clarification/slot-fill-resolved | OrbitChat showing the resolved query result after answering the slot-fill question -->
> 🖼️ **Screenshot placeholder:** OrbitChat showing the resolved result table after answering.
> _(To be added — see [`_media-todo.md`](_media-todo.md))_

### 4. Trigger disambiguation

Disambiguation only fires when the top candidate's confidence lands *below*
`clarification_high_threshold` but the top two are close together — a genuinely vague
query, not a clear match missing one detail. Depending on your embedding model, the
salary query above may resolve directly to one template (as in step 3) rather than
tying. To see disambiguation reliably, either:

- **Try a different vague query** that doesn't lean toward one template's wording —
  e.g. something that could equally match `find_employees_earning_at_least` or
  `find_employees_earning_more_than` without their distinguishing phrase.
- **Or temporarily raise the ceiling** so the same query from step 3 falls inside the
  ambiguous band instead of clearing it outright:

  ```yaml
  # config/adapters/hr.yaml — temporary, for this demo only
  clarification_high_threshold: 0.95
  ```

  Restart the server, then re-run the step-3 query on a fresh session. **Expected:** a
  question listing 2–3 candidate templates by description instead of a single
  slot-fill question. Set the threshold back to `0.65` afterward.

Answer a disambiguation question by number, ordinal word, or a keyword from the
template's own description ("1", "the second one", or a word from its listed name
all resolve):

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $ORBIT_KEY" \
  -H "X-Session-ID: $SID" \
  -d '{"message": "the first one"}' | jq -r '.response'
```

**Expected:** it executes the template you pointed at — a real result, not another
question.

### 5. What happens if you never answer, or answer too vaguely

- A pending clarification only survives `clarification_ttl_seconds` (5 minutes by
  default). Answer later than that and it's treated as a brand-new query instead of a
  resume.
- If your slot-fill answer is still unusable, the adapter re-asks — up to
  `clarification_max_rounds` times — before giving up with a plain "I still couldn't
  get all the information I need for that request" message, rather than looping
  forever.

### Where the outcome shows up

Every clarification is also recorded to the same Prometheus metric from
[Intent Adapter Observability](intent-observability.md):

```bash
curl -s http://localhost:3000/metrics | grep orbit_intent_template_matches_total
```

Look for `outcome="clarify_disambiguate"` and `outcome="clarify_slot_fill"` alongside
the usual `executed`/`no_match`/`below_threshold` outcomes — so a rising clarification
rate for one adapter is as visible as a rising miss rate, and just as good a signal
that a template needs a clearer `nl_example` or a required parameter needs a sensible
default.

### What this doesn't cover

- Only the SQL/DuckDB intent retriever family supports this today (`intent-sql-*`,
  `intent-duckdb-*` — SQLite, PostgreSQL, DuckDB). HTTP-family adapters (MongoDB,
  Elasticsearch, GraphQL, plain HTTP, Firecrawl, agent-tool retrievers) don't have it
  yet — setting `clarification_enabled: true` on one of those has no effect.
- Resume state is in-memory and per-server-process — it doesn't survive a restart,
  and won't work if your deployment load-balances the same session across multiple
  server instances without sticky routing.
- There's no UI to browse currently-pending clarifications the way the Misses panel
  lets you browse misses — a pending question just lives in the conversation until
  it's answered, expires, or the round cap is hit.

---

[Tutorial home](../tutorial.md) | [Previous: Example 14: Intent Adapter Observability](intent-observability.md) | [Next: Creating API Keys](creating-api-keys.md)

---
