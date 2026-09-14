# Chat History Service Follow-Ups — Implementation Plan

## Summary

During a `/simplify` cleanup pass on `server/services/chat_history_service.py`
(2026-09-13), four review agents (reuse, simplification, efficiency, altitude)
surfaced three items that were deliberately **not** applied inline because
each would change behavior, require changes outside the reviewed diff, or
touch shared infrastructure beyond one file. This plan addresses them
one at a time, in isolation, so each can be reviewed and tested on its own
merits rather than folded into an unrelated cleanup commit.

Applied in that same pass (not part of this plan): a shared
`CHARS_PER_TOKEN_ESTIMATE` constant, a `_get_msg_token_count()` helper, a
`_cancel_task()` helper in `close()`, a `_untrack_session()` helper, a local
`_fail()` helper in `clear_conversation_history()`, and `asyncio.gather`
parallelization of `_delete_generation_memory()` and the per-file deletion
loop in `_cascade_delete_session()`.

## Phase 1 — Retry decorator consolidation [COMPLETE]

Implemented 2026-09-13. `RetryHandler`/`retry_on_error()` in
`server/ai_services/connection.py` gained `retry_on` and `jitter` parameters
(both default to the prior behavior, so no other caller changed). The two
`@with_retry()` call sites in `chat_history_service.py` now use
`@retry_on_error(max_retries=2, initial_wait_ms=1000, max_wait_ms=10000,
retry_on=_DB_RETRY_ON, jitter=True)` — `max_retries=2` was required (not 3)
to preserve the original 3-total-call count, per the attempt-count
reconciliation below. `with_retry()` and its now-unused imports were
removed. Tests added in
`server/tests/test_services/test_chat_history_service.py`:
`test_add_message_retries_transient_db_error_then_succeeds`,
`test_add_message_retry_exhaustion_makes_exactly_three_total_calls`,
`test_add_message_non_retryable_exception_is_not_retried`,
`test_add_message_duplicate_key_behavior_unchanged`. All 42 tests in that
file pass.

**Item:** `with_retry()` (`server/services/chat_history_service.py:47-81`)
duplicates the exponential-backoff retry pattern already implemented by
`retry_on_error()` / `RetryHandler` in `server/ai_services/connection.py`.

**Why it was skipped inline:** the two are not drop-in compatible.
`RetryHandler.execute_with_retry()` catches bare `Exception` on every retry
attempt, while `with_retry()` retries only on
`(DatabaseConnectionError, DatabaseTimeoutError, DatabaseOperationError)`
(configurable via `retry_on`) and lets everything else propagate
immediately. Swapping without addressing this would either retry
non-database errors it shouldn't (e.g. a `SessionOwnershipError` raised
inside `add_message`, which must fail fast, not retry 3 times with backoff),
or silently change which failures `add_message`/`get_conversation_history`
tolerate.

**Plan:**
1. Add an optional `retry_on: tuple[type[Exception], ...] | None` parameter
   to `RetryHandler.__init__` / `retry_on_error()`, defaulting to `None`
   (current bare-`Exception` behavior preserved for all existing callers).
   When set, `execute_with_retry` re-raises immediately on any exception not
   in that tuple instead of retrying it.
2. Confirm `retry_on_error()`'s jitter/backoff math
   (`initial_wait_ms * exponential_base ** attempt`, capped at `max_wait_ms`)
   produces equivalent behavior to `with_retry`'s
   `random.uniform(0, base_delay * 2**attempt)` full-jitter — they differ
   (no jitter vs. full jitter). Decide whether to standardize on one
   (recommendation: keep full jitter, since `with_retry`'s comment explains
   *why* it uses it, and add a `jitter: bool` flag to `RetryHandler` for
   backward compatibility with other callers that may rely on the
   non-jittered timing in tests).
3. **Attempt-count mismatch — must be resolved explicitly, not silently
   changed.** `with_retry(max_attempts=3)`
   (`server/services/chat_history_service.py:50`) makes 3 total calls: the
   `for attempt in range(max_attempts)` loop body itself performs the call,
   so `max_attempts` *is* the total call count. `RetryHandler(max_retries=3)`
   (`server/ai_services/connection.py:147`, `for attempt in
   range(self.max_retries + 1)`) makes 4 total calls — `max_retries` is
   retries *on top of* the first attempt. Migrating the two `@with_retry()`
   call sites to `retry_on_error()` with `max_retries=3` would silently
   change `add_message`/`get_conversation_history` from 3 total attempts to
   4, extending worst-case latency and changing retry-exhaustion tests.
   Resolve this by calling
   `retry_on_error(max_retries=2, retry_on=(DatabaseConnectionError, DatabaseTimeoutError, DatabaseOperationError))`
   to preserve the existing 3-total-call behavior, and add a one-line
   comment at the call site cross-referencing this discrepancy so a future
   reader doesn't "fix" it back to `max_retries=3`. If preserving the exact
   count is not actually important, document that decision explicitly
   instead (e.g. standardize on `max_retries=3` meaning 4 total attempts
   everywhere, and update the completion-criteria test in this phase to
   assert 4, not 3).
4. Update `ChatHistoryService.add_message` and `.get_conversation_history`
   (the two `@with_retry()` call sites) to use
   `@retry_on_error(max_retries=2, retry_on=(DatabaseConnectionError, DatabaseTimeoutError, DatabaseOperationError))`
   (or the standardized alternative from step 3) instead.
5. Delete `with_retry()` and its now-unused imports (`functools`, `random`)
   from `chat_history_service.py` if nothing else in the file uses them.
6. Grep for other files defining their own retry decorator (this may not be
   the only duplicate) and note them for a follow-up, but do not fold them
   into this phase — scope is the two call sites above.

**Verification:** `server/tests/test_services/test_chat_history_service.py`
does not currently contain explicit transient-database retry tests — this
phase must add them, not assume existing coverage. At minimum:
- A retryable failure (e.g. `DatabaseConnectionError`) followed by success
  on a later attempt, asserting the operation ultimately returns
  successfully.
- Retry exhaustion: all attempts raise the retryable error, asserting the
  original exception propagates and the underlying call was made exactly
  3 times total (matching the resolved attempt count from step 3 above —
  update this assertion if step 3's standardization decision changes the
  total).
- A non-retryable exception (e.g. `SessionOwnershipError`) is not retried
  and the underlying call was made exactly once.
- Duplicate-key handling (`DatabaseDuplicateKeyError`) behavior is
  unchanged — it must still return `None` from `add_message` without
  triggering a retry loop.

## Phase 2 — Bounded/streaming session and cleanup queries

**Items:**
- `get_user_sessions()` (`chat_history_service.py:1262-1267`) fetches up to
  10,000 full message documents (including `content`) per call just to
  compute per-session counts/timestamps/last-message preview.
- `_cleanup_excess_messages()` (`chat_history_service.py:1077-1082`) fetches
  up to 10,000 full messages per session on every cleanup call, even though
  typically only the oldest handful need deleting.

**Why it was skipped inline:** both need a DB-side aggregation or
cursor/limit capability that `database_service` does not currently expose
uniformly across its three backends — MongoDB, SQLite, **and PostgreSQL**
(`server/services/database_service.py:328` documents all three; see
`create_database_service()`). Adding that is a schema/interface change to a
shared service with three concrete implementations to update and test, not
a same-file cleanup or a two-backend change.

**Plan:**
1. Audit `server/services/database_service.py` and its three backend
   implementations (`MongoDBService`, `SQLiteService`, `PostgresService`) for
   existing aggregation primitives (e.g. does the Mongo backend expose a raw
   `aggregate()` passthrough already? does Postgres have a query builder that
   supports `GROUP BY`/window functions?). Document the gap for whichever
   backend(s) lack it — treat all three as in scope from the start.
2. Design a minimal, backend-agnostic addition to the `DatabaseService`
   interface — do not leak MongoDB-specific aggregation pipeline syntax or
   Postgres-specific SQL into callers. Candidate shape:
   - `count_by_group(collection, group_field, filter) -> dict[str, int]`
     for session message counts.
   - `find_one_per_group(collection, group_field, filter, sort) -> list[dict]`
     for "last message per session" (used by `get_user_sessions`'s preview).
   - A new primitive for `_cleanup_excess_messages()` that reflects the
     **actual** operation: cleanup walks a session's messages from *newest*
     to *oldest*, accumulating token counts until the per-adapter budget is
     reached, then deletes everything older than that boundary (see the
     current `messages_reversed` walk in
     `_cleanup_excess_messages()`/`get_context_messages()` for the reference
     semantics) — it is not a simple "find the N oldest" query. Name and
     shape it accordingly, e.g. `find_messages_beyond_token_budget(
     collection, session_filter, token_field, content_field, budget,
     sort_desc_field) -> list[dict]` (documenting it as returning the *ids to
     delete*, i.e. the tail beyond the retained newest-first budget window).
     The primitive must handle legacy rows with no `token_count` (`None`) by
     estimating from `content` inline (matching today's
     `_get_msg_token_count()`/`_estimate_token_count()` fallback) — if the
     estimation can't be pushed into the query layer for a given backend,
     the primitive should return `token_count` (nullable) and `content`
     alongside each row so `ChatHistoryService` can still apply the same
     fallback logic in Python, rather than silently treating an unestimated
     row as 0 tokens.
3. Implement the SQLite backend version first (simpler, single-process,
   well-covered by existing tests), then MongoDB, then Postgres.
4. Migrate `get_user_sessions()` to the new grouped-count/last-message
   primitive; keep the existing return shape unchanged so route callers
   (`server/routes/`) need no changes.
5. Migrate `_cleanup_excess_messages()`'s initial fetch to the new bounded
   query; keep the per-session lock, the newest-first budget-walk semantics,
   and the cache-adjustment logic unchanged.
6. Add regression tests per step 7 below to confirm the new query paths
   don't re-introduce a full-table load, against all three backends.

**Verification:** test `get_user_sessions()` and `_cleanup_excess_messages()`
separately — they exercise different failure modes:
- `get_user_sessions()`: a test with many *sessions* (not necessarily many
  messages per session) verifying pagination, counts, and last-message
  preview are correct across the new grouped-query path. A single
  large-session test would not catch a pagination or per-session-count
  regression here.
- `_cleanup_excess_messages()`: a test with >10,000 messages in *one*
  session (or a low test-only limit override) confirming the budget-walk
  boundary and deletion set are unchanged, plus a case mixing rows with and
  without `token_count` to confirm the legacy-estimation fallback still
  applies correctly through the new query path.

Run both sets of tests against all three backends (MongoDB, SQLite,
Postgres), not just SQLite/MongoDB.

## Phase 3 — Provider native-parameter-alias knowledge moved to shared metadata

**Scope note:** this phase is explicitly broader than context-window
metadata alone. `ProviderCacheManager._MAX_TOKENS_ALIASES` (provider →
native max-tokens param name, e.g. `ollama`/`ollama_cloud`/`ollama_remote` →
`num_predict`) has no chat-history-side duplicate to consolidate against,
but it lives in the same source dict block as `_CONTEXT_WINDOW_ALIASES` and
describes the same kind of fact (a provider's native parameter name for a
generic setting). `provider_metadata.py` is intended as the shared home for
**all native-parameter-alias metadata of this kind**, not context-window
aliases specifically — so `_MAX_TOKENS_ALIASES` moves too, in the same pass,
even though only the context-window mapping was a strict duplicate.
Consolidating it separately later would leave the module half-populated and
`provider_cache_manager.py` still owning parallel provider-keyed metadata,
which is the exact problem this phase exists to close.

**Items:**
- `_CONTEXT_WINDOW_PARAM_NAMES` (`chat_history_service.py:90-99`) — maps each
  inference provider to its native context-length config key (`num_ctx`,
  `n_ctx`, `max_model_len`, ...).
- `default_context_windows` inside `_get_context_window_size`
  (`chat_history_service.py:382-412`) — hardcoded default context-window size
  per provider.
- **A third, previously-missed duplicate:**
  `ProviderCacheManager._CONTEXT_WINDOW_ALIASES`
  (`server/services/cache/provider_cache_manager.py:199-207`, alongside the
  adjacent `_MAX_TOKENS_ALIASES`) contains essentially the same
  provider-to-native-param-name mapping as
  `_CONTEXT_WINDOW_PARAM_NAMES`, used there to write adapter-level parameter
  overrides under the correct native key. Fixing only the chat-history copy
  would leave two independently-maintained copies of the same mapping and
  not actually produce a single source of truth — this phase is not done
  until both consumers read from the same place.

**Why it was skipped inline:** this is provider metadata being special-cased
inside multiple consumers instead of owned by one shared definition. Moving
it is a cross-cutting change touching at least two files outside the
originally-reviewed diff, and risks behavior changes for every provider if
done hastily.

**Important correction to the original framing:** there is no evidence of an
established "provider registry" or per-provider class/schema in this
codebase that already owns attributes like this. `AIServiceFactory` (check
`server/ai_services/`) is a registry of *service classes* (which client to
instantiate for a given provider name), not a registry of provider
*metadata* like context-window aliases and defaults. Do not assume a
provider-class home exists — the first implementation step below is to
confirm this, and the default plan is to introduce a small, purpose-built
shared metadata module rather than retrofitting attributes onto a
service-class registry that wasn't designed to hold them.

**Plan:**
1. Confirm there is no existing provider-metadata home: grep
   `server/ai_services/`, `server/inference/`, and
   `server/services/cache/provider_cache_manager.py` for any other
   provider-keyed dict of this shape (context window, native param aliases,
   max-tokens aliases) beyond the two already identified, so this phase
   consolidates all of them, not just two.
2. Introduce a small shared module — e.g.
   `server/services/provider_metadata.py` — holding, per provider, the
   values currently duplicated across `_CONTEXT_WINDOW_PARAM_NAMES`,
   `default_context_windows`, `ProviderCacheManager._CONTEXT_WINDOW_ALIASES`,
   and `ProviderCacheManager._MAX_TOKENS_ALIASES`. A plain module-level dict
   of small dataclasses/namedtuples is sufficient — this does not need to be
   a class registry:
   ```python
   @dataclass(frozen=True)
   class ProviderContextWindowInfo:
       context_window_param: str = "context_window"
       max_tokens_param: str = "max_tokens"
       default_context_window: int = 4096
   ```
   Populate values from the exact numbers currently in all four source dicts
   so this phase is a pure consolidation, not a re-tuning of any provider's
   numbers — flag and resolve any place the four sources disagree (e.g. if
   `_MAX_TOKENS_ALIASES` has an entry `_CONTEXT_WINDOW_PARAM_NAMES` doesn't,
   or vice versa) as an explicit decision, not silently.
3. Add a lookup function, e.g.
   `get_provider_context_window_info(provider: str) -> ProviderContextWindowInfo`,
   returning the frozen default (`context_window`, `max_tokens`, 4096) for an
   unknown/unregistered provider — matching today's implicit fallback
   behavior in both consumers.
4. Update `ChatHistoryService._get_context_window_size()` and
   `._calculate_max_token_budget()` to call the shared lookup instead of
   reading local dicts. Keep the alternative-param-name fallback chain
   (`context_window`, `max_context_length`, `context_length`) as-is — that
   part isn't provider-specific.
5. Update `ProviderCacheManager._apply_param_overrides()` (and any other
   caller of `_CONTEXT_WINDOW_ALIASES`/`_MAX_TOKENS_ALIASES`) to use the same
   shared lookup.
6. Remove `_CONTEXT_WINDOW_PARAM_NAMES` and `default_context_windows` from
   `chat_history_service.py`, and `_CONTEXT_WINDOW_ALIASES`/
   `_MAX_TOKENS_ALIASES` from `provider_cache_manager.py`, once nothing
   references them.
7. Add a table-driven test asserting every provider currently listed in any
   of the four old dicts resolves to the identical values through the new
   shared lookup — this is the regression guard for "pure consolidation, not
   a re-tune," and must cover both consumers (chat history's token-budget
   calculation and the cache manager's param-override injection).

**Verification:** the token-budget calculation tests in
`server/tests/test_services/test_chat_history_service.py` must produce
identical `max_token_budget` values for every provider before and after this
phase; existing `ProviderCacheManager` override tests must produce identical
adapter-override behavior for every provider; the table-driven test from
step 7 locks both in.

## Sequencing and ownership

These three phases are independent of each other and can be done in any
order or by different people; Phase 1 is the smallest and lowest-risk and is
a reasonable starting point. Land each phase as its own PR/commit, not
combined, so a regression in one is easy to isolate and revert.

## Completion criteria

- Phase 1: `chat_history_service.py` has no local retry decorator; both call
  sites use the shared `retry_on_error` with an explicitly resolved (not
  silently changed) total-attempt count; non-retryable exceptions
  (`SessionOwnershipError`) are verified not to be retried; the four new
  tests listed in Phase 1's verification section exist and pass.
- Phase 2: `get_user_sessions()` and `_cleanup_excess_messages()` no longer
  load full message sets (content included) into Python memory to compute
  aggregate/boundary values; separate regression tests for session-list
  pagination and for cleanup's token-budget boundary (including legacy rows
  with no `token_count`) pass against all three backends — MongoDB, SQLite,
  and PostgreSQL.
- Phase 3: `_CONTEXT_WINDOW_PARAM_NAMES` and the inline
  `default_context_windows` dict are removed from
  `chat_history_service.py`; `_CONTEXT_WINDOW_ALIASES` and
  `_MAX_TOKENS_ALIASES` are removed from `provider_cache_manager.py`; both
  consumers read from one shared provider-metadata module; the table-driven
  equivalence test covering both consumers passes.
- Full server test suite passes after each phase, with any external-service
  skips documented per the existing convention (see
  `docs/roadmap/complete/ruff-python-typing-modernization.md`).
