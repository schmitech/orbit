# Ruff Blind-Except Hardening — Implementation Plan

## Summary

Resolve the repository's Ruff `BLE001` (blind-except) findings by replacing
bare `except Exception:` clauses with the specific exception types each call
site actually expects, or by explicitly documenting why a broad catch is
correct there.

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

- `BLE001`: 1,513 findings across 482 files in `server/` and `bin/`.
- None are automatically fixable (`ruff check --fix` reports 0 fixed for this
  rule).
- Heaviest concentrations (by finding count) are in test fixtures/cleanup
  scripts, database/vector-store backends, and a handful of route/service
  files with broad top-level `try/except` blocks around request handling:

  ```
  23  server/tests/test_auth/test_api_key_integration.py
  22  server/services/cache_backends/redis_provider.py
  21  server/tests/cleanup/cleanup_test_users.py
  20  server/utils/template_diagnostics.py
  19  server/tests/test_adapters/test_adapter_reload.py
  19  server/services/chat_history_service.py
  17  server/vector_stores/implementations/qdrant_store.py
  17  server/tests/test_admin/test_admin_integration.py
  17  server/services/mongodb_service.py
  15  server/services/service_factory.py
  15  server/routes/auth_routes.py
  15  server/retrievers/base/intent_http_base.py
  14  server/vector_stores/implementations/chroma_store.py
  14  server/tests/file-adapter/test_file_types_full_pipeline.py
  ```

These counts are a planning baseline and will drift as the repository evolves;
re-run the command below before starting work.

```bash
venv/bin/ruff check server bin --select BLE001 --statistics
```

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
4. Prioritize non-test production code first (`server/services`,
   `server/routes`, `server/retrievers`, `server/vector_stores`,
   `bin/orbit`), since these affect real error visibility. Test fixtures and
   cleanup scripts (the majority of the 1,513 findings) are lower risk and can
   follow, or may be a candidate for a scoped `ruff.toml` per-path ignore if
   the team decides blind catches are acceptable there (see "Ruff
   configuration" below — must be an explicit, documented decision, not a
   silent default).
5. Run the server test suite after each chunk, paying particular attention to
   any test that asserted on a specific exception type or error message that a
   narrowed `except` might now let propagate differently.
6. Suggested chunking, largest first, so each commit stays reviewable:
   1. `server/services/` (backends: mongodb, redis, sqlite/postgres, cache)
   2. `server/vector_stores/` and `server/retrievers/`
   3. `server/routes/` and `server/middleware/`
   4. `bin/orbit/`
   5. `server/tests/` (or scope-ignore, per the team decision in step 4)
7. Re-run the statistics command after each chunk and confirm the count only
   decreases (a `# noqa` suppression should still be visible via
   `ruff check --select BLE001 --statistics` unless the file is fully clean).

## Ruff configuration

No `ruff.toml` change is required to perform this migration incrementally.
Do not add a blanket `BLE001` ignore to `ruff.toml` to make a repo-wide run
pass — that defeats the purpose of the rule. A scoped, documented per-path
ignore for genuinely low-value catches (e.g. test cleanup scripts) is
acceptable if the team decides that tradeoff explicitly, but it must be
recorded here or in `ruff.toml` with a comment explaining the scope and
rationale, not left as a silent blanket suppression.

## Completion criteria

- `venv/bin/ruff check server bin --select BLE001` reports no findings, or
  every remaining finding carries an explicit `# noqa: BLE001` with a reason,
  or falls under an explicitly documented scoped ignore per the section above.
- No behavior change for the intentionally-broad catches identified in step 3
  — they still catch everything they did before, just with a documented
  reason instead of silently.
- The full available test suite passes, with external-service skips or
  failures documented separately (matching the existing convention — see
  `docs/roadmap/complete/ruff-python-typing-modernization.md`).
- `git diff --check` passes.
