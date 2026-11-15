# SQL Connection-Layer Dedup & Firecrawl Reconciliation — Follow-up Plan

## Summary

Split out from `docs/roadmap/complete/retrievers-implementations-cleanup.md`
(2026-11-15) as its two remaining open items once everything else in that
plan (Phases 1, 2, 3's retry-loop half, 5, 6) was completed. Both items were
left deliberately unimplemented there because, unlike the rest of that plan,
each needs an explicit product/design decision and new test infrastructure
before any code should move — not because they're low priority, but because
rushing them risks a real behavior change in production DB connectivity or
Firecrawl query handling.

This doc's Item 1 was corrected again on 2026-11-15 against an external
review that checked the current code and found the SQL lifecycle
investigation had a load-bearing gap (it hadn't established which
connection-management methods are actually reachable in production vs. only
exercised by tests), an inaccurate MySQL-vs-Postgres capability-gap
comparison, and an overstated "near-identical" characterization of the four
backends' health checks. Item 2 was corrected with a confirmed sixth
behavioral difference (empty-formatter-result handling) and an explicit,
enumerated test-matrix list. All four corrections were verified by reading
the actual code, not taken on the review's word alone — see the per-section
notes below for what changed and why.

---

## Item 1 — Cross-hierarchy SQL connection duplication (`intent/` vs `relational/`)

**Status: not started.** Investigated 2026-11-15 as the original plan's
"Phase 4"; investigated further 2026-11-15 against an external review that
caught a load-bearing gap in the first investigation — see "Lifecycle audit"
below, now the first concrete deliverable before any mixin design.

### Lifecycle audit (do this first — corrected from external review)

The first pass at this item treated `create_connection()`/`_close_connection()`
on the `intent/*` SQL retrievers as active lifecycle methods worth
deduplicating. That's wrong, confirmed by reading the actual call paths:

- `IntentSQLRetriever.close()` (`base/intent_sql_base.py:1664-1677`)
  explicitly does **not** close the DB connection, with a comment that
  database connections are managed by the datasource registry with
  reference counting, and closing one here would break other adapters
  sharing the same datasource.
- `BaseSQLDatabaseRetriever.execute_query`/`test_connection`
  (`base/base_sql_database.py:264-349`) source `self.connection` via
  `_ensure_datasource_initialized()` → `self._datasource.get_connection()`;
  reconnection on error also goes through `self._datasource.get_connection()`
  (line 343), never through `create_connection()`.
- Grepping the whole server tree for `.create_connection(` /
  `._close_connection(` calls: in production code, these are called **only**
  in `relational/mysql_retriever.py:142` and
  `relational/postgresql_retriever.py:127`. Every other call site (DuckDB,
  SQLite intent variants, `query_guard` e2e) is in `tests/`. So for the
  `intent/*` SQL retrievers, `create_connection()`/`_close_connection()` are
  **dead code in production** — never invoked outside tests.
- `datasources/implementations/relational/postgres_datasource.py` already
  implements its own full connection pooling (`psycopg_pool.ConnectionPool`,
  `getconn`/`putconn`, health check, pool close), independent of and
  parallel to `intent_postgresql_retriever.py`'s own retriever-level
  pooling. There may be two pooling layers active for Postgres today, not
  zero-vs-one as the first pass assumed.

**Implication**: before designing any shared connection mixin, first
establish — per backend, by tracing actual call sites, not by reading
method names — which of `create_connection()`/`_close_connection()`/the
retriever-level liveness checks are reachable in production at all. The
right fix for the `intent/*` variants may be **deleting unreachable
dead code** (methods tests exercise but production never calls) rather than
extracting it into a shared mixin. Do this audit, backend by backend, as
its own deliverable before touching the mixin design below.

### What's actually duplicated (and what isn't)

The original premise — "start with SQLite, the simplest, then Postgres,
then MySQL" — doesn't hold:

- `implementations/relational/sqlite_retriever.py` has **no**
  `create_connection()` at all. It's purely datasource-registry-based: the
  connection is injected by the registry, not self-managed. There is no
  connection-creation duplication to extract for SQLite.
- `implementations/intent/intent_sqlite_retriever.py`, by contrast, manages
  its own raw `sqlite3.connect()`, its own liveness check, and its own
  close/rollback logic — though per the lifecycle audit above, it's an open
  question whether that connect/close logic is even reachable in production
  rather than only exercised by tests.
- So the `intent/` vs `relational/` split isn't "two copies of the same
  logic" for SQLite — it's two different connection-management
  *architectures* for the same backend.

The real duplication is in **Postgres and MySQL**, where both `intent/` and
`relational/` variants do hand-roll their own `psycopg.connect()` /
`mysql.connector.connect()`, liveness checks, and commit/rollback — but
they are not behaviorally identical, and the gap is not symmetric between
the two backends (corrected from external review — see below).

**Postgres**:

- `implementations/intent/intent_postgresql_retriever.py` (`create_connection`
  L59-122, `_execute_raw_query` L144-168) adds connection pooling via
  `psycopg_pool`, an `_is_connection_alive()` check before every query, and
  pool-aware `_close_connection()` — modulo the lifecycle-audit caveat above
  about whether this path is actually reached in production.
- `implementations/relational/postgresql_retriever.py` (`create_connection`
  L47-73, `_execute_raw_query` L83+) has none of that — no retriever-level
  pooling, no liveness check before each query (though its *datasource*,
  `postgres_datasource.py`, has its own independent pooling — see the
  lifecycle audit above).

**MySQL** — not the "same capability gap" as Postgres (corrected from
external review: the original description of this pair was inaccurate).
`intent_mysql_retriever.py` has **neither** a Postgres-style
`_is_connection_alive()` liveness check **nor** retriever-managed pooling —
confirmed by grep, zero matches for either in that file. What actually
differs between the two MySQL variants:

- `intent_mysql_retriever.py` has `ssl_disabled`/`use_ssl` config
  (lines 32, 66-67), `autocommit` handling (lines 33, 63, 105, 110), and
  `dictionary=True` cursors (lines 72, 94) — none of which
  `relational/mysql_retriever.py` has.
- `relational/mysql_retriever.py` has a PyMySQL fallback (tries
  `mysql.connector` first, falls back to
  `pymysql.connect(..., cursorclass=pymysql.cursors.DictCursor)`) that the
  intent variant lacks entirely.
- Any reconciliation must preserve these explicitly, for whichever paths
  remain supported — autocommit semantics, SSL options, dict-cursor
  behavior, and the PyMySQL fallback are each a real capability difference,
  not incidental duplication to collapse away.

Also worth correcting (from an earlier draft of this item): `IntentSQLRetriever`
and `BaseSQLDatabaseRetriever` are **not** "two unrelated base contracts" —
`IntentSQLRetriever` already extends `BaseSQLDatabaseRetriever` directly
(`base/intent_sql_base.py:27`). The duplication is in the *driver-specific*
`create_connection`/`_execute_raw_query` bodies within that shared hierarchy,
not a split between disconnected class trees. And `relational/postgresql_retriever.py`
already resolves `sslmode` from config and passes it to the connection call
(line 28/57) — an earlier draft's claim that it lacks SSL support the
`intent/` variant has is wrong.

### The four `_is_connection_alive`/health-check implementations are not near-identical

An earlier draft of this item described the SQL-backend liveness checks as
one duplicated pattern worth a single shared helper. Corrected from external
review: reading all four confirms they're genuinely different
implementations, not copies:

- **Postgres** (`intent_postgresql_retriever.py:128-140`): checks
  `self.connection.closed`, then opens a cursor, runs `SELECT 1`, closes the
  cursor.
- **DuckDB** (`intent_duckdb_retriever.py:149-157`): no cursor at all —
  `self.connection.execute("SELECT 1").fetchone()` directly.
- **Athena** (`intent_athena_retriever.py:60-70`): opens a cursor, executes,
  `fetchone()`, closes the cursor.
- **SQLite** (`intent_sqlite_retriever.py:106-116`): opens a cursor,
  executes, but does **not** fetch, then closes the cursor.

Any consolidation must either keep these as backend-specific hooks (a
shared *interface*, not shared *implementation*), or explicitly normalize
the differences (cursor vs. no cursor, fetch vs. no fetch) and add tests
proving the normalized version behaves the same as each backend's current
check for a live connection, a cleanly closed connection, and a connection
that's open but failing. Don't assume normalization is free — a fetch where
none existed before, or vice versa, can change error timing/type on a
broken connection.

### Why this is a different risk class than the work already done

Phases 1, 2, 3 (retry loop), 5, and 6 of the original plan were all pure
logic changes, unit-testable without a live database or HTTP server, and
each shipped with regression tests. This item is different:

- Unifying the Postgres/MySQL `intent/`/`relational/` variants means either
  (a) adding connection pooling to the `relational/` variant — a real
  behavior change, not a pure dedup — or (b) building a mixin where pooling
  is optional, which needs the pooling question decided explicitly up front,
  not inferred mid-refactor.
- It touches production database connectivity (reconnection behavior,
  transaction/commit-rollback semantics, connection shutdown) for every SQL
  backend in use.
- No reconnection/transaction/shutdown test harness exists yet for these
  retrievers — today's tests are smoke-level ("connects successfully"), not
  behavior tests for a dropped connection or a rollback mid-transaction.

### If picked up later

1. **Do the lifecycle audit first** (see above) for every backend, not just
   Postgres/MySQL: confirm, by tracing actual call sites rather than
   reading method names, which connection-management code is reachable in
   production vs. only exercised by tests. Remove or clearly mark dead code
   before designing anything shared.
2. Re-scope the mixin work to Postgres or MySQL (not SQLite — see the
   correction above) as the starting backend, and only for the parts
   confirmed live in step 1; pick whichever is judged lower-risk.
3. Decide the pooling question explicitly before writing the mixin: does
   `relational/`'s variant gain pooling, or does `intent/`'s variant's
   pooling become optional/configurable? Also account for
   `postgres_datasource.py`'s own independent pooling found in the
   lifecycle audit — avoid ending up with two pooling layers stacked on
   top of each other. Write the decision down.
4. Build reconnection/transaction/shutdown tests for the chosen backend's
   *current* behavior first (both variants), so the extraction has a
   regression baseline before any code moves.
5. Extract one backend's connection mixin at a time — not all three/four at
   once, and do not expand a single-backend extraction into a change across
   all four health-check implementations (see the health-check section
   above). Treat the pooling/timeout/statement_timeout capability change as
   a separate, explicit step from the structural extraction: first make
   `intent/` and `relational/` share identical connection code with
   identical behavior, then decide separately (and visibly) whether one
   variant's extra capability should be added to the other. For MySQL
   specifically, preserve autocommit handling, SSL options, dict-cursor
   behavior, and the PyMySQL fallback explicitly (see the MySQL correction
   above) rather than assuming the two variants converge cleanly.
6. Once the mixin exists for a given backend, fold in that backend's
   smaller, same-shape duplications riding on it (not independent — do
   these in the same per-backend PRs as the connection-mixin extraction,
   not as a separate mechanical sweep across all backends):
   - SELECT/WITH dispatch duplicated 5x across
     `intent_postgresql_retriever.py:155-156`,
     `intent_mysql_retriever.py:101-102`,
     `intent_sqlite_retriever.py:177-178`,
     `intent_duckdb_retriever.py:221-222`,
     `intent_athena_retriever.py:102-103` — one shared `_is_select_query()`
     helper. (This one is a safe, backend-agnostic text check — lower risk
     than the connection/health-check items above, but still fold it in
     per-backend rather than as a separate sweep, to keep each PR's diff
     reviewable against one backend's behavior.)
   - `SQLQueryExecutionMixin.execute_query_with_retry`
     (`base/base_sql_database.py:177-200`) is defined but unused — every
     retriever reimplements its own retry/rollback instead of calling it;
     worth checking why it was never adopted before wiring retrievers up to
     it (may have been superseded by something else).

---

## Item 2 — Firecrawl's `_get_relevant_context_impl` reconciliation

**Status: not started**, blocked on a product decision, not an engineering
one.

`intent_firecrawl_retriever.py:212-311` was originally described (in the
source plan this was split from) as differing from the base's
`_get_relevant_context_impl` (`base/intent_http_base.py:781-978`) only in
using an async formatter. On closer comparison that's not the only
difference — confirmed by reading both implementations side by side:

- **Cancellation**: the base checks `cancel_event` before template search
  and between each template attempt (`base/intent_http_base.py:785, 814`);
  Firecrawl's version has no `cancel_event` handling at all.
- **Required-parameter checks**: the base explicitly skips a template if any
  `required` parameter is still missing after extraction
  (`base/intent_http_base.py:843-855`), with a comment explaining why
  (avoids a doomed live call with an unfilled placeholder); Firecrawl has no
  equivalent check.
- **Follow-up storage**: the base calls
  `self._store_followup_turn(kwargs.get('session_id'), ...)` on success
  (`base/intent_http_base.py:908, 920`); Firecrawl's version never calls it.
- **Failure metadata**: the base tracks `failed_templates` with per-template
  error strings and includes them in the final below-threshold/all-failed
  response metadata (`base/intent_http_base.py:811-812, 851, 862, 940-963`);
  Firecrawl tracks only `any_above_threshold` and a bare `candidates` list
  with template id + similarity, no per-template failure reasons.
- **Response-generator fallback**: the base has an entire
  `self.response_generator`-driven formatting branch
  (`base/intent_http_base.py:881-918`) that builds LLM-context content from
  a domain-aware formatter before falling back to `_format_http_results`;
  Firecrawl has no equivalent branch — it only ever calls its own async
  formatter.
- **What the formatter hook needs**: Firecrawl's call already passes
  `query=query` and `usage_sink=usage_sink` to `_format_http_results_async`
  for chunk ranking (`intent_firecrawl_retriever.py:275-282`) — any
  async-formatter hook added to the base must forward both of these, not
  just `results`/`template`/`parameters`/`similarity`.
- **Empty-formatter-result handling** (confirmed by code read, missing from
  the original five-point list above — corrected from external review):
  Firecrawl's `_get_relevant_context_impl`
  (`intent_firecrawl_retriever.py:277-289`) calls
  `return formatted_results` unconditionally after formatting — no
  emptiness check, so if the async formatter returns an empty list,
  Firecrawl returns that empty result as final output. The base's
  non-response_generator branch (`intent_http_base.py:930-933`) explicitly
  guards this: `if formatted_results: ... return formatted_results` — when
  empty, its `for` loop continues to the next template candidate instead of
  returning. Reconciling onto the base's loop structure must either
  preserve Firecrawl's "stop on first formatted result, empty or not"
  behavior deliberately (if that's wanted for scraped content) or adopt the
  base's "try the next template on an empty result" behavior explicitly —
  this is a sixth behavioral difference, not an oversight to silently fix
  either way.
- **Why Firecrawl disables `response_generator`** (confirmed, not previously
  noted): `intent_firecrawl_retriever.py:69-71` explicitly sets
  `self.response_generator = None`, with a comment that the generic
  response generator doesn't understand Firecrawl's response structure.
  That's a reasonable default to preserve rather than a gap to close — any
  reconciliation that routes Firecrawl through the base's
  `response_generator` branch needs its own explicit decision and adapter,
  not an assumption that the base's existing formatter understands scraped
  content.

### Fix, once the product decision is made

Before touching code, write down explicitly which of the six behavioral
differences above should survive consolidation:

- Cancellation and required-parameter checks are very likely bugs in
  Firecrawl's version that should simply be adopted from the base.
- Follow-up-turn storage and failed-template metadata need a product
  decision on whether Firecrawl should support follow-up questions the same
  way the other HTTP-backed retrievers do.
- The response-generator branch may or may not apply to scraped content —
  Firecrawl's current `response_generator = None` is a reasonable default;
  keep it unless there's an explicit decision and adapter to route scraped
  content through the generic formatter.
- Empty-formatter-result handling (stop vs. try-next-template) needs its own
  explicit decision, not an incidental side effect of adopting the base's
  loop structure.

Only once each of the six is explicitly kept, adopted from the base, or
deliberately dropped should the base method be extended with an
async-formatter hook (forwarding `query`/`usage_sink`) and Firecrawl
reconciled onto it. A mechanical hook-and-delete would silently change
cancellation, required-parameter, follow-up, failure-metadata, and
empty-result behavior for every Firecrawl query — don't delete Firecrawl's
override until that decision is made and the reconciliation is verified.

Needs the full no-match/below-threshold/rerank test matrix run against all
four affected retrievers (graphql, http_json, firecrawl, and the base's
direct consumers) before merging, explicitly covering (corrected from
external review — the original plan only said "test matrix" without
enumerating what it must cover):

- Cancellation mid-search (`cancel_event` set between template attempts).
- A template with a missing required parameter after extraction (should be
  skipped, not attempted).
- Follow-up-turn storage on a successful result (if adopted for Firecrawl).
- The failure envelope/metadata shape on an all-templates-failed or
  below-threshold response, including per-template failure reasons.
- `query`/`usage_sink` correctly forwarded through any new async-formatter
  hook on the base.
- Source/error-code/error-message fields in both the success and exception
  response paths — confirm Firecrawl's existing shape is preserved or the
  change to the base's shape is deliberate.
- Candidate metadata fields (template id, similarity, and whatever else
  Firecrawl's `candidates` list carries today) preserved or deliberately
  changed.
- Empty-formatter-result behavior (stop vs. continue to next template),
  alongside the existing chunking and fallback-formatting tests that must
  keep passing unchanged.
