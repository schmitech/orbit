# Manual/Integration Check: External Identity Providers (Entra ID + Auth0)

End-to-end verification of the two external-auth features, using real Microsoft
Entra ID and Auth0 accounts:

- **Part 1 — Bearer JWT validation:** ORBIT accepts a provider access token as
  `Authorization: Bearer <jwt>` on the API and JIT-provisions a local user.
- **Part 2 — Admin panel SSO:** administrators sign in to `/admin` via a
  server-side OAuth Authorization Code + PKCE flow.

The automated unit tests (`test_external_auth.py`, `test_admin_sso.py`) already
cover validation logic with fake JWKS. This playbook exercises the real
provider round-trips that unit tests can't.

Prerequisites: an admin can log in with the built-in password (`orbit login`)
so you can inspect provisioned users, and ORBIT runs at `http://localhost:3000`.

## 0. Install the dependency profile

The OIDC libraries are opt-in:

```bash
./install/setup.sh --profile auth-providers   # installs PyJWT[crypto]
```

Verify:

```bash
venv/bin/python -c "import jwt; from jwt import PyJWKClient; print('PyJWT', jwt.__version__)"
```

If `auth.providers.enabled: true` but this profile is missing, the server
**fails fast at startup** with an install hint — that itself is scenario **F1**.

---

# Part 1 — Bearer JWT validation (API)

## 1. Configure a provider

Edit the `auth.providers` block in `config/config.yaml`. Enable the master
switch plus at least one provider. Example for both:

```yaml
auth:
  providers:
    enabled: true
    default_role: "user"
    entra:
      enabled: true
      tenant_id: ${ORBIT_AUTH_ENTRA_TENANT_ID:-}
      client_id: ${ORBIT_AUTH_ENTRA_CLIENT_ID:-}
    auth0:
      enabled: true
      domain: ${ORBIT_AUTH_AUTH0_DOMAIN:-}
      audience: ${ORBIT_AUTH_AUTH0_AUDIENCE:-}
      client_id: ${ORBIT_AUTH_AUTH0_CLIENT_ID:-}
```

Set the env vars in the shell where ORBIT runs (see `env.example`):

```bash
export ORBIT_AUTH_ENTRA_TENANT_ID=<directory-tenant-id>
export ORBIT_AUTH_ENTRA_CLIENT_ID=<application-client-id>
export ORBIT_AUTH_AUTH0_DOMAIN=<your-tenant>.us.auth0.com
export ORBIT_AUTH_AUTH0_AUDIENCE=<your-api-identifier>
export ORBIT_AUTH_AUTH0_CLIENT_ID=<your-app-client-id>
```

Restart ORBIT (config is read at startup):

```bash
python3 server/main.py        # or ./bin/orbit.sh start
```

## 2. Obtain a test access token

You need an access token whose **audience matches ORBIT's config**. The
client-credentials grant is the most reliable way to mint one by hand (it
represents an app identity — fine for verifying the validation path).

**Auth0** — requires a Machine-to-Machine app authorized for your API:

```bash
curl -s --request POST \
  --url "https://$ORBIT_AUTH_AUTH0_DOMAIN/oauth/token" \
  --header 'content-type: application/json' \
  --data "{\"client_id\":\"<m2m-client-id>\",\"client_secret\":\"<m2m-secret>\",\"audience\":\"$ORBIT_AUTH_AUTH0_AUDIENCE\",\"grant_type\":\"client_credentials\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
```

**Entra ID** — the app must "Expose an API" with App ID URI `api://<client_id>`:

```bash
curl -s -X POST "https://login.microsoftonline.com/$ORBIT_AUTH_ENTRA_TENANT_ID/oauth2/v2.0/token" \
  -d 'grant_type=client_credentials' \
  -d "client_id=$ORBIT_AUTH_ENTRA_CLIENT_ID" \
  -d 'client_secret=<client-secret>' \
  -d "scope=api://$ORBIT_AUTH_ENTRA_CLIENT_ID/.default" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
```

> **Before hitting ORBIT, inspect the token.** Paste it into <https://jwt.io> (or
> `python3 -c "import jwt,sys; print(jwt.decode(sys.argv[1], options={'verify_signature':False}))" <token>`)
> and confirm:
> - `iss` equals `https://login.microsoftonline.com/<tenant>/v2.0` (Entra) or
>   `https://<domain>/` (Auth0).
> - `aud` equals your `client_id`/`api://<client_id>` (Entra) or the API
>   `audience` (Auth0). **A wrong `aud` is the #1 cause of rejection** — for
>   Entra especially, a Microsoft Graph token (`aud` = Graph) will not validate.
> - `sub` is present.

Save it: `export TOKEN=<paste>`.

## 3. Authenticate with the token

```bash
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:3000/auth/me
```

Confirm:
- HTTP 200 with a user object.
- `username` is `entra:<sub>` or `auth0:<sub>`.
- `role` is `user` (the configured `default_role`).

## 4. Confirm JIT provisioning persisted

As a password admin:

```bash
orbit login --username admin
orbit user list        # the entra:<sub> / auth0:<sub> user appears, with provider + email
```

Or query the backend directly (SQLite default):

```bash
sqlite3 orbit.db "SELECT username, role, provider, email FROM users WHERE provider IS NOT NULL;"
```

Confirm exactly one row per subject, `provider` set, and a random (unusable)
password hash — the user cannot password-login.

---

## Additional Bearer Scenarios

### A. Re-use, not duplicate

Call `/auth/me` with the same token again. Confirm no second user row is
created (`orbit user list` count unchanged) and the same `id` is returned.

### B. Tampered / bad-signature token rejected

Flip a character in the token's payload segment and call `/auth/me`:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer ${TOKEN}x" http://localhost:3000/auth/me
```

Expect **401**. Same for an expired token (wait past `exp`, or mint one and
let it expire).

### C. Wrong-audience token rejected

Mint an Entra Microsoft Graph token (scope `https://graph.microsoft.com/.default`)
and present it. Expect **401** — its `aud` is Graph, not ORBIT. This is the
caveat documented in `docs/authentication.md`.

### D. External JWT logout is a no-op success

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" http://localhost:3000/auth/logout
```

Expect **200** `{"message":"Logout successful"}` — a stateless JWT has no
server session to revoke, so logout must succeed (not 500). Confirm the token
still works on `/auth/me` afterward (logout didn't revoke the provider token).

### E. Password auth is unaffected

Confirm `orbit login --username admin` and the built-in `/auth/login` still
work while providers are enabled — external auth is strictly additive.

### F1. Fail-fast when the dependency is missing

In a venv without the `auth-providers` profile, set `providers.enabled: true`
and start ORBIT. Confirm startup aborts with a clear message naming the
`auth-providers` profile rather than silently 401-ing every JWT.

### G. Deactivated external user cannot re-authenticate

Deactivate the provisioned user (`orbit user deactivate --user-id <id>` or the
admin UI), then present the token again. Expect **401** — a deactivated JIT
user is not silently reactivated.

---

# Part 2 — Admin Panel SSO (browser)

## 5. Register the redirect URI

The callback URL ORBIT uses is:

```
http://localhost:3000/admin/auth/entra/callback
http://localhost:3000/admin/auth/auth0/callback
```

(Behind a proxy, set `ORBIT_ADMIN_BASE_URL` and register `{base}/admin/auth/{provider}/callback`.)

- **Entra:** App registration → Authentication → add a **Web** platform redirect
  URI (above). Create a client **secret** (recommended for the Web flow).
- **Auth0:** Application (a *Regular Web Application* is simplest) → **Allowed
  Callback URLs** → add the URL above. Note the client id + secret.

> `client_secret` is optional in ORBIT: with a secret the code exchange is a
> confidential client (recommended, and required by Entra's "Web" platform);
> without one it runs as a public client with PKCE (register the redirect under
> a **SPA** platform / Auth0 *Single Page Application* instead).

## 6. Configure admin SSO

Extend the same `auth.providers` block:

```yaml
auth:
  providers:
    entra:
      enabled: true
      tenant_id: ${ORBIT_AUTH_ENTRA_TENANT_ID:-}
      client_id: ${ORBIT_AUTH_ENTRA_CLIENT_ID:-}
      client_secret: ${ORBIT_AUTH_ENTRA_CLIENT_SECRET:-}
    auth0:
      enabled: true
      domain: ${ORBIT_AUTH_AUTH0_DOMAIN:-}
      audience: ${ORBIT_AUTH_AUTH0_AUDIENCE:-}
      client_id: ${ORBIT_AUTH_AUTH0_CLIENT_ID:-}
      client_secret: ${ORBIT_AUTH_AUTH0_CLIENT_SECRET:-}
    admin_sso:
      enabled: true
      base_url: ${ORBIT_ADMIN_BASE_URL:-}
      admin_users:
        - "you@yourcompany.com"      # the email you'll sign in with
```

Set the extra env vars and restart:

```bash
export ORBIT_AUTH_ENTRA_CLIENT_SECRET=<entra-secret>
export ORBIT_AUTH_AUTH0_CLIENT_SECRET=<auth0-secret>
```

> `admin_sso.enabled` is independent of `providers.enabled` — admin SSO can be
> on even if bearer validation is off. It needs the provider blocks configured
> either way.

## 7. Sign in through the browser

1. Open `http://localhost:3000/admin/login`. **Scenario A:** confirm the
   password form still renders **and** an "or continue with" divider with a
   "Sign in with Microsoft"/"Sign in with Auth0" button appears per enabled
   provider.
2. Click a provider button → you're redirected to the IdP → complete login.
3. **Scenario B:** you land back in the ORBIT admin panel, authenticated. The
   panel loads normally (adapters, metrics, etc.) — same as a password admin.

## 8. Confirm the SSO admin was provisioned

```bash
sqlite3 orbit.db "SELECT username, role, provider, email FROM users WHERE provider IS NOT NULL;"
```

Confirm a `entra:<sub>` / `auth0:<sub>` row with `role = admin` and your email.

---

## Additional SSO Scenarios

### H. Non-allowlisted user is rejected

Remove your email from `admin_users` (or sign in as a different directory user
not on the list), restart, and complete the IdP login. Confirm you're bounced
back to `/admin/login` with **"Your account is not authorized for admin
access."** and are **not** in the panel. (The account may be created as a
non-admin `user` row, but it has no panel access.)

### I. Promotion on allowlisting

With the user from H still a non-admin, add their email to `admin_users`,
restart, and sign in again via SSO. Confirm they're now `admin` and land in the
panel — `provision_sso_user` promotes an existing user when they appear on the
allowlist.

### J. Subject matching is case-sensitive

Add a `provider:subject` entry with the wrong case, e.g. copy the real `sub`
from the users table and upper-case it: `admin_users: ["entra:ABCD..."]` when
the real sub is `abcd...`. Restart, sign in. Confirm access is **denied** —
OIDC subjects are case-sensitive (email entries remain case-insensitive).

### K. CSRF / state protection

Hit the callback directly with a bogus state and no flow cookie:

```bash
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" \
  "http://localhost:3000/admin/auth/entra/callback?code=abc&state=forged"
```

Confirm a 303 redirect to `/admin/login?error=sso_failed` (state mismatch /
missing flow cookie) — never a 500 or a granted session.

### L. Logout clears the SSO session

In the panel, click **Logout**. Confirm you're returned to `/admin/login` and
that reloading `/admin` requires signing in again (the `dashboard_token` cookie
was cleared). SSO admins log out exactly like password admins.

### M. Both providers side by side

With both enabled, confirm both buttons appear and each completes an
independent login producing its own `entra:<sub>` / `auth0:<sub>` admin row.

### N. Disabled provider hides its button

Set `auth0.enabled: false` (leave `admin_sso.enabled: true`), restart. Confirm
only the Microsoft button shows, and visiting
`/admin/auth/auth0/login` redirects to `/admin/login?error=sso_unavailable`.

---

## 9. Run the automated checks

```bash
ruff check server/
venv/bin/python -m pytest server/tests/test_auth/test_external_auth.py server/tests/test_auth/test_admin_sso.py -v
```

> Note: two pre-existing failures in `test_api_key_service_*` (singleton
> caching) are unrelated to external auth and also fail on `main` — don't be
> alarmed if you run the whole `test_auth/` directory.

---

## Troubleshooting

- **401 on `/auth/me` with a token that "looks fine":** decode it and check
  `aud`/`iss` against config (step 2). Wrong audience is the usual cause —
  Entra Graph tokens and Auth0 tokens minted without the `audience` parameter
  both fail. `sub` must also be present.
- **Server refuses to start after enabling providers:** the `auth-providers`
  profile isn't installed — `./install/setup.sh --profile auth-providers`.
- **`redirect_uri_mismatch` / `invalid redirect` at the IdP:** the registered
  callback must match byte-for-byte. Watch for `http` vs `https`, trailing
  slashes, and ports. Set `ORBIT_ADMIN_BASE_URL` when behind a proxy.
- **SSO button doesn't appear:** `admin_sso.enabled` must be `true` and the
  provider must be enabled with the fields it needs (Auth0 SSO additionally
  needs `client_id`). Check startup logs for "Admin SSO enabled for providers".
- **Redirected to `/admin/login?error=sso_failed`:** token exchange or
  id_token validation failed — check `client_secret` (Entra Web flow requires
  it), the id_token `aud` (must equal `client_id`), and server logs.
- **Redirected to `?error=not_authorized`:** login succeeded but the identity
  isn't on `admin_users` (or a `provider:subject` entry has the wrong case).
- **Missing `email` on an Entra user:** ensure the app requests the `email`
  scope and the account has an email/`preferred_username`; matching by
  `entra:<sub>` in `admin_users` always works regardless.
- **Inspect current storage / users:** `orbit user list` (as a password admin)
  or the `sqlite3` query in step 4/8.
