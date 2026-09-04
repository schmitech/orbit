# Admin IP Allowlisting — Implementation Plan

## Summary

Restrict access to `/admin/*` routes (the admin panel and its API surface) to
a configurable set of IP addresses/CIDR ranges, as a defense-in-depth layer
on top of authentication and RBAC — useful for deployments where the admin
panel should only ever be reachable from an office network, VPN, or bastion,
regardless of whether credentials are otherwise correct.

**Roadmap position:** Phase 6. No hard dependency, but benefits from
[Session Monitoring](complete/phase-5-auth-session-monitoring.md) (Phase 5) having already
established the `ip_address` extraction/storage convention for consistency.

## Current state

No existing IP-based access control for admin routes. What exists and is
reusable:

- `parse_trusted_networks` / `extract_ip` in `server/utils/ip_utils.py` —
  already does CIDR parsing and trusted-proxy-aware client IP resolution for
  the rate-limit middleware.
- The `user_blacklist`/`user_allowlist` table + service pattern
  (`server/services/user_blacklist_service.py`,
  `server/services/user_allowlist_service.py`) — a directly analogous
  "pattern-matched allow/deny with admin CRUD + cache" shape, just matching
  CIDR ranges instead of identity strings.

This is **not** the same control as the identity allowlist documented in
`docs/authentication.md` ("Pre-clearing external identities") — that gates
*who* can be provisioned an account at all; this phase gates *where* the
admin panel can be reached from, independent of identity.

## Configuration / schema

```yaml
auth:
  admin_ip_allowlist:
    enabled: false          # opt-in; default off so this can't lock out an
                             # existing deployment on upgrade
    mode: allowlist          # allowlist | open — same fail-closed convention
                             # as auth.providers.access_control
    default_ranges: []       # e.g. ["10.0.0.0/8", "203.0.113.4/32"]
```

New table `admin_ip_rules`, added following the `user_blacklist`/
`user_allowlist` migration pattern (`CREATE TABLE IF NOT EXISTS` in
`sqlite_service.py`, mirrored in `postgres_service.py` and MongoDB, with a
version-history entry in both schema docs):

```sql
CREATE TABLE IF NOT EXISTS admin_ip_rules (
    id TEXT PRIMARY KEY,
    cidr TEXT NOT NULL,
    reason TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_admin_ip_rules_cidr ON admin_ip_rules(cidr);
```

## Implementation notes

- Gate at the middleware level, applied specifically to `/admin/*` (and the
  equivalent admin-scoped API routes under `/auth/*` that require
  `users.manage`/similar admin permissions) — not globally, since regular
  `/v1/chat` traffic must not be affected.
- Evaluate `default_ranges` (static config) unioned with the DB-backed
  `admin_ip_rules` table, so a deployment can start with a simple static
  config list and grow into DB-managed rules without a breaking change —
  mirror how the identity allowlist treats `admin_sso.admin_users` as
  implicitly-allowed alongside DB rules.
- **Self-lockout guard is critical here**: unlike the identity allowlist
  (where an admin locked out of the *panel* can still reach it from another
  cleared identity), an IP allowlist misconfiguration can lock out *every*
  admin simultaneously, including via the CLI if the CLI's own admin API
  calls go through the same gate. Two mitigations, both should ship:
  - Exempt CLI-originated requests using local/loopback detection or a
    separate internal auth path, so `orbit` commands run *on the server
    itself* are never blocked by this control (`orbit` typically talks to
    `localhost` or a configured admin URL — confirm which, and exempt that
    specific path rather than all CLI traffic generally, to avoid
    reintroducing a bypass).
  - Before writing a rule set that would exclude the requesting admin's own
    current IP, require an explicit confirmation flag (`--i-am-sure`-style),
    the same pattern already used by `AllowlistSeedCommand`'s confirmation
    prompt in `bin/orbit/commands/allowlist.py`.
- Log denials through the existing audit path (see
  [Audit Trail](phase-4-auth-audit-trail-coverage.md)) as `auth.admin_ip.denied`,
  including the source IP but not attempting to log full request bodies.
- Reuse `extract_ip`'s trusted-proxy logic exactly — if this check uses a
  different IP resolution path than the rate limiter, a reverse-proxy
  misconfiguration could cause the two to disagree, which is a security-
  relevant inconsistency worth avoiding by construction rather than testing
  for after the fact.

## Verification

- Unit test: a request from an IP outside all configured ranges is denied
  with 403 before reaching route logic; one from an allowed range proceeds
  normally.
- Unit test: `mode: open` (or `enabled: false`) preserves current behavior
  exactly — no regression for deployments that don't opt in.
- Unit test: the CLI's own admin operations are unaffected regardless of the
  configured ranges (confirms the exemption path).
- Manual: configure a narrow range that excludes your current test client,
  confirm the admin panel becomes unreachable in a browser but `orbit`
  CLI commands against the same server still work.
- Manual: attempt to add a rule set that would exclude your own current IP
  without the confirmation flag; confirm it's rejected with a clear message.
- `ruff check server/`.
