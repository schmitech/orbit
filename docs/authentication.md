# Authentication Technical Details

## Overview

ORBIT's authentication leverages PBKDF2-SHA256 (600k iterations) for password security and cryptographically secure bearer tokens for session management. The modular architecture persists sessions to the configured internal backend (SQLite, PostgreSQL, or MongoDB), implements permission-based role-based access control (RBAC), and provides both programmatic and CLI interfaces for comprehensive user lifecycle management.

RBAC itself — the role/permission registry, built-in roles (`admin`, `operator`, `auditor`, `analyst`, `user-manager`, `user`), and how permissions gate individual admin routes — is documented in detail in [rbac-architecture.md](rbac-architecture.md). This document covers authentication mechanics (password hashing, tokens, sessions, credential storage, OIDC/SSO); the schema and endpoints below show the role/roles fields authentication produces, but defer to rbac-architecture.md for what each role/permission actually grants.

In addition to this built-in username/password system, ORBIT can **validate access tokens issued by external identity providers** — Microsoft Entra ID (Azure AD) and Auth0 — presented as bearer tokens. Which external identities are allowed in at all is governed separately by the [identity allowlist](#pre-clearing-external-identities-allowlist), which denies by default. This lets browser clients such as `orbitchat` sign users in via OAuth 2.0 / OIDC and call the ORBIT API with the resulting JWT, while the built-in admin/CLI login continues to work unchanged. See [External Identity Providers](#external-identity-providers-oidc).

## Architecture

### Components

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│                 │    │                 │    │                 │
│   CLI Client    │◄──►│  API Routes     │◄──►│  Auth Service   │
│   (orbit.py)    │    │ (auth_routes.py)│    │(auth_service.py)│
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                       │                       │
         v                       v                       v
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│                 │    │                 │    │  Database       │
│ Token Storage   │    │  FastAPI        │    │  Service        │
│ (keyring / file)│    │  Middleware     │    │  (abstraction)  │
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                       │
                                                       v
                                    ┌──────────────────────────────────┐
                                    │  internal_services.backend.type  │
                                    ├──────────┬───────────┬───────────┤
                                    │  sqlite  │ postgres  │  mongodb  │
                                    └──────────┴───────────┴───────────┘
                                       users · sessions · user_blacklist
                                             · user_allowlist
```

`AuthService` never talks to a specific database. It holds a `DatabaseService`
built by `create_database_service()` (`server/services/database_service.py`) and
issues backend-agnostic operations against *collection names* — so the same
authentication code runs unchanged on SQLite, PostgreSQL, or MongoDB, selected
by `internal_services.backend.type`. Read "collection" throughout this document
as "collection or table" depending on that setting.

Per-backend physical schemas: [`docs/sqlite-schema.md`](sqlite-schema.md),
[`docs/postgres-schema.md`](postgres-schema.md). MongoDB is schemaless, so the
documents below *are* its schema.

### Data Flow

1. **Authentication Request**: Client sends credentials to API
2. **Credential Verification**: Service validates against the configured backend
3. **Token Generation**: Cryptographically secure token created
4. **Session Storage**: Token and user info persisted to the configured backend
5. **Token Response**: Bearer token returned to client
6. **Token Persistence**: CLI stores token in secure storage (keyring/file) and loads into session variable
7. **Request Authorization**: Subsequent requests include bearer token from session variable
8. **Token Validation**: Service validates token against active sessions

## Database Schema

### Users Collection

```javascript
{
  "_id": ObjectId("..."),
  "username": "admin",
  "password": "base64_encoded_pbkdf2_hash",  // salt + hash
  "role": "admin",           // primary/display role - first entry of roles, kept for backward compat
  "roles": ["admin"],        // source of truth - full list of assigned roles (see rbac-architecture.md)
  "active": true,
  "created_at": ISODate("2025-01-01T00:00:00Z"),
  "last_login": ISODate("2025-01-01T12:00:00Z")
}
```

A user may hold multiple roles (e.g. `["operator", "auditor"]`); effective permissions are the union of each role's grants, computed by `permissions_for_roles()` in `server/auth/rbac.py`. On SQLite/PostgreSQL, `roles` is stored as a JSON-encoded string column; MongoDB stores it as a native array.

### Sessions Collection

```javascript
{
  "_id": ObjectId("..."),
  "token": "cryptographically_secure_hex_string",
  "user_id": ObjectId("..."),  // Reference to users collection
  "username": "admin",
  "expires": ISODate("2025-01-01T24:00:00Z"),  // TTL index
  "created_at": ISODate("2025-01-01T12:00:00Z")
}
```

### User Blacklist Collection

```javascript
{
  "_id": ObjectId("..."),
  "pattern": "*@spam-domain.com",   // Lowercased; * and ? are wildcards
  "entry_type": "email",            // email | user_id | username
  "reason": "Repeated abuse",
  "created_by": "admin",
  "created_at": ISODate("2026-08-07T12:00:00Z")
}
```

### User Allowlist Collection

Same shape as the blacklist, in its own collection so a pattern can appear in
both rule sets (deny still wins).

```javascript
{
  "_id": ObjectId("..."),
  "pattern": "*@corp.example.com",  // Lowercased; * and ? are wildcards
  "entry_type": "email",            // email | user_id | username
  "reason": "Employees",
  "created_by": "admin",
  "created_at": ISODate("2026-08-26T12:00:00Z")
}
```

### Indexes

- **users.username**: Unique index for fast user lookup
- **sessions.token**: Unique index for token validation
- **sessions.expires**: TTL index for automatic session cleanup
- **user_blacklist.(entry_type, pattern)**: Unique index preventing duplicate rules
- **user_allowlist.(entry_type, pattern)**: Unique index preventing duplicate rules

## Security Features

### Password Security

- **Algorithm**: PBKDF2-SHA256 (Password-Based Key Derivation Function 2 with SHA-256)
- **Iterations**: 600,000 (configurable via `pbkdf2_iterations` setting)
- **Salt Length**: 16 bytes (128 bits) of cryptographically secure random data
- **Key Length**: 32 bytes (256 bits)
- **Salt Generation**: Using Python's `secrets.token_bytes(16)` for cryptographically secure randomness
- **Storage Format**: Base64-encoded concatenation of salt + hash
- **Constant-time comparison**: Using `hmac.compare_digest()` to prevent timing attacks

```python
# Actual password hashing implementation
salt = secrets.token_bytes(16)  # 128 bits of entropy
dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 600000)
encoded_password = base64.b64encode(salt + dk).decode('utf-8')
```

### Token Security

- **Token Generation**: Using `secrets.token_hex(32)` 
- **Token Length**: 64 hexadecimal characters (256 bits of entropy)
- **Token Type**: Opaque bearer tokens (not JWT)
- **Entropy Source**: Python's `secrets` module (cryptographically secure)
- **Session Storage**: Server-side in the configured backend, with an indexed unique lookup on `token`
- **No Token Refresh**: New login required after expiration

### Blacklisting Users

Blacklist rules deny authentication for identities matching a pattern. They are
managed from the admin panel's Users tab ("Blocked Identities") or the
[blacklist endpoints](#blacklist-endpoints), and are stored in the database
rather than in config.

**Why this exists alongside the `active` flag.** Deactivating a user needs a row
in the `users` table, so it only works on someone who has already signed in at
least once, and it handles exactly one account. A blacklist rule is a pattern,
so it can block an abusive external user *before* their first login provisions
them, and can cover a whole disposable-email domain in one entry.

**Matching.** Each rule has an `entry_type` naming the identity field it applies
to — `email`, `user_id`, or `username` — and a `pattern` matched against that
field with shell-style wildcards (`*` matches any run of characters, `?` matches
one). Comparison is case-insensitive and whitespace-trimmed on both sides. A
pattern with no wildcards is an exact match. Patterns consisting only of
wildcards are rejected, since `*` would lock out every administrator.

For external (Entra/Auth0) users the stored username is `{provider}:{subject}`,
so `entra:abc*` blocks by provider subject while `*@spam-domain.com` blocks by
email domain.

**Enforcement point.** Rules are evaluated in `AuthService` at every place a
credential becomes an identity: `validate_token` (both the opaque-session and
external-JWT branches), `authenticate_user` (password login), and
`verify_credentials` (WebSocket basic auth). `_find_or_create_external_user`
also refuses to provision a blacklisted identity, so no row is created for them.

**This only blocks callers who present an identity.** On the admin panel a
user identity is always required, so blacklisting fully covers it. On
inference (chat, files, voice, A2A), however, a valid **API key alone** is
normally sufficient — no bearer token is required, so `validate_token` is
never called and a blacklisted user can simply omit the `Authorization`
header and reach inference unimpeded. Closing this gap is what
[`auth.require_authenticated_user`](#requiring-an-authenticated-user) is for;
without it, treat the blacklist as covering the admin panel and any client
that happens to send a bearer token, not as a hard guarantee on inference.

**Session revocation.** Adding a rule deletes the sessions of every currently
matching user, so an in-flight abuser is cut off at once rather than at token
expiry. The API response reports `matched_users` and `revoked_sessions`.
Removing a rule restores the ability to authenticate but does not restore those
sessions.

**Audit trail.** When `internal_services.audit.admin_events` is enabled, each
mutation is recorded as `auth.blacklist.create`, `auth.blacklist.update`, or
`auth.blacklist.delete` against resource type `blacklist_rule`. Create and
update events record the `pattern`, `entry_type`, and `reason`, so the ledger
answers *who was blocked* rather than merely noting that a rule changed. The
pattern is operator-authored matching syntax, not a credential, so it is safe
to store. Reads (`GET /auth/blacklist`) are not audited.

Successful mutations are keyed by the stored rule id and record the *normalized*
pattern, not the raw submitted string — the handler publishes both to the audit
middleware via `request.state.audit_context`, which is scoped by the route's own
declaration: summary fields pass through the per-route allowlist, and the
resource id is accepted only because the create route explicitly declares the
`context` source. This matters for correlation:
submitting `"  ABUSER@Example.COM  "` stores `abuser@example.com`, and an audit
search for the stored value would miss an event that recorded the raw input. A
failed create has no resource id, since no rule was created, but its
`request_summary` still shows what was attempted, verbatim.

**Lockout guard.** A rule that would match the requesting administrator's own
identity is rejected with a 400, since the blacklist is enforced at token
validation and would otherwise lock the caller out of the panel they'd need in
order to undo it. This guard checks only the requester — an administrator can
still block a *different* administrator.

**Caching and multiple workers.** Because wildcard matching happens in Python
rather than SQL, each worker caches the (small) rule set for
`auth.blacklist.cache_ttl` seconds, default 30. Writes invalidate the writing
worker's cache immediately; under `performance.workers > 1`, sibling workers
pick up a new rule within the TTL. Set `cache_ttl: 0` to re-read on every
authentication. Session revocation is not subject to this delay, so the urgent
case is handled immediately regardless. If the database is unreachable, the
last known rule set is retained rather than failing open to an empty one.

### Pre-clearing external identities (allowlist)

The blacklist above is a *deny*-list, and on its own it leaves external logins in
an untenable posture. ORBIT just-in-time provisions a local user for any subject
an enabled provider will authenticate, so the effective rule is "everyone the
IdP will authenticate is an ORBIT user, minus whoever we explicitly blocked". On
an Auth0 tenant with open signup or social connections that set is effectively
the internet, and blocking abusers one subject at a time is whack-a-mole when
the IdP mints new ones freely.

The **identity allowlist** inverts it. Under
`auth.providers.access_control: allowlist` (the default), an external subject
gains no ORBIT identity at all — no `users` row, no session, on any surface —
unless it matches an allowlist rule.

```yaml
auth:
  providers:
    access_control: allowlist   # allowlist (default) | open
```

- **`allowlist`** — the identity must be pre-cleared. **An empty rule set admits
  nobody**, which is what makes the control fail closed.
- **`open`** — the previous behavior: any identity an enabled provider
  authenticates is provisioned. Appropriate only when the IdP *is* the access
  control (e.g. a single-tenant Entra directory with no guest accounts).

Rules use the same storage, wildcard matching, `entry_type` values, caching, and
management surfaces as blacklist rules — see [Blacklisting Users](#blacklisting-users)
for the pattern semantics, which are identical. What differs:

| | Blacklist | Allowlist |
|---|---|---|
| Empty rule set | blocks nobody | admits nobody (when enforcing) |
| Applies to | every identity, local and external | external identities only |
| Adding a rule | denies; revokes matching sessions | grants; revokes nothing |
| Removing a rule | restores access; no revocation | **withdraws** access; revokes sessions |
| Self-lockout guard | on create and edit | on delete and a narrowing edit |

**Local users are never gated.** Only identities carrying a `provider` are
checked, so the bootstrap `admin` and every password account keep working no
matter what is (or isn't) in the allowlist. Turning enforcement on cannot lock
you out of the panel via a local account.

**`admin_users` entries are implicitly cleared.** An identity listed in
`auth.providers.admin_sso.admin_users` (by email or `provider:subject`) does not
also need an allowlist rule — that listing is already an approval decision, and
requiring it to be restated in two places is how operators lock themselves out.

**Deny wins.** The blacklist is evaluated first, so a deny rule always beats an
allow rule covering the same identity. This is what lets you clear a whole
domain (`*@corp.example.com`) and still block one person in it.

**Enforcement points.** Clearance is checked where an identity is created *and*
on every request:

- `_find_or_create_external_user` — the primary control. A non-cleared subject
  never gets a `users` row, so it never becomes an ORBIT identity on inference,
  files, voice, A2A, or the admin panel.
- `validate_token` — re-checked per request on **both** token paths, so
  *removing* a rule denies an already-provisioned user within
  `auth.allowlist.cache_ttl` seconds. The opaque-session path matters as much as
  the JWT one: admin-panel SSO mints an opaque `dashboard_token`, so a callback
  still in flight when a rule is removed (or one served by a worker whose rule
  cache is stale) can create a session *after* revocation has run. Only the
  per-request check makes removal reliable for those.
- The admin SSO callback reports a distinct `not_cleared` error, so "nobody
  pre-cleared this identity" is distinguishable from "this identity is cleared
  but holds no admin-panel role" — different problems with different fixes.

**Wildcard-only patterns are rejected**, as they are for the blacklist. "Clear
everyone" is a mode, not a rule: set `access_control: open`.

#### Migrating an existing deployment

Enabling enforcement denies every existing external user that no rule covers.
The server names the count at startup rather than leaving you to find out from
support requests:

```
Identity allowlist is enforcing: 47 of 51 existing external users match no rule
and can no longer sign in. Run 'orbit user allowlist seed-from-existing' ...
```

To grandfather the current population in one step:

```bash
orbit user allowlist seed-from-existing --dry-run   # review first
orbit user allowlist seed-from-existing
```

It creates one `username`-type rule per existing external user, printing every
identity and asking for confirmation — signing in once is not an approval
decision, so this stays an explicit, reviewed action rather than anything
automatic at startup.

#### Managing rules

Admin panel: Users tab → **Allowed Identities**, beside Blocked Identities.

```bash
orbit user allowlist list
orbit user allowlist add --pattern '*@corp.example.com' --entry-type email \
  --reason 'Employees'
orbit user allowlist add --pattern 'entra:00000000-...' --entry-type username
orbit user allowlist remove --rule-id 507f1f77bcf86cd799439011
```

For external users the stored username is `{provider}:{subject}`, so
`entry_type: username` with `auth0:abc*` clears by provider subject while
`entry_type: email` with `*@corp.example.com` clears by email domain.

**Audit trail.** Mutations are recorded as `auth.allowlist.create`,
`auth.allowlist.update`, and `auth.allowlist.delete` against resource type
`allowlist_rule`, with the same pattern-recording rationale as the blacklist —
the ledger answers *who was granted access, and by whom*. A deletion is the
security-relevant direction here (it withdraws access), the reverse of the
blacklist.

### Requiring an authenticated user

By default, ORBIT's inference surfaces (chat, files, voice, A2A) authenticate
by **API key alone** — no user identity is required. Setting
`auth.require_authenticated_user: true` (default `false`) makes a valid
`Authorization: Bearer <user-token>` mandatory on every inference request, in
addition to the API key. This is what makes the blacklist above — and a key's
`allowed_user_ids`/`allowed_emails` — actually enforceable on inference: with
the flag off, a blacklisted or non-allowlisted user can simply present the API
key with no bearer token and reach inference anyway, since identity was never
resolved in the first place.

**Per-adapter override.** An adapter's `capabilities.requires_authenticated_user`
(`true`/`false`) overrides the global flag for that adapter only; leaving it
unset inherits the global setting. This lets one public-facing adapter opt out
while the rest of a strict deployment stays locked down, or lets one sensitive
adapter opt in while the rest of the deployment stays key-only.

**The `Authorization: Bearer` header changes meaning.** Normally
`Authorization: Bearer <api-key>` is accepted as a fallback to `X-API-Key`,
for OpenAI-SDK compatibility. Once strict mode applies to a request, that
fallback is disabled — `Authorization: Bearer` is reserved for the user
token, and the API key **must** be sent via `X-API-Key`. OpenAI SDK clients
that only ever send the key as `Authorization: Bearer` need to switch to
`default_headers={"X-API-Key": "<key>"}` with `api_key=<user-token>` in
strict deployments.

**`X-User-ID` is ignored.** That header is unverified and spoofable — it is
attribution metadata used only when no authenticated identity is available.
Once identity is required, the resolved bearer identity is the only source
of `user_id`; a client-supplied `X-User-ID` is silently ignored rather than
trusted.

**A2A** already uses a dedicated `X-ORBIT-User-Authorization` header for user
identity (since `Authorization` carries the API key there). Strict mode makes
that header mandatory rather than optional; no other change to A2A's header
scheme.

**Voice** WebSocket clients authenticate via the handshake `Authorization`
header, or `?access_token=<token>` as a query-param fallback for browser
clients that cannot set handshake headers. A required-but-missing/invalid
identity closes the socket before `accept()` with code `4401`, rather than
producing an HTTP error response (which WebSocket handlers can't return).
Identity is resolved once at connect time; a user blacklisted mid-session
keeps that session until it closes.

**`/mcp` is not covered.** The MCP mount bypasses ORBIT's normal
API-key/user auth entirely (it re-invokes routes internally rather than
going through the FastAPI dependency chain), so it cannot honor this flag.
When `auth.require_authenticated_user` is `true`, ORBIT refuses to mount
`/mcp` at startup and logs a warning, rather than leaving an unauthenticated
surface next to a flag whose purpose is to require authentication.

**Bypass lanes fail closed.** `/health` remains reachable without
credentials so liveness probes keep working. Every other lane that would
otherwise skip API-key validation — no `api_key_service` configured,
`api_keys.enabled: false`, or an empty key resolving via
`api_keys.allow_default` — instead requires an authenticated identity when
strict mode applies, rather than silently exempting itself from it.

**Default is `false`.** Enabling this rejects any client that only sends an
API key, including OpenAI SDK clients using the Bearer fallback. Turn it on
deliberately, after confirming your clients send a bearer token.

### Security Standards Compliance

- **NIST SP 800-63B Compliant**: Meets NIST guidelines for authentication
- **OWASP Standards**: Follows OWASP Authentication Cheat Sheet recommendations
  - 600,000 iterations exceeds OWASP 2023 minimum (600,000 for PBKDF2-SHA256)
  - Secure random generation for all tokens and salts
  - No password logging even in verbose mode
- **FIPS 140-2 Compatible**: Uses approved cryptographic algorithms

## Cryptographic Implementation Details

### Password Hashing Process

1. **Input Validation**: Password encoded to UTF-8
2. **Salt Generation**: 16 bytes from `secrets.token_bytes()`
3. **Key Derivation**: PBKDF2-HMAC-SHA256 with 600,000 iterations
4. **Storage**: Base64(salt || hash) stored in database

### Token Generation Process

1. **Entropy Collection**: 32 bytes from system CSPRNG
2. **Encoding**: Hexadecimal encoding for URL-safe tokens
3. **Uniqueness**: Verified against existing sessions
4. **Storage**: Indexed in the configured backend for O(1) lookups

### Security Considerations

- **No Client-Side Hashing**: All hashing done server-side
- **No Password Hints**: No password recovery without admin intervention
- **No Security Questions**: Only password-based authentication
- **No Remember Me**: Each session requires full authentication

### Additional Security Measures

- **Database Connection Security**: TLS/SSL supported on every backend that
  has a network connection (MongoDB `tls`, PostgreSQL `sslmode`); SQLite is a
  local file, so secure it with filesystem permissions instead
- **Exception Handling**: Backend errors are caught as the abstraction's own
  `DatabaseConnectionError`/`DatabaseTimeoutError`/`DatabaseOperationError`
  types rather than surfaced raw, so driver internals never leak into a response
- **Token Isolation**: Each token is unique and cannot be derived from user info
- **No Password History**: Previous passwords are not stored
- **Secure Defaults**: Default admin password must be changed on first use

### Session Management

- **Bearer token authentication**: Standard HTTP authorization
- **Stateful sessions**: Server-side session storage in the configured backend
- **Session isolation**: Each login creates a new session
- **Forced logout**: Password changes invalidate all sessions
- **Graceful expiration**: Expired tokens automatically cleaned up

## API Endpoints

### Authentication Endpoints

#### POST /auth/login
Authenticate user and create session.

**Request:**
```json
{
  "username": "admin",
  "password": "password123"
}
```

**Response:**
```json
{
  "token": "abc123...",
  "user": {
    "id": "507f1f77bcf86cd799439011",
    "username": "admin", 
    "role": "admin",
    "roles": ["admin"],
    "permissions": ["adapters.manage", "apikeys.manage", "audit.read", "config.manage",
                    "conversations.read", "feedback.read", "logs.read", "metrics.read",
                    "prompts.manage", "system.manage", "users.manage"],
    "active": true
  }
}
```

#### POST /auth/logout
Invalidate current session.

**Headers:**
```
Authorization: Bearer abc123...
```

**Response:**
```json
{
  "message": "Logout successful"
}
```

#### GET /auth/me
Get current user information.

**Headers:**
```
Authorization: Bearer abc123...
```

**Response:**
```json
{
  "id": "507f1f77bcf86cd799439011",
  "username": "admin",
  "role": "admin",
  "roles": ["admin"],
  "active": true
}
```

### User Management Endpoints

#### POST /auth/register
Create new user (requires the `users.manage` permission).

**Headers:**
```
Authorization: Bearer abc123...
```

**Request:**
```json
{
  "username": "newuser",
  "password": "password123",
  "role": "user",
  "roles": ["operator", "auditor"]
}
```

`roles` (optional) assigns multiple roles at once and takes precedence over `role`; when omitted, the user gets `roles: [role]`. Roles are validated against the registry in `server/auth/rbac.py` (see [rbac-architecture.md](rbac-architecture.md)) — an unrecognized role name is rejected with 400.

#### GET /auth/roles
List all registered role names (requires `users.manage`). Used to populate role-assignment UI/CLI.

**Response:**
```json
{"roles": ["admin", "analyst", "auditor", "operator", "user", "user-manager"]}
```

#### GET /auth/users
List all users (requires `users.manage`).

**Headers:**
```
Authorization: Bearer abc123...
```

**Response:**
```json
[
  {
    "id": "507f1f77bcf86cd799439011",
    "username": "admin",
    "role": "admin",
    "roles": ["admin"],
    "active": true,
    "created_at": "2025-01-01T00:00:00Z",
    "last_login": "2025-01-01T12:00:00Z"
  }
]
```

#### PUT /auth/users/{user_id}/roles
Replace a user's role assignment (requires `users.manage`).

**Request:**
```json
{"roles": ["operator", "analyst"]}
```

**Response:**
```json
{"message": "Roles updated successfully", "user_id": "507f1f77bcf86cd799439011", "roles": ["operator", "analyst"]}
```

#### DELETE /auth/users/{user_id}
Delete user (requires `users.manage`).

**Headers:**
```
Authorization: Bearer abc123...
```

### Blacklist Endpoints

Pattern-based denial of authenticated identities. See
[Blacklisting Users](#blacklisting-users) for the semantics.

#### GET /auth/blacklist
List every rule, newest first (requires `users.manage`).

#### POST /auth/blacklist
Add a rule (requires `users.manage`). Matching users' sessions are revoked immediately.

**Request:**
```json
{"pattern": "*@spam-domain.com", "entry_type": "email", "reason": "Disposable-email abuse"}
```

**Response:**
```json
{
  "id": "507f1f77bcf86cd799439011",
  "pattern": "*@spam-domain.com",
  "entry_type": "email",
  "reason": "Disposable-email abuse",
  "created_by": "admin",
  "created_at": "2026-08-07T12:00:00+00:00",
  "matched_users": 3,
  "revoked_sessions": 5
}
```

Returns 400 if the pattern is empty, wildcard-only, longer than 320 characters,
duplicates an existing rule, or would match the requesting administrator.

#### PUT /auth/blacklist/{rule_id}
Edit a rule in place (requires `users.manage`). Takes the same body as `POST`
and is subject to the same validation and self-lockout guard.

Because editing a pattern changes *who* is blocked, this re-runs session
revocation against the new pattern's matches and reports `matched_users` /
`revoked_sessions` the same way creation does. Users the rule no longer matches
keep any sessions they still have — an edit never grants access, it only stops
being the thing that denies them. Returns 404 for an unknown rule id, and 400
if the new `(entry_type, pattern)` collides with a *different* existing rule
(re-saving a row with its own values is allowed and is a no-op).

#### DELETE /auth/blacklist/{rule_id}
Remove a rule (requires `users.manage`). Restores the ability to authenticate;
does not restore sessions that were revoked when the rule was added.

### Allowlist Endpoints

Pattern-based pre-clearing of external identities. See
[Pre-clearing external identities](#pre-clearing-external-identities-allowlist)
for the semantics. Request and response bodies match the blacklist endpoints.

#### GET /auth/allowlist
List every rule, newest first (requires `users.manage`).

#### POST /auth/allowlist
Pre-clear an identity pattern (requires `users.manage`).

**Request:**
```json
{"pattern": "*@corp.example.com", "entry_type": "email", "reason": "Employees"}
```

Adding a rule only ever grants access, so nothing is revoked and no
`matched_users`/`revoked_sessions` counts are reported. Returns 400 on the same
validation failures as the blacklist (empty, wildcard-only, over 320 characters,
or a duplicate).

#### PUT /auth/allowlist/{rule_id}
Edit a rule in place (requires `users.manage`). Narrowing a rule *withdraws*
access, so this revokes sessions for external users the new rule set no longer
clears and reports `matched_users` / `revoked_sessions` accordingly. Returns 404
for an unknown rule id, and 400 if the change would revoke the requesting
administrator's own clearance.

#### DELETE /auth/allowlist/{rule_id}
Remove a rule (requires `users.manage`). Unlike deleting a blacklist rule, this
**withdraws** access: users cleared only by this rule are signed out at once
rather than at token expiry, and the response reports the counts. Returns 400 if
it would revoke the caller's own clearance — a local password administrator is
never gated, so that guard only bites an external admin.

### Password Management Endpoints

#### POST /auth/change-password
Change current user's password.

**Headers:**
```
Authorization: Bearer abc123...
```

**Request:**
```json
{
  "current_password": "oldpassword",
  "new_password": "newpassword123"
}
```

#### POST /auth/reset-password
Reset user password (requires `users.manage`).

**Headers:**
```
Authorization: Bearer abc123...
```

**Request:**
```json
{
  "user_id": "507f1f77bcf86cd799439011",
  "new_password": "newpassword123" 
}
```

## Credential Storage

### Overview

ORBIT CLI stores authentication credentials using configurable storage methods with a simplified state management approach:

- **Keyring (Default)**: Uses system's native credential management
  - **macOS**: macOS Keychain Access
  - **Linux**: Secret Service API (GNOME Keyring, KWallet, etc.)
- **File Storage**: Plain text file in `~/.orbit/.env` (less secure but visible)
- **Fallback**: Base64 encoded file storage when keyring fails

### Authentication State Management

The CLI uses a simplified authentication state management approach:

1. **Secure Storage**: Single source of truth for persistence (keyring or file)
2. **Session Token**: `self.admin_token` instance variable for current CLI session
3. **No Environment Variables**: Tokens are not stored in `os.environ`

**Authentication Flow:**
- **Initialization**: Load token from secure storage → `self.admin_token`
- **Login**: Server → `self.admin_token` + save to secure storage
- **Logout**: Clear `self.admin_token` + clear secure storage
- **API Calls**: Use `self.admin_token` for authorization

### Storage Methods

#### Keyring Storage (Recommended)
- **Security**: High - uses system's encrypted credential storage
- **Visibility**: Hidden - tokens not visible in plain text
- **Configuration**: `auth.credential_storage: keyring` (default)
- **Storage**: System keychain with service "orbit-cli" and account "auth-token"

#### File Storage (User Choice)
- **Security**: Medium - plain text file with restricted permissions (600)
- **Visibility**: High - tokens visible in `~/.orbit/.env`
- **Configuration**: `auth.credential_storage: file`
- **Use Case**: Development, debugging, or when keyring is not available
- **Format**: Direct file reading (no environment variable loading)

### Storage Locations

#### macOS Keychain
```
~/Library/Keychains/login.keychain-db
```

#### Linux Secret Service
```
~/.local/share/keyrings/ (GNOME Keyring)
~/.kde/share/apps/kwallet/ (KDE Wallet)
```

#### Fallback File Storage
```
~/.orbit/.env (base64 encoded, chmod 600)
```

### Managing Stored Credentials

#### Retrieve Bearer Token

After logging in with `orbit login`, the bearer token is stored in the system keychain (or file fallback). To retrieve it for use with admin API endpoints, scripts, or tools like `test_template_query.py`:

##### macOS

Tokens are stored in macOS Keychain via the `security` command:

```bash
# Print the raw bearer token value
security find-generic-password -s "orbit-cli" -a "auth-token" -w
```

Inline usage:
```bash
TOKEN=$(security find-generic-password -s "orbit-cli" -a "auth-token" -w)
```

##### Ubuntu / Debian Linux

Tokens are stored via GNOME Keyring (Secret Service API). Requires `libsecret-tools`:

```bash
# Install if needed
sudo apt-get install libsecret-tools

# Retrieve the token
secret-tool lookup service "orbit-cli" account "auth-token"
```

Inline usage:
```bash
TOKEN=$(secret-tool lookup service "orbit-cli" account "auth-token")
```

> **Note:** On headless servers without a desktop session, GNOME Keyring may not be running. In this case ORBIT falls back to file storage (see below).

##### KDE Linux

Tokens are stored in KDE Wallet:

```bash
kwallet-query kdewallet -f "orbit-cli" -r "auth-token"
```

##### Amazon Linux / AWS EC2 / Headless Servers

Headless environments typically don't have a keyring daemon. ORBIT automatically falls back to file-based storage at `~/.orbit/.env`. Retrieve the token:

```bash
# If stored in plain text (auth.credential_storage: file)
grep 'API_ADMIN_TOKEN=' ~/.orbit/.env | cut -d'=' -f2

# If stored as base64 fallback (default when keyring is unavailable)
grep 'API_ADMIN_TOKEN_B64=' ~/.orbit/.env | cut -d'=' -f2 | base64 --decode
```

Inline usage:
```bash
# Plain text storage
TOKEN=$(grep 'API_ADMIN_TOKEN=' ~/.orbit/.env | cut -d'=' -f2)

# Base64 fallback storage
TOKEN=$(grep 'API_ADMIN_TOKEN_B64=' ~/.orbit/.env | cut -d'=' -f2 | base64 --decode)
```

> **Tip:** To force file storage instead of keyring on any platform, set `auth.credential_storage: file` in your config or run `orbit config set auth.credential_storage file`.

##### Windows

Tokens are stored in Windows Credential Manager via the `keyring` Python library:

```powershell
# Using Python directly
python -c "import keyring; print(keyring.get_password('orbit-cli', 'auth-token'))"
```

Or via PowerShell with the `CredentialManager` module:
```powershell
# Install module if needed
Install-Module -Name CredentialManager

# Retrieve the token
(Get-StoredCredential -Target "orbit-cli:auth-token").Password
```

If keyring is not installed, check the fallback file:
```powershell
Get-Content "$env:USERPROFILE\.orbit\.env" | Select-String "API_ADMIN_TOKEN"
```

##### Using the Token

Once retrieved, the token works the same on all platforms:

```bash
# With the template diagnostics CLI tool
python server/tools/test_template_query.py \
  --query "salary stats" \
  --adapter intent-sql-sqlite-hr \
  --api-key "$TOKEN"

# With curl
curl -H "Authorization: Bearer $TOKEN" http://localhost:3000/admin/adapters/info
```

##### Cross-Platform Helper Script

A convenience script at `utils/scripts/get-auth-token.sh` auto-detects the platform and credential storage method:

```bash
# Print the token (with platform detection info on stderr)
./utils/scripts/get-auth-token.sh

# Quiet mode - token only, no status messages
./utils/scripts/get-auth-token.sh --quiet

# Export as shell variable
eval "$(./utils/scripts/get-auth-token.sh --export)"
echo $ORBIT_TOKEN

# Use directly with tools
python server/tools/test_template_query.py \
  --query "salary stats" --adapter intent-sql-sqlite-hr \
  --api-key "$(./utils/scripts/get-auth-token.sh --quiet)"
```

The script tries these methods in order based on detected platform:
- **macOS**: Keychain → Python keyring → file fallback
- **Linux**: GNOME Keyring → KDE Wallet → Python keyring → file fallback
- **AWS/cloud/headless**: Python keyring → file fallback
- **Windows (Git Bash)**: Python keyring → file fallback

##### Verifying Storage Method

To check which storage method is active:
```bash
orbit config show --key auth.credential_storage
```

#### View Stored Credentials

**macOS:**
```bash
# View auth token entry (full metadata)
security find-generic-password -s "orbit-cli" -a "auth-token"

# View server URL entry
security find-generic-password -s "orbit-cli" -a "server-url"

# List all orbit-cli entries
security find-generic-password -s "orbit-cli"
```

**Linux:**
```bash
# Using secret-tool (GNOME Keyring)
secret-tool search service "orbit-cli"

# Using kwallet (KDE)
kwallet-query kdewallet -r "orbit-cli"

# Using dbus (generic)
dbus-send --session --dest=org.freedesktop.secrets \
  --print-reply /org/freedesktop/secrets \
  org.freedesktop.Secret.Service.SearchItems \
  dict:string:string:"service","orbit-cli"
```

**GUI Method (macOS):**
1. Open "Keychain Access" app
2. Search for "orbit-cli"
3. View entries for "auth-token" and "server-url"

**GUI Method (Linux):**
- **GNOME**: Open "Passwords and Keys" (seahorse)
- **KDE**: Open "KDE Wallet Manager"

#### Delete Stored Credentials

**macOS:**
```bash
# Delete auth token
security delete-generic-password -s "orbit-cli" -a "auth-token"

# Delete server URL
security delete-generic-password -s "orbit-cli" -a "server-url"

# Delete all orbit-cli entries
security delete-generic-password -s "orbit-cli"
```

**Linux:**
```bash
# Using secret-tool (GNOME Keyring)
secret-tool remove service "orbit-cli" account "auth-token"
secret-tool remove service "orbit-cli" account "server-url"

# Using kwallet (KDE)
kwallet-query kdewallet -d "orbit-cli"
```

**Fallback File:**
```bash
# Remove fallback file storage
rm ~/.orbit/.env
```

#### Troubleshooting Credential Storage

**Check if keyring is available:**
```bash
python -c "import keyring; print('Keyring available:', keyring.get_keyring())"
```

**Force fallback storage:**
```bash
# Clear keyring and force file storage
orbit logout
rm ~/.orbit/.env  # if exists
# Next login will use fallback storage
```

**Reset all credentials:**
```bash
# Complete credential reset
orbit logout
rm -rf ~/.orbit/
# Re-login to recreate storage
```

### Security Considerations

#### Keyring vs File Storage

- **Keyring (Recommended)**: Uses system's encrypted credential storage
- **File Storage (Fallback)**: Base64 encoded, file permissions 600
- **Migration**: Automatically migrates from file to keyring when available

#### Security Best Practices

1. **Use Keyring**: Install `keyring` package for enhanced security
2. **Regular Rotation**: Change passwords periodically
3. **Session Management**: Use `orbit logout` to clear credentials
4. **Access Control**: Keep `~/.orbit/` directory secure (chmod 700)

#### Installation Requirements

**macOS:**
```bash
# Keyring support is built-in
pip install keyring
```

**Linux:**
```bash
# GNOME Keyring
sudo apt-get install python3-keyring gnome-keyring

# KDE Wallet
sudo apt-get install python3-keyring kwallet

# Generic Secret Service
sudo apt-get install python3-keyring libsecret-1-dev
```

#### Configuring Storage Method

**Set storage method in config.yaml:**
```yaml
auth:
  credential_storage: keyring  # or "file"
```

**Change storage method:**
```bash
# Switch to file storage (plain text)
orbit config set auth.credential_storage file

# Switch back to keyring storage
orbit config set auth.credential_storage keyring

# Clear existing credentials after changing method
orbit logout
```

**Check current storage method:**
```bash
orbit config show --key auth.credential_storage
```

## CLI Commands

### Authentication Commands

#### Login
```bash
# Interactive login (recommended)
orbit login

# With credentials (less secure)
orbit login --username admin --password secret123
```

#### Logout
```bash
orbit logout
```

#### Current User Info
```bash
orbit me
```

#### Check Authentication Status
```bash
# Check if authenticated and show user info
orbit auth-status

# Check with JSON output for scripting
orbit auth-status --output json

# Check authentication and credential storage
orbit auth-status
# Shows:
# - Authentication status
# - User information
# - Security storage method (keyring vs file)
```

### Password Management

#### Change Password (Self-Service)
```bash
# Interactive (recommended)
orbit change-password

# With arguments (less secure)
orbit change-password --current-password old --new-password new
```

### User Management (requires the `users.manage` permission)

#### List Users
```bash
orbit user list
```

#### List Registered Roles
```bash
orbit user roles
```

#### Register New User
```bash
# Single role (backward compatible)
orbit register --username newuser --password pass123 --role user

# Multiple roles
orbit register --username newuser --password pass123 --roles operator,auditor
```

#### Assign/Replace a User's Roles
```bash
orbit user set-roles --username newuser --roles analyst
orbit user set-roles --user-id 507f1f77bcf86cd799439011 --roles operator,auditor
```

#### Delete User
```bash
orbit user delete --user-id 507f1f77bcf86cd799439011
```

#### Manage the Identity Allowlist
```bash
orbit user allowlist list
orbit user allowlist add --pattern '*@corp.example.com' --entry-type email
orbit user allowlist remove --rule-id 507f1f77bcf86cd799439011

# Grandfather existing external users when enabling enforcement
orbit user allowlist seed-from-existing --dry-run
orbit user allowlist seed-from-existing
```

#### Reset User Password
```bash
orbit user reset-password --user-id 507f1f77bcf86cd799439011 --password newpass123
```

## Configuration

### Security Configuration

```yaml
auth:
  # Enable/disable authentication system
  enabled: true
  
  # Password hashing configuration
  pbkdf2_iterations: 600000  # OWASP 2023 recommended minimum
  
  # Session configuration
  session_duration_hours: 12
  
  # Default admin (change immediately!)
  default_admin_username: "admin"
  default_admin_password: "${ORBIT_DEFAULT_ADMIN_PASSWORD}"
  
  # Credential storage method: "keyring" (default) or "file"
  # - keyring: Uses system keychain (macOS Keychain, Linux Secret Service) - more secure
  # - file: Uses plain text file in ~/.orbit/.env - less secure but visible
  credential_storage: keyring
```

### Backend Settings

Authentication reads and writes through whichever backend
`internal_services.backend.type` selects:

```yaml
internal_services:
  backend:
    type: "sqlite"                     # sqlite | postgres | mongodb
    sqlite:
      database_path: "orbit.db"
```

On the SQL backends every table name is fixed (`users`, `sessions`,
`user_blacklist`, `user_allowlist`). On MongoDB, only the `users` and
`sessions` collections are renameable — the two rule collections are
constants (`UserBlacklistService.COLLECTION` / `UserAllowlistService.COLLECTION`)
and are not configurable on any backend.

#### MongoDB Settings

```yaml
internal_services:
  mongodb:
    host: ${INTERNAL_SERVICES_MONGODB_HOST}
    port: ${INTERNAL_SERVICES_MONGODB_PORT}
    database: ${INTERNAL_SERVICES_MONGODB_DB}
    username: ${INTERNAL_SERVICES_MONGODB_USERNAME}
    password: ${INTERNAL_SERVICES_MONGODB_PASSWORD}
    # Collection names (MongoDB only)
    users_collection: "users"
    sessions_collection: "sessions"
```

> If you rename these, note that session revocation reads the *configured*
> names — a rule write reporting `revoked_sessions: 0` on a renamed deployment
> was a bug, fixed by resolving the names the same way `AuthService` does.

## External Identity Providers (OIDC)

ORBIT can validate access tokens issued by **Microsoft Entra ID** and **Auth0** on top of the built-in username/password system. This is a **validation-only** integration: the client (e.g. `orbitchat`) performs the OAuth 2.0 Authorization Code + PKCE login and sends the resulting access token to ORBIT as `Authorization: Bearer <jwt>`. ORBIT verifies the JWT and maps it to a local user. ORBIT itself never initiates an OAuth flow — there is no CLI browser login.

### How it works

The bearer token presented on every request is inspected by `AuthService.validate_token()`:

- **Opaque session tokens** (issued by `orbit login`, 64 hex characters, no dots) → validated against the database `sessions` table as before.
- **JWTs** (external-provider access tokens, always contain two dots) → routed to the OIDC validator when `auth.providers.enabled` is true.

For a JWT, ORBIT:

1. Reads the unverified `iss` claim only to select the matching provider (routing).
2. Fetches the provider's signing key from its JWKS endpoint (cached in memory) and fully verifies the token: **RS256** signature, `iss`, `aud`, and `exp` (60s leeway). `sub` is required.
3. **Just-in-time provisions** a local user on first login, keyed by subject — but only if the identity is cleared by the [identity allowlist](#pre-clearing-external-identities-allowlist), which by default requires an explicit rule. An uncleared subject is rejected and no account is created. The stored username is `"{provider}:{sub}"` (e.g. `entra:00000000-...` or `auth0|abc123`), with the email captured for display. On later logins the existing user is reused.
4. Returns the same user context (`id`, `username`, `role`, `roles`, `permissions`, `active`) as a normal login, so RBAC, admin routes, and audit logging all work identically.

Any invalid, expired, mis-issued, or wrong-audience token is rejected (401) — the validator fails closed and never raises.

Notes:
- **Pre-clearing**: by default (`access_control: allowlist`) an external identity must match an allowlist rule before any of this happens. See [Pre-clearing external identities](#pre-clearing-external-identities-allowlist).
- **Role assignment**: a JIT-provisioned user receives `roles: [auth.providers.default_role]` **at creation only**. Keep this a role with no permissions (`user`); anything else grants every external identity admin-panel access at first login, and the server logs a warning at startup if it does. Roles are managed in ORBIT thereafter (e.g. `orbit user set-roles`) and are **not** overwritten on subsequent logins.
- **External users cannot password-login**: they have no usable local password. `orbit login` and `change-password` reject them.
- **Deactivation is honored**: deactivating a JIT-provisioned user blocks re-login; it is not silently reactivated.

### Installation

The OIDC libraries are not part of the default install. Add the `auth-providers` profile:

```bash
./install/setup.sh --profile auth-providers   # installs PyJWT[crypto]
```

If `auth.providers.enabled` is true but the profile is not installed, the server **fails fast at startup** with an install hint.

### Configuration

In `config/config.yaml`, under the `auth:` block:

```yaml
auth:
  # ... existing username/password settings ...
  providers:
    enabled: false                 # Master switch for external-provider validation
    access_control: allowlist      # allowlist (deny-by-default) | open
    default_role: "user"           # Role assigned to users provisioned on first login
    entra:
      enabled: false
      tenant_id: ${ORBIT_AUTH_ENTRA_TENANT_ID:-}
      client_id: ${ORBIT_AUTH_ENTRA_CLIENT_ID:-}   # Expected token audience
    auth0:
      enabled: false
      domain: ${ORBIT_AUTH_AUTH0_DOMAIN:-}          # e.g. your-tenant.us.auth0.com
      audience: ${ORBIT_AUTH_AUTH0_AUDIENCE:-}      # API identifier = expected audience
```

Secrets are supplied via environment variables:

| Variable | Provider | Purpose |
|----------|----------|---------|
| `ORBIT_AUTH_ENTRA_TENANT_ID` | Entra | Directory (tenant) ID — used to build issuer and JWKS URLs |
| `ORBIT_AUTH_ENTRA_CLIENT_ID` | Entra | Application (client) ID — the expected token `aud` |
| `ORBIT_AUTH_AUTH0_DOMAIN` | Auth0 | Tenant domain, e.g. `your-tenant.us.auth0.com` |
| `ORBIT_AUTH_AUTH0_AUDIENCE` | Auth0 | API identifier registered in Auth0 — the expected token `aud` |

Derived endpoints (no configuration needed):

| Provider | Issuer (`iss`) | JWKS |
|----------|----------------|------|
| Entra | `https://login.microsoftonline.com/{tenant_id}/v2.0` | `https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys` |
| Auth0 | `https://{domain}/` | `https://{domain}/.well-known/jwks.json` |

Accepted audience: Auth0 → the configured `audience`; Entra → either the bare `client_id` or `api://{client_id}`.

### Provider setup

**Microsoft Entra ID**
1. Register an application in Entra ID (Azure AD) → copy the **Application (client) ID** and **Directory (tenant) ID**.
2. Under **Expose an API**, set the Application ID URI (`api://{client_id}`) and add a scope (e.g. `access_as_user`). The client must request this scope so the issued access token's `aud` targets ORBIT.
3. Set `ORBIT_AUTH_ENTRA_TENANT_ID` / `ORBIT_AUTH_ENTRA_CLIENT_ID` and enable the provider.

**Auth0**
1. Create an **API** in Auth0 → its **Identifier** is the audience (`ORBIT_AUTH_AUTH0_AUDIENCE`).
2. Create/register the SPA application the client uses; note the tenant **domain** (`ORBIT_AUTH_AUTH0_DOMAIN`).
3. The client requests tokens with `audience` set to the API identifier so the access token's `aud` matches ORBIT.

> **Important — Entra audience caveat.** Entra only issues a token whose `aud` equals your app when the client requests a scope for *your* API (`api://{client_id}/...`). If the client only requests Microsoft Graph scopes (e.g. `User.Read`), it receives a **Graph** access token whose audience is Graph — ORBIT cannot and must not validate that token. Ensure the client (e.g. the `orbitchat` MSAL scopes) requests ORBIT's own API scope, not just Graph scopes.

For a full click-by-click walkthrough of both dashboards (Auth0 API creation, application authorization, Entra scope exposure, consent settings) plus troubleshooting for the failure modes you'll actually hit, see [orbitchat-external-auth-setup.md](orbitchat-external-auth-setup.md).

### Admin Panel SSO

The bearer-token validation above is for API clients that already hold a provider token. ORBIT's **own admin panel** (`/admin`) can additionally offer "Sign in with Microsoft / Auth0" using a **server-side OAuth 2.0 Authorization Code + PKCE** flow. On success it mints the same `dashboard_token` session cookie the username/password login uses, so the rest of the admin panel is unchanged.

**Flow**

1. The login page shows a button per enabled provider linking to `GET /admin/auth/{provider}/login`.
2. That route generates `state`, a PKCE `code_verifier`/`code_challenge`, and a `nonce`, stashes them in a short-lived httponly cookie (`admin_sso_flow`, ~5 min, `SameSite=Lax`), and redirects to the provider's authorize endpoint.
3. The provider redirects back to `GET /admin/auth/{provider}/callback`. ORBIT verifies `state`, exchanges the `code` at the token endpoint, and validates the returned **id_token** (RS256 via JWKS, `aud == client_id`, `iss`, `exp`, and matching `nonce`).
4. The user's email/subject is checked against the **admin allowlist** (`admin_users`); an email entry matches only if the provider verified the address (see [Email verification and the shape of `admin_users` entries](#email-verification-and-the-shape-of-admin_users-entries)). If they match, they are JIT-provisioned (or re-promoted) as `admin`. If they don't match, the identity must be cleared by the [identity allowlist](#pre-clearing-external-identities-allowlist) — an uncleared identity is refused outright, with no account created. A cleared identity is JIT-provisioned/looked up and granted a session if it already holds *any* admin-panel role (assigned manually via the Users tab or `orbit user set-roles`); otherwise the login page shows an error. See "Admin Panel SSO" below for the full allowlist-vs-manual-role interaction, including why a role assigned to an allowlisted identity won't stick.

**Configuration**

```yaml
auth:
  providers:
    entra:
      enabled: true
      tenant_id: ${ORBIT_AUTH_ENTRA_TENANT_ID}
      client_id: ${ORBIT_AUTH_ENTRA_CLIENT_ID}
      client_secret: ${ORBIT_AUTH_ENTRA_CLIENT_SECRET:-}   # optional (confidential client)
    auth0:
      enabled: true
      domain: ${ORBIT_AUTH_AUTH0_DOMAIN}
      audience: ${ORBIT_AUTH_AUTH0_AUDIENCE}
      client_id: ${ORBIT_AUTH_AUTH0_CLIENT_ID}             # required for SSO (id_token audience)
      client_secret: ${ORBIT_AUTH_AUTH0_CLIENT_SECRET:-}   # optional (confidential client)
    admin_sso:
      enabled: true
      base_url: ${ORBIT_ADMIN_BASE_URL:-}   # optional; set when behind a proxy so the redirect URI is correct
      admin_users:                          # emails and/or "provider:subject" granted admin at login
        - "alice@example.com"
        - "entra:00000000-0000-0000-0000-000000000000"
```

#### Email verification and the shape of `admin_users` entries

An `admin_users` entry is either an **email** or a **`provider:subject`** pair, and
the two are not equally strong.

A `provider:subject` entry is matched against the id_token's `sub` claim, which the
IdP assigns and a user cannot choose. **Prefer this form.**

An email entry is matched against the token's email claim, and on some providers a
user can *self-assert* that address — an Auth0 database-signup connection, or a
social connection that doesn't verify. Left unchecked, anyone who could register an
allowlisted address at the IdP would be promoted to `admin` at first login. ORBIT
therefore matches an email entry only when the id_token vouches for the address:

```yaml
auth:
  providers:
    auth0:
      require_verified_email: true    # default for Auth0
    entra:
      require_verified_email: false   # default for Entra
```

With the flag on, an email entry matches only if the id_token carries
`email_verified: true`; a `false` **or absent** claim does not match, and the denial
is logged with the `provider:subject` you could allowlist instead. The flag never
affects `provider:subject` entries.

The defaults differ because the providers differ. Auth0 emits `email_verified` and
its connections may allow self-asserted addresses, so it defaults to `true`. Entra
id_tokens carry no `email_verified` claim at all, and the address comes from the
directory rather than from the user, so requiring it there would break a path that
is not attacker-controlled; it defaults to `false`. Set it explicitly if your tenant
differs — e.g. `true` on Entra only if you inject a verified-email optional claim.

Additional environment variables: `ORBIT_AUTH_AUTH0_CLIENT_ID`, `ORBIT_AUTH_ENTRA_CLIENT_SECRET`, `ORBIT_AUTH_AUTH0_CLIENT_SECRET`, `ORBIT_ADMIN_BASE_URL`.

- **`client_secret` is optional.** With PKCE alone the flow works as a public client (you can reuse an SPA app registration). Supplying a secret upgrades the code exchange to a confidential client.
- **Full admin access is granted only by `admin_users`.** A matching identity is created/promoted to `admin` at every login (this overrides any role assigned locally). There's no need for a bootstrap password admin.
- **Non-matching identities aren't automatically rejected — but they must still be pre-cleared.** A user not on `admin_users` can sign into the Admin Panel via SSO only if *both* hold: their identity is cleared by the [identity allowlist](#pre-clearing-external-identities-allowlist), and an admin has assigned them a scoped role (`operator`, `auditor`, `analyst`, `user-manager`) via the Users tab or `orbit user set-roles` — that role is preserved across logins. The two failures are reported distinctly: an identity no allowlist rule covers gets `not_cleared` (and no account is created for it at all), while a cleared identity with no admin-panel role gets `not_authorized`.

> **Troubleshooting: "I changed this SSO user's role but it keeps reverting to admin."** This happens when the identity (by email or `provider:subject`) is still listed in `admin_users` — the allowlist is authoritative and re-promotes to `admin` on *every* login, overriding anything set in the Users tab. To make a demotion stick, remove the identity from `admin_users` in `config/config.yaml` and reload/restart the server; the role you assigned locally (e.g. `analyst`) will then take effect on their next SSO login. Make sure at least one other path to full admin remains available (another allowlisted identity, or the local bootstrap `admin` account) before removing the only allowlisted identity.

**Redirect URI to register** with each provider (must match exactly):

```
{base_url or auto-detected origin}/admin/auth/entra/callback
{base_url or auto-detected origin}/admin/auth/auth0/callback
```

For Auth0, add these to the application's **Allowed Callback URLs**; for Entra, add them as **Web** redirect URIs on the app registration. Set `base_url` when ORBIT sits behind a reverse proxy/TLS terminator so the callback URL matches what was registered.

**Security notes**

- `state` (CSRF), PKCE `code_challenge` (S256), and `nonce` (replay) are all enforced; the flow secrets live only in a short-lived httponly cookie.
- An `admin_users` **email** entry matches only a provider-verified address, so a self-asserted email cannot be used to claim an allowlisted admin identity. `provider:subject` entries are unspoofable and always match.
- The id_token is validated against `client_id` as audience (distinct from the API-audience used for bearer access tokens), plus issuer, expiry, and nonce; validation fails closed.
- Buttons are plain links — no client-side JS SDK is loaded, so the admin panel's Content-Security-Policy is unaffected.

### Consistency with the orbitchat client

Provider names (`entra`, `auth0`) and the token model match the `orbitchat` client, which already implements these logins (MSAL for Entra, `@auth0/auth0-react` for Auth0) and sends the access token as a bearer token. The server maps identity from the validated JWT `sub` claim (the same immutable subject the client uses), so server and client agree on user identity.

### Adding a new provider

Any OpenID Connect provider (Okta, Keycloak, Google, Ping, etc.) can be added with a small, well-contained change. Because both the bearer path and admin SSO are driven by config-selected provider metadata, the work is mostly "teach ORBIT this provider's endpoint URLs." The example below adds a provider named `okta`.

The core assumption to preserve: tokens are **RS256-signed OIDC JWTs** validated against the provider's **JWKS** by `issuer`/`audience`/`exp`/`sub`. Providers that don't fit that model (opaque tokens, non-OIDC OAuth) need more than these steps.

#### 1. Add the endpoint derivation

Both services build their provider metadata from a single helper per provider in `server/services/oidc_validator.py`. Add one for the new provider next to `entra_endpoints()` / `auth0_endpoints()`:

```python
def okta_endpoints(domain: str) -> Dict[str, str]:
    domain = domain.rstrip('/')
    return {
        "issuer": f"https://{domain}",                       # some Okta orgs use /oauth2/default
        "jwks_uri": f"https://{domain}/oauth2/v1/keys",
        "authorize_url": f"https://{domain}/oauth2/v1/authorize",
        "token_url": f"https://{domain}/oauth2/v1/token",
    }
```

> Prefer fetching these from the provider's discovery document (`/.well-known/openid-configuration`) if you don't want to hardcode paths. Keep the four keys (`issuer`, `jwks_uri`, `authorize_url`, `token_url`) — that's the shape both services consume.

#### 2. Register it for bearer validation

In `OIDCValidator.__init__` (`server/services/oidc_validator.py`), add a block mirroring the `entra`/`auth0` ones, and a `_build_okta()` that returns `{issuer, audiences, jwks_client}`:

```python
okta = providers_config.get('okta', {})
if okta.get('enabled'):
    self._providers['okta'] = self._build_okta(okta)
```

`validate()` needs no change: it already routes by matching the token's `iss` to a registered provider's `issuer`, verifies RS256 against that provider's JWKS, and normalizes claims to `{provider, external_id=sub, email}`. Provisioning, the `provider:sub` username scheme, and the `validate_token` shape-branch are all provider-agnostic.

#### 3. (Optional) Register it for admin panel SSO

In `AdminSSOService.__init__` (`server/services/admin_sso_service.py`), add the same enable-check calling `self._build(okta_cfg, okta_endpoints(...), label="Okta")`. `build_authorize_url` / `exchange_code` / `validate_id_token` / `is_admin` are generic and need no change. The login route `/admin/auth/{provider}/login` accepts any provider name the service knows, and the login page renders a button for each via `provider_labels()`.

#### 4. Add config keys

Extend `auth.providers` in `config/config.yaml`:

```yaml
auth:
  providers:
    okta:
      enabled: false
      domain: ${ORBIT_AUTH_OKTA_DOMAIN:-}          # e.g. dev-12345.okta.com
      audience: ${ORBIT_AUTH_OKTA_AUDIENCE:-}      # bearer-path access-token audience
      client_id: ${ORBIT_AUTH_OKTA_CLIENT_ID:-}    # admin-SSO id_token audience
      client_secret: ${ORBIT_AUTH_OKTA_CLIENT_SECRET:-}  # optional (confidential SSO client)
```

Use the `${VAR:-}` optional form so a disabled provider produces no startup warnings, and document the new env vars in `env.example`.

#### 5. Test it

Mirror `server/tests/test_auth/test_external_auth.py` and `test_admin_sso.py`: sign tokens with a local RSA keypair and monkeypatch the provider's `PyJWKClient.get_signing_key_from_jwt` to return the test public key — no network. Cover a valid token (provisions `okta:<sub>`), wrong audience, bad signature, expired, and missing `sub`.

#### Checklist

| Step | File | Required for |
|------|------|--------------|
| `*_endpoints()` helper | `server/services/oidc_validator.py` | both |
| `__init__` enable-block + `_build_*` | `server/services/oidc_validator.py` | bearer validation |
| `__init__` enable-block | `server/services/admin_sso_service.py` | admin SSO (optional) |
| `auth.providers.<name>` block | `config/config.yaml` | both |
| env vars | `env.example` | both |
| tests | `server/tests/test_auth/` | both |

What you do **not** touch: `AuthService.validate_token` (routes by `iss`), the `provider:sub` provisioning, `auth_dependencies.py`, any route, or the login-page template — they're all provider-agnostic by design.

### Security notes

- Signatures are verified with **RS256 only** (no algorithm downgrade, no `none`).
- `exp`, `iss`, `aud`, and `sub` are all required; tokens missing any are rejected.
- Signing keys are fetched from JWKS over TLS and cached; the blocking fetch runs off the event loop.
- Identity is taken **only** from the verified JWT — the `X-User-ID` header is used for chat-history attribution, never for authorization.

## Implementation Details

### Service Layer (AuthService)

Located in `server/services/auth_service.py`

#### Key Methods:

- `authenticate_user()`: Validate credentials and create session
- `validate_token()`: Check token validity and return user info (routes JWTs to OIDC validation — see [External Identity Providers](#external-identity-providers-oidc))
- `change_password()`: Update password with verification
- `reset_user_password()`: Admin password reset without verification
- `create_user()`: Create new user account
- `delete_user()`: Remove user and all sessions
- `list_users()`: Get all user accounts

External-provider (OIDC) token verification lives in `server/services/oidc_validator.py` (`OIDCValidator`), built by `AuthService` during `initialize()` when `auth.providers.enabled` is set.

#### Security Features:

- Password hashing with PBKDF2-SHA256
- Cryptographically secure token generation
- Session management with automatic cleanup
- Comprehensive error handling and logging

### API Layer (auth_routes.py)

Located in `server/routes/auth_routes.py`

#### Features:

- FastAPI-based REST endpoints
- Pydantic models for request/response validation
- Dependency injection for service access
- Role-based authorization decorators
- Comprehensive error handling

### CLI Layer (orbit.py)

Located in `bin/orbit.py`

#### Features:

- Interactive password prompts with `getpass`
- Simplified token storage using secure storage (keyring/file) as single source of truth
- Session token management via `self.admin_token` instance variable
- Comprehensive error handling and user feedback
- Support for both interactive and scripted usage
- Automatic migration from legacy storage formats

## Security Best Practices

### Implemented

✅ **Strong Password Hashing**: PBKDF2-SHA256 with 600k iterations  
✅ **Secure Token Generation**: Cryptographically random tokens  
✅ **Session Expiration**: Automatic timeout and cleanup  
✅ **Password Confirmation**: Interactive CLI prompts confirmation  
✅ **Session Invalidation**: Password changes clear all sessions  
✅ **Permission-Based Access**: Each admin route gated by a specific permission, not a binary admin flag (see [rbac-architecture.md](rbac-architecture.md))  
✅ **Input Validation**: Pydantic models validate all inputs  
✅ **Error Handling**: Secure error messages, no info leakage  
✅ **Audit Logging**: Authentication events logged  
✅ **Login Rate Limiting**: Cache-backed IP and username throttling with degraded-mode fallback — [implementation plan](roadmap/authentication/complete/phase-1-auth-login-rate-limiting.md)
✅ **Password Complexity**: Configurable local password requirements and common-password rejection — [implementation plan](roadmap/authentication/complete/phase-2-auth-password-complexity.md)

### Recommended Additional Security

Plans for the remaining phases are tracked under
[`docs/roadmap/authentication/`](roadmap/authentication/), ordered by dependency and effort (Phase 3 → 7).

🔸 **Account Lockout**: Temporary lockout after failed attempts — [roadmap](roadmap/authentication/phase-3-auth-account-lockout.md) (Phase 3)  
🔸 **Audit Trail**: Detailed logging of all user actions — [roadmap](roadmap/authentication/phase-4-auth-audit-trail-coverage.md) (Phase 4)  
🔸 **Session Monitoring**: Track active sessions per user — [roadmap](roadmap/authentication/phase-5-auth-session-monitoring.md) (Phase 5)  
🔸 **IP Whitelisting**: Restrict admin access by IP — [roadmap](roadmap/authentication/phase-6-auth-admin-ip-allowlist.md) (Phase 6)  
🔸 **2FA Support**: Two-factor authentication for admin accounts — [roadmap](roadmap/authentication/phase-7-auth-2fa.md) (Phase 7)  

## Error Handling

### Common Error Responses

#### 401 Unauthorized
```json
{
  "detail": "Invalid username or password"
}
```

#### 403 Forbidden  
```json
{
  "detail": "Only users with the users.manage permission can create new users"
}
```

#### 404 Not Found
```json
{
  "detail": "User not found or could not be deleted"
}
```

#### 400 Bad Request
```json
{
  "detail": "Current password is incorrect or password change failed"
}
```

### CLI Error Handling

The CLI provides user-friendly error messages and proper exit codes:

```bash
# Example error output
$ orbit login --username invalid --password wrong
Login failed: Login failed: 401 {"detail":"Invalid username or password"}

# Exit codes
0 = Success
1 = Error/Failure
```

## Usage Examples

### Initial Setup

```bash
# 1. Start the server (creates default admin)
orbit start

# 2. Login with default credentials
orbit login --username admin --password admin123

# 3. Change default password immediately
orbit change-password
# Enter current password: admin123
# Enter new password: [secure_password]
# Confirm new password: [secure_password]

# 4. Create additional users, assigning least-privilege roles
orbit register --username developer --password devpass123 --role user
orbit register --username ops --password opspass123 --roles operator
orbit register --username reviewer --password revpass123 --roles analyst
orbit register --username manager --password mgmtpass123 --role admin
```

### Daily Operations

```bash
# Login
orbit login --username developer

# Check current user
orbit me

# Change your password
orbit change-password

# List all users (requires users.manage)
orbit user list

# Reassign a user's roles (requires users.manage)
orbit user set-roles --username ops --roles operator,auditor

# Reset forgotten password (requires users.manage)
orbit user reset-password --user-id 507f1f77bcf86cd799439011 --password temppass123

# Logout
orbit logout
```

## Monitoring and Maintenance

### Session Monitoring

The queries below are MongoDB shell syntax. On SQLite/PostgreSQL the same
data lives in the `sessions` and `users` tables — see
[`docs/sqlite-schema.md`](sqlite-schema.md) — so translate to
`SELECT count(*) FROM sessions WHERE expires > CURRENT_TIMESTAMP`, and so on.

Monitor active sessions:

```javascript
// Count active sessions
db.sessions.countDocuments({expires: {$gt: new Date()}})

// List active sessions
db.sessions.find({expires: {$gt: new Date()}}).pretty()

// Clean up expired sessions (automatic via TTL)
db.sessions.deleteMany({expires: {$lt: new Date()}})
```

### User Management

```javascript
// List all users
db.users.find({}, {password: 0}).pretty()

// Find inactive users
db.users.find({active: false})

// Count users by primary role
db.users.aggregate([
  {$group: {_id: "$role", count: {$sum: 1}}}
])

// Count users by each assigned role (a user with multiple roles counts once per role)
db.users.aggregate([
  {$unwind: "$roles"},
  {$group: {_id: "$roles", count: {$sum: 1}}}
])
```

### Security Audit

```bash
# Check for default passwords
orbit user list | grep -i admin

# Monitor failed login attempts in logs
grep "Invalid password" logs/orbit.log

# Check session duration configuration
grep -r "session_duration_hours" config/
```

## Development Notes

### Adding New Authentication Features

1. **Service Layer**: Add method to `AuthService`
2. **API Layer**: Add endpoint to `auth_routes.py` 
3. **CLI Layer**: Add command to `orbit.py`
4. **Documentation**: Update this document
5. **Testing**: Add integration tests

### Testing Authentication

```bash
# Run authentication tests
cd server/tests
python -m pytest test_auth_*.py -v

# Manual API testing
curl -X POST http://localhost:3000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

### Database Migration

When modifying user/session schema:

1. **Backup**: Export existing users/sessions
2. **Update**: Modify service layer schema
3. **Migrate**: Convert existing data
4. **Test**: Verify authentication still works
5. **Deploy**: Update production systems
