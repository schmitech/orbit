# Chat History Bounded Aggregation Queries — Implementation Plan

## Summary

Extracted from Phase 2 of `docs/roadmap/complete/chat-history-service-followups.md`
(now complete), which implemented a reduced-scope version of this work: a
`projection` parameter on `DatabaseService.find_many()` that eliminates
loading message `content` for rows that don't need it. That reduced the
dominant memory cost, but `get_user_sessions()` and `_cleanup_excess_messages()`
still fetch **up to 10,000 rows per call**, capped by a hardcoded `limit`
rather than computed server-side. This item is the remaining, larger half of
the original plan: replacing that fetch-then-group-in-Python approach with
real DB-side aggregation, removing the cap entirely.

This was deferred rather than done alongside the reduced-scope work because
it requires new query-dialect code (SQL `GROUP BY`/window functions,
MongoDB aggregation pipelines) for all three `DatabaseService` backends
(`MongoDBService`, `SQLiteService`, `PostgresService`), and only SQLite was
verifiable against a live instance in the environment that did that work —
PostgreSQL/MongoDB integration tests require a live server and hang without
one.

## Items

- `get_user_sessions()` (`server/services/chat_history_service.py`) fetches
  up to 10,000 message rows (`session_id`/`timestamp` only, as of the Phase 2
  projection work) per call just to compute per-session counts and activity
  timestamps, then a further one small query per returned session for its
  last-message preview. The 10,000-row cap means a user with more history
  than that has session counts/timestamps silently computed from an
  incomplete set.
- `_cleanup_excess_messages()` (`server/services/chat_history_service.py`)
  fetches up to 10,000 message rows (`timestamp`/`token_count`, as of Phase
  2) per session on every cleanup call, even though typically only the
  oldest handful need deleting. A session that grows past 10,000 messages
  before ever triggering cleanup would have its budget-walk computed from an
  incomplete set, potentially retaining stale old messages the walk never saw.

## Why this needs a schema/interface change, not a same-file fix

Both need a DB-side aggregation or cursor/limit capability that
`DatabaseService` does not currently expose uniformly across its three
backends — MongoDB, SQLite, **and PostgreSQL**
(`server/services/database_service.py:328` documents all three; see
`create_database_service()`). Adding that is an interface change to a
shared service with three concrete implementations to update and test, not
a same-file cleanup or a two-backend change.

## Design corrections from review (read before implementing)

A first draft of this plan proposed `count_by_group()` +
`find_one_per_group()` as separate primitives for `get_user_sessions()`, and
left the cleanup primitive's boundedness and the budget-estimation semantics
underspecified. A review caught four gaps that must be resolved before this
is implementation-ready — **the most important one is ensuring both APIs
are genuinely bounded at the database boundary, not just moving an
unbounded result set behind a new abstraction**:

1. **`get_user_sessions()` needs one paginated group-summary primitive, not
   two.** `count_by_group()` + `find_one_per_group()` each have gaps:
   neither computes `first_activity` (the earliest message timestamp per
   session, currently used for `duration_seconds`), both would return every
   group before pagination is applied (defeating the point of bounding the
   query), and using `find_one_per_group()` for the last-message preview
   could still leave the N+1 per-session preview queries in place instead of
   collapsing them into one round trip. Replace both with a single primitive
   — see `find_user_session_summaries()` below — that computes count, min
   timestamp, max timestamp, and latest message content/role per group, and
   applies ordering, offset, and limit **in the database**, returning only
   the one page of sessions actually needed. Token estimation is unrelated
   to session summaries, so this primitive takes no ratio/estimation
   parameter at all (see correction 3 for where that belongs) — instead it
   takes an `include_summary: bool` parameter, mirroring
   `get_user_sessions()`'s own existing `include_summary` argument, so that
   `include_summary=False` skips computing/fetching the latest message's
   `content`/`role` entirely rather than fetching it and discarding it.
2. **The cleanup primitive must not return every ID to delete, or every row
   for Python-side legacy estimation — and chunking only the delete step is
   not enough if determining the boundary first materializes every row or
   ID.** A session with a very large tail to delete could otherwise exceed a
   MongoDB command-size limit or a SQL driver's parameter-count limit — the
   same unbounded-result problem this plan exists to fix, just moved one
   layer down. Prefer a backend operation that determines the delete
   boundary and performs the delete **server-side**: for SQL backends, a
   single `DELETE ... WHERE` with a subquery/window-function boundary. For
   MongoDB, there is no aggregation-pipeline delete — an aggregation
   pipeline can compute a result but cannot delete the source documents it
   read; `delete_many()` only ever accepts a plain query filter, not a
   pipeline. The Mongo implementation must instead (1) aggregate to find the
   boundary (e.g. the `(timestamp, _id)` of the oldest message to keep,
   using the exact ordering from correction 3 below), then (2) call
   `delete_many()` with a stable range filter derived from that boundary
   (e.g. `timestamp < boundary_timestamp OR (timestamp == boundary_timestamp
   AND _id < boundary_id)`) — or, if that two-step read-then-delete needs to
   be atomic against concurrent writes, wrap both in a MongoDB transaction
   where the deployment supports one (replica set/sharded cluster; not
   standalone). Either way, this returns a small, fixed-shape result — at
   least `{deleted_count: int, tokens_removed: int}` — rather than a list of
   ids sized by however many messages the session has accumulated. If a
   given backend genuinely cannot express the full walk-and-delete
   server-side (see the estimation-pushdown note below), the fallback must
   be a **bounded cursor/page walk to find the boundary, and bounded delete
   batches to remove it** — at no point accumulating an unbounded
   in-memory collection of rows or ids, even transiently. A single unbatched
   `$in`/`IN (...)` covering every id, or a single unpaginated fetch used
   only to *compute* the boundary before a separate bounded delete, are both
   unacceptable — the boundedness requirement applies to *every* step of the
   operation, not just the final delete call. Also specify up front what
   `tokens_removed` means if a batch partially fails partway through: it
   must reflect only the rows actually, successfully deleted so far, not the
   full amount originally planned for deletion — a caller must never be told
   more tokens were freed than really were.
3. **Exact, deterministic budget semantics — spelled out, not implied.**
   These two orderings are different operations over different row shapes
   and must not be conflated:
   - **Selecting the latest message within a session** (both
     `find_user_session_summaries()`'s preview and the cleanup primitive's
     newest-to-oldest walk) orders individual message rows by
     `timestamp DESC, _id DESC` — two messages can share a timestamp at
     millisecond/microsecond resolution, and an unstable sort makes both
     "which message is the preview" and the "keep newest N" budget boundary
     (and therefore which messages get deleted) nondeterministic across
     repeated runs or between backends. `_id` is a real, unambiguous
     tie-breaker here because each row is an individual message document.
   - **Ordering session groups** (`find_user_session_summaries()`'s
     pagination) orders the *grouped* rows by `last_activity DESC,
     session_id ASC`. A grouped/aggregated row has no message `_id` to break
     ties on — `session_id` is the stable tie-breaker for this operation
     instead. Using `_id` here would be a mistake: it doesn't exist on a
     group-by result.
   - The legacy `token_count IS NULL` estimate computed by any backend must
     exactly match `max(1, len(content) // 3)` as `_estimate_token_count()`
     computes it today — including `len()`'s Unicode-codepoint semantics
     (not bytes, not UTF-8-encoded length). A SQL backend pushing this into
     `LENGTH()`/`CHAR_LENGTH()` must confirm that function counts codepoints,
     not bytes, for the column's encoding; get this wrong and legacy-row
     token counts silently diverge from Python's existing behavior in a way
     unit tests using ASCII-only content won't catch.
   - The `3`-characters-per-token ratio (`CHARS_PER_TOKEN_ESTIMATE` in
     `chat_history_service.py`) must not be re-hardcoded as a fourth copy
     inside three backend implementations. Either pass it into the
     primitive as a parameter sourced from that one constant, or centralize
     it somewhere all four call sites (Python fallback + 3 backends) read
     from — do not duplicate the literal `3`.
4. **Index/schema audit, with a performance check in Verification, not just
   correctness.** The current user-history index is effectively
   `(user_id, timestamp)` (see `_create_indexes()` in
   `chat_history_service.py`). Grouping and paginating by `session_id` while
   ordering by `timestamp` may need `(user_id, session_id, timestamp)` or a
   different backend-specific index/covering index to avoid the new
   aggregation query silently doing a full collection/table scan per call —
   the same performance problem this plan exists to fix, just moved from
   "loads too many rows in Python" to "scans too many rows in the database."
   Audit each backend's query plan against the new queries and add/adjust
   indexes as needed: `EXPLAIN QUERY PLAN` for SQLite, `.explain()` for
   MongoDB's aggregation, and for Postgres, plain `EXPLAIN` for the
   `SELECT`-shaped session-summary query. For the Postgres **cleanup
   `DELETE`**, never run a bare `EXPLAIN ANALYZE` — unlike plain `EXPLAIN`,
   `EXPLAIN ANALYZE` actually executes the statement, so a bare run against
   a mutating `DELETE` would delete real rows as a side effect of taking a
   query plan. Use plain `EXPLAIN` (no `ANALYZE`, estimated plan only), or if
   real timing is needed, wrap `EXPLAIN ANALYZE` in an explicit transaction
   that is rolled back afterward rather than committed.

## Plan

1. Audit `server/services/database_service.py` and its three backend
   implementations (`MongoDBService`, `SQLiteService`, `PostgresService`) for
   existing aggregation primitives (e.g. does the Mongo backend expose a raw
   `aggregate()` passthrough already? does Postgres have a query builder that
   supports `GROUP BY`/window functions?). Document the gap for whichever
   backend(s) lack it — treat all three as in scope from the start.
2. Design a minimal, backend-agnostic addition to the `DatabaseService`
   interface, incorporating the four corrections above — do not leak
   MongoDB-specific aggregation pipeline syntax or Postgres-specific SQL
   into callers:
   - `find_user_session_summaries(collection, user_id, offset, limit,
     include_summary, content_field, role_field) -> list[dict]` — one
     primitive, replacing the `count_by_group`/`find_one_per_group` pair.
     Groups by `session_id` filtered to `user_id`, computing per session:
     `message_count`, `first_activity` (min timestamp), `last_activity` (max
     timestamp), and — only when `include_summary=True` — the latest
     message's `content`/`role`; when `include_summary=False`, the primitive
     must not fetch or compute those fields at all (not fetch-then-discard).
     No token-estimation parameter belongs here — token estimation is
     unrelated to session summaries (see the cleanup primitive below).
     Orders session *groups* by `last_activity DESC, session_id ASC`
     (`session_id`, not `_id` — a grouped row has no message id to break
     ties on), then applies `offset`/`limit` **before** returning — the
     database returns only the page actually needed, not every session.
     Selecting *which* message is "latest" within a group (for the
     `content`/`role` preview) is a separate ordering, over individual
     message rows: `timestamp DESC, _id DESC`.
   - A new primitive for `_cleanup_excess_messages()` that reflects the
     **actual** operation: cleanup walks a session's messages from *newest*
     to *oldest*, ordered `timestamp DESC, _id DESC` (individual message
     rows, so `_id` is a valid and necessary tie-breaker here), accumulating
     token counts until the per-adapter budget is reached, then deletes
     everything older than that boundary (see the current
     `messages_reversed` walk in `_cleanup_excess_messages()`/
     `get_context_messages()` for the reference semantics) — it is not a
     simple "find/delete the N oldest" query. E.g.
     `delete_messages_beyond_token_budget(collection, session_filter,
     token_field, content_field, budget, sort_desc_field,
     chars_per_token_estimate) -> {deleted_count, tokens_removed}` —
     **determines and deletes the tail server-side**, returning only the
     small fixed-shape result, not a list of ids sized by the session. Must
     handle legacy rows with `token_count IS NULL` by estimating from
     `content` using the exact `max(1, len(content) // 3)` semantics (via
     the passed-in `chars_per_token_estimate`, sourced from
     `CHARS_PER_TOKEN_ESTIMATE`, not a re-hardcoded literal), with correct
     Unicode-codepoint-length behavior confirmed per backend. See correction
     2 above for what "bounded" must actually mean here — chunking only the
     final delete is not sufficient on its own.
3. Implement the SQLite backend version first (simpler, single-process,
   well-covered by existing local tests), then MongoDB, then Postgres —
   Postgres/MongoDB implementations will need verification against a live
   server, which the environment used for the Phase 2 reduced-scope work did
   not have; plan for that verification step explicitly before merging.
4. Migrate `get_user_sessions()` to `find_user_session_summaries()`; keep
   the existing return shape unchanged so route callers (`server/routes/`)
   need no changes.
5. Migrate `_cleanup_excess_messages()` to the new bounded delete primitive;
   keep the per-session lock and the cache-adjustment logic (now driven by
   the primitive's returned `tokens_removed`) unchanged.
6. Audit and add/adjust indexes per correction 4 above for each backend
   (e.g. `(user_id, session_id, timestamp)` for SQLite/Postgres; a
   corresponding compound index for MongoDB's aggregation), and capture the
   before/after query plan for each new query as part of the change.
7. Add regression and query-plan/performance tests per Verification below
   to confirm the new query paths don't re-introduce a full-table load or a
   full-table scan, against all three backends.
8. While implementing, double-check the `_id: {"$in": [...]}` / `projection`
   fixes made during the Phase 2 reduced-scope work still hold under the new
   query shapes — those fixes were verified only via SQLite and standalone
   logic tests, not a live MongoDB/PostgreSQL server.

## Verification

Test `get_user_sessions()` and `_cleanup_excess_messages()` separately —
they exercise different failure modes:
- `get_user_sessions()`: a test with many *sessions* (not necessarily many
  messages per session) verifying pagination, counts, `first_activity`, and
  last-message preview are correct across the new grouped-query path,
  including a session count exceeding the old 10,000-row cap. A single
  large-session test would not catch a pagination or per-session-count
  regression here. This needs two *separate* tie-break tests, since they
  exercise different orderings over different row shapes (see correction 3
  above) — one does not exercise the other:
  - **Session-group ordering**: two different *sessions* whose latest
    message shares the same `last_activity` timestamp, asserting the
    session-group ordering resolves the tie via `session_id ASC` and that
    ordering is stable/deterministic across repeated calls.
  - **Preview selection**: two *messages within the same session* sharing
    the same `timestamp`, asserting the last-message preview is selected
    via `_id DESC` (i.e. the correct one of the two tied messages is
    returned as `content`/`role`, not whichever happened to be scanned
    first).
- `_cleanup_excess_messages()`: a test with >10,000 messages in *one*
  session confirming the budget-walk boundary and `deleted_count`/
  `tokens_removed` are correct without a configurable batch-limit override
  standing in for the real cap (the point is proving correctness *without*
  a hardcoded ceiling at all — a low test-only limit would no longer
  demonstrate that once the 10,000-row cap itself is gone, unless the final
  primitive genuinely has its own configurable batch size, in which case
  test that batch size explicitly as its own parameter, not as a stand-in
  for "no cap"), plus a case mixing rows with and without `token_count` —
  including non-ASCII/multi-byte Unicode content — to confirm the
  legacy-estimation fallback matches `max(1, len(content) // 3)` exactly
  through the new query path.
- Query-plan/performance check for both primitives on each backend
  (`EXPLAIN QUERY PLAN` for SQLite, `.explain()` for MongoDB's aggregation,
  plain `EXPLAIN` for Postgres's session-summary `SELECT` and, for the
  Postgres cleanup `DELETE`, either plain `EXPLAIN` or an `EXPLAIN ANALYZE`
  wrapped in a rolled-back transaction — never a bare `EXPLAIN ANALYZE`
  against the mutating `DELETE`), confirming the new queries use the
  audited/added index rather than a full collection/table scan. This is in
  addition to, not a replacement for, correctness tests.

Run both sets of tests against all three backends (MongoDB, SQLite,
Postgres) — this item is not complete until it has real coverage on all
three, not just SQLite.

## Completion criteria

- `get_user_sessions()` and `_cleanup_excess_messages()` no longer cap their
  initial fetch at a fixed row count; both compute their results via
  DB-side aggregation instead of an in-Python group-by over a
  bounded-size fetch.
- Both new primitives are genuinely bounded at the database boundary, at
  every step: the session-summary primitive applies ordering/offset/limit
  in the database before returning (never fetching every group), and the
  cleanup primitive determines and deletes the tail server-side, returning
  a small fixed-shape result rather than an id/row list sized by the
  session — or, where a backend can't do the walk-and-delete server-side,
  uses a bounded cursor/page walk to find the boundary *and* bounded delete
  batches to remove it, never accumulating an unbounded row/id collection
  at any point (including while only determining the boundary). A partial
  batch failure is reflected honestly: `tokens_removed` covers only rows
  actually, successfully deleted, never the full amount originally planned.
- `find_user_session_summaries()` takes no token-estimation parameter (that
  concern belongs solely to the cleanup primitive) and an `include_summary`
  parameter that, when `False`, skips fetching/computing the latest
  message's `content`/`role` entirely rather than fetching and discarding
  it.
- Ordering is correct and deterministic per operation, each verified by its
  own tied-input test (the two must not be conflated — see Verification):
  session-group pagination ordering (`last_activity DESC, session_id ASC`)
  is verified with two sessions sharing a `last_activity`; preview/cleanup
  message selection (`timestamp DESC, _id DESC`) is verified with two
  messages *within the same session* sharing a `timestamp`.
- Legacy token-count estimation matches `max(1, len(content) // 3)`
  exactly, including Unicode-codepoint-length semantics, verified with
  non-ASCII content; the `3`-characters-per-token ratio is sourced from one
  place (`CHARS_PER_TOKEN_ESTIMATE`), not re-hardcoded per backend.
- An index audit was performed for all three backends, indexes were
  added/adjusted where the new queries needed them, and a query-plan check
  confirms each new query is not doing a full scan.
- Regression tests for session-list pagination/counts/`first_activity` and
  for cleanup's token-budget boundary (including legacy rows with no
  `token_count`, and Unicode content) pass against all three backends —
  MongoDB, SQLite, and PostgreSQL.
- The `_id: {"$in": [...]}` and `projection` fixes from the Phase 2
  reduced-scope work are confirmed to hold against live MongoDB and
  PostgreSQL servers, not just SQLite and standalone logic tests.
