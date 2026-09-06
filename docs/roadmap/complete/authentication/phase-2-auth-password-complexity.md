# Password Complexity Requirements — Implementation Plan

**Status:** Complete (2026-08-31)

## Summary

Strengthen `AuthService.validate_password` with configurable minimum
complexity rules (length, character classes, and a common-password/blocklist
check), applied uniformly to registration, password change, and password
reset. No new infrastructure — this extends an existing validator in place.

**Roadmap position:** Phase 2 — no dependencies, lowest effort item on the
list alongside [Login Rate Limiting](phase-1-auth-login-rate-limiting.md) (Phase 1).

## Current state

`AuthService.validate_password` (classmethod, `server/services/auth_service.py`
around line 256) is the single existing extension point already called from
registration and password-change/reset paths. Today it enforces only a
minimum length. There is no `auth` config section for password policy.

## Configuration / schema

No schema change.

```yaml
auth:
  password_policy:
    min_length: 12                 # current default is weaker; raise deliberately
    require_uppercase: true
    require_lowercase: true
    require_digit: true
    require_symbol: true
    reject_common_passwords: true  # check against a small bundled blocklist
    max_length: 128                 # DoS guard on PBKDF2 cost, not a complexity rule
```

## Implementation notes

- Extend `validate_password` to read `auth.password_policy` from config
  (falling back to today's length-only behavior if the section is absent, so
  this is not a breaking change for deployments that don't opt in).
- `reject_common_passwords`: bundle a small (few-thousand-entry) common
  password list as a static resource under `server/` rather than calling an
  external API (e.g. HaveIBeenPwned) — no network dependency, no leaking
  candidate passwords off-box.
- `max_length` matters because PBKDF2-SHA256 cost scales with input size in
  some implementations and because unbounded input is a trivial DoS vector on
  a 600k-iteration hash; cap it and reject with a clear message rather than
  silently truncating.
- Return one aggregated error message listing every unmet rule (not just the
  first), matching the existing UX pattern of Pydantic validation errors
  elsewhere in the API.
- This only affects **new** and **changed** passwords going forward — do not
  retroactively invalidate existing sessions or force a reset for currently
  compliant-under-old-rules accounts. If a stricter policy should be
  backfilled, that's a separate, explicit admin action, not an automatic
  side effect of shipping this.

## Verification

- Unit tests: each rule (length, uppercase, lowercase, digit, symbol, common
  password) rejected individually and in combination; aggregated error
  message lists all violations.
- Unit test: with `auth.password_policy` absent, behavior matches today's
  length-only check (no regression for deployments that don't configure it).
- Manual: `orbit user set-password` (or the equivalent registration/reset
  flow) surfaces the aggregated message clearly in CLI and admin-panel forms.
- `ruff check server/`.
