# Drop the legacy `_id` field from API-key responses — Implementation Plan

## Summary

The API-key admin endpoints serialize their Mongo/SQLite record id twice —
`_id` ("legacy — admin_panel.js depends on this") and `id` ("canonical") —
in `list_api_keys` and `get_api_key_detail`
(`server/routes/admin/api_keys.py`). `get_api_key_status`/
`get_api_key_status_by_id` already return `id` only, so the dual field is
inconsistent even within this one route file. `create_api_key` used to carry
the same duplication; it was simplified to `id`-only after confirming nothing
reads `_id` from it (see `CHANGELOG.md` 2.21.0 bug fixes).

This plan removes `_id` from the remaining two endpoints and migrates their
one real consumer, `server/admin/admin_panel/tabs/api-keys.js`, to `id`
everywhere, so the admin panel no longer depends on a Mongo-flavored field
name leaking through the API.

This is pure cleanup — no behavior change, no new functionality. Low risk,
narrow blast radius (one backend file, one frontend file, two integration
tests), but touches ~15 call sites, so it's sequenced into phases rather than
done as a single sweeping edit.

## Why now, why phased

- `id` is already present everywhere `_id` is, with the same string value —
  this is a rename, not a data migration.
- The frontend file has ~15 separate `._id` references spread across
  selection state, pagination, bulk actions, and detail rendering. Changing
  them in one shot is mechanical but easy to get subtly wrong (e.g. missing
  one comparison and silently breaking selection-highlight sync). Phasing
  lets each step be verified independently.
- Two integration tests assert `_id` is present in the list response and
  need updating in lockstep with the backend change, not after.
- Removing `_id` is an API response-shape change. Any external consumer that
  reads `_id` directly from `GET /api-keys` or the detail endpoint — a
  script, a different client, a stale admin panel build already open in a
  browser tab — breaks the moment Phase 3 ships. **Phase 1 (frontend reads
  either field) and Phase 3 (backend stops sending `_id`) must ship as
  separate releases, not as sequential phases inside one PR**, if backward
  compatibility across a deploy boundary matters for this installation.
  Ship Phase 1 first. A release cycle alone does not guarantee every admin
  panel instance has it — a browser tab left open across the deploy is
  still running the old JS in memory and will keep reading `_id` until it's
  reloaded. Before shipping Phase 3, explicitly: (1) require/communicate an
  admin panel reload (hard refresh, not just "the new build is deployed")
  rather than assuming time elapsed is sufficient, and (2) confirm any
  external `_id` consumers (scripts, other clients) have migrated to `id`.
  If this deployment has no external `_id` consumers and panel instances
  always update atomically with the backend (e.g. single-tenant, same-deploy
  admin UI, no long-lived open tabs to worry about), both phases can land
  together — but that's a deliberate, confirmed call to make at
  implementation time, not an assumption based on elapsed time.

## Phase 1 — Frontend: normalize to `id` once, at the data boundary

**Status: done.** `normalizeKeyRecord()` landed in
`server/admin/admin_panel/tabs/api-keys.js`, applied at the create/list/
detail boundaries; all downstream reads (including the row-click handler's
temporary selection object) use `.id`. See `CHANGELOG.md` [UNRELEASED].

Rather than scattering `key.id || key._id` across ~15 call sites, normalize
once where API responses enter the module (wherever list/detail/create
responses are parsed, e.g. a shared `normalizeKey(raw)` applied right after
each `api(...)` call that returns key records) so every object the rest of
the file touches already has a single, reliable `id` field. Internally:

```js
function normalizeKey(raw) {
  return Object.assign({}, raw, { id: raw.id || raw._id });
}
```

Then change every downstream read from `._id` to `.id`, including:

- Selection state: `selectedKey`, `selection.selectedIds`,
  `checkbox._selectionId`.
- List rendering and row lookups (`keys.some(...)`, `keyPaginator.
  ensureItemVisible`, bulk-select-all).
- Detail panel load/refresh (`loadKeyDetail`, `renderKeyDetail`'s `keyId`).
- Bulk delete's selected-key-clearing check.
- The temporary selection object built in the row-click handler (set as a
  placeholder before the detail fetch resolves), `selectedKey = { _id:
  k._id }` — this is easy to miss because it's a freshly constructed
  object, not a read of an existing one. Change it to
  `selectedKey = { id: k.id }` (or just pass the normalized `k` through).

Do not prefer `_id` over `id` anywhere in new code — `id` is the canonical
field going forward; `_id` is read only as a fallback during the transition
window, never written.

Do **not** touch the backend in this phase.

### Manual verification (no dedicated frontend test suite for this file)

Exercise every action that depends on the selected/row id, against the
unchanged (`_id`-and-`id`-both-present) backend:

- Create → Test Key, immediately after creation (the case the 2.21.0 fix
  addressed) and again after a list refresh.
- Select a key, multi-select, select-all, bulk delete.
- Edit (client name / adapter / prompt / allowlists) and save.
- Rename.
- Activate / deactivate.
- Renew expiration (including the non-expiring-exception path).
- Quota view, quota update, quota reset.
- Reopen the detail panel after a list refresh and confirm the same record
  stays selected.

## Phase 2 — Tests: make the contract checks actually fail

**Status: done.** Both integration test files now require a present,
nonempty, string `id` (failing instead of logging-and-continuing), round-trip
a created key's `id` through the list and new `/detail` checks, and page
through `GET /api-keys` with `limit=1000` before asserting membership so the
check doesn't miss a key past the default 100-record first page on a
populated server. The `_ASSERT_LEGACY_KEY_ID_REMOVED` scaffolding for Phase 3
is in place but still `False`.

`server/tests/test_admin/test_admin_integration.py` and
`test_admin_integration_sqlite.py` currently only *log a warning* when a
listed key is missing an expected field and then return success regardless
— `test_list_api_keys` returns `True` even when the field check fails, so
today this provides no real regression protection. Separately, the field
check there is dead code: it does `if isinstance(result, list)`, but
`GET /api-keys` returns `{"keys": [...], "expiration_warning_days": ...}`,
never a bare list, so the branch never executes.

Rewrite the check (in both files) to:

1. Read `result["keys"]` (not `result` itself).
2. Require, for every returned key, a **present, nonempty, string** `id` —
   fail the test (return `False` / raise) if it's missing, empty, or not a
   string, instead of logging and continuing.
3. Create a key, capture the `id` from the create response, list keys, and
   assert that id appears **verbatim** among the listed records' `id`
   values (not just "some id exists somewhere") — catches a scenario where
   list returns an id but it's inconsistent with the create response.
4. Do the same round-trip against `GET /api-keys/{id}/detail`.

Land this in the same change as Phase 1 (or immediately after) so the test
suite enforces the contract the frontend now actually relies on, before
Phase 3 changes what the backend sends.

**Add a second check, written now but only enabled once Phase 3 ships**
(or written as a TODO-gated assertion): after `_id` is removed, assert
`"_id" not in key` for both list and detail records. This is the regression
test that proves the field is actually gone, not just that `id` is present
— add it in Phase 2 as inert/skipped scaffolding referencing Phase 3, or
add it directly in Phase 3 alongside the backend change; either is fine as
long as it exists before Phase 3 is considered done.

## Phase 3 — Backend: drop `_id` from list/detail responses

**Ship as its own release**, after Phase 1 has had a chance to reach every
admin panel instance (see "Why now, why phased" above) — unless this
deployment has already confirmed there's no compatibility window to protect.

In `server/routes/admin/api_keys.py`:

- `list_api_keys`: remove the `"_id": record_id,  # legacy...` line, keep
  `"id": record_id`.
- `get_api_key_detail`: same change.

Grep the file afterward for `_id` to confirm no other response-building code
path still emits it, and confirm no `response_model` on either route
silently re-adds it (neither currently declares one — both return a plain
dict — so nothing to update there, unlike the `create_api_key` case where
`ApiKeyResponse` had to gain an `id` field).

Enable/add the `"_id" not in key` assertions from Phase 2 here if they
weren't already active.

## Phase 4 — Verify and close out

- Run `server/tests/test_admin/test_admin_integration.py`,
  `test_admin_integration_sqlite.py`, and the full `test_auth/
  test_api_key_service*.py` suite.
- Manually re-run the full Phase 1 verification list (create/Test Key,
  select/multi-select/bulk-delete, edit, rename, activate/deactivate,
  renew, quota view/update/reset) against the now-`id`-only backend.
- Grep `server/admin/admin_panel/` and `bin/orbit/commands/keys.py` one more
  time for `_id` to confirm no straggler reference remains (the CLI's list
  rendering already prefers `.get('id') or .get('_id')` — simplify to
  `.get('id')` once the backend guarantee holds, or leave the fallback as
  cheap insurance; not required for correctness either way).

## Out of scope

- Other admin resources (e.g. prompts — `test_admin_integration.py:451`
  asserts `_id` on a prompt record) may follow a similar `_id`/legacy
  convention in their own routes. Not touched here; a separate pass if this
  pattern turns out to be worth generalizing.
- `get_api_key_status` / `get_api_key_status_by_id` are unaffected — they
  already return `id` only.
