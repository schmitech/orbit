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

## Phase 2 — Bounded/streaming session and cleanup queries [COMPLETE, reduced scope]

Implemented 2026-09-14, with a narrower mechanism than the original plan's
`count_by_group`/`find_one_per_group`/`find_messages_beyond_token_budget`
primitives. Rather than adding new GROUP BY/aggregation-shaped methods per
backend (which would need per-backend query-dialect code that cannot be
verified against a live PostgreSQL or MongoDB server in this environment —
only SQLite is locally testable here), `DatabaseService.find_many()` gained
an optional `projection: list[str] | None` parameter (field selection,
implemented identically in `MongoDBService`, `SQLiteService`, and
`PostgresService` — the row/document id is always included regardless of
whether it's listed). Both consumers were migrated to fetch only the fields
they need instead of full documents:
- `_cleanup_excess_messages()` now fetches only `timestamp`/`token_count`
  for the budget walk, then issues a second, targeted `find_many` (filtered
  by `_id: {"$in": [...]}`) for `content` — but only for rows whose
  `token_count` is `None` (legacy pre-migration rows), not the whole set.
- `get_user_sessions()` now fetches only `session_id`/`timestamp` to compute
  per-session counts and activity timestamps, then — only when
  `include_summary=True`, and only for the page of sessions actually being
  returned (bounded by `limit`, default 10) — issues one small `limit=1`
  query per session for its last message's `content`/`role`.

This still caps the initial fetch at 10,000 rows (unlike the original plan's
DB-side aggregation, which would remove that cap entirely) but eliminates
loading message `content` for the other ~9,990+ rows in the common case,
which was the dominant memory cost identified in the original review. Fully
removing the 10,000-row cap via DB-side `GROUP BY`/aggregation is deferred —
see "Deferred" below.

**Bug found and fixed along the way:** implementing the second, targeted
`_id: {"$in": [...]}` query surfaced a pre-existing correctness bug, unrelated
to this refactor: `SQLiteService._convert_query_to_sql()` and
`PostgresService._convert_query_to_sql()` special-cased `_id` as a plain
equality match unconditionally, so a query shaped like
`{"_id": {"$in": [...]}}` (as already used by `_cleanup_excess_messages()`'s
own bulk `delete_many()` call, pre-dating this phase) silently matched zero
rows. Fixed by special-casing `_id` + `$in` ahead of the plain-equality
branch. This means the existing oldest-message bulk delete may have been
silently deleting 0 rows on the SQLite and PostgreSQL backends before this
fix, on this code path. If this is running in production, existing sessions
may have accumulated more history than intended on SQLite/PostgreSQL; no
worse than that, since the enclosing cleanup logic already treats delete
failures as non-fatal/logged, not crash-worthy.

Tests added in `server/tests/test_services/test_chat_history_service.py`
(against the real SQLite backend via the existing `chat_history_services`
fixture): `test_get_user_sessions_counts_and_preview_across_sessions`,
`test_get_user_sessions_without_summary_skips_content_fetch`,
`test_cleanup_excess_messages_handles_legacy_rows_without_token_count`. All
45 tests in that file pass. The `_id: {"$in": [...]}` fix is additionally
covered indirectly by the legacy-row test (it depends on the targeted
content re-fetch actually returning rows).

**Three more cross-backend contract bugs found and fixed on review** (SQLite
was the only backend actually exercised by the automated tests above, so a
manual/logic-only review caught what testing couldn't):
1. MongoDB's `_id: {"$in": [...]}` query has its own separate bug from the
   SQLite/PostgreSQL one above: `_convert_string_ids_to_objectid()` only
   converts a bare `_id` string value to `ObjectId`, not elements nested
   inside an `_id: {"$in": [...]}` list — so on a MongoDB backend using
   normal auto-generated ObjectIds, the legacy-row content re-fetch above
   returned nothing, and the legacy message was silently estimated at 0
   tokens instead of its real size. Fixed by converting each element of the
   `$in` list individually. Verified with a standalone logic test (no live
   Mongo server needed, since this is pure query-transformation code) for
   both ObjectId-shaped and non-ObjectId-shaped (e.g. UUID) id strings.
2. `SQLiteService`/`PostgresService`'s new `projection` parameter selected
   logical (MongoDB-style) field names literally as SQL column names, but
   two fields are stored under a different column name: `_id` is column
   `id`, and `chat_history.metadata` is the JSON-serialized `metadata_json`
   column. Projecting either raised an undefined-column error on Postgres,
   and on SQLite would have selected zero rows for `_id` (no such column)
   or a raw undecoded JSON string under `metadata` instead of a parsed
   dict. Fixed by adding a `_projection_storage_columns()` helper (identical
   in both files) that
   maps logical to storage names before building the `SELECT` column list,
   mirroring `_convert_row_to_document`'s existing reverse mapping. Verified
   with a standalone logic test.
3. All three backends treated `projection=[]` the same as `projection=None`
   (falsy-list check) and returned every field instead of an id-only result;
   MongoDB additionally treats an empty `{}` projection dict the same as no
   projection at all, so the fix there requires an explicit `{"_id": 1}`
   rather than just switching the truthiness check. Fixed in all three
   backends by checking `is not None` instead of truthiness, and building
   MongoDB's projection dict as `{"_id": 1}` when the list is empty.

None of the current call sites in `chat_history_service.py` pass an empty
projection list, so bug 3 was latent (not yet reachable in production) but
is part of the parameter's stated contract and now correctly implemented.

**Deferred — extracted to its own roadmap item:** the 10,000-row fetch cap
itself, and the original plan's DB-side `count_by_group`/`find_one_per_group`
aggregation primitives that would remove it, are unchanged by this phase.
MongoDB and PostgreSQL implementations of the `projection` parameter above
are code-reviewed against the same query-construction helpers already used
elsewhere in each file, but — unlike the SQLite path — could not be
exercised against a live server in this environment. Both of these (the
row-cap removal and live MongoDB/PostgreSQL verification of this phase's own
fixes) are tracked as their own item in
`docs/roadmap/chat-history-bounded-aggregation-queries.md`, so they aren't
lost now that this plan is being closed out.

## Phase 3 — Provider native-parameter-alias knowledge moved to shared metadata [COMPLETE]

Implemented 2026-09-14, matching this phase's plan closely (no scope
reduction, unlike Phase 2). Added `server/services/provider_metadata.py`
with a frozen `ProviderContextWindowInfo` dataclass
(`context_window_param`, `max_tokens_param`, `default_context_window`,
each defaulting to the generic key name / 4096) and a module-level
`get_provider_context_window_info(provider)` lookup, populated verbatim
from the four dicts it replaces — confirmed the two context-window-alias
dicts (`ChatHistoryService._CONTEXT_WINDOW_PARAM_NAMES` and
`ProviderCacheManager._CONTEXT_WINDOW_ALIASES`) already agreed exactly, so
no value discrepancy needed resolving.

- `ChatHistoryService._get_context_window_size()` and
  `._calculate_max_token_budget()`'s adapter-override native-key write now
  call the shared lookup instead of reading `_CONTEXT_WINDOW_PARAM_NAMES`/the
  inline `default_context_windows` dict (both removed). The
  alternative-param-name fallback chain (`context_window`,
  `max_context_length`, `context_length`) is unchanged.
- `ProviderCacheManager._apply_param_overrides()` now calls the same shared
  lookup instead of `_CONTEXT_WINDOW_ALIASES`/`_MAX_TOKENS_ALIASES` (both
  removed), guarding the alias write with `!= 'context_window'`/
  `!= 'max_tokens'` to reproduce the prior "no alias for providers without
  one" behavior exactly (previously a plain dict miss returning `None`).
- Grepped `server/ai_services/`, `server/inference/`, and
  `provider_cache_manager.py` for any other provider-keyed dict of this
  shape; found none beyond the two already known.

Tests added in `server/tests/test_services/test_provider_metadata.py`: a
table-driven equivalence test (Verification's step 7) parametrized over
every provider from all four original dicts, confirming each resolves to
the identical value through the shared lookup; a "providers without a
native alias get the generic key" test; an unknown-provider-defaults test;
and direct tests against both consumers (`ChatHistoryService`'s default
context window and adapter-override native-key write,
`ProviderCacheManager`'s native-alias write for Ollama and its absence for
a plain generic-key provider like OpenAI). 46 new tests pass, plus all 190
pre-existing tests across `test_chat_history_service.py` and
`test_cache_managers.py` still pass unchanged.

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
- Phase 2 [DONE, reduced scope]: `get_user_sessions()` and
  `_cleanup_excess_messages()` no longer load message `content` for rows
  that don't need it, via a new `projection` parameter on
  `DatabaseService.find_many()`; regression tests for session-list grouping
  and for cleanup's token-budget boundary (including legacy rows with no
  `token_count`) pass against SQLite (the only backend testable in this
  environment). The 10,000-row fetch cap and full DB-side
  aggregation/`GROUP BY` primitives from the original plan remain
  unimplemented — extracted to
  `docs/roadmap/chat-history-bounded-aggregation-queries.md`.
- Phase 3 [DONE]: `_CONTEXT_WINDOW_PARAM_NAMES` and the inline
  `default_context_windows` dict are removed from
  `chat_history_service.py`; `_CONTEXT_WINDOW_ALIASES` and
  `_MAX_TOKENS_ALIASES` are removed from `provider_cache_manager.py`; both
  consumers read from one shared provider-metadata module
  (`server/services/provider_metadata.py`); the table-driven equivalence
  test covering both consumers passes
  (`server/tests/test_services/test_provider_metadata.py`).
- Full server test suite passes after each phase, with any external-service
  skips documented per the existing convention (see
  `docs/roadmap/complete/ruff-python-typing-modernization.md`).
