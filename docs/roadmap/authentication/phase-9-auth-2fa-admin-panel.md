# Two-Factor Authentication — Admin Panel Integration — Implementation Plan

## Summary

[Phase 7](complete/phase-7-auth-2fa.md) shipped native TOTP-based 2FA entirely
as a backend/API surface (`/auth/mfa/*`, `/auth/login/2fa`,
`DELETE /auth/users/{user_id}/mfa`). There is no way to enroll, view status,
disable, or administer another user's 2FA from the admin panel today — the
only UI that exists is a bare, unstyled inline HTML form
(`_render_admin_2fa_html` in `server/routes/admin_panel_routes.py:305-328`)
that appears in place of a redirect when a dashboard-cookie login hits
`mfa_required: true`. Operators otherwise have to drive the whole feature
with `curl` (see [`playbook-mfa-totp.md`](../../../server/tests/test_auth/playbook-mfa-totp.md)).

This phase adds the missing frontend: self-service enrollment/disable in the
Users tab's "My Account" panel, an admin-facing "Reset 2FA" action on the
user detail view, and a properly styled second-factor step in the
server-rendered dashboard login page. No backend routes, schema, or config
change — this is UI work wired to endpoints that already exist and are
already tested.

**Roadmap position:** Phase 9. Hard dependency on [Phase 7](complete/phase-7-auth-2fa.md)
(the backend this phase has no reason to exist without). No dependency on
Phase 8 (API key expiration, unimplemented and unrelated).

## Current state

- **Admin panel is not a framework SPA.** `server/admin/admin_panel/` is
  hand-written vanilla ES modules (no React/Vue/build step): `core/` holds
  `api.js` (fetch wrapper + `ENDPOINTS` map), `dom.js` (an `el()` helper
  standing in for JSX), `charts.js`, `metrics.js`; `tabs/` holds one module
  per nav tab, instantiated by `server/admin/admin_panel.js` (the shell:
  nav rail, toasts, confirm-dialog system, pagination, column sorting).
- **The Users tab already has the pattern to copy.** `tabs/users.js`
  (1339 lines) renders, in order: `listPanel`, `detailPanel`, `createPanel`,
  `allowlistPanel`, `blacklistPanel`, `accountPanel` ("My Account", last).
  Two existing precedents this phase reuses directly:
  - `RULE_PANELS` (users.js:404) + `renderIdentityRulesPanel(panel, spec)`
    (users.js:521) — one spec-driven function rendering both the Blocked
    and Allowed Identities panels from a shared builder. This is the idiom
    for a collapsible enrollment form with its own copy/validation/errors.
  - `renderSessionsSection(user, isCurrentUser)` (users.js:1257-1336) —
    appended to every user's detail panel (users.js:1249), branches its
    endpoint by `isCurrentUser` vs. an admin viewing someone else, and
    drives a per-row action button through `confirmAction`. This is the
    exact shape a "Two-Factor Authentication" detail subsection needs:
    self-view shows enroll/status/disable, admin-view of another user shows
    status + a "Reset 2FA" button hitting `DELETE /auth/users/{user_id}/mfa`.
  - `renderAccountSecurityPanel` (users.js:787-825) is the "My Account"
    panel itself — currently username, roles, and (for non-SSO users) a
    collapsible change-password form via `renderChangeMyPassword`
    (users.js:827-907). 2FA enrollment is self-service and belongs here,
    gated the same way password change already is: `isSsoUser` (users.js:790)
    — 2FA applies only to local password accounts, same restriction Phase 7
    enforces server-side.
  - Shared primitives already available and sufficient, no new dependency:
    `field()`/`passwordField()` form helpers (admin_panel.js:105, :162),
    `confirmAction({title, message, isDanger, onConfirm})` (admin_panel.js:774),
    `showStatus`/`showError` toasts (admin_panel.js:628-635),
    `wrapTable()` (dom.js:55). Rendering the QR is trivial:
    `el("img", { src: enrollResponse.qr_code_data_uri, alt: "..." })` — the
    backend already returns a same-origin `data:image/png;base64,...` URI,
    no library needed.
- **The admin-panel SPA does not perform its own login.** `admin_panel.js`'s
  `init()` (admin_panel.js:869-894) exchanges the `dashboard_token` cookie
  for a bearer token via `GET /admin/api/token`; on 401 it hard-redirects to
  the **server-rendered** `server/admin/admin_login.html`, POSTing to
  `/admin/login` (`admin_panel_routes.py:213-304`). The two-step 2FA
  challenge therefore lives outside `admin_panel/` entirely, in
  `admin_panel_routes.py` and its companion template/render helpers
  (`render_login_html` in `routes/auth_helpers.py`, `admin_login.html`) —
  a separate, smaller workstream from the Users-tab work above.
- **`GET /auth/mfa/status` and `POST /auth/mfa/enroll|confirm|disable`
  already exist and are tested** (`server/tests/test_auth/test_mfa.py`, 13
  tests). This phase adds no new backend behavior; `ENDPOINTS` in
  `core/api.js` just needs entries for them plus `login2fa`.

## Scope

### 1. Self-service enrollment/disable — "My Account" panel

In `renderAccountSecurityPanel` (users.js:787-825), add a "Two-Factor
Authentication" section below the password form, gated by the same
`isSsoUser` check:

- On mount, call `GET /auth/mfa/status`. Render either:
  - **Not enrolled**: a "Set up two-factor authentication" collapsible
    button (same toggle idiom as the change-password form), which on open
    calls `POST /auth/mfa/enroll`, renders the returned `qr_code_data_uri`
    as an `<img>`, shows `secret` as selectable/copyable text for manual
    entry, and a code-input field + "Confirm" button calling
    `POST /auth/mfa/confirm`. On success, render the ten recovery codes in
    a way that is easy to copy/print (e.g. a `<pre>` block) with an
    explicit "these are shown only once" warning, and a "Done" button that
    collapses the form and refreshes status.
  - **Enrolled**: a status line ("Two-factor authentication is enabled")
    and a "Disable" button. Disabling requires the current password
    (matches `POST /auth/mfa/disable`'s contract) — reuse `passwordField()`
    inside a `confirmAction` dialog rather than a bare `prompt()`, consistent
    with how other destructive actions confirm.
  - **Enrolled, but the account's role requires 2FA** (i.e. the backend
    will reject the disable, `auth_routes.py`'s `role_requires_2fa` guard):
    hide or disable the "Disable" button client-side with an explanatory
    tooltip/hint, rather than only surfacing the server's 400 after the
    fact. Requires knowing `auth.two_factor.required_for_roles` and the
    current user's roles — expose the former via the existing effective-config
    surface the panel already reads roles from (`currentUser.roles`), or a
    small new read-only field on `GET /auth/mfa/status`
    (e.g. `required_for_role: bool`) if not already inferable client-side.
    Decide which during implementation; either is a small, additive change.
- Recovery codes and the raw secret must never be logged to the browser
  console or persisted in `localStorage` — hold them only in component state
  for the duration of the confirmation flow.

### 2. Admin-facing "Reset 2FA" — user detail view

Alongside `renderSessionsSection` (appended at users.js:1249), add a
`renderMfaSection(user, isCurrentUser)` following its exact branching
pattern:

- Fetch status: `GET /auth/mfa/status` for the current user's own row (self),
  or a per-user status the admin view needs — check whether `GET /auth/mfa/status`
  should be extended to accept a target user (admin, `users.manage`) or
  whether the existing user list/detail payload should carry an
  `mfa_enabled` field instead (avoids an extra round-trip per row viewed).
  Prefer extending the user detail payload if `list_users`/`get_user_by_id`
  can cheaply join `user_mfa.enabled` — smaller surface than a new
  admin-scoped status endpoint.
- Render "Two-factor authentication: enabled/not enrolled" for the viewed
  user.
- When viewing **another** user (not `isCurrentUser`) with 2FA enabled and
  the caller holds `users.manage`, show a "Reset 2FA" danger button through
  `confirmAction` (mirroring the Delete User button at users.js:1223-1236 and
  Revoke Session at users.js:1277-1293) calling
  `DELETE /auth/users/{user_id}/mfa`. Confirm-dialog copy should say plainly
  that this disables 2FA immediately and the user must re-enroll — matching
  the backend's framing of this as a sensitive recovery override
  (`auth.mfa.admin_reset` audit event).
- Gate the button's visibility on `userHasPermission(currentUser, "users.manage")`
  (admin_panel.js:1010-1013), consistent with every other admin-only action
  in this tab.

### 3. Two-step dashboard login — `admin_panel_routes.py` / `admin_login.html`

Replace `_render_admin_2fa_html`'s bare inline form (admin_panel_routes.py:305-328)
with a real templated page:

- Add a second template alongside `admin_login.html` (or a second named
  block within it, following whatever `render_login_html`'s
  `{{NEXT_PATH}}`/`{{ERROR_BLOCK}}`/`{{SSO_BLOCK}}` placeholder convention
  in `routes/auth_helpers.py` already establishes) reusing the same
  `:root` CSS variables, `.login-shell`, and `password-field`/`password-toggle`
  markup so the 2FA step is visually indistinguishable in polish from the
  password step.
- Fields: a code input (autofocus, numeric-friendly, accepts either a
  6-digit TOTP or a recovery code — same as the API), a "Remember this
  device" checkbox, hidden `pending_token`/`next` fields exactly as today.
- Preserve existing behavior: wrong code re-renders the same page with an
  inline error and the pending token intact (`admin_panel_routes.py:368-379`);
  successful verification sets `dashboard_token` (and `device_token` when
  "remember" was checked) and redirects to `next`
  (`admin_panel_routes.py:381-397`).
- Preserve the existing XSS-escaping fix for `next_path`/`pending_token`
  (`html.escape(..., quote=True)`, added after the phase-7 security review) —
  do not regress this when restyling.
- No JS framework needed here either; this is a server-rendered form like
  `admin_login.html`, not part of the `admin_panel/` SPA bundle.

### 4. `ENDPOINTS` and API wiring

Add to `core/api.js`'s `ENDPOINTS` map: `mfaStatus: "/auth/mfa/status"`,
`mfaEnroll: "/auth/mfa/enroll"`, `mfaConfirm: "/auth/mfa/confirm"`,
`mfaDisable: "/auth/mfa/disable"`, and a per-user variant for the admin
reset (`(userId) => `/auth/users/${userId}/mfa``, matching the existing
`endpoints.users + "/" + id + "/sessions"` string-building idiom at
users.js:1259-1261 rather than introducing a templating helper).

## Out of scope

- Any backend route, schema, or config change (Phase 7 is complete and
  unmodified by this phase).
- A first-class "recovery codes regenerate" endpoint — Phase 7 only issues
  codes once at confirmation; regenerating requires disable + re-enroll.
  Surfacing that combined flow more conveniently in the UI ("Regenerate
  recovery codes") is a candidate follow-up, not required here.
- Enforcing/relaxing `required_for_roles` from the UI (remains
  `config.yaml`-only, matching how `auth.admin_ip_allowlist` and other
  `auth.*` policy blocks are configured today — no admin-panel settings-tab
  editor exists for any of them).
- Admin bulk operations (e.g. "reset 2FA for all users in a role").

## Testing and acceptance criteria

Since this phase touches only presentation and API wiring around an
already-tested backend, coverage is primarily manual/browser-driven plus a
light route-level check for the two changed server-rendered paths:

- Manual verification following an updated
  [`playbook-mfa-totp.md`](../../../server/tests/test_auth/playbook-mfa-totp.md)
  §10 (the dashboard flow section), extended to cover the panel additions:
  enroll end-to-end from the Users tab (QR scan with a real authenticator
  app), confirm, view enabled status, disable (with and without a
  `required_for_roles` role), and an admin resetting another user's 2FA
  from the detail view.
- `server/tests/test_auth/test_admin_panel_2fa_routes.py` (new): route-level
  tests for the restyled `/admin/login/2fa` page — confirm it still returns
  the pending token/next path escaped (regression guard for the XSS fix),
  still sets `dashboard_token`/`device_token` cookies identically to today,
  and still enforces the same rate-limit/audit behavior Phase 7 already
  covers at the service layer.
- No changes required to `server/tests/test_auth/test_mfa.py` — the backend
  contract is unchanged.
- `ruff check server/` for any touched Python (the route/template file);
  the vanilla-JS `admin_panel/` files have no linter configured in this
  repo today, so review is manual (matches how `users.js` itself ships).

## Assumptions and defaults

- The admin panel's "no framework, no build step" architecture is
  deliberate and out of scope to change — this phase writes plain ES
  modules matching the existing style, not a migration to a framework.
- Recovery codes are shown once, client-side only, never persisted browser-side.
- The two workstreams (Users-tab panels vs. the server-rendered login page)
  are independent and can ship separately; neither blocks the other.

## Related documentation

- [Phase 7 — Two-Factor Authentication implementation plan](complete/phase-7-auth-2fa.md)
- [Authentication guide — Two-Factor Authentication section](../../authentication.md)
- [Manual/Integration playbook — 2FA](../../../server/tests/test_auth/playbook-mfa-totp.md)
- [Session Monitoring — the closest prior admin-panel precedent](complete/phase-5-auth-session-monitoring.md)
