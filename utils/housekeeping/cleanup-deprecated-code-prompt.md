You are working in the Orbit repository. Clean up deprecated, legacy, or backward-compatible code in:

<TARGET_FILE_OR_MODULE>

Scope:
- Remove code paths, aliases, shims, fallback mappings, imports, warnings, docstrings, and comments that exist only for deprecated or backward-compatible behavior.
- Keep the change narrowly scoped to the target file/module and directly required tests.
- Do not remove functional capability gates, provider-specific behavior, graceful degradation, or current fallback behavior unless it is clearly only legacy compatibility scaffolding.
- Be especially careful with provider capability checks. A method whose name sounds compatibility-related may still be required to avoid sending unsupported parameters to some providers.
- Stale wording-only cleanup in comments/docstrings is safe to batch when it does not change behavior.

Workflow:
1. Inspect the target file/module.
2. Search for direct references and tests using terms such as:
   `deprecated`, `backward`, `compat`, `legacy`, `alias`, `shim`, and relevant symbol names.
3. For removed write-side shims, grep consumers before removing. This includes code that copies, sets, aliases, or normalizes values for other modules to read later. If consumers are found, update them to read from the canonical source rather than restoring the shim.
4. Determine whether each match is:
   - removable compatibility/deprecation scaffolding,
   - live functional behavior,
   - a current graceful fallback,
   - or only stale wording/commentary.
5. When a fallback returns a non-empty/truthy value or permissive result, verify the new no-capabilities/no-config/no-provider path before removing it.
6. Remove only removable scaffolding and clean stale comments/docstrings from the target area.
7. Update focused tests if behavior intentionally changes.
8. Add a regression test when removed code gates what parameters reach an external call, especially `**kwargs` passed to provider APIs, databases, HTTP clients, or SDKs.
9. Do not revert unrelated dirty work.

Validation:
- Run a focused marker search on the touched files:
  `rg -n "deprecated|backward|compat|legacy|alias|shim" <TOUCHED_FILES>`
- Run compile checks for touched Python files:
  `python -m py_compile <TOUCHED_PY_FILES>`
- Run the narrowest relevant pytest tests.
- Run:
  `git diff --check -- <TOUCHED_FILES>`

Final response:
- List what was removed or preserved and why.
- List validation commands and results.
- Mention any compatibility-looking code intentionally preserved because it is functional current behavior.