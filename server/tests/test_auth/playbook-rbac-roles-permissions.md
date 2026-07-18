# Manual/Integration Check: Permission-Based RBAC (Roles & Permissions)

End-to-end verification of ORBIT's permission-based RBAC: the role/permission
registry (`server/auth/rbac.py`), the three enforcement paths (bearer token,
`X-API-Key`, admin-panel cookie/WebSocket), the CLI, and the admin panel UI's
role picker.

The automated tests already cover this in isolation with mocked
dependencies — `test_rbac.py` (registry math), `test_admin_permission_guards.py`
(dependency-layer 401/403 behavior), `test_auth_service.py` (role assignment +
legacy backfill), `test_admin_audit.py`, `test_admin_panel_feedback_analytics.py`.
This playbook exercises the same matrix **against a real running server**,
real sessions, and the real browser UI — the things a mocked dependency
override can't catch (cookie flow, WebSocket auth, the admin panel's role
picker interaction, an actual pre-existing SQLite/Mongo row getting
backfilled on startup).

Prerequisites: ORBIT running at `http://localhost:3000` with the default
admin account still intact, and `orbit` CLI configured against that server.

---

## 0. Reference: role → permission map

Keep this open while testing — every expectation below derives from it
(`server/auth/rbac.py`):

| Role | Permissions |
|---|---|
| `admin` | `*` (every permission) |
| `operator` | `config.manage`, `adapters.manage`, `apikeys.manage`, `prompts.manage`, `system.manage`, `metrics.read` |
| `auditor` | `logs.read`, `audit.read`, `metrics.read` |
| `analyst` | `conversations.read`, `feedback.read` |
| `user-manager` | `users.manage` |
| `user` | *(none)* |

Permission → route(s):

| Permission | Routes |
|---|---|
| `users.manage` | `/auth/register`, `/auth/users*`, `/auth/roles`, `/auth/users/{id}/roles`, delete/deactivate/activate/reset-password |
| `apikeys.manage` | `/admin/api-keys*`, quota routes |
| `adapters.manage` | `/admin/adapters/*`, reload-adapters, reload-templates, test-query |
| `prompts.manage` | `/admin/prompts*`, render-markdown |
| `config.manage` | `/admin/config*` |
| `system.manage` | `/admin/info`, `/admin/jobs`, shutdown, restart |
| `logs.read` | `/admin/logs/*` |
| `audit.read` | `/admin/audit/events` |
| `metrics.read` | metrics WebSocket |
| `conversations.read` | `/admin/chat-history/{id}`, feedback-analytics conversation excerpts |
| `feedback.read` | `/admin/api/feedback-analytics` aggregates |

**One asymmetry to know before you start**, so you don't mistake it for a bug:
- Routes gated by `require_permission(...)` (bearer-only: `conversations.read`,
  and all of `/auth/*`) return **403** for an authenticated user who lacks the
  permission, **401** if unauthenticated.
- Routes gated by `permission_or_api_key(...)` (everything else under
  `/admin/*`) return **401**, not 403, for an authenticated-but-lacking-permission
  user — the dependency has no separate "authenticated but forbidden" branch,
  it just falls through to the API-key check and then fails closed. Both are
  "you may not do this," just a different status code depending on which
  dependency guards the route.

---

## 1. Seed one test user per role

As the default admin:

```bash
orbit login --username admin

orbit register --username rb-operator     --password TestPass123! --roles operator
orbit register --username rb-auditor      --password TestPass123! --roles auditor
orbit register --username rb-analyst      --password TestPass123! --roles analyst
orbit register --username rb-user-manager --password TestPass123! --roles user-manager
orbit register --username rb-user         --password TestPass123! --roles user
orbit register --username rb-multi        --password TestPass123! --roles operator,analyst
```

Confirm the roster:

```bash
orbit user list
```

Expect each `rb-*` account listed with exactly the roles you assigned
(`rb-multi` shows both `operator` and `analyst`).

Get a bearer token per role (repeat for each username):

```bash
curl -s -X POST http://localhost:3000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"rb-operator","password":"TestPass123!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])"
```

Export as `$TOKEN_ADMIN`, `$TOKEN_OPERATOR`, `$TOKEN_AUDITOR`, `$TOKEN_ANALYST`,
`$TOKEN_USER_MANAGER`, `$TOKEN_USER`, `$TOKEN_MULTI` for the curl commands below.

---

## 2. Backend permission matrix (curl)

For each row, run the request as every role and confirm the **Result**
column. `200/OK` here means "passed the auth dependency" — a downstream 404
or 503 (missing service/session) is fine, the point is it isn't 401/403.

### `GET /admin/chat-history/session-1` — `conversations.read`, bearer-only

```bash
for T in ADMIN OPERATOR AUDITOR ANALYST USER_MANAGER USER; do
  ROLE=$T; TOKEN_VAR="TOKEN_$T"
  echo -n "$ROLE: "
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "Authorization: Bearer ${!TOKEN_VAR}" \
    http://localhost:3000/admin/chat-history/session-1
done
```

Expect: `admin` → 200-class (not 401/403), `analyst` → 200-class, everyone
else (`operator`, `auditor`, `user-manager`, `user`) → **403**. No token at
all → **401**.

### `GET /admin/api/feedback-analytics` — `feedback.read`, plus `conversations.read` for the conversation excerpts

```bash
curl -s -H "Authorization: Bearer $TOKEN_ANALYST" \
  http://localhost:3000/admin/api/feedback-analytics | python3 -m json.tool
```

As `analyst` (has both permissions): confirm `recent_negative[].user_prompt`,
`.assistant_response`, and `.session_id` are populated with real content.

As `operator` (has neither `feedback.read` nor `conversations.read` per the
table above — confirm this via the cookie/panel route in §3, since this
specific endpoint is cookie-gated, not bearer): via the admin panel, confirm
the Feedback tab isn't visible at all for `operator` (no `feedback.read`).

### `GET /admin/config/sections` — `config.manage`

```bash
for T in ADMIN OPERATOR ANALYST; do
  TOKEN_VAR="TOKEN_$T"
  echo -n "$T: "
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "Authorization: Bearer ${!TOKEN_VAR}" \
    http://localhost:3000/admin/config/sections
done
```

Expect: `admin` and `operator` → 200-class. `analyst` → **401** (see the
asymmetry note in §0 — not 403).

### `GET /admin/api-keys` — `apikeys.manage`

Same pattern: `admin`/`operator` → 200-class, everyone else → 401.

### `GET /admin/logs/tail` and `GET /admin/audit/events` — `logs.read` / `audit.read`

`admin`/`auditor` → 200-class. `operator`/`analyst`/`user`/`user-manager` →
401. **`operator` is deliberately excluded here** — it runs day-to-day
operations (config, adapters, restart/shutdown) but has no visibility into
logs or the audit trail; that's scoped to `auditor` alone. This is the
opposite pairing from the chat-history check above, so it's worth confirming
both directions: `operator` can reach `/admin/config/sections` but not
`/admin/logs/tail`, while `auditor` is the reverse.

### `GET /auth/users` — `users.manage`

```bash
for T in ADMIN USER_MANAGER OPERATOR; do
  TOKEN_VAR="TOKEN_$T"
  echo -n "$T: "
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "Authorization: Bearer ${!TOKEN_VAR}" \
    http://localhost:3000/auth/users
done
```

Expect: `admin`/`user-manager` → 200. `operator` → **403** (this route uses
`require_permission`, not `permission_or_api_key` — confirms the asymmetry
from §0 in the other direction).

### `POST /admin/adapters/{name}/test-query` — bearer-only `adapters.manage`

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  -H "Authorization: Bearer $TOKEN_OPERATOR" -H "X-API-Key: some-valid-key" \
  -H "Content-Type: application/json" -d '{"query":"test"}' \
  http://localhost:3000/admin/adapters/some-adapter/test-query
```

Confirm `operator` passes (has `adapters.manage`). Then repeat with
`$TOKEN_ANALYST` — confirm **403**, and confirm an `X-API-Key` alone (no
bearer) is **not** sufficient here either (this route is `require_permission`,
bearer-only, unlike most other adapter routes).

### System routes — do **not** actually trigger these

`/admin/restart` and `/admin/shutdown` require `system.manage`. To check
authorization without actually restarting/killing your server, confirm the
dependency layer rejects wrong roles on a **safe** `system.manage` route
first (`GET /admin/info`), then trust the shared `system_auth` dependency
instance is applied identically to restart/shutdown (see
`server/routes/admin_routes.py` — all four routes use the same `system_auth`
object). If you do want to exercise restart for real, do it last, expect the
process to bounce, and re-authenticate afterward.

---

## 3. Admin panel UI walkthrough

Log into `/admin/login` as each `rb-*` user (password auth) and confirm tab
visibility matches its permissions — the `TABS` array in `admin_panel.js`
gates each tab by a required permission:

| Tab | Required permission | `rb-operator` | `rb-auditor` | `rb-analyst` | `rb-user-manager` | `rb-user` |
|---|---|:---:|:---:|:---:|:---:|:---:|
| Overview | *(none)* | ✅ | ✅ | ✅ | ✅ | — |
| Feedback | `feedback.read` | ❌ | ❌ | ✅ | ❌ | — |
| Users | `users.manage` | ❌ | ❌ | ❌ | ✅ | — |
| API Keys | `apikeys.manage` | ✅ | ❌ | ❌ | ❌ | — |
| Personas | `prompts.manage` | ✅ | ❌ | ❌ | ❌ | — |
| Adapters | `adapters.manage` | ✅ | ❌ | ❌ | ❌ | — |
| Ops | `system.manage` | ✅ | ❌ | ❌ | ❌ | — |
| Audit | `audit.read` | ❌ | ✅ | ❌ | ❌ | — |
| Settings | `config.manage` | ✅ | ❌ | ❌ | ❌ | — |

`rb-user` has zero permissions: confirm the password login form itself
rejects them with the generic "Invalid admin username or password" message
(not a permission-specific error — `has_any_permission` gates panel entry
before any tab logic runs) and they never reach `/admin`.

**Ops tab sub-gating**: `rb-operator` sees the Ops tab (has `system.manage`)
with working Restart/Shutdown buttons, but confirm the server-log viewer
section is replaced with a "Server log viewing requires the logs.read
permission" message instead of a broken/401ing panel — `operator` has
`system.manage` but not `logs.read` (that's `auditor`'s job). Note that
`rb-auditor` can't open the Ops tab at all (no `system.manage`), so today
`admin` is the only role that sees the log viewer in the panel; `auditor`
must hit `GET /admin/logs/tail` directly (bearer token or API key) instead.
A role holding both `system.manage` and `logs.read` (e.g. `rb-multi` if you
add `auditor` to it) would see the viewer too.

For `rb-multi` (`operator` + `analyst`): confirm the *union* — Feedback tab
visible **and** API Keys/Adapters/Ops/Settings visible, in the same session.

### Role picker (Users tab, `user-manager` or `admin` session)

Open **Create User** and confirm the redesigned picker:

1. **Admin exclusivity** — check `admin`. Confirm every other checkbox
   instantly unchecks and visually disables (dimmed, `not-allowed` cursor).
   Uncheck `admin` — confirm the rest re-enable and are selectable again.
2. **Descriptions** — confirm each role shows an inline one-line summary
   matching §0's table (e.g. `operator` → "Runs system configuration,
   adapters, and server control; no chat, log, or audit access.").
3. **Visual grouping** — confirm `admin` sits above a "Scoped access" divider,
   visually distinct from the rest, and the scoped roles render as an
   alphabetized card grid (`analyst`, `auditor`, `operator`, `user`,
   `user-manager`).
4. **Reset after creating an admin** — check only `admin`, create the user,
   and confirm the form resets to just `user` checked **with every other
   checkbox re-enabled** (not stuck disabled from the prior admin-selection
   state). This is the specific regression the reset fix targeted.
5. Create a multi-role user (e.g. `operator` + `auditor`) via the picker and
   confirm `orbit user list` shows both roles for that account.

### WebSocket metrics — `metrics.read`

Open the Overview tab (which opens the metrics WebSocket) as `rb-operator`
or `rb-auditor` (both have `metrics.read`) — confirm live metrics stream in.
As `rb-analyst` or `rb-user-manager` (neither has `metrics.read`), confirm
the WebSocket connection is refused (check the browser Network tab for a
4401/4403 close code) rather than silently hanging.

---

## 4. CLI walkthrough

```bash
# List all registered role names
orbit user roles
# admin, analyst, auditor, operator, user, user-manager

# Reassign an existing user's roles
orbit user set-roles --username rb-user --roles analyst
orbit user list   # rb-user now shows role "analyst", not "user"

# Multi-role assignment at creation
orbit register --username rb-cli-multi --password TestPass123! --roles operator,auditor
orbit user list   # rb-cli-multi shows both roles

# Invalid role name is rejected client- and server-side
orbit user set-roles --username rb-user --roles not-a-real-role
# Expect a clear error, not a silent success
```

---

## Additional Scenarios

### A. API key reaches automation routes but never conversations

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "X-API-Key: <a valid programmatic key>" \
  http://localhost:3000/admin/config/sections
# Expect 200-class

curl -s -o /dev/null -w "%{http_code}\n" \
  -H "X-API-Key: <the same valid key>" \
  http://localhost:3000/admin/chat-history/session-1
# Expect 401 — conversations.read is bearer-only by design
```

### B. Legacy single-role row gets backfilled on startup

Insert a pre-migration-shaped row directly (SQLite default backend):

```bash
sqlite3 orbit.db "INSERT INTO users (id, username, password, role, active, created_at) \
  VALUES ('legacy-test-id', 'rb-legacy', '<any hash>', 'admin', 1, datetime('now'));"
sqlite3 orbit.db "SELECT username, role, roles FROM users WHERE username='rb-legacy';"
# roles column is NULL/empty at this point
```

Restart ORBIT (`AuthService._backfill_roles()` runs once on every
`initialize()`), then re-check:

```bash
sqlite3 orbit.db "SELECT username, role, roles FROM users WHERE username='rb-legacy';"
# roles is now '["admin"]'
```

Confirm the user still authenticates and has full admin access — the
backfill didn't change behavior, just materialized `roles`. Clean up:
`orbit user delete --username rb-legacy` (or via SQL if that user can't log
in to self-service).

### C. Invalid role rejected at every entry point

```bash
curl -s -X POST http://localhost:3000/auth/register \
  -H "Authorization: Bearer $TOKEN_ADMIN" -H "Content-Type: application/json" \
  -d '{"username":"rb-bad","password":"TestPass123!","roles":["superadmin"]}'
```

Expect **400** naming the invalid role and listing valid ones (`is_valid_role`
in `server/auth/rbac.py`). Repeat against `PUT /auth/users/{id}/roles` —
same 400.

### D. `require_admin` / wildcard checks still recognize `admin`

This guards against the wildcard-preservation regression fixed earlier
(`permissions_for_roles` must retain the literal `"*"` marker, not just
expand it). Confirm `admin` still reaches `POST /admin/adapters/{name}/test-query`
(gated by `require_permission("adapters.manage")`, which for `admin` resolves
through the wildcard) and, if admin SSO is configured, that an allowlisted
SSO login still promotes to full admin (see
`test_auth/playbook-external-auth.md` scenario H/I for the SSO half of this).

### E. SSO JIT-provisioned users get exactly one role

External auth's `default_role` config is a single string, not a list —
confirm a freshly JIT-provisioned SSO user (see the external-auth playbook)
shows `roles: ["<default_role>"]`, e.g. `["user"]`, not multiple roles. Multi-
role assignment for SSO users is only available after the fact, via
`orbit user set-roles` — group/claim-based multi-role mapping is a documented
future item in `docs/rbac-architecture.md` §7A, not yet implemented.

### F. Cookie-based panel entry vs. bearer 403 asymmetry

Log into the admin panel as `rb-operator` (password form, gets a
`dashboard_token` cookie) and separately curl `/admin/config/sections` with
that same account's **bearer** token. Confirm both succeed (operator has
`config.manage`) — the point of this scenario is confirming the two auth
paths (`get_admin_user` cookie vs. bearer `permission_or_api_key`) agree on
the same permission set for the same user, since they're two independent
code paths reading the same `_user_info` projection.

---

## 5. Run the automated checks

```bash
venv/bin/python -m pytest server/tests/test_auth/test_rbac.py \
  server/tests/test_auth/test_auth_service.py \
  server/tests/test_routes/test_admin_permission_guards.py \
  server/tests/test_services/test_admin_audit.py \
  server/tests/test_routes/test_admin_panel_feedback_analytics.py -v
```

All should pass. These cover the same matrix with mocked dependencies —
this playbook is the live-server complement, not a replacement.

---

## Troubleshooting

- **Got 401 where you expected 403 (or vice versa):** check which dependency
  guards the route — `permission_or_api_key` (most of `/admin/*`) returns 401
  for "authenticated but lacking permission"; `require_permission` (`/auth/*`
  and `conversations.read`) returns 403 for the same case. See §0.
- **A role you just assigned doesn't seem to apply:** the user must
  re-authenticate (new login/token) to pick up a role change — `permissions`
  is computed once per token validation from the current DB row, but an
  already-open browser session's in-memory `currentUser` in the admin panel
  won't refresh until next `/admin/api/token` call (reload the page).
  Or double check that `roles` on the user document actually got the value
  you expect — Roles column TEXT on SQLite is JSON-encoded, so a comparison
  against a raw string would be misleading. Look for the actual key.
- **Role picker doesn't disable scoped options after checking `admin`:**
  confirm `admin_panel.js`'s `syncAdminRoleState` is wired to every
  checkbox's `change` event (`createRoleOption`) and re-run after a hard
  refresh in case of a stale cached bundle.
- **A legacy user's `roles` column stayed empty after restart:** confirm
  `AuthService.initialize()` actually ran `_backfill_roles()` (check startup
  logs) and that the row's `role` field was non-null to backfill from.
- **SSO user has more roles than expected:** `default_role` only ever
  produces one role at creation; any additional roles came from a later
  `set_roles`/`orbit user set-roles` call, not from the SSO flow itself.
