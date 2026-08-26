# Account Lockout — Implementation Plan

## Summary

Temporarily lock a **local password account** out after a configurable number
of consecutive failed login attempts, with automatic expiry (no permanent
admin-only unlock requirement, to avoid turning this into a denial-of-service
vector against known usernames). Shares the cache-backed counter pattern from
[Login Rate Limiting](phase-1-auth-login-rate-limiting.md); does not apply to external
(Entra/Auth0) identities, whose authentication failures happen at the IdP, not
locally.

**Roadmap position:** Phase 3. Depends conceptually on Phase 1's
username-keyed failure counter (can share the same counter, or read from it),
but is implementable independently if Phase 1 hasn't landed yet — the lockout
counter can be its own field.

## Current state

The `users` table (`server/services/sqlite_service.py`, `postgres_service.py`,
and the MongoDB path) has no failure-tracking columns. `AuthService`'s
`authenticate_user` has no concept of a locked account — every attempt is
evaluated fresh against the stored password hash.

## Configuration / schema

```yaml
auth:
  account_lockout:
    enabled: true
    max_failed_attempts: 5
    lockout_duration_minutes: 15
    reset_counter_after_minutes: 30   # a failure this long after the last one doesn't count toward the threshold
```

New `users` columns, added the same way `user_blacklist`/`user_allowlist`
tables were added (`CREATE TABLE IF NOT EXISTS`/`ALTER TABLE` in
`sqlite_service.py`, mirrored in `postgres_service.py` and the MongoDB
document shape), with a version-history entry in both
`docs/sqlite-schema.md` and `docs/postgres-schema.md`:

```sql
ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN last_failed_login_at TEXT;
ALTER TABLE users ADD COLUMN locked_until TEXT;
```

## Implementation notes

- **Applies only to local password accounts** (`user.provider` unset), mirroring
  how the identity allowlist explicitly excludes them in the other direction —
  external identities have no local password to brute-force, and locking a
  `users` row provisioned from Entra/Auth0 would just get silently
  re-provisioned or, worse, deny a legitimate SSO session for reasons unrelated
  to the SSO login itself.
- Store the counters as columns rather than only in cache, because a lockout
  is a security decision that must survive a cache restart/eviction — the
  cache-backed counter from Phase 1 is fine for *rate limiting* (best-effort
  throttling) but lockout state should be durable.
- On each failed `authenticate_user` call: increment
  `failed_login_attempts`, set `last_failed_login_at`; if the threshold is
  crossed, set `locked_until = now + lockout_duration_minutes`. On a
  **successful** login, reset `failed_login_attempts` to 0 and clear
  `locked_until`.
- `reset_counter_after_minutes`: if `last_failed_login_at` is older than this
  window when a new failure arrives, reset the counter to 1 instead of
  incrementing — otherwise sporadic failures over weeks eventually trip
  lockout even with long gaps between them.
- `authenticate_user` must check `locked_until` **before** doing the PBKDF2
  comparison (constant-time password check is expensive; don't do it for a
  request that's going to be rejected regardless) but the rejection message
  must not distinguish "locked" from "wrong password" in a way that confirms
  the username exists — return a generic message, optionally with a
  `Retry-After` header giving the unlock time without stating *why*.
- Do not lock the bootstrap `admin` account out permanently by policy —
  `reset_counter_after_minutes` and the auto-expiry already prevent permanent
  lockout, but consider exempting `default_admin_username` from lockout
  entirely if the deployment has no other admin recovery path, and document
  the tradeoff explicitly rather than deciding it silently.

## Verification

- Unit test: `max_failed_attempts` consecutive failures locks the account;
  the next attempt (even with the correct password) is rejected until
  `locked_until` passes.
- Unit test: a successful login before the threshold resets the counter.
- Unit test: `reset_counter_after_minutes` correctly discounts stale failures.
- Unit test: an external (SSO) identity's `authenticate_user` path is
  entirely unaffected by lockout state (there is none to check).
- Manual: confirm the CLI/API error message for a locked account doesn't leak
  more than a generic "try again later" would.
- `ruff check server/`.
