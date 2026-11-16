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

#### Lifecycle audit results (completed 2026-11-15)

Full per-backend, per-method call-site trace across all of `server/`
(production and test code), for every backend, not just Postgres/MySQL:

| File | `create_connection` | `_close_connection` | `_is_connection_alive` | `test_connection` |
|---|---|---|---|---|
| `intent/intent_postgresql_retriever.py` | defined :59, **0 callers anywhere** | defined :170, **0 callers anywhere** | defined :128, self-called in `_execute_raw_query` :149 (production) | — (inherited) |
| `intent/intent_mysql_retriever.py` | defined :51, **0 callers anywhere** | defined :117, **0 callers anywhere** | not defined | — (inherited) |
| `intent/intent_sqlite_retriever.py` | defined :55, test-only callers (`test_intent_sqlite_retriever.py`) | defined :181, test-only callers | defined :106, self-called in `_execute_raw_query` :124 (production); also test-called | — (inherited) |
| `intent/intent_duckdb_retriever.py` | defined :61, test-only callers (18 sites in `test_intent_duckdb_retriever.py`, plus `test_query_guard_e2e.py`) | defined :224, test-only callers (19 sites) | defined :149, self-called in `_execute_raw_query` :164 (production); also test-called | — (inherited) |
| `intent/intent_athena_retriever.py` | defined :47, **0 callers anywhere** (no test file exists for Athena) | defined :129, **0 callers anywhere** | defined :60, self-called in `_execute_raw_query` :80 (production) | — (inherited) |
| `relational/postgresql_retriever.py` | defined :48, **production caller**: `initialize()` calls `await self.create_connection()` at :127 | defined :118, **0 callers anywhere** | not defined | inherited; backend supplies `get_test_query()` :79 |
| `relational/mysql_retriever.py` | defined :46, **production caller**: `initialize()` calls `await self.create_connection()` at :142 | defined :133, **0 callers anywhere** | not defined | inherited; backend supplies `get_test_query()` :94 |
| `relational/sqlite_retriever.py` | not defined | not defined | not defined | inherited; backend supplies `get_test_query()` :52 |

Key conclusions:

- **The dead-code finding is specific to `intent/*`, not `relational/*`.**
  `relational/postgresql_retriever.py` and `relational/mysql_retriever.py`
  genuinely call their own `create_connection()` from `initialize()` in
  production. It is the `intent/*` variants' `create_connection()` /
  `_close_connection()` that are unreachable from production across *every*
  backend (Postgres, MySQL, SQLite, DuckDB, Athena) — confirmed, not just
  assumed for the two originally checked.
- The only method in the `intent/*` four-method group that production code
  does reach is `_is_connection_alive()`, and only as a **self-call from
  that same class's own `_execute_raw_query()`** — never called externally,
  never called from the base class. MySQL's intent variant doesn't define
  it at all (consistent with the "MySQL has neither liveness check nor
  pooling" finding above).
- `base/base_sql_database.py`'s `execute_query()`/`test_connection()` and
  its reconnection path never call `create_connection()`; reconnection goes
  `self._datasource.close()` → `self._datasource.initialize()` →
  `self._datasource.get_connection()` (lines ~340-343). Confirms the
  original finding: the datasource registry, not retriever-level
  `create_connection()`, owns connection acquisition/reconnection for the
  shared base path.
- `BaseSQLDatabaseRetriever.test_connection()` (`base_sql_database.py:264`)
  itself has **zero callers anywhere in `server/`** — it is also unused
  dead code at the base-class level, not just at the backend level.
- `IntentSQLRetriever.close()` (`intent_sql_base.py:1665`) confirmed: does
  not call `_close_connection()`, by design — comment explains the
  datasource registry's reference-counted connections would break if closed
  here. `AbstractSQLRetriever.close()` (`base/sql_retriever.py:176`, used by
  the `relational/*` hierarchy) instead calls
  `self._datasource.return_connection()` / `self._datasource.close()` —
  also never `_close_connection()`.
- Datasource-level pooling is independent and already complete for Postgres
  and MySQL, confirming the "two pooling layers" risk: `postgres_datasource.py`
  has `get_connection()` (:92, pool `getconn`), `return_connection()` (:115,
  pool `putconn`), `health_check()` (:120), `close()` (:147, pool close).
  `mysql_datasource.py` has the equivalent set (`get_connection()` :87,
  `return_connection()` :108, `health_check()` :113, `close()` :140).
  `sqlite_datasource.py` has no pool (`health_check()` :37, `close()` :52
  only) — consistent with SQLite being non-pooled throughout.
- Athena has no test coverage at all for `create_connection`/`_close_connection`
  — not even test-only reachability, unlike DuckDB and SQLite.

**Net effect for the mixin design**: for every `intent/*` backend,
`create_connection()` and `_close_connection()` are dead in production and
exist solely for tests to drive the backend's `_execute_raw_query`/
`_is_connection_alive` logic directly. Any mixin extraction (or deletion)
must preserve `_is_connection_alive()` as the one production-reachable
piece, and must not assume `relational/*`'s `create_connection()` is
equally dead — it isn't, for Postgres and MySQL.

#### New bug found while building the MySQL regression baseline (2026-11-15, undocumented until now)

While writing `server/tests/test_retrievers/test_mysql_retriever.py`'s
`initialize()` test (plan step 4, below), reproducing the production call
path surfaced a real bug in both of the two confirmed production
`create_connection()` call sites:

- `relational/mysql_retriever.py:142` and `relational/postgresql_retriever.py:127`
  both do `self.connection = await self.create_connection()`.
- `connection` is a **read-only property** on `AbstractSQLRetriever`
  (`base/sql_retriever.py:81-92`) — a getter only; no setter is defined
  anywhere in the hierarchy.
- When the datasource has no connection to hand back yet (so
  `if not self.connection:` is true and this branch is entered),
  `create_connection()` is called and awaited successfully, but the
  subsequent assignment raises `AttributeError: property 'connection' of
  '<Class>' object has no setter` — `initialize()` crashes instead of
  storing the newly created connection.
- Confirmed via a reproducing unit test, not just by reading the code.
- Whether this was reached in real deployments depended on whether the
  Postgres/MySQL datasources always handed back a connection before
  `initialize()` ran (in which case the buggy branch was simply never
  entered) — that's a separate question from whether the code was correct.

**Fixed 2026-11-15** (explicit decision: fix now as a standalone patch,
confirmed with the user before touching production code, since this is
exactly the kind of production-behavior change this item's plan otherwise
gates on an explicit decision):

- Added a setter for `connection` on `AbstractSQLRetriever`
  (`base/sql_retriever.py`, `@connection.setter`, storing to
  `self._connection`) — a 3-line, surgical fix scoped to the one missing
  piece, not a broader property/connection-handling rewrite.
- This fixes the bug for **both** Postgres and MySQL relational retrievers
  (and any other subclass of the shared `AbstractSQLRetriever`/
  `BaseSQLDatabaseRetriever` hierarchy that assigns to `self.connection`),
  since the setter lives on the shared base class, not a MySQL-specific one.
- Regression test: `test_initialize_calls_create_connection_when_datasource_has_none`
  in `server/tests/test_retrievers/test_mysql_retriever.py` now pins the
  fixed, working behavior (`initialize()` succeeds and stores the new
  connection) instead of the crash. No equivalent Postgres-specific test was
  added — there's no existing Postgres relational test file, and adding one
  was out of scope for the MySQL-start decision; the fix's correctness for
  Postgres rests on the shared base class and the full
  `server/tests/test_retrievers/` suite (510 passed, 2 skipped) passing
  unchanged after the fix.

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

### Decisions made for the MySQL start (2026-11-15)

- **Starting backend: MySQL**, chosen explicitly over Postgres — Postgres
  carries the added complication of `postgres_datasource.py`'s own
  independent pool stacked under a pooled `intent/` retriever; MySQL has no
  such stacking to untangle.
- **Pooling question, resolved by the audit itself, not a new design
  choice**: neither `intent_mysql_retriever.py` nor
  `relational/mysql_retriever.py` implements retriever-level pooling or a
  liveness check (`_is_connection_alive` is not defined on either MySQL
  class — confirmed in the lifecycle audit above). The only pooling layer
  in play for MySQL is `mysql_datasource.py`'s independent pool
  (`get_connection()`/`return_connection()`/`health_check()`/`close()`),
  which is untouched by this work either way. So for MySQL specifically,
  step 3 below ("decide the pooling question") has no open question to
  resolve — there is nothing to add to either variant.
- What must still be preserved explicitly when reconciling the two MySQL
  variants (per the capability-gap section above): `ssl_disabled`/`use_ssl`
  config, `autocommit` handling, `dictionary=True` cursors (intent side),
  and the PyMySQL fallback (relational side).
- **Step 4 (regression-test baseline) completed 2026-11-15**:
  `server/tests/test_retrievers/test_intent_mysql_retriever.py` (10 tests)
  and `server/tests/test_retrievers/test_mysql_retriever.py` (8 tests) pin
  both MySQL variants' current connection/transaction/reconnection/shutdown
  behavior — autocommit-conditional vs. unconditional commit/rollback,
  dictionary vs. plain cursors, SSL/charset/sql_mode config forwarding,
  `_close_connection()` idempotency, the datasource-registry reconnection
  path (not `create_connection()`), and the `initialize()` read-only-property
  bug found and pinned as current behavior (see finding above). All 18 pass
  against mocked `mysql.connector` (no live MySQL server required/available
  in this environment).

**Step 5 (connection-mixin extraction) completed 2026-11-15**: explicit
decision confirmed with the user first — the shared mixin supports the
*union* of both variants' capabilities (SSL toggle, autocommit, charset,
sql_mode, dictionary cursor, PyMySQL fallback), each defaulting to that
variant's pre-extraction behavior, so neither variant's production behavior
changed silently.

- New file: `server/retrievers/base/mysql_connection_mixin.py` —
  `MySQLConnectionMixin` with `_create_mysql_connection()` and
  `_close_mysql_connection()`.
- `IntentMySQLRetriever` and `MySQLRetriever` (relational) both now mix in
  `MySQLConnectionMixin` and delegate `create_connection()`/`_close_connection()`
  to it, each passing its own existing defaults explicitly (intent:
  `ssl_disabled`/`autocommit` from config, dictionary cursor, no PyMySQL
  fallback; relational: `charset`/`sql_mode` from config, SSL always
  disabled — matching its prior behavior of never passing `use_ssl` — plain
  cursor, PyMySQL fallback allowed).
- No behavior change intended or observed: all 18 of the MySQL regression
  tests from step 4 pass unchanged against the extracted mixin, and the full
  `server/tests/test_retrievers/` suite (510 passed, 2 skipped) is unaffected.
- `ruff check` is clean for every new/touched line; pre-existing, unrelated
  lint findings in the two retriever files (`Optional[X]` vs `X | None`,
  `startswith` calls) were left alone — out of scope for this change.
### Postgres mixin extraction (completed 2026-11-15)

Explicit decision confirmed with the user first, since Postgres's pooling
situation is genuinely different from MySQL's (where the pooling question
turned out to be a non-issue): **the mixin stays pooling-agnostic**. It
extracts only what both variants genuinely share (connection-param
building, the post-connect version test query, `_is_connection_alive()`,
pool-aware vs. plain close), as configurable options — it does not itself
decide whether a given retriever pools. `intent/` keeps choosing to pool
(via `use_connection_pool`, using `psycopg_pool`) exactly as before
extraction; `relational/` stays unpooled exactly as before. The double
independent-pooling-layer risk the lifecycle audit flagged
(`postgres_datasource.py`'s own pool, separate from `intent/`'s
retriever-level pool) is **not resolved** by this change — it's explicitly
left as-is, same risk as before, not made worse or better.

- New file: `server/retrievers/base/postgresql_connection_mixin.py` —
  `PostgreSQLConnectionMixin` with `_create_postgresql_connection()`
  (handles both the pooled and unpooled paths via a `use_pool` flag),
  `_is_postgresql_connection_alive()`, and `_close_postgresql_connection()`
  (pool-aware vs. plain, via the same flag).
- `IntentPostgreSQLRetriever` now mixes it in and passes
  `use_pool=self.use_connection_pool`, `autocommit=False` (only applied on
  the unpooled path, matching its pre-extraction behavior of forcing
  `connection.autocommit = False` only when not pooling),
  `statement_timeout`, and `pool_size`. `_is_connection_alive()` and
  `_close_connection()` both now delegate to the mixin.
- `PostgreSQLRetriever` (relational) now mixes it in and passes
  `use_pool=False` unconditionally, with no `autocommit` argument (so the
  mixin never touches `connection.autocommit` for this variant, matching
  its pre-extraction behavior of never setting it at all).
- Regression tests added (no prior retriever-level Postgres tests existed):
  `server/tests/test_retrievers/test_intent_postgresql_retriever.py` (11
  tests covering pooled/unpooled connection creation, pool reuse, liveness
  checks, commit/rollback, pool-aware vs. plain close) and
  `server/tests/test_retrievers/test_postgresql_retriever.py` (5 tests,
  confirming the relational variant never pools, never touches
  `autocommit`, and that `initialize()`'s read-only-property bug fix
  from the MySQL work applies here too, since the fix lives on the shared
  `AbstractSQLRetriever` base).
- All 16 new tests pass; full `server/tests/test_retrievers/` suite (526
  passed, 2 skipped — up from 510 before this addition) is unaffected.
  `ruff check` is clean for every new/touched line in the mixin and new
  test files; pre-existing, unrelated lint findings in the two retriever
  files were left alone, same as the MySQL work.

**Corrected 2026-11-15, after independent review of this extraction found
two real issues** (both confirmed, not taken on the review's word alone):

1. **Dependency-entanglement regression (fixed)**: the first version of
   `postgresql_connection_mixin.py` imported `psycopg` and `psycopg_pool` in
   a single combined `try`/`except` block, so if `psycopg_pool` was merely
   absent (e.g. `psycopg[binary]` installed without the `pool` extra), the
   `except` set `psycopg = None` too — breaking the *unpooled* relational
   path even though it never needed `psycopg_pool` at all, and never had
   before this extraction. Fixed: `psycopg`/`dict_row` and `psycopg_pool`
   are now imported in separate `try`/`except` blocks, and
   `_create_postgresql_connection()` only requires `psycopg_pool` when
   `use_pool=True` is actually requested (raising a clear, specific
   `ImportError` otherwise). Regression tests added:
   `test_create_connection_works_without_psycopg_pool_installed` (relational)
   and `test_create_connection_pooled_raises_clear_error_without_psycopg_pool`
   (intent).
2. **Pool-reuse behavior change, previously mischaracterized as preserved
   (now documented honestly, not reverted)**: the pre-extraction intent/
   code only took the pooled path on the *first* `create_connection()` call
   (`if self.use_connection_pool and not self.connection_pool`); once a pool
   existed, every later call fell through to the unpooled `else` branch and
   opened a brand-new standalone connection instead of reusing the pool —
   almost certainly an unintentional bug, not a deliberate design choice.
   The extracted mixin always gets a connection from the pool when
   `use_pool=True`, which is a genuine behavior change, not an
   exact-preservation extraction. The earlier version of this doc and the
   corresponding test's docstring stated this as preserved baseline
   behavior, which was wrong; both the mixin's docstring and the test
   (`test_create_connection_pooled_reuses_existing_pool`) now say explicitly
   that this is an intentional fix made during extraction, not a pinned
   pre-existing behavior.
3. **Weak assertion (fixed)**: the relational "never touches autocommit"
   test only checked `psycopg.connect()`'s call kwargs, which would not
   catch a later `connection.autocommit = ...` statement. Replaced the plain
   mock connection in that test with a small tracking double
   (`AutocommitTrackingConnection`) whose `autocommit` is a property that
   records whether it was ever assigned, and the test now asserts
   `connection.autocommit_was_set is False` directly.

All 18 Postgres tests (up from 16) pass after these fixes; full
`server/tests/test_retrievers/` suite: 528 passed, 2 skipped. `ruff check`
clean on every touched line.

### `_is_select_query()` dedup (completed 2026-11-15)

Step 6 of the original plan flagged this as "a safe, backend-agnostic text
check — lower risk than the connection/health-check items above." Extracted
as `SQLQueryExecutionMixin.is_select_query()` (static method,
`server/retrievers/base/base_sql_database.py`) — available to every SQL
retriever via `BaseSQLDatabaseRetriever` (both `intent/` and `relational/`
inherit from it), not just the 5 `intent/` sites the plan listed:

- Replaced the identical `query_upper = query.strip().upper(); if
  query_upper.startswith("SELECT") or query_upper.startswith("WITH"):`
  block at all 8 sites it existed (not just 5 — the plan's list only
  covered `intent/`; the same duplicate also existed in all 3 `relational/`
  retrievers): `intent_postgresql_retriever.py`, `intent_mysql_retriever.py`,
  `intent_sqlite_retriever.py`, `intent_duckdb_retriever.py`,
  `intent_athena_retriever.py`, `relational/postgresql_retriever.py`,
  `relational/mysql_retriever.py`, `relational/sqlite_retriever.py`.
- Athena's call site checks `normalized_query` (its own transformed query
  text), not the raw `query` argument — preserved exactly
  (`self.is_select_query(normalized_query)`), not silently changed to check
  the untransformed query.
- No behavior change: the extracted method is byte-for-byte the same
  `strip().upper()` + prefix check as every call site had (the only
  simplification was merging the two `startswith()` calls into one
  `startswith(("SELECT", "WITH"))`, a `ruff`-flagged equivalent rewrite,
  not a logic change).
- New direct unit tests: `server/tests/test_retrievers/test_is_select_query.py`
  (12 cases: SELECT/WITH in various casing/whitespace, and
  INSERT/UPDATE/DELETE/CREATE/empty/whitespace-only as negatives).
- All 12 new tests pass; full `server/tests/test_retrievers/` +
  `test_chunking_safeguards/` suites: 702 passed, 2 skipped (up from 690).
  `ruff check` clean on every touched line.

### Remaining for this item

- SQLite, DuckDB, and Athena mixin extractions were not attempted — out of
  scope for both the MySQL- and Postgres-start decisions made in this
  session. DuckDB and Athena's `_is_connection_alive()`-only production
  reachability (confirmed in the lifecycle audit) makes them candidates for
  a much smaller extraction (or no mixin at all, if `create_connection()`/
  `_close_connection()` are simply deleted as dead code per the original
  "Implication" note above) rather than a MySQL/Postgres-style merge.
- `SQLQueryExecutionMixin.execute_query_with_retry()` (defined but unused —
  every retriever reimplements its own retry/rollback instead of calling
  it) has not been investigated or adopted.

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

**Status: done (2026-11-15)** for the four decided-on behavioral
differences; the response-generator branch and per-template failure
metadata/follow-up storage were explicitly decided against adoption (see
below), not left undecided.

### Decisions confirmed with the user before any code changed (2026-11-15)

Of the six behavioral differences listed below, each was explicitly
resolved rather than silently merged:

1. **Cancellation** — adopt the base's behavior (bug fix).
2. **Required-parameter checks** — adopt the base's behavior (bug fix).
3. **Follow-up-turn storage** — **not adopted**. Firecrawl keeps its current
   behavior (no `_store_followup_turn` call) as a deliberate product choice.
4. **Failed-template metadata** — **not adopted**. Firecrawl's candidates
   list stays template id + similarity only; no per-template failure
   reasons.
5. **Response-generator branch** — **not adopted**. `self.response_generator
   = None` stays; no adapter was built to route scraped content through the
   generic formatter.
6. **Empty-formatter-result handling** — adopt the base's "try the next
   template candidate" behavior, replacing Firecrawl's previous "stop on
   first result, empty or not".

### What changed

`server/retrievers/implementations/intent/intent_firecrawl_retriever.py`'s
`_get_relevant_context_impl`:

- Added `cancel_event` handling: checked before template search and between
  each template attempt, returning `[]` immediately when set — matching
  `base/intent_http_base.py:791,819`. `cancel_event` is optional (via
  `kwargs.pop('cancel_event', None)`), so omitting it is unchanged behavior.
- Added the same missing-required-parameter skip as the base
  (`base/intent_http_base.py:849-860`) — a template missing a required
  parameter after extraction is skipped in favor of the next candidate,
  without a doomed scrape request. Unlike the base, no `failed_templates`
  list is built (decision 4 above: not adopted), so the skip is silent
  beyond a debug log line.
- Changed `return formatted_results` (unconditional) to
  `if formatted_results: return formatted_results` inside the template
  loop, so an empty result from one template now falls through to try the
  next candidate instead of ending the search immediately (decision 6).
  When every candidate's result is empty, the existing
  `all_templates_failed` response is returned, same as an execution error.
- `self.response_generator = None` and the absence of
  `_store_followup_turn()`/per-template failure metadata are all unchanged
  (decisions 3, 4, 5 — explicitly confirmed, not touched).

### Tests

New file `server/tests/test_retrievers/test_intent_firecrawl_reconciliation.py`
(8 tests): cancellation before search, cancellation mid-iteration,
no-`cancel_event` is backward compatible, missing-required-parameter skip,
empty-result-tries-next-template, all-empty falls through to
`all_templates_failed`, and two tests pinning the *not*-adopted behaviors
(no follow-up-turn call, candidates metadata has no per-template failure
reasons) so a future change can't silently reintroduce them.

All 8 new tests pass. Full `server/tests/test_retrievers/` suite (681
passed, 2 skipped) and the existing
`server/tests/test_chunking_safeguards/test_firecrawl_fallback.py` (21
tests, unaffected) both pass unchanged. `ruff check` is clean for the one
new test file; pre-existing, unrelated lint findings in
`intent_firecrawl_retriever.py` (import order, `Optional[X]` vs `X | None`,
a bare `Exception`, nested `if`s, dict-access style) were left alone, same
convention as the SQL work above.

### Cross-retriever test matrix (completed 2026-11-15)

New file `server/tests/test_retrievers/test_intent_http_base_reconciliation.py`
(9 tests) exercises `IntentHTTPRetriever._get_relevant_context_impl` in
`base/intent_http_base.py` directly — the shared code path that
`IntentGraphQLRetriever` and `IntentHTTPJSONRetriever` both use unmodified
(neither overrides `_get_relevant_context_impl`), and that Firecrawl was
reconciled against above. Nothing in this base class was changed during the
Firecrawl work; these tests exist to confirm the base's own behavior (which
Firecrawl now matches on the four adopted points) is itself correctly
covered, per the plan's enumerated list:

- Cancellation mid-search (`cancel_event` set between template attempts) and
  before search.
- A template with a missing required parameter after extraction — skipped,
  not attempted, **and** recorded in `failed_templates` metadata (unlike
  Firecrawl, which deliberately does not adopt this metadata).
- Follow-up-turn storage on a successful result, on **both** the
  `response_generator` branch and the plain-formatter branch.
- The failure envelope/metadata shape for `below_threshold` and
  `parameter_extraction_failed` responses, including per-template failure
  reasons and candidate metadata fields.
- Empty-formatter-result behavior (the base's existing "try the next
  template" behavior, which Firecrawl was reconciled to match — this test
  confirms the base already behaved this way, so Firecrawl's reconciliation
  target was accurately described).
- `no_matching_template` bounded error response.

All 9 pass. Re-ran `test_intent_http_json_retriever.py` (28 tests, one of
the named consumers) directly to confirm it's unaffected — all pass,
unchanged. Full `server/tests/test_retrievers/` + `test_chunking_safeguards/`
suites: 690 passed, 2 skipped. No GraphQL-specific test file exists yet
(none existed before this session either); since it doesn't override
`_get_relevant_context_impl`, the base-level coverage above applies to it
equally — a GraphQL-specific test file would mostly duplicate this one's
mocking of the same shared method, not add new coverage of the reconciled
behavior.

### Not done / explicitly out of scope

- No async-formatter hook was added to the base class itself (the plan's
  final step, "extend the base method with an async-formatter hook... and
  reconcile Firecrawl onto it") — Firecrawl's `_get_relevant_context_impl`
  remains its own override, now behaviorally aligned on the four adopted
  points, not structurally merged into the base's loop.

---

## Original Item 2 notes (superseded by the decisions above, kept for context)

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
