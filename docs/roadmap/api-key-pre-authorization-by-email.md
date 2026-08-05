# Pre-authorize API keys by email (before the user has ever logged in)

## Problem

`allowed_user_ids` (see `server/services/api_key_service.py`, [api-keys.md](../api-keys.md)) restricts a key to specific ORBIT users, but it stores the *internal* `users.id` — which only exists after a user has logged in once (JIT-provisioning via `AuthService._find_or_create_external_user`). There is currently no way to say "restrict this key to alice@company.com" before Alice has ever signed in.

**Consequence**: if you deploy an adapter meant for one specific person who hasn't logged in yet, the key is either unrestricted (exposed to anyone holding it) or doesn't exist yet (blocking the person you actually want). Today's workaround is operational sequencing (get them to log in first, then restrict) or a placeholder nonexistent-id trick to fake deny-all in the interim — both are annoying and error-prone for admins doing onboarding at any scale.

## Goal

Let an admin restrict a key to `alice@company.com` (or a list of emails) *before* Alice exists in ORBIT's `users` table, with the restriction taking effect automatically the moment she logs in — no race, no placeholder tricks, no re-editing the key after the fact.

## Proposed design

### 1. New field: `allowed_emails`

Add `allowed_emails: List[str]` alongside the existing `allowed_user_ids` on the `api_keys` schema (same additive-column-migration pattern used for `allowed_user_ids` — see `docs/sqlite-schema.md` v1.10 entry as the template). Stored lowercase; compared case-insensitively.

A key is authorized if the caller matches **either** list (their internal id is in `allowed_user_ids`, **or** their verified email is in `allowed_emails`) — not required to match both. This means:
- An admin can add `alice@company.com` today; it works the instant she logs in for the first time, with zero standing exposure in between.
- After she's logged in and has an internal id, the email-based entry keeps working indefinitely — no requirement to "graduate" it to an id-based entry (simpler for admins), though see Open Questions on why you might still want to.

### 2. Where the email comes from

The verified email is already produced today by the JIT-provisioning path (`AuthService._user_info()`), sourced from `OIDCValidator`'s per-provider claim extraction (`email`/`preferred_username`/`upn`/`unique_name` for Entra, configurable `email_claim` for Auth0 — see `server/services/oidc_validator.py`). No new verification logic needed; this feature only needs that value threaded to the same places `current_user_id` already reaches.

### 3. Threading the email through (mirrors the existing `current_user_id` work)

- `server/routes/auth_helpers.py::resolve_authenticated_user_id` currently returns only the id. Add a sibling (or expand it) to also return the verified email — cleanest is probably `resolve_authenticated_user(request, header_name=...) -> Optional[dict]` returning the full user-info dict, with the existing `resolve_authenticated_user_id` becoming a one-line wrapper (`(await resolve_authenticated_user(request)) or {}).get("id")`) so none of the current call sites break.
- Every call site that currently passes `current_user_id=` into `ApiKeyService.validate_api_key`/`get_adapter_for_api_key`/`get_adapter_info` (routes_configurator.py, discovery_routes.py, auth_dependencies.py, file_routes.py, a2a_routes.py, voice_routes.py) needs the equivalent `current_user_email=` passed too.

### 4. Enforcement change

In `ApiKeyService.validate_api_key`, extend the allowlist check:
```python
allowed_user_ids = key_doc.get("allowed_user_ids")
allowed_emails = key_doc.get("allowed_emails")
if allowed_user_ids or allowed_emails:
    id_match = current_user_id and current_user_id in allowed_user_ids
    email_match = current_user_email and current_user_email.lower() in allowed_emails
    if not (id_match or email_match):
        return False, None, None
```
Still fails closed: no authenticated caller at all (`current_user_id`/`current_user_email` both `None`) with either list configured → denied, same as today.

### 5. Admin panel UI

The current "Restrict to users" picker (`server/admin/admin_panel.js`, `allowedUsersSelect()`) only lists already-provisioned users from `GET /auth/users` — a not-yet-logged-in person can't appear there by definition. Extend it to a combobox/tag input that accepts:
- Selecting an existing user from the list (adds to `allowed_user_ids`, as today), or
- Typing a free-text email address not in the list (adds to `allowed_emails`).

Basic validation (looks like an email) client-side; no server-side verification that the email will ever actually log in — that's inherent to "pre-authorizing."

### 6. Optional stretch: auto-promote on first login

When `_find_or_create_external_user` provisions a new user, check whether their verified email matches any key's `allowed_emails`, and if so, also add their new internal id to that key's `allowed_user_ids`. Not required for correctness (email-only matching keeps working indefinitely per the design above), but would let an admin see the picker "graduate" a pending email entry into a real user entry, which is a nicer audit trail. Cut this from v1 if it adds too much complexity.

## Open questions to resolve before implementing

- **Email drift**: if a user's email changes in Entra/Auth0 after being added by email (before their first login), the pre-authorization silently never matches. Not fixable in general — document as a known limitation of pre-authorization by email (use id-based restriction post-login for anything long-lived/sensitive).
- **Case/domain normalization**: lowercase-compare is enough for typical IdP emails, but some tenants alias/case-fold differently. Probably fine to keep it simple (exact case-insensitive match) and document it.
- **Should email-based entries expire/get pruned automatically once the same-lookalike id exists?** Leaning no (simpler, and see auto-promote stretch above as the more useful version of this idea) — but worth deciding explicitly rather than by accident.

## Files likely touched (estimate, not final)

- `server/services/sqlite_service.py`, `postgres_service.py` — new `allowed_emails` column + JSON (de)serialization, mirroring `allowed_user_ids`
- `server/models/schema.py` — `ApiKeyCreate`/`ApiKeyUpdate`/`ApiKeyResponse`
- `server/services/api_key_service.py` — `create_api_key`, `update_api_key_metadata`, `validate_api_key`, `get_adapter_for_api_key`, `get_adapter_info`
- `server/routes/auth_helpers.py` — email-returning resolver
- `server/routes/routes_configurator.py`, `discovery_routes.py`, `auth_dependencies.py`, `file_routes.py`, `a2a_routes.py`, `voice_routes.py` — thread `current_user_email` alongside existing `current_user_id`
- `server/routes/admin/api_keys.py` — pass-through
- `server/admin/admin_panel.js` — combobox/tag-input UI accepting free-text emails
- `docs/sqlite-schema.md` — new column + version-history entry
- `server/tests/test_auth/test_api_key_service_sqlite.py` — mirror the existing `allowed_user_ids` test coverage for email matching, plus a case-insensitivity test and a combined-list test

## Verification (when implemented)

1. Add a key with `allowed_emails: ["alice@company.com"]`, no `allowed_user_ids`. Confirm: unauthenticated request → 401; a different logged-in user → 401; Alice logs in for the first time and immediately succeeds, with no intermediate exposed/unrestricted window observable in logs.
2. Confirm existing `allowed_user_ids`-only keys behave identically to today (regression check).
3. Confirm a key with both lists set authorizes on a match against either.
