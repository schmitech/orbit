# Login Rate Limiting — Implementation Plan

## Summary

Add a stricter, login-specific rate-limit bucket on top of ORBIT's existing
general-purpose rate limiter so repeated failed sign-ins are throttled per
username+IP, independent of the per-endpoint/per-IP limits already applied to
every route. No new infrastructure — this reuses the cache-backed counter and
IP-extraction utilities already in the codebase.

**Roadmap position:** Phase 1. No dependencies. Pairs naturally with
[Password Complexity](phase-2-auth-password-complexity.md) (Phase 2) as the two
lowest-effort items, and is a prerequisite building block for
[Account Lockout](phase-3-auth-account-lockout.md) (Phase 3), which shares its counter
pattern.

## Current state

`server/middleware/rate_limit_middleware.py` already implements a fixed-window
limiter keyed by IP and/or API key, backed by the configured cache service with
an `InMemoryRateLimiter` fallback when the cache is unavailable. It emits
`X-RateLimit-*` response headers and is driven by a `security.rate_limiting`
block in `config/config.yaml`. IP extraction (`extract_ip`) and trusted-proxy
CIDR parsing (`parse_trusted_networks`) live in `server/utils/ip_utils.py`.

This limiter is generic per-route/per-IP. It has no awareness of the
**identity being authenticated**, so a distributed brute-force spread across
many source IPs against one username is not distinguished from normal traffic,
and a legitimate user behind a shared/proxy IP is not protected any better than
an attacker.

## Configuration / schema

No schema change — this is config + middleware only.

```yaml
auth:
  login_rate_limit:
    enabled: true
    window_seconds: 60
    max_attempts_per_ip: 10        # coarse guard, independent of identity
    max_attempts_per_username: 5   # the real control
    lockout_after_username_limit: false   # if true, hands off to Account Lockout (Phase 2)
```

Applies to both `POST /auth/login` (local password) and the SSO initiation/
callback routes in `admin_panel_routes.py` where a distinguishable identity is
present (email/subject from the IdP claims, evaluated only after `exchange_code`
succeeds — you cannot rate-limit on a claim you don't have yet, so the IP-only
bucket is the first line of defense on that path).

## Implementation notes

- Add a dedicated `LoginRateLimiter` (or a mode on the existing
  `RateLimitMiddleware`) that keys the cache counter on
  `f"login:{username_lower}"` in addition to the existing IP key, using the
  same cache-backed counter primitive already used in
  `rate_limit_middleware.py` — do not introduce a second cache client.
- Increment the username-keyed counter only on a *failed* login attempt (wrong
  password / unknown user), not on every request, so legitimate repeated logins
  from one user aren't penalized. This means the increment has to live inside
  `AuthService.authenticate_user`'s failure path, or the route handler right
  after it returns `False`, not in the middleware's request-start hook — the
  middleware doesn't know whether a request already inside the window will
  succeed or fail.
- Do not distinguish "unknown username" from "wrong password" in the throttled
  response — same behavior and same error message either way, to avoid
  leaking which usernames exist (this is already the existing 401 message
  convention in `auth_service.py`; keep it).
- Return `429` with `Retry-After` once the username-keyed bucket is exceeded,
  reusing the existing `X-RateLimit-*` header convention for consistency.
- Log a rate-limit-triggered event through the existing audit path (see
  [Audit Trail](phase-4-auth-audit-trail-coverage.md)) rather than inventing a
  separate log line.

## Verification

- Unit test: N+1 failed logins for the same username within the window return
  429 on the (N+1)th; a successful login for a *different* username in the
  same window is unaffected.
- Unit test: the per-IP bucket still trips independently when attempts are
  spread across many distinct usernames from one IP.
- Confirm the cache-down fallback (`InMemoryRateLimiter`) still throttles
  correctly when the configured cache backend is unreachable, matching the
  existing middleware's degraded-mode behavior.
- `ruff check server/`.
