# Ruff Python Typing Modernization

## Summary

Modernize the server's Python type annotations and imports to resolve the
existing Ruff `UP006` and `UP035` findings. This is repository-wide technical
debt and is not specific to the authentication roadmap.

The project targets Python 3.11 in `ruff.toml`, so the modern syntax requested
by Ruff is supported. The preferred resolution is to update the code rather
than suppress these rules.

## Current state

Snapshot taken with Ruff 0.16.5 on 2026-09-03:

- `UP006`: 3,753 findings across 456 files.
- `UP035`: 833 findings across 459 files.
- Total: 4,586 findings, of which Ruff currently reports 3,835 as
  automatically fixable.

These counts are a planning baseline and will change as the repository evolves.

### Rule meanings

- `UP006` replaces legacy `typing` generics with PEP 585 built-in generics,
  such as `Dict[str, Any]` to `dict[str, Any]` and `List[str]` to `list[str]`.
- `UP035` replaces deprecated `typing` imports. For example, runtime protocol
  types such as `Callable` and `Iterable` should be imported from
  `collections.abc` where appropriate.

## Implementation plan

1. Create a dedicated maintenance branch or commit so the mechanical diff is
   isolated from feature work.
2. Record the baseline before editing:

   ```bash
   venv/bin/ruff check server --select UP006,UP035 --statistics
   ```

3. Apply Ruff's safe automatic fixes:

   ```bash
   venv/bin/ruff check server --select UP006,UP035 --fix
   ```

4. Run the check again and resolve the remaining deprecated imports manually:

   ```bash
   venv/bin/ruff check server --select UP006,UP035
   ```

5. Review changes involving runtime annotation inspection, type aliases,
   dataclasses, Pydantic models, and imports used outside annotations. These
   are the areas most likely to need more than a mechanical replacement.
6. Remove unused `typing` imports and format the changed files.
7. Run the server test suite, paying particular attention to configuration
   loading, adapters, database backends, authentication, and API model
   serialization.

The work may be split into directory-scoped commits if a single repository-wide
change is too large to review comfortably. Each commit should leave its scope
passing `UP006` and `UP035` checks.

## Ruff configuration

No `ruff.toml` change is required to perform this migration. Its
`target-version = "py311"` setting is compatible with built-in generic syntax.

Do not permanently add `UP006` or `UP035` to the ignore list merely to make a
repo-wide Ruff run pass. If a temporary suppression is needed while migrating
directory by directory, document its scope and remove it once the migration is
complete. Explicitly defining the intended lint rule selection can be handled
separately as a lint-policy decision.

## Completion criteria

- `venv/bin/ruff check server --select UP006,UP035` reports no findings.
- No unnecessary legacy collection imports remain in `typing`.
- The full available test suite passes, with external-service skips or failures
  documented separately.
- `git diff --check` passes.
- No permanent Ruff suppression was introduced for `UP006` or `UP035`.
