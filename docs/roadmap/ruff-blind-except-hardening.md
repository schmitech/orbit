# Ruff Blind-Except Hardening — Implementation Plan

## Summary

Resolve the repository's Ruff `BLE001` (blind-except) findings by replacing
bare `except Exception:` clauses with the specific exception types each call
site actually expects, or by explicitly documenting why a broad catch is
correct there.

Scope is production code only — `server/tests/` is explicitly excluded (see
"Ruff configuration" below).

Unlike the completed `UP006`/`UP035` typing modernization
(`docs/roadmap/complete/ruff-python-typing-modernization.md`), this is **not**
mechanically fixable. Ruff cannot safely auto-fix `BLE001` — narrowing an
`except` clause requires knowing what the wrapped call can actually raise, and
getting it wrong either leaves an unhandled crash where the code assumed
graceful degradation, or continues to hide errors it shouldn't. This must be
done file-by-file with judgment, which is why it is being deferred rather than
folded into feature work.

## Current state

Snapshot taken with Ruff after the Phase 8 (API key expiration) review pass,
2026-09-05:

- `BLE001`: 1,513 findings across 482 files in `server/` and `bin/`, of which
  a significant share are under `server/tests/` — out of scope for this plan
  (see "Ruff configuration" below). Excluding `server/tests/`, production-code
  findings are lower; re-run the scoped command below to get the current
  count.
- None are automatically fixable (`ruff check --fix` reports 0 fixed for this
  rule).
- Heaviest concentrations (by finding count) in production code are in
  database/vector-store backends and a handful of route/service files with
  broad top-level `try/except` blocks around request handling:

  ```
  22  server/services/cache_backends/redis_provider.py
  20  server/utils/template_diagnostics.py
  19  server/services/chat_history_service.py
  17  server/vector_stores/implementations/qdrant_store.py
  17  server/services/mongodb_service.py
  15  server/services/service_factory.py
  15  server/routes/auth_routes.py
  15  server/retrievers/base/intent_http_base.py
  14  server/vector_stores/implementations/chroma_store.py
  ```

  (`server/tests/` findings — e.g. `test_auth/test_api_key_integration.py`,
  `cleanup/cleanup_test_users.py`, `test_adapters/test_adapter_reload.py`,
  `test_admin/test_admin_integration.py`,
  `file-adapter/test_file_types_full_pipeline.py` — are excluded from this
  count and from this plan's scope entirely.)

These counts are a planning baseline and will drift as the repository evolves;
re-run the command below before starting work.

```bash
venv/bin/ruff check server bin --select BLE001 --statistics --exclude server/tests
```

## Progress log

Work is landing incrementally on `chore/ruff-ble001-hardening`, one file (or a
few related files) per commit, per the chunking plan below. Deliberately
paced across sessions rather than in one pass.

- 2026-09-07: `server/services/cache_backends/redis_provider.py` (22 → 0).
  Narrowed 2 catches to their real exception surface (JSON decode,
  connection-pool attribute introspection); justified the rest with
  `# noqa: BLE001` — they guard the redis-py client boundary and feed a
  circuit breaker, so must not crash on network/library errors outside
  `RedisError`.
- 2026-09-07: `server/services/chat_history_service.py` (27 → 0). Narrowed 1
  catch (pure config-derived token-budget arithmetic) to
  `(TypeError, ValueError, KeyError, AttributeError)`; justified the rest —
  database-backend calls, background worker loops, a pluggable tokenizer with
  no fixed exception surface, and per-item best-effort cleanup loops.
- 2026-09-07: `server/services/auth_service.py` (21 → 0). All justified: every
  site already catches specific DB/value exception types first, and the
  trailing `except Exception` is a deliberate last-resort so auth flows fail
  safe (return `False`/`None`) instead of crashing the caller.
- 2026-09-07: 100 files under `server/ai_services/` (187 provider-boundary
  catches resolved). These catches preserve the existing fallback behavior
  for unstable third-party SDKs and optional provider runtimes while making
  the intentional broad exception surface explicit.
- 2026-09-13: `server/services/mongodb_service.py` (17 → 0). Narrowed 2
  catches (ObjectId string conversion) to
  `(TypeError, ValueError, bson.errors.InvalidId)`; justified the rest —
  motor/pymongo driver calls and best-effort attribute probing in
  `_sanitize_document` for arbitrary third-party response objects.
- 2026-09-13: `server/services/service_factory.py` (15 → 0). All justified:
  each catch wraps a pluggable service's startup initialization and must not
  crash app boot — degrades to `app.state.<service> = None` instead.
- 2026-09-13: `server/services/prompt_service.py` (15 → 0). Narrowed 4
  catches (cached-value JSON/dict parsing, version-string increment) to
  `(json.JSONDecodeError, TypeError, KeyError, AttributeError)` /
  `(ValueError, IndexError, AttributeError, KeyError)`; justified the rest —
  cache-backend (Redis/Memcached) calls and database-backend calls.
- 2026-09-13: `server/services/api_key_service.py` (15 → 0). All justified:
  database-backend calls (mongodb/sqlite), plus the key-validation path which
  must fail safe (`return False`) rather than crash the caller, matching the
  precedent set by `auth_service.py`.
- 2026-09-13: `server/services/postgres_service.py` (13 → 0). All justified:
  psycopg driver and schema-DDL calls have a broad, version-dependent error
  surface; the broad handlers preserve the service's existing result fallbacks,
  expected concurrent-DDL-race handling, and best-effort cleanup.
- 2026-09-16: `server/routes/auth_routes.py` (30 → 0). Narrowed 4 catches
  (datetime `isoformat()`/`str()` conversion of user timestamp fields) to
  `(AttributeError, ValueError, TypeError)`; justified the remaining 26 —
  every one is a top-level FastAPI route-handler boundary that must convert
  an unexpected failure into a 500 response instead of crashing the request,
  matching the precedent set by `auth_service.py`.
- 2026-09-16: 28 files across `server/retrievers/`, `server/vector_stores/`,
  `server/services/`, `server/routes/`, and `bin/orbit/` (355 findings
  resolved). Narrowed a handful of catches with a known, specific exception
  surface (JSON/dict parsing in `routes_configurator.py`/`file_routes.py`,
  base64 decode and file I/O in `bin/orbit/services/auth_service.py`); the
  rest are justified with `# noqa: BLE001` — pluggable vector-store/DB client
  boundaries (qdrant, chroma, pinecone, pgvector, duckdb, milvus, marqo,
  weaviate, memcached, sqlite), diagnostic tooling that probes arbitrary
  retriever/extractor internals, FastAPI route handlers that must degrade to
  a 5xx, and best-effort cleanup/cache/telemetry/audit paths. No behavior
  change. Files: `server/utils/template_diagnostics.py`,
  `server/retrievers/base/intent_sql_base.py`,
  `server/retrievers/base/intent_http_base.py`,
  `server/retrievers/base/intent_composite_base.py`,
  `server/retrievers/implementations/intent/intent_agent_retriever.py`,
  `server/vector_stores/implementations/{qdrant,chroma,pinecone,pgvector,duckdb,marqo,weaviate,milvus}_store.py`,
  `server/vector_stores/services/template_embedding_store.py`,
  `server/services/sqlite_service.py`,
  `server/services/file_metadata/metadata_store.py`,
  `server/services/file_processing/file_processing_service.py`,
  `server/services/cache_backends/{sqlite,memcached}_provider.py`,
  `server/services/autocomplete_service.py`,
  `server/services/audit/elasticsearch_audit_strategy.py`,
  `server/services/parallel_adapter_executor.py`,
  `server/routes/{metrics,routes_configurator,file,health}_routes.py`,
  `bin/orbit/services/{server,auth}_service.py`.

Running baseline (production code, `server/tests/` excluded): 1022 → 565
(457 resolved).
- 2026-09-16: 51 files across `server/retrievers/`, `server/vector_stores/`,
  `server/services/` (including `audit/`, `reload/`, `loader/`, `cache/`,
  `chat_handlers/`), `server/routes/admin/`, `server/inference/`,
  `server/config/`, `server/datasources/`, `server/utils/`, and
  `bin/orbit/services/` (285 findings resolved). Narrowed catches with a
  known exception surface: `sqlglot.errors.SqlglotError` in
  `query_guard.py`'s SQL parsing, `json.JSONDecodeError`/`TypeError` in
  several JSON-parsing sites (`intent_http_json_retriever.py`,
  `mcp_client_service.py`, `thread_service.py`), `bson.errors.InvalidId` in
  `intent_mongodb_retriever.py`'s ObjectId conversion, `ImportError`/
  `AttributeError` in optional-dependency import fallbacks
  (`metrics_service.py`, `admin/adapters.py`'s dynamic adapter import), and
  file I/O / dict-access narrowing in `moderator_service.py` and
  `config_manager.py`'s preset resolvers. The rest are justified with
  `# noqa: BLE001` — pluggable retriever/vector-store/datasource/audit-backend
  client boundaries with unstable third-party exception hierarchies, FastAPI
  route handlers and websocket connections that must degrade gracefully
  instead of crashing, generative-media pipeline steps that must isolate a
  provider failure, hot-reload/cache-eviction paths that must not break the
  reload cycle, and best-effort cleanup/telemetry/audit paths. No behavior
  change.

Running baseline (production code, `server/tests/` excluded): 1022 → 278
(744 resolved). Next up: re-run the statistics command to pick the
next-largest file — remaining findings are mostly single-digit counts spread
across `server/retrievers/implementations/`, `server/vector_stores/`,
`server/routes/admin/`, and `server/services/`.

### Rule meaning

`BLE001` flags `except Exception:` (and bare `except:`) clauses. Catching the
base `Exception` class swallows programming errors (`TypeError`, `KeyError`,
`AttributeError` from a typo or bad assumption) alongside the specific
failures the code intends to handle (a database timeout, a malformed
response), which makes bugs silently disappear instead of surfacing during
development or triggering the right alerting in production.

## Why this is hard, unlike the typing migration

- **No safe default.** `Optional[X]` → `X | None` is a pure syntax rewrite
  with one correct answer. `except Exception:` → `except SomeSpecificError:`
  requires reading the wrapped code (and its transitive callees, including
  third-party client libraries) to know the real exception surface.
- **Some blind catches are intentional and correct**, and must be preserved,
  not narrowed:
  - Top-level FastAPI route handlers and background workers that must never
    crash the process on an unexpected error, and instead convert it to a
    5xx/logged failure.
  - Best-effort cleanup/telemetry paths (a failed audit-log write, a failed
    cache invalidation) that should not fail the primary operation.
  - Plugin/adapter boundaries calling arbitrary third-party SDKs (vector
    stores, LLM providers) whose exception hierararchies are not fully known
    or stable across versions.

  For these, the fix is not narrowing the exception type but adding a
  `# noqa: BLE001` with a one-line reason, or restructuring so the broad catch
  is clearly scoped to only the risky call.
- **Some are real bugs waiting to happen**: a narrow operation (e.g. parsing
  a JSON field, converting a type, a single dict lookup) wrapped in
  `except Exception:` that should catch `(ValueError, KeyError, TypeError)`
  specifically, so an unrelated bug introduced later isn't silently absorbed
  by the same handler.

## Implementation plan

1. Create a dedicated maintenance branch so this mechanical-but-manual diff
   stays isolated from feature work; land it in reviewable, directory-scoped
   chunks (see step 6) rather than one repository-wide commit.
2. Record the baseline before editing:

   ```bash
   venv/bin/ruff check server bin --select BLE001 --statistics
   ```

3. Triage findings into three buckets per call site:
   - **Narrow**: replace `except Exception:` with the specific exception
     type(s) the wrapped call can raise (check the library's documented
     exceptions, or what the existing code already does with the caught
     value — e.g. `e.response.status_code` implies an HTTP client exception
     type is expected).
   - **Justify and suppress**: for an intentionally broad catch (see "Why
     this is hard" above), add `# noqa: BLE001` with a short inline reason
     (e.g. `# noqa: BLE001 - must not crash the request handler on an
     unexpected adapter error`).
   - **Restructure**: where a broad catch wraps both a risky call and
     unrelated code, narrow the `try` block to just the risky call so a
     smaller, more specific `except` becomes possible.
4. Scope is production code only: `server/services`, `server/routes`,
   `server/retrievers`, `server/vector_stores`, `bin/orbit`, etc. `server/tests/`
   is excluded from this plan entirely (see "Ruff configuration" below) — test
   fixtures and cleanup scripts are lower value to harden and are not part of
   the completion criteria.
5. Run the server test suite after each chunk, paying particular attention to
   any test that asserted on a specific exception type or error message that a
   narrowed `except` might now let propagate differently.
6. Suggested chunking, largest first, so each commit stays reviewable:
   1. `server/services/` (backends: mongodb, redis, sqlite/postgres, cache)
   2. `server/vector_stores/` and `server/retrievers/`
   3. `server/routes/` and `server/middleware/`
   4. `bin/orbit/`

   `server/tests/` is out of scope and is not part of this chunking plan.
7. Re-run the statistics command after each chunk and confirm the count only
   decreases (a `# noqa` suppression should still be visible via
   `ruff check --select BLE001 --statistics --exclude server/tests` unless the
   file is fully clean).

## Ruff configuration

`server/tests/` is excluded from this plan's scope: unit test fixtures and
cleanup scripts routinely swallow arbitrary exceptions in setup/teardown, and
narrowing them is low value relative to production code. Add a scoped
per-path ignore to `ruff.toml`:

```toml
[lint.per-file-ignores]
"server/tests/**" = ["BLE001"]
```

Do not add a blanket `BLE001` ignore covering `server/` or `bin/` as a whole
to make a repo-wide run pass — that defeats the purpose of the rule for
production code. This `server/tests/` ignore is the one explicit, documented
exception; anything outside it must still be narrowed or carry a
`# noqa: BLE001` with a reason.

## Completion criteria

- `venv/bin/ruff check server bin --select BLE001 --exclude server/tests`
  reports no findings, or every remaining finding carries an explicit
  `# noqa: BLE001` with a reason, or falls under an explicitly documented
  scoped ignore per the section above. `server/tests/` is out of scope and
  excluded from this criterion.
- No behavior change for the intentionally-broad catches identified in step 3
  — they still catch everything they did before, just with a documented
  reason instead of silently.
- The full available test suite passes, with external-service skips or
  failures documented separately (matching the existing convention — see
  `docs/roadmap/complete/ruff-python-typing-modernization.md`).
- `git diff --check` passes.
