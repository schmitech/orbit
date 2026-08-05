# Setting up Auth0 / Entra ID login for orbitchat

Step-by-step guide for wiring orbitchat's Auth0 or Entra login into ORBIT so that per-user API key restriction (`allowed_user_ids`, see [api-keys.md](api-keys.md)) works end-to-end. For the underlying architecture (JIT provisioning, token validation, admin SSO), see [authentication.md § External Identity Providers](authentication.md#external-identity-providers-oidc).

This document is a practical runbook — what to click, what to set, and the non-obvious gotchas that will otherwise cost you an afternoon of silent failures.

## Why this is needed

Without this setup, orbitchat's `X-User-ID` header is unverified — anyone can claim any identity. ORBIT restricts an API key to specific users by verifying the `Authorization: Bearer <token>` orbitchat sends and matching the *verified* identity, not the header. That verification only works if the token orbitchat gets from Auth0/Entra is a real, audience-scoped JWT — which requires a small amount of IdP-side configuration most quickstarts skip, because they don't scope tokens to a custom API.

## Auth0 setup

### 1. Create a custom API

Auth0 only issues a verifiable JWT access token when the login request specifies an `audience` for a registered API. Without one, Auth0 returns an **opaque token** — not a JWT — and ORBIT silently fails to validate it (more on this in Troubleshooting).

1. Auth0 Dashboard → **Applications → APIs → Create API** (not the pre-existing "Auth0 Management API").
2. **Name**: anything, e.g. `ORBIT API`.
3. **Identifier**: a URI you make up, e.g. `https://your-api`. Doesn't need to resolve to anything real — Auth0 just uses it as the token audience.
4. **Signing Algorithm**: leave as **RS256**. ORBIT verifies signatures via JWKS, which requires asymmetric (RS256) signing — HS256 will not work.

### 2. Authorize the orbitchat application against the API

Creating an API does **not** automatically let existing applications request tokens for it — this step is easy to miss and produces a confusing error if skipped.

1. Open the API you just created → **Machine to Machine Applications** tab (despite the name, this also gates the Authorization Code / user-delegated flow SPAs use).
2. Find orbitchat's application in the list and toggle it to **Authorized**.
3. Click **Update**.

Skipping this produces, on login attempt:
```
error=invalid_request&error_description=Client "..." is not authorized to access resource server "https://your-api".
```

### 3. Set the audience in both places

- `clients/orbitchat/.env.local`: `VITE_AUTH_AUDIENCE=https://your-api`
- ORBIT's `.env`: `ORBIT_AUTH_AUTH0_AUDIENCE=https://your-api`

They must match **exactly**.

### 4. (Optional) Capture user email via a custom claim

Auth0 access tokens issued against a custom API audience carry only bare OAuth claims (`sub`/`aud`/`exp`/`scope`/...) — **never `email`**, unlike Entra. To capture it for JIT-provisioned users:

1. Auth0 Dashboard → **Actions → Flows → Login** → add a new custom Action:
   ```js
   exports.onExecutePostLogin = async (event, api) => {
     const namespace = 'https://your-api/';
     if (event.user.email) {
       api.accessToken.setCustomClaim(`${namespace}email`, event.user.email);
     }
   };
   ```
   Drag it into the Login flow and deploy. Custom claims must be namespaced (a URI-shaped key) — Auth0 silently drops unnamespaced ones.
2. In ORBIT's `config/config.yaml`, under `auth.providers.auth0`:
   ```yaml
   email_claim: "https://your-api/email"
   ```
3. Restart ORBIT.

Without this step, Auth0 users still get JIT-provisioned and restriction still works — they just show up in the admin panel's "Restrict to users" picker by their `auth0:<sub>` username instead of an email.

## Entra ID (Azure AD) setup

### 1. Expose an API on the app registration

1. Azure Portal → **App registrations** → the app orbitchat uses to log in (same client ID as `ORBIT_AUTH_ENTRA_CLIENT_ID` in ORBIT's `.env`).
2. **Expose an API** → set the **Application ID URI** if not already set (Azure suggests `api://<client-id>` by default — accept that).
3. **Add a scope**: name it `access_as_user`, fill in an admin consent display name/description, state **Enabled**.
4. **Who can consent?** — set to **Admins and users**, not the default "Admins only." Admins-only requires a tenant admin to explicitly grant consent for the whole organization before *anyone* (including you) can get a token; Admins-and-users lets each user consent individually on first login, which is the right choice for a first-party scope on your own app.

### 2. Set orbitchat's env vars to the Entra values

`clients/orbitchat/.env.local` holds credentials for **whichever provider is active** — Auth0 and Entra values share the same variable names, so switching providers means replacing these, not adding alongside the other provider's values:

```
VITE_AUTH_CLIENT_ID=<same as ORBIT_AUTH_ENTRA_CLIENT_ID>
VITE_AUTH_TENANT_ID=<same as ORBIT_AUTH_ENTRA_TENANT_ID>
VITE_AUTH_SCOPES=openid profile email api://<client-id>/access_as_user
```

The `api://<client-id>/access_as_user` scope is what makes MSAL request a token audienced for *your* API — requesting only `openid profile email` (or default Graph scopes like `User.Read`) yields a Microsoft Graph-scoped token that ORBIT correctly refuses to accept.

Also confirm the orbitchat config file you're running (e.g. `orbitchat-local.yaml`) has:
```yaml
auth:
  enabled: true
  provider: "entra"
```

### 3. Known Entra quirks (already handled by ORBIT, no action needed)

Two Entra behaviors surprised us during setup — both are already handled in `server/services/oidc_validator.py`, called out here so you don't waste time chasing them if you're debugging:

- **Issuer format**: Entra can mint either a v2.0-format token (`iss = https://login.microsoftonline.com/{tenant}/v2.0`) or a legacy v1.0-format token (`iss = https://sts.windows.net/{tenant}/`) for the *same* audience/scope, depending on the app registration's `accessTokenAcceptedVersion` manifest field — not something you control per login. ORBIT accepts both.
- **Missing email claim**: v1-style tokens carry `upn`/`unique_name` instead of `email`/`preferred_username`. ORBIT falls back through all four claim names automatically.

If you ever see a *different* Entra claim shape that still fails, decode the token at [jwt.io](https://jwt.io) and check `iss`/`aud`/`scp` against what's configured — see Troubleshooting below for the general process.

## Applying config changes

- **ORBIT server**: env vars (`.env`) are read at process startup — restart the server after any change.
- **orbitchat**: also just needs a **process restart**, not a rebuild. `bin/orbitchat.js` reads `VITE_*` vars from `process.env` at server startup and injects them into `window.ORBIT_CHAT_CONFIG`, which takes priority over whatever Vite baked into the JS bundle at build time. `npm run build` / npm publishing is never required for changing these values.

## Verifying it worked

1. Restart both ORBIT and orbitchat, then log out and back in through the browser (a fresh login is required — a stale token from before your config change won't reflect it).
2. Check `logs/orbit.log` for a line like:
   ```
   Provisioned external user: entra:<sub> (provider=entra)
   ```
   or `auth0:<sub>` for Auth0. **No log line at all** (not even a rejection warning) usually means the token never reached the OIDC validator — see Troubleshooting.
3. Confirm the row landed correctly:
   ```bash
   sqlite3 orbit.db "SELECT id, username, provider, external_id, email FROM users WHERE provider IN ('auth0','entra') ORDER BY created_at DESC LIMIT 5;"
   ```
4. In the admin panel → API Keys → edit a key → "Restrict to users" — the new user should be pickable (by email if captured, otherwise by `provider:sub` username).
5. Restrict a key to that user, chat through orbitchat as them (should work), then test with a different/unauthenticated user against the same key (should get rejected).

## Troubleshooting

**No log entry at all on login/chat, not even a rejection.** This is the most common failure and it's silent by design (only exceptions during OIDC verification get logged; "issuer didn't match any provider" and "not a JWT at all" both fall through quietly). Work through these in order:
1. **Is the token even a JWT?** In the browser DevTools Network tab, find the request and check the `Authorization` header. A JWT is three dot-separated base64 segments (`eyJhbGci... . eyJzdWIi... . signature`). If it's a short, dot-less string, it's an **opaque token** — almost always because `audience` (Auth0) wasn't set on the login request, or the scope requested (Entra) didn't target your API. Recheck steps above.
2. **Decode the token at [jwt.io](https://jwt.io)** (paste there, not into chat/logs) and check `iss` and `aud` against what ORBIT's `.env` expects for that provider. A mismatch here means the token was issued correctly but for the wrong resource/tenant/app.
3. **Confirm both processes actually restarted after your `.env`/`.env.local` edits.** `ps aux | grep orbitchat` shows the process start time; compare it against the env file's modification time. Restarting the *ORBIT* server does not restart the separate *orbitchat* Node process, and vice versa — both need a fresh start after a credential change.

**`invalid_request`: "Client ... is not authorized to access resource server ..."** (Auth0). The application hasn't been authorized against the API yet — see Auth0 step 2 above.

**Entra login blocked needing admin approval, or fails after consent.** "Who can consent?" is set to Admins-only on the exposed scope — switch to Admins-and-users (Entra step 1.4), or have a tenant admin grant consent explicitly via API permissions → Grant admin consent.

**User provisions correctly but with no email.** Expected for Auth0 unless you've added the custom-claim Action (step 4); for Entra this should no longer happen with current ORBIT code — if it does, decode the token and check which claim actually carries the address, then set `email_claim` under that provider's config block in `config/config.yaml` to match.
