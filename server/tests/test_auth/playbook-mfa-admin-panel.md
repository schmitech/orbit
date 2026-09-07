# Manual Check: Two-Factor Authentication — Admin Panel UI

End-to-end verification of the **admin-panel frontend** for native TOTP 2FA
(`docs/roadmap/authentication/auth-2fa-admin-panel.md`): self-service
enrollment/disable in "My Account," the admin-facing "Reset 2FA" action on
another user's detail view, and the restyled two-step dashboard login page.

This phase added **no new backend behavior** beyond what
[`playbook-mfa-totp.md`](playbook-mfa-totp.md) already exercises via the raw
API (`/auth/mfa/*`), plus two small additive pieces called out below (§0).
This playbook is UI-only: every button, dialog, and page state the panel adds
on top of that already-tested backend. Do the API playbook first if you
haven't — it's faster to reason about failures here once you know the
underlying contract works.

Prerequisites:
- ORBIT running at `http://localhost:3000` with `auth.two_factor.enabled: true`
  and `ORBIT_MFA_ENCRYPTION_KEY` set (see §1 of `playbook-mfa-totp.md`).
- Two admin-panel accounts: your own (`users.manage`, e.g. `admin`) and a
  second local password account to reset 2FA on (e.g. `admin2` — create it
  via the Users tab's "Create User" panel if it doesn't exist yet).
- A phone with an authenticator app, and a browser.

---

## 0. Reference: what this phase changed vs. what it didn't

| Surface | Endpoint(s) | New here? |
|---|---|---|
| My Account — enroll/disable | `GET/POST /auth/mfa/*` | UI only; endpoints existed |
| User detail — Reset 2FA | `DELETE /auth/users/{id}/mfa` | UI only; endpoint existed |
| Dashboard login 2FA page | `POST /admin/login/2fa` | Restyled only; route existed |
| `GET /auth/mfa/status` response | — | **Added** `required_for_role` and `globally_enabled`; **added** optional `?user_id=` for an admin viewing another user (permission-checked) |
| `POST /auth/mfa/enroll` | — | **Added** a 400 guard when `auth.two_factor.enabled` is `false` globally |

Everything else (rate limiting, recovery codes, `required_for_roles` login
blocking, the encryption-key failure mode) is unchanged — see the API
playbook for those.

---

## 1. Self-service enrollment — "My Account"

Log into the admin panel as your own account, open the **Users** tab, scroll
to **My Account** at the bottom.

1. Confirm a **"Two-Factor Authentication"** section appears below the
   password form, currently reading *"Two-factor authentication is not
   enabled."* with a **"Set Up Two-Factor Authentication"** button.
2. Click it. Confirm it expands inline (not a new page) showing:
   - A QR code image.
   - The raw secret as selectable text next to a **Copy** button — click
     Copy and confirm a "Secret copied" toast, then paste somewhere to
     verify the clipboard actually holds the secret.
   - A verification code input and **Confirm** button.
3. Scan the QR with your authenticator app (or add the secret manually).
   Enter the current 6-digit code and click **Confirm**.
4. Confirm ten recovery codes render in a monospace block with an explicit
   "shown only once" warning, and a **Done** button.
5. **Before clicking Done**, refresh the page and reopen My Account — confirm
   the codes are *not* recoverable (they were never persisted client-side,
   per the design constraint) and the section already shows the enrolled
   state (a real reload also proves they were saved server-side, not just
   held in memory).
6. Click **Done** (or, after the refresh, just observe the enrolled state
   directly). Confirm the section now reads *"Two-factor authentication is
   enabled."* with a **Disable** button in place of the setup button.

**Confirm nothing sensitive was logged**: open the browser console before
repeating enrollment on a throwaway account, and confirm neither the secret
nor the recovery codes appear in any `console.log` output.

---

## 2. Self-service disable — password-gated

Still in My Account, with 2FA enabled from §1:

1. Click **Disable**. Confirm a dialog opens asking for your **current
   password** (not a bare browser `prompt()` — it should be the same
   styled confirm-dialog used elsewhere in the panel, with a password field
   inside it).
2. Submit with a **wrong** password. Confirm the dialog shows an inline
   error and stays open (does not silently close or disable 2FA).
3. Submit with the correct password. Confirm a "Two-factor authentication
   disabled" toast, and the section reverts to the not-enrolled state.
4. Re-enroll (repeat §1) so the following sections have an enrolled account
   to work with.

---

## 3. Global-disable guard (P1 regression check)

This is the highest-severity fix from review: the UI must never claim an
account is protected when the feature is off server-wide and login will
never enforce it.

1. Set `auth.two_factor.enabled: false` in `config/config.yaml` and restart
   the server (leaving your account's `user_mfa` row/enrollment state from
   §1 untouched — you're testing the flag, not re-enrolling).
2. Reload the admin panel, open My Account. Confirm the section reads that
   two-factor authentication is **disabled for this ORBIT deployment** and
   that an administrator must enable it in server configuration — and that
   this message appears **regardless of whether your account was
   previously enrolled**:
   - If your test account was **not** enrolled: confirm the "Set Up
     Two-Factor Authentication" button is **hidden entirely** (not just
     disabled) — there is nothing to gate a login flow that never checks it.
   - If your test account **was** enrolled (from §1): confirm the section
     still says "Two-factor authentication is enabled" **but** appends a
     visible note that it "is currently disabled for this ORBIT deployment,
     so this enrollment is not being enforced at login" — this is the false-
     assurance fix; the UI must not let an enrolled-but-unenforced account
     look identical to a genuinely protected one.
3. Confirm the API agrees: `GET /auth/mfa/status` (bearer token) now returns
   `"globally_enabled": false` alongside `enabled`.
4. Attempt enrollment directly against the API while disabled:
   ```bash
   curl -s -w '\nHTTP %{http_code}\n' -X POST http://localhost:3000/auth/mfa/enroll \
     -H "Authorization: Bearer $TOKEN"
   ```
   Expect **400**, *"Two-factor authentication is disabled on this server
   and cannot be enrolled."* — the panel hiding the button is UX, not the
   only guard; the server must refuse it too.
5. Set `auth.two_factor.enabled: true` again, restart, and confirm the panel
   returns to its normal enrolled/not-enrolled rendering with no leftover
   "not enforced" note.

---

## 4. Admin-facing "Reset 2FA" — user detail view

As your `admin` (`users.manage`) account, in the Users tab:

1. Select the second account (`admin2`). If it isn't enrolled in 2FA yet,
   log in as `admin2` in a separate browser/incognito window and enroll it
   via My Account (§1) first.
2. Back in `admin`'s view of `admin2`'s detail panel, scroll to the
   **Two-Factor Authentication** subsection (below Active Sessions). Confirm
   it shows *"Status: Enabled"* and a **Reset 2FA** danger button.
3. Click **Reset 2FA**. Confirm the confirm-dialog states plainly that this
   disables 2FA immediately and `admin2` must re-enroll.
4. Confirm. Confirm a "Two-factor authentication reset" toast, the section
   updates to *"Status: Not enrolled,"* and (switching to the `admin2`
   session) `GET /auth/mfa/status` for that account now reports
   `"enabled": false`.
5. **Permission check**: view the same detail panel signed in as an account
   that lacks `users.manage` — since the Users tab itself requires
   `users.manage` to open at all, confirm such an account cannot reach this
   view in the first place (no separate escape hatch exists).
6. **Audit check**: with `internal_services.audit.admin_events.enabled: true`,
   confirm this produced an `auth.mfa.admin_reset` event in the Audit tab.

---

## 5. Required-role reset warning (P2 regression check)

This is the second review fix: resetting a required-role user's 2FA doesn't
just remove a convenience, it can lock the account out of login entirely
(an unenrolled required-role account is blocked at the password step, before
any session is issued — see §8 of the API playbook), so the dialog must not
imply casual re-enrollment is possible.

1. Set `auth.two_factor.required_for_roles: ["admin"]` and restart. Confirm
   `admin2` (role `admin`, enrolled from §4's prerequisite) is the target —
   re-enroll it if you already reset it in §4.
2. As `admin`, open `admin2`'s detail panel → Two-Factor Authentication →
   **Reset 2FA**.
3. Confirm the dialog is now the **typed-confirmation** style (matching
   Delete User), not a plain confirm/cancel — and that its message:
   - States `admin2`'s role **requires** 2FA.
   - Warns the reset will lock the account out of **signing in entirely**
     (not just out of 2FA), because it can't re-enroll without a session.
   - Says an administrator must first change the role or remove it from
     `required_for_roles` before this is safe.
4. Cancel without typing the username. Confirm 2FA remains enabled for
   `admin2` (the dialog must not proceed on a bare "Reset" click the way the
   non-required-role case does).
5. If you want to confirm the lockout itself: type `admin2` to confirm the
   reset, then attempt `POST /auth/login` as `admin2` and expect the **403
   `mfa_enrollment_required`** block described in §8 of the API playbook —
   this proves the dialog's warning was accurate, not just alarmist. Recover
   by setting `required_for_roles` back to `[]` (or reassigning `admin2`'s
   role) and restarting.
6. Reset `required_for_roles` to its original value when done.

---

## 6. The restyled dashboard login 2FA page

1. Log out of the admin panel (or use a private window). Navigate to
   `http://localhost:3000/admin/login`, sign in with an **enrolled**
   account's username/password.
2. Confirm you land on a **styled** second-factor page (matching the main
   login page's dark gradient, card, and input styling — not the old bare
   unstyled HTML form), titled "Two-Factor Authentication," with:
   - A code input, autofocused.
   - A "Remember this device" checkbox.
   - A "Verify" button.
3. Submit a wrong code. Confirm the same styled page re-renders with an
   inline error banner, and that submitting again (without navigating away)
   with the correct code still works — the pending token embedded in the
   hidden field must have survived the failed attempt.
4. Submit the correct code. Confirm redirect into the dashboard with a
   `dashboard_token` cookie set.
5. Repeat with **"Remember this device"** checked and confirm a
   `device_token` cookie is also set; log out and back in with only the
   password to confirm the second factor is skipped this time.

**XSS regression check** (unchanged from the original inline form, must
survive the restyle):
```
http://localhost:3000/admin/login?next=%2F%3F%22%3E%3Cscript%3Ealert(1)%3C%2Fscript%3E
```
Log in with this URL, reach the 2FA page, and confirm no alert fires and no
raw `<script>` tag appears in the page source.

---

## 7. Mobile recovery-code entry (P2 regression check)

Recovery codes are generated with `secrets.token_hex()` and commonly contain
letters `a`–`f`; the combined TOTP-or-recovery-code field must not present a
digits-only keypad that makes those letters impossible to type.

1. On an actual mobile device (or your browser's device-emulation mode with
   touch/virtual keyboard simulation, e.g. Chrome DevTools' device toolbar),
   open `http://localhost:3000/admin/login`, sign in with an enrolled
   account to reach the 2FA page (§6).
2. Tap the code field. Confirm the on-screen keyboard presented is a **full
   text keyboard**, not a numeric-only keypad — you must be able to type
   letters without switching keyboards.
3. Type one of the account's saved recovery codes (hex, e.g. containing
   `a`–`f`) directly and submit. Confirm it's accepted the same as it would
   be via the API (§5 of the API playbook), and that the same code is
   rejected on a second attempt (single-use, unchanged behavior).
4. For contrast, confirm a 6-digit TOTP code still submits fine through the
   same field — the fix is about the keyboard's affordance, not about
   restricting the field to one code shape or the other.

---

## 8. Run the automated checks

```bash
venv/bin/python -m pytest server/tests/test_auth/test_mfa.py server/tests/test_auth/test_admin_panel_2fa_routes.py -v
```

`test_mfa.py` covers the unchanged service contract;
`test_admin_panel_2fa_routes.py` covers the restyled `/admin/login/2fa`
route-level behavior (escaping regression, wrong-code re-render, cookie/
redirect on success) that §6 and its XSS check exercise manually above.

There is no automated coverage for the vanilla-JS `admin_panel/` files
(no linter/test runner configured for them in this repo) — §1 through §5 of
this playbook are what stand in for that.

---

## Troubleshooting

- **My Account shows a skeleton loader forever.** `GET /auth/mfa/status` is
  failing — check the browser console/network tab; a common cause is the
  bearer token having expired (re-login) or `auth_service.mfa` being `None`
  server-side (encryption key missing — see §1 of the API playbook).
- **The "Reset 2FA" button never appears on another user's detail panel.**
  Confirm the target user actually has 2FA enabled (status must read
  "Enabled") and that you're not viewing your own account — self-view
  intentionally omits the admin action (use My Account → Disable instead).
- **Enrolling shows a QR code that won't scan.** Same failure modes as the
  API playbook's §2 (network/rendering issue with the `data:image/png`
  URI) — try the manual-entry secret via Copy instead to isolate whether
  it's the QR image or the underlying secret that's the problem.
- **The global-disable note never appears even with `auth.two_factor.enabled:
  false`.** Confirm the server actually restarted — like `MfaService`'s
  encryptor, `mfa.enabled` is read once from config at process start, not
  re-read per request.
