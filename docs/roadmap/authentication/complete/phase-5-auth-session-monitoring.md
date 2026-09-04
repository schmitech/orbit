# Session Monitoring — Implementation Plan

**Status:** Complete (2026-09-03)

## Summary

Track enough metadata per session (source IP, user agent, last-activity time)
to let a user see and revoke their own active sessions, and let an
administrator do the same for any user. This is the first phase that touches
the `sessions` table, and is the foundation the [2FA](phase-7-auth-2fa.md) phase
builds "remember this device" on top of.

**Roadmap position:** Phase 5. No hard dependency on earlier phases, but is
naturally sequenced after the login-hardening phases (1–4) since it's a
larger, schema-touching change. [IP Whitelisting](phase-6-auth-admin-ip-allowlist.md)
(Phase 6) and [2FA](phase-7-auth-2fa.md) (Phase 7) both benefit from this phase's
`sessions.ip_address` column existing first.

## Current state

`sessions` (`server/services/sqlite_service.py` ~line 147, mirrored in
`postgres_service.py` and the MongoDB document shape) currently stores only
`id, token, user_id, username, expires, created_at`. `AuthService` has
`create_session`, `validate_token`, and `logout`, but no way to list a user's
other active sessions or revoke one selectively — `logout` only ends the
caller's own current session, and admin-initiated revocation today only
happens as a side effect of identity-allowlist/blacklist changes (see
`docs/authentication.md`'s "Pre-clearing external identities" section), not
as a general-purpose feature.

## Configuration / schema

```sql
ALTER TABLE sessions ADD COLUMN ip_address TEXT;
ALTER TABLE sessions ADD COLUMN user_agent TEXT;
ALTER TABLE sessions ADD COLUMN last_seen_at TEXT;
```

Added the same way `user_blacklist`/`user_allowlist` were added — mirrored in
`postgres_service.py` and the MongoDB path, with a version-history entry in
both `docs/sqlite-schema.md` and `docs/postgres-schema.md`.

New permission in `server/auth/rbac.py`'s `ALL_PERMISSIONS`/
`ROLE_PERMISSIONS`: `sessions.manage` (list/revoke sessions belonging to
*other* users — every authenticated user can always list/revoke their
**own** sessions without a special permission, the same way `GET /auth/me`
needs no elevated permission today).

No new config section required — this is a capability, not a policy knob.

## Implementation notes

- Populate `ip_address`/`user_agent` at `create_session` time using the same
  `extract_ip` helper from `server/utils/ip_utils.py` already used by the
  rate-limit middleware, so IP resolution behind trusted proxies is
  consistent across features rather than reimplemented.
- Update `last_seen_at` on `validate_token` — but not on *every* call if
  that's request-volume-significant; a reasonable throttle (e.g. update at
  most once per minute per session) avoids turning every authenticated
  request into a write. Check how session `expires` extension (if any) is
  currently throttled, if at all, and match that pattern.
- New service methods on `AuthService`: `list_sessions(user_id)` and
  `revoke_session(session_id, requesting_user)`, where the latter checks
  either "this is my own session" or `sessions.manage` on the requester —
  mirror the self-lockout-guard pattern already used by the blacklist/
  allowlist routes (reject a self-revoke of the *only remaining* session
  only if that's genuinely surprising; more likely, allow it — revoking your
  own last session is just a logout, not a lockout).
- New routes, following the existing `/auth/blacklist`/`/auth/allowlist`
  endpoint shape in `server/routes/auth_routes.py`:
  - `GET /auth/sessions` — the caller's own sessions.
  - `DELETE /auth/sessions/{session_id}` — revoke one of the caller's own.
  - `GET /auth/users/{user_id}/sessions` and
    `DELETE /auth/users/{user_id}/sessions/{session_id}` — admin, gated on
    `sessions.manage`.
- Admin panel: a "Sessions" sub-section on the user detail view (or a new tab
  entry) listing IP/user-agent/last-seen/created per session with a revoke
  button — follow the existing Users tab table/action-button structure in
  `server/admin/admin_panel/tabs/users.js`.
- Do **not** conflate this with the identity-allowlist's `_revoke_uncleared`
  session-revocation path (see `docs/authentication.md`) — that is a
  security-policy-driven bulk revoke; this phase's revoke is a targeted,
  self-service or admin-initiated action on a single session. They can share
  the underlying "delete this session row" primitive but are triggered
  differently and should stay in separate code paths for clarity.

## Verification

- Unit test: `create_session` populates `ip_address`/`user_agent`; a second
  login from a different IP/agent creates a second, independently
  identifiable session row for the same user.
- Unit test: a user can list and revoke their own sessions without
  `sessions.manage`; cannot list or revoke another user's sessions without
  it.
- Unit test: revoking a session immediately invalidates its token on the
  next `validate_token` call.
- Manual, via the admin panel: log in from two browsers/devices as the same
  user, confirm both sessions appear with distinguishable IP/user-agent,
  revoke one, confirm only that one is logged out.
- `ruff check server/`.
