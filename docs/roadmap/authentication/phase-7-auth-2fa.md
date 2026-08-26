# Two-Factor Authentication (2FA/TOTP) — Implementation Plan

## Summary

Add optional TOTP-based two-factor authentication for **local password
accounts**, required at minimum for the `admin` role, with an enrollment flow,
a second-factor check in the login path, and recovery codes for account
recovery if the authenticator device is lost. This is the highest-effort item
on the roadmap and the last phase, since it benefits from
[Session Monitoring](phase-5-auth-session-monitoring.md)'s session metadata for an
optional "remember this device" feature.

**Roadmap position:** Phase 7. Soft dependency on
[Session Monitoring](phase-5-auth-session-monitoring.md) (Phase 5) for device-remember;
implementable without it (every login just always prompts for the TOTP code).
No dependency on Phases 1, 2, 3, 4, or 6.

## Current state

No 2FA/TOTP code exists anywhere in the codebase. `AuthService.authenticate_user`
performs a single-factor check (password against the stored hash) and returns
a session directly. External (Entra/Auth0) identities are out of scope here —
2FA for those identities is the IdP's responsibility (Entra/Auth0 both support
their own MFA policies), so this phase applies only to local password
accounts, the same scoping boundary as
[Account Lockout](phase-3-auth-account-lockout.md).

## Configuration / schema

```yaml
auth:
  two_factor:
    enabled: true
    required_for_roles: ["admin"]     # roles that cannot log in without 2FA enrolled
    issuer_name: "ORBIT"               # shown in authenticator apps
    recovery_codes_count: 10
    remember_device_days: 30           # 0 disables device-remember entirely
```

New table `user_mfa`, added following the `user_blacklist`/`user_allowlist`
migration pattern:

```sql
CREATE TABLE IF NOT EXISTS user_mfa (
    user_id TEXT PRIMARY KEY,
    totp_secret_encrypted TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    recovery_codes_hashed TEXT,        -- JSON array of hashed one-time codes
    created_at TEXT NOT NULL,
    enabled_at TEXT
);
```

If [Session Monitoring](phase-5-auth-session-monitoring.md) has landed, device-remember
reuses its `sessions` table with an additional `mfa_verified_until` column
rather than a separate device-token table.

## Implementation notes

- **Secret storage**: `totp_secret_encrypted` must be encrypted at rest, not
  stored in plaintext like a password hash would be (TOTP secrets are
  symmetric — anyone who reads the DB can generate valid codes forever,
  unlike a password hash which is one-way). Use the same encryption-at-rest
  mechanism already used elsewhere in ORBIT for sensitive config values (check
  how provider API keys / OIDC client secrets are protected in config — reuse
  that key-management approach rather than inventing a new one for this single
  table).
- **Enrollment flow**: generate a secret, display a QR code (encode the
  standard `otpauth://` URI) and the raw secret as a fallback, require the
  user to confirm by entering one valid code before `enabled` flips to true —
  this proves the user actually captured the secret in their authenticator
  app rather than enrolling and then being locked out immediately.
- **Recovery codes**: generate `recovery_codes_count` one-time codes at
  enrollment, store them **hashed** (same PBKDF2 approach as passwords, or a
  faster hash since these are high-entropy random strings, not
  low-entropy user-chosen passwords — a plain SHA-256 is defensible here,
  document the reasoning either way), shown to the user exactly once at
  enrollment time. Each recovery code is single-use — mark consumed rather
  than deleting, so a compromised list is auditable.
- **Login flow change**: `authenticate_user` succeeds on password as today,
  but if the user has 2FA enabled (or their role is in `required_for_roles`
  and they haven't enrolled yet — decide whether to force enrollment at that
  point or block login until an admin assists; blocking is safer and simpler
  to reason about), issue a short-lived intermediate token instead of a full
  session, requiring a second `POST /auth/login/2fa` call with a valid TOTP or
  recovery code before a real session is created. This two-step shape avoids
  ever having a "logged in but not fully authenticated" session token floating
  around with full session capabilities.
- **Rate limit the second factor** using the same pattern as
  [Login Rate Limiting](phase-1-auth-login-rate-limiting.md) — a 6-digit TOTP code has
  low enough entropy that it must be throttled independently of the password
  check.
- **Admin reset**: an admin with `users.manage` must be able to disable 2FA
  for a user who's lost both their device and recovery codes — this is a
  necessary recovery path, log it prominently via the audit trail
  (`auth.mfa.admin_reset`) since it's a sensitive override.
- New permission in `server/auth/rbac.py`: none strictly required beyond
  existing `users.manage` for the admin-reset path — enrollment/verification
  for oneself needs no special permission, the same as password changes.

## Verification

- Unit test: enrollment requires a valid confirmation code before `enabled`
  flips true; an invalid confirmation code leaves the account without 2FA.
- Unit test: login with correct password but no/incorrect TOTP does not
  issue a full session token.
- Unit test: a recovery code is accepted exactly once; a second use of the
  same code is rejected.
- Unit test: a user with a role in `required_for_roles` who hasn't enrolled
  cannot obtain a full session (confirms the forced-enrollment/blocked-login
  decision made above).
- Unit test: admin-initiated 2FA reset disables it and produces an audit row.
- Manual: enroll with a real authenticator app (e.g. Google Authenticator),
  confirm the QR code scans correctly and login round-trips end-to-end,
  including one recovery-code login.
- `ruff check server/`.
