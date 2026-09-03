# Audit Trail Coverage — Implementation Plan

**Status:** Complete (2026-09-03)

## Summary

Extended ORBIT's **existing** audit infrastructure to cover authentication
events it previously missed — failed logins and durable lockouts — while
retaining its existing password-change/reset and rate-limit coverage. This
was a coverage gap, not an infrastructure gap.

**Roadmap position:** Phase 4. No hard dependency, but is most useful once
[Login Rate Limiting](complete/phase-1-auth-login-rate-limiting.md) and
[Account Lockout](complete/phase-3-auth-account-lockout.md) exist, since two of the new event
types this phase adds (`auth.login.rate_limited`, `auth.login.locked_out`)
come from those phases. Land this phase last of the three so there's
something concrete to log; land it standalone if those phases slip, using
just the password-change/failed-login events, which don't depend on them.

## Current state

Substantial infra already exists and should not be duplicated:

- `server/services/audit/` — a strategy pattern with sqlite/postgres/mongodb/
  elasticsearch backends.
- `server/middleware/admin_audit_middleware.py` — a route-action table that
  already logs `auth.login`, `auth.logout`, `auth.dashboard.login/logout`,
  and generic admin CRUD actions.
- `audit_logs` / `audit_admin_logs` tables, documented in
  `docs/sqlite-schema.md` (~L496, ~L600).
- `audit.read` permission already exists in `server/auth/rbac.py`, gating who
  can view the trail.

What's missing is coverage of **failure and account-management paths**:
failed login attempts (successful ones are logged; failures currently are
not), rate-limit/lockout triggers, and password changes/resets — all of
which are security-relevant "user actions" the doc's item 7 calls for but
that don't currently produce a row.

## Configuration / schema

No new tables or config sections. This phase only adds entries to the
existing route-action mapping in `admin_audit_middleware.py` (or the
equivalent hook point in `auth_service.py` for non-route-triggered events
like an internal lockout expiry).

Event names added to the existing taxonomy, following the current
`auth.<action>` / `auth.dashboard.<action>` naming convention:

- `auth.login.failed` — username (or masked identity), source IP, reason
  class (`invalid_credentials` — never distinguish "unknown user" from
  "wrong password" in the stored reason any more than in the HTTP response).
- `auth.login.rate_limited` — emitted by Phase 1's existing middleware hook.
- `auth.login.locked_out` — emitted when Phase 3's durable-lockout check
  rejects a local-password attempt.
- `auth.password.changed` / `auth.password.reset` — actor, target user
  (self vs. admin-initiated), never the password itself or its hash.
- `auth.session.revoked` — already may partially exist via logout; confirm
  and extend to cover admin-initiated forced revocation
  ([Session Monitoring](phase-5-auth-session-monitoring.md), Phase 5) once that
  ships.

## Implementation notes

- `AuthService.authenticate_user` classifies every failure path through an
  optional caller-owned context, including a lockout check that short-circuits
  before password comparison. The HTTP handlers pass that coarse classification
  to the existing audit middleware, which supplies request-derived IP and user
  agent data. This preserves a single write path without making the service
  depend on a request object.
- Reuse the existing audit write path/service rather than adding a second
  logging mechanism — check how `auth.login` (success) is currently emitted
  in `admin_audit_middleware.py` and mirror that call shape for the failure
  variant.
- Redact consistently with existing entries: no raw passwords, no full
  bearer tokens (existing entries likely already mask these — verify and
  match the same masking helper rather than reimplementing it).
- Rate limit the audit writes themselves for repeated rapid failures against
  the same identity (e.g. one row per lockout event, not one row per
  individual failed attempt once well past the threshold) so a brute-force
  attempt doesn't also become a log-flooding vector — check whether the
  existing audit backends already batch/rate-limit before adding this.

## Verification

- Unit test: a failed local login produces exactly one `auth.login.failed`
  audit row with the expected fields and no password material.
- Unit test: a successful login after failures still logs both the prior
  failures and the success — the record isn't overwritten.
- Manual: `GET` the audit endpoint (gated by `audit.read`) after triggering
  a failed login, a password change, and (if Phase 2 has shipped) a lockout;
  confirm all three appear with correct actor/target/timestamp.
- Confirm existing `test_admin_audit_middleware`-style tests (locate via
  `grep -rn "admin_audit_middleware" server/tests/`) still pass unmodified —
  this phase only adds rows, it doesn't change existing ones.
- `ruff check server/`.

## Completed implementation

- Local API and dashboard password-login failures now emit
  `auth.login.failed`; currently locked local accounts emit
  `auth.login.locked_out` instead. Rate-limit events retain precedence when a
  failure also reaches a configured rate limit.
- Failure summaries record only the submitted username and the single
  `invalid_credentials` reason class. Passwords, hashes, tokens, and a
  user-existence distinction are never passed to the ledger.
- The existing change-password event now uses the documented canonical name
  `auth.password.changed`; administrator resets retain `auth.password.reset`.
- Added route-level regression coverage confirming a failed login produces the
  expected redacted audit record.
