# Retrievers Implementations Cleanup — Phased Follow-ups

## Summary

A `/simplify` pass (four parallel review angles — reuse, simplification,
efficiency, altitude) over `server/retrievers/implementations/` (~16.5K
lines: ~10 `intent_*_retriever.py` DB-backend retrievers, plus `relational/`,
`vector/`, `qa/`, `composite/`, `file/`) and the shared bases it depends on
(`server/retrievers/base/intent_sql_base.py`, `base_sql_database.py`,
`abstract_vector_retriever.py`, `intent_http_base.py`,
`domain_strategies/`).

The safe, single-file (or small, mechanically-safe cross-file) findings were
applied directly in that session:

- Deleted two dead, unreferenced classes (`VectorDBRetriever`, `SQLRetriever`)
  from `base/base_retriever.py`.
- Extracted the duplicated file-database-path resolution
  (`database_path > database > db_path > default`) out of
  `intent_sqlite_retriever.py` and `intent_duckdb_retriever.py` into
  `SQLConnectionMixin.resolve_file_database_path()`
  (`base/base_sql_database.py`).
- Extracted the duplicated "collection not found → `HTTPException(404)`"
  logic out of `chroma_retriever.py`, `qdrant_retriever.py`,
  `pinecone_retriever.py`, `milvus_retriever.py` into
  `AbstractVectorRetriever._raise_collection_not_found()`.
- `qa_sql_retriever.py`: removed a redundant re-tokenization of the same
  query in `get_relevant_context` / `_get_search_query`.
- `composite_intent_retriever.py`'s `get_routing_statistics()`: parallelized
  the per-child-adapter template-store stats fetch with `asyncio.gather`
  instead of sequential awaits in a loop.

Everything below touches shared base classes across multiple backend files,
changes an established (if messy) parameter-binding contract, or needs
behavior verification this session couldn't do safely, so it's phased for
independent follow-up rather than folded into the same-session pass.

**Priority order: Phase 1 (Pinecone) → Phase 2 (SQL binding contract) →
Phase 3 (HTTP consolidation) → Phase 4 (connection-layer dedup) → Phase 5
(efficiency).** This order was corrected after an external review of the
first draft of this doc found that draft's own Phase 1/2/3 ordering and
several of its root-cause claims didn't hold up — see the per-item notes
below for what changed and why.

Reference: review findings were produced by four parallel agent passes
(reuse, simplification, efficiency, altitude) over
`server/retrievers/implementations/` and the bases above on 2026-11-15; this
doc's phasing and several item descriptions were corrected against a second,
independent review on the same date (see "Corrected from external review"
notes per item).

---

## Phase 1 — Pinecone: eliminate the duplicate embed+search pipeline

- [ ] **Delete Pinecone's redundant `get_relevant_context` override, after
      defining the output contract it must preserve.**
      `vector/pinecone_retriever.py:197-276` doesn't just duplicate the base
      pipeline's logic — it structurally double-executes it: the override's
      first line is `await super().get_relevant_context(...)`, which runs the
      *entire* base pipeline (collection resolution, embed, search, filter,
      format, truncate) and returns a result that is **thrown away**; the
      override then independently re-embeds the query and re-runs
      `vector_search` itself, building its own `context_items` list from
      scratch. So every Pinecone query embeds and searches **twice** today,
      not once with redundant logic sitting next to it. Confirmed via code
      read, not inference: `pinecone_retriever.py:206` calls `super()...`,
      and `pinecone_retriever.py:214-220` immediately calls `self.embed_query`
      and `self.vector_search` again.
      The two code paths are not behaviorally identical, so this isn't a pure
      deletion — it's a contract decision:
      - The override's `item["metadata"]["score"] = score` (the raw Pinecone
        score, in addition to `similarity`) does **not** exist in the base
        path's output.
      - The base path's output includes truncation/diagnostic metadata the
        override never adds: `total_available`, `truncated`, `result_count`,
        `vector_search_count`, `after_confidence_filtering`,
        `after_domain_filtering` (`base/abstract_vector_retriever.py:477-486`).
      - The base path calls `_ensure_datasource_initialized()` explicitly;
        the override relies on that happening inside the discarded
        `super()` call, which is incidental, not a documented contract.
      Fix, in order:
      1. Decide and write down the intended output contract (recommended:
         adopt the base's full metadata set, and add `metadata["score"]` to
         the base path behind the existing `score is not None` branch it
         already has — Pinecone isn't the only score-based backend, so this
         benefits others too, not just Pinecone).
      2. Write a mocked-client test (no real Pinecone index needed) that
         asserts `embed_query` and `vector_search` are each called **exactly
         once** per `get_relevant_context` call, and that the output includes
         the agreed-on metadata fields.
      3. Delete the override once that test passes against the base class
         directly.
      Corrected from external review: the original draft of this item
      (previously in "Phase 5") undersold the bug as "redundant pipeline
      logic" and recommended a real-index comparison before fixing. The
      actual defect is a structural double-request (every query hits the
      embedding service and the vector DB twice), which is a correctness/cost
      bug worth fixing now, not just a style cleanup — and it can be verified
      with mocks (asserting call counts), so a live index isn't a blocker.
      Moved to Phase 1 and given top priority as a result.

## Phase 2 — SQL parameter-binding extension point

This is the most-converged finding across review angles (reuse,
simplification, altitude all named the same root cause independently), but
the fix is more involved than "add one hook" — see the corrections below.

- [ ] **Add a parameter-binding hook on `IntentSQLRetriever` that has access
      to the template's parameter definitions, not just the rendered SQL
      string — then delete the regex-sniffing from the base and the
      duplicated conversions from the subclasses.**
      `base/intent_sql_base.py:1524-1575` (`_execute_template`) regex-sniffs
      the *rendered SQL string* to decide dialect
      (`%(name)s` → "PostgreSQL-style", `:name` → "DuckDB/SQLite-style", `?`
      → "SQLite-style"), with backend names hardcoded in comments inside
      otherwise-generic shared code — even though a clean extension point
      already exists one line above it (`dialect = resolve_dialect(...)`).
      Meanwhile `intent_sqlite_retriever.py:140-175`,
      `intent_duckdb_retriever.py:182-219`, and
      `intent_athena_retriever.py:79-169` (plus its private
      `_escape_literal_percents_for_pyformat`) each *independently*
      re-implement the same placeholder-style conversion a second time, with
      different target dialects.
      Corrected from external review: the original draft proposed a
      `format_query_params(sql, params)` hook that infers everything from the
      driver's target placeholder style alone. That's insufficient — the
      *source* template's placeholder style and positional ordering can't be
      recovered from the rendered SQL text or the target style alone (e.g. a
      positional `?` template's parameter order comes from the template's
      `parameters` list, not from the SQL string). The hook needs the
      template's parameter definitions passed in, not just `(sql, params)`.
      The new hook/implementation must explicitly handle, with test cases for
      each:
      - Repeated placeholders (the same named or positional parameter
        appearing more than once in one query).
      - Optional parameters with defaults that are absent from the caller's
        `parameters` dict entirely (today's default-filling logic in
        `_execute_template`, e.g. `base/intent_sql_base.py:1472-1475` and the
        per-style default-filling at L1535-1540/1549-1554, must keep working
        under the new hook).
      - Literal text or SQL comments that contain placeholder-like substrings
        (e.g. a string literal containing `%(name)s` or `:foo` that must not
        be treated as a real placeholder).
      - PostgreSQL type casts (`::type`), whose `::` can collide with naive
        `:name`-style regex matching.
      - Literal `%` characters in LIKE patterns or other string literals that
        must not be mistaken for `%(name)s` pyformat syntax (this is exactly
        what Athena's existing `_escape_literal_percents_for_pyformat` works
        around today — the new hook must keep handling this case, not drop
        it).
      - The bound-`LIMIT` row-cap enforcement
        (`clamp_bound_limit_parameter` in `base/query_guard.py`, invoked from
        `base/intent_sql_base.py:1504-1508`) must keep working when the
        placeholder conversion changes — this depends on correctly
        identifying which parameter is the bound LIMIT value, which in turn
        depends on the same template-parameter-order information the hook
        needs.
      - `intent_sqlite_retriever.py:163-167`'s existing `ValueError` guard
        (dict params against `?` placeholders) is validation for a case the
        current sniffing can get wrong — keep equivalent mismatched-binding
        validation in the new implementation rather than silently dropping
        it; don't assume the new hook makes all such mismatches impossible.
      Needs a dedicated PR with placeholder-conversion tests covering every
      case above, for all five affected backends (postgres, sqlite, duckdb,
      mysql, athena), before merging — not a same-session mechanical change.

## Phase 3 — HTTP retriever consolidation (retry loop + Firecrawl)

- [ ] **Add retry support to `IntentHTTPRetriever._execute_http_request** and
      have the three HTTP-backed retrievers use it instead of hand-rolling
      their own loop.** `intent_graphql_retriever.py:206-248`,
      `intent_http_json_retriever.py:400-443`, and
      `intent_firecrawl_retriever.py:440-472` each independently implement an
      identical retry-with-backoff loop (max_retries/retry_delay, no-retry on
      4xx, retry on 5xx, `asyncio.sleep`), even though
      `base/intent_http_base.py:1237`'s `_execute_http_request` is the
      designated shared HTTP call point — it just doesn't support retries
      today, so all three bypassed it. Fix: add the retry loop to the base
      method (parameterized by max_retries/retry_delay, defaulting to
      no-retry so existing non-retrying call sites are unaffected), then
      delete the three duplicated loops.
      Needs retry-behavior tests (including the 4xx/5xx distinction) before
      the three call sites switch over.
- [ ] **Treat Firecrawl's `_get_relevant_context_impl` consolidation as
      behavior reconciliation, not a pure formatter swap.**
      `intent_firecrawl_retriever.py:212-311` was originally described here
      as differing from the base's `_get_relevant_context_impl`
      (`base/intent_http_base.py:781-978`) only in using an async formatter.
      On closer comparison that's not the only difference — confirmed by
      reading both implementations side by side:
      - **Cancellation**: the base checks `cancel_event` before template
        search and between each template attempt
        (`base/intent_http_base.py:785, 814`); Firecrawl's version has no
        `cancel_event` handling at all.
      - **Required-parameter checks**: the base explicitly skips a template
        if any `required` parameter is still missing after extraction
        (`base/intent_http_base.py:843-855`), with a comment explaining why
        (avoids a doomed live call with an unfilled placeholder); Firecrawl
        has no equivalent check.
      - **Follow-up storage**: the base calls
        `self._store_followup_turn(kwargs.get('session_id'), ...)` on success
        (`base/intent_http_base.py:908, 920`); Firecrawl's version never
        calls it.
      - **Failure metadata**: the base tracks `failed_templates` with
        per-template error strings and includes them in the final
        below-threshold/all-failed response metadata
        (`base/intent_http_base.py:811-812, 851, 862, 940-963`); Firecrawl
        tracks only `any_above_threshold` and a bare `candidates` list with
        template id + similarity, no per-template failure reasons.
      - **Response-generator fallback**: the base has an entire
        `self.response_generator`-driven formatting branch
        (`base/intent_http_base.py:881-918`) that builds LLM-context content
        from a domain-aware formatter before falling back to
        `_format_http_results`; Firecrawl has no equivalent branch — it only
        ever calls its own async formatter.
      - **What the formatter hook needs**: Firecrawl's call already passes
        `query=query` and `usage_sink=usage_sink` to
        `_format_http_results_async` for chunk ranking
        (`intent_firecrawl_retriever.py:275-282`) — any async-formatter hook
        added to the base must forward both of these, not just
        `results`/`template`/`parameters`/`similarity`.
      Fix: before touching code, write down explicitly which of the five
      behavioral differences above should survive consolidation (e.g.
      cancellation and required-parameter checks are very likely bugs in
      Firecrawl's version that should simply be adopted from the base;
      follow-up-turn storage and failed-template metadata need a product
      decision on whether Firecrawl should support follow-up questions the
      same way; the response-generator branch may or may not apply to
      scraped content). Only then extend the base method with an
      async-formatter hook (forwarding `query`/`usage_sink`) and reconcile
      Firecrawl onto it.
      Corrected from external review: the original item understated this as
      "solely to swap in an async formatter" and proposed deleting
      Firecrawl's override outright. Don't delete it until the behavioral
      differences above are each explicitly kept, adopted from the base, or
      deliberately dropped — a mechanical hook-and-delete would silently
      change cancellation, required-parameter, follow-up, and failure-
      metadata behavior for every Firecrawl query.
      Needs the full no-match/below-threshold/rerank test matrix run against
      all four affected retrievers (graphql, http_json, firecrawl, and the
      base's direct consumers) before merging.

## Phase 4 — Cross-hierarchy connection duplication (intent/ vs relational/)

- [ ] **Factor a shared per-DB connection mixin, extracted one backend at a
      time, with pooling/timeout changes handled as a separate step.**
      `implementations/intent/intent_postgresql_retriever.py` (`create_connection`
      L59-122, `_execute_raw_query` L144-168, default port/database/test-query
      methods) and `implementations/relational/postgresql_retriever.py`
      (`create_connection` L47-73, `_execute_raw_query` L83+) are near
      line-for-line copies of the same psycopg connect / `SELECT version()`
      liveness check / cursor-commit-rollback logic. The same duplicate pair
      exists for MySQL (`intent_mysql_retriever.py` vs
      `relational/mysql_retriever.py`) and SQLite (`intent_sqlite_retriever.py`
      vs `relational/sqlite_retriever.py`).
      Corrected from external review: the original draft called
      `IntentSQLRetriever` and `BaseSQLDatabaseRetriever` "two unrelated base
      contracts" — they are not. `IntentSQLRetriever` already extends
      `BaseSQLDatabaseRetriever` directly
      (`base/intent_sql_base.py:27`:
      `class IntentSQLRetriever(IntentDomainComponentsMixin,
      BaseSQLDatabaseRetriever)`), so the two hierarchies already share a
      base — the duplication is in the *driver-specific* `create_connection`/
      `_execute_raw_query` bodies within that shared hierarchy, not a split
      between two disconnected class trees. The original draft also claimed
      the `relational/` Postgres variant lacks SSL support that the `intent/`
      variant has; that's also wrong — `relational/postgresql_retriever.py`
      already resolves `sslmode` from config (line 28) and passes it to the
      connection call (line 57). The actual capability gap (if any) between
      the two Postgres variants needs re-auditing per-feature (pooling,
      statement_timeout, reconnection behavior) rather than assumed from the
      first pass's read.
      Driver-specific reuse is still worth doing, but:
      1. Extract one backend's connection mixin at a time (start with
         SQLite, the simplest), not all three/four at once.
      2. Treat any pooling/timeout/statement_timeout capability change as a
         separate, explicit step from the structural extraction — i.e. first
         make `intent/` and `relational/` share identical connection code
         with identical behavior, then decide separately (and visibly) if one
         variant's extra capability (if confirmed to exist after re-auditing)
         should be added to the other.
      3. Each backend's extraction needs explicit tests for reconnection
         (does a dropped connection get re-established the same way),
         transaction behavior (commit/rollback semantics preserved), and
         shutdown (connection cleanup on `close()`), not just a "connects
         successfully" smoke test.
- [ ] **Collapse the repeated small SQL helpers across sibling DB retrievers**
      once the mixin above exists, since several of these are instances of
      the same problem at smaller scale:
      - `_is_connection_alive` reimplemented identically in
        `intent_postgresql_retriever.py:128-142`,
        `intent_sqlite_retriever.py:117-128`,
        `intent_duckdb_retriever.py:160-169`,
        `intent_athena_retriever.py:56-67` — belongs once on
        `BaseSQLDatabaseRetriever` using the existing `get_test_query()`.
      - SELECT/WITH dispatch duplicated 5x across
        `intent_postgresql_retriever.py:155-156`,
        `intent_mysql_retriever.py:101-102`,
        `intent_sqlite_retriever.py:177-178`,
        `intent_duckdb_retriever.py:221-222`,
        `intent_athena_retriever.py:102-103` — one shared `_is_select_query()`
        helper.
      - `SQLQueryExecutionMixin.execute_query_with_retry`
        (`base/base_sql_database.py:177-200`) is defined but unused — every
        retriever reimplements its own retry/rollback instead of calling it;
        worth checking why it was never adopted before wiring retrievers up
        to it (may have been superseded by something else).
      Fold into the same per-backend PRs as the connection-mixin extraction
      above, rather than a separate mechanical sweep.

## Phase 5 — Efficiency: caching and concurrency

- [ ] **Cache `_build_openai_tools`'s output instead of rebuilding it per
      request.** `intent/intent_agent_retriever.py:349` rebuilds the full
      OpenAI tool-schema list (`tool.to_openai_tool()` per cached
      `ToolDefinition`) on every call to `_try_native_function_calling`, even
      though `self._function_tools` is only loaded once per adapter lifetime
      in `_load_function_tools`. Fix: build once alongside
      `_load_function_tools` / `initialize()`, cache as
      `self._openai_tools`, and invalidate only when templates/tools reload.
      Deferred because: needs the invalidation path confirmed against
      whatever template-reload mechanism exists today, so a stale cached
      tool list is never served after a reload — not verified this session.
- [ ] **Precompute/cache compiled regex patterns in
      `intent/domain/extraction/value_extractor.py`.**
      `_extract_from_context` (L117-118) calls
      `re.compile(pattern_str, re.IGNORECASE)` inside a nested
      `for term in search_terms: for pattern_str in context_patterns:` loop,
      run per parameter per query, even though the patterns are built from
      static domain-config field names/synonyms. Fix: precompute/cache
      compiled patterns per field at domain-config load time (e.g. in
      `DomainConfig` or an `lru_cache`/dict keyed by `term`) instead of
      recompiling per request.
      Deferred because: low individual risk, but bundled here rather than
      applied directly since it touches the extraction hot path shared by
      every intent query and deserves a quick before/after extraction-
      accuracy check (same patterns, just compiled once) rather than being
      folded into an already-large same-session diff.

## Phase 6 — Vector retriever follow-ups

- [ ] **Hoist duplicated collection-name resolution into
      `AbstractVectorRetriever`.** `chroma_retriever.py:46-54` and
      `qdrant_retriever.py:167-175` (and similar in other vector retrievers)
      repeat the same "check `adapter_config['collection']` else
      `datasource_config['collection']`" fallback chain. Fix: a shared
      `_resolve_collection_name()` on the abstract base, since it's
      datasource-agnostic.
      Small and low-risk — left for a follow-up pass rather than this
      session only because it wasn't part of the convergent findings applied
      directly and the session's edit budget was spent on the
      higher-confidence collection-not-found dedup instead.

---

## Out of scope / accepted as-is

Noted by the review and explicitly judged not worth fixing, or already
correct:

- **False positive, corrected from external review**: an earlier draft of
  this doc flagged `milvus_retriever.py:201`'s `self.distance_scaling_factor`
  (used in its L2-distance-to-similarity branch) as unset and a latent
  `AttributeError`. It is in fact set unconditionally in
  `AbstractVectorRetriever.__init__`
  (`base/abstract_vector_retriever.py:57`:
  `self.distance_scaling_factor = self.datasource_config.get(
  'distance_scaling_factor', 200.0)`), which `MilvusRetriever.__init__` calls
  via `super().__init__(...)`. Confirmed by reading both files. No action;
  removed from this roadmap.
- `base/intent_composite_base.py`'s `_search_all_template_stores`
  (~L1285-1316) already fans out child-adapter template searches
  concurrently via `asyncio.gather` with per-adapter timeouts — the
  suspected main composite-retriever inefficiency, but confirmed already
  implemented correctly. No action.
- `_rerank_candidates`/`_calculate_combined_scores`
  (`base/intent_composite_base.py`) make one batched rerank call for all
  candidates, not one call per candidate — no redundant LLM calls found.
- `intent/domain/extraction/extractor.py` batches LLM fallback extraction via
  `extract_multiple` when more than one parameter is missing, only falling
  back to per-parameter LLM calls when exactly one parameter is missing —
  correct as-is.
- Vector retrievers (chroma, qdrant, pinecone, elasticsearch, redis, milvus)
  embed-then-search sequentially, but search genuinely depends on the
  embedding result — a true dependency chain, not a missed concurrency
  opportunity.
- No closures-over-large-captured-scope / long-lived-object memory-leak
  patterns were found in this directory — the composite retriever stores
  only adapter references/dicts, not full captured environments.
- `intent/domain_strategies/registry.py` + `generic.py` are clean:
  `_builtin_strategies` is empty, everything routes through
  `GenericDomainStrategy` driven by YAML config, with no isinstance/backend
  branching to fix.
- `base/query_guard.py`'s dialect map (postgres/mysql/sqlite/duckdb/…) is a
  legitimate table-driven lookup for `sqlglot`, not an altitude smell.
- `intent_mongodb_retriever.py` and `intent_elasticsearch_retriever.py`
  correctly override `_execute_template` wholesale instead of reusing the
  SQL-placeholder-sniffing base path — the right pattern for non-SQL
  backends; not touched by Phase 1's fix.
- `intent_postgresql_retriever.py` / `intent_mysql_retriever.py` have no
  altitude issues of their own — they're clean only because the mess lives
  upstream in the shared base (Phase 1).
