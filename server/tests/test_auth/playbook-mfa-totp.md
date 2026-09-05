# Manual/Integration Check: Two-Factor Authentication (TOTP)

End-to-end verification of **native TOTP-based 2FA for local password
accounts** (`auth.two_factor`) — enrollment, QR scanning with a real
authenticator app, the two-step login exchange, recovery codes, "remember
this device," rate limiting, and admin recovery.

The automated tests (`test_mfa.py`) already cover the service-level logic
against a real SQLite backend: confirmation-gated enrollment, blocked login
without a valid code, single-use recovery-code consumption under
concurrency, `required_for_roles` enforcement, and the self-disable guard.
This playbook exercises what they can't: a real authenticator app on a real
phone scanning a real QR code, the HTTP routes end to end, the dashboard's
inline 2FA form, and the operational failure modes an operator will actually
hit (missing encryption key, locking yourself out, rate-limit throttling).

Prerequisites:
- ORBIT running at `http://localhost:3000`, default admin account intact.
- A phone with an authenticator app (Google Authenticator, Authy, 1Password,
  etc. — any standard TOTP app works, this is not Google-specific).
- `curl` and `python3` on the machine you're testing from.

> **Do §1 before enabling `required_for_roles` for a role you're currently
> logged in as.** Enrollment requires an existing bearer token; if a role is
> both required and unenrolled, that account is locked out of login
> entirely — there is no "prompt to enroll" fallback, it's a hard block by
> design (the roadmap plan calls this out explicitly: blocking is simpler to
> reason about than forcing enrollment mid-login).

---

## 0. Reference: what decides the login shape

| Account state | `POST /auth/login` result |
|---|---|
| 2FA disabled for the account, role not in `required_for_roles` | Normal single-step login — full session token, `mfa_required: false` |
| 2FA enabled for the account | `mfa_required: true`, `token` is a short-lived (5 min) **intermediate** token with no session capabilities — must be completed via `POST /auth/login/2fa` |
| 2FA **not** enabled, but role **is** in `required_for_roles` | Login refused outright (403) with `reason: mfa_enrollment_required` — no token issued at all |

**`ORBIT_MFA_ENCRYPTION_KEY` gates enrollment, not login.** Existing sessions
and already-enrolled accounts are unaffected if it's removed after the fact,
but `POST /auth/mfa/enroll` raises loudly rather than ever storing a secret
unencrypted.

**External (Entra/Auth0) identities are out of scope.** 2FA here applies
only to local password accounts; MFA for federated identities is the IdP's
own responsibility (see [`playbook-external-auth.md`](playbook-external-auth.md)).

---

## 1. Set up the encryption key and enable 2FA

```bash
python utils/scripts/generate_mfa_encryption_key.py --write-env
```

```yaml
# config/config.yaml
auth:
  two_factor:
    enabled: true
    required_for_roles: []     # leave empty until you've enrolled — see the warning above
    issuer_name: "ORBIT"
    recovery_codes_count: 10
    remember_device_days: 30
    rate_limit:
      enabled: true
      window_seconds: 60
      max_attempts: 5
```

Restart the server so both the env var and config are picked up.

**Confirm the missing-key failure mode first**, since operators will hit
this if they enable 2FA before setting the key. Temporarily unset
`ORBIT_MFA_ENCRYPTION_KEY`, **restart the server** (this must be a real
process restart — `MfaService` caches its encryptor for the process's
lifetime, so removing the env var without restarting has no effect and the
next step will misleadingly succeed), log in, and attempt enrollment (§2):

```bash
curl -s -w '\nHTTP %{http_code}\n' -X POST http://localhost:3000/auth/mfa/enroll \
  -H "Authorization: Bearer $TOKEN"
```

Expect **503** directly in that response body:

```json
{"detail":"Two-factor authentication is misconfigured on the server (missing or invalid encryption key). Contact an administrator."}
```

This is a client-facing error, not just a server-log line — if you only see
a generic `{"detail":"Internal Server Error"}` (or nothing distinctive) here,
something didn't restart cleanly; check the server's own console/log output
for the underlying `FileEncryptionError`:

```
files.encryption.enabled is true but ORBIT_MFA_ENCRYPTION_KEY is not set.
Generate a key with: python -c "import secrets, base64; ..."
```

(that log line's one-liner is generic to the shared encryption primitive —
prefer `python utils/scripts/generate_mfa_encryption_key.py --write-env` from
§1, which writes straight to `.env` instead of requiring you to copy a key
by hand.)

**Also confirm the login-completion path fails the same clear way**, not as
a misleading "invalid code": with an *already-enrolled* account and the key
still missing, attempt `POST /auth/login/2fa` with any code and expect the
same 503 body — never a 401.

Set the key back, restart, and continue.

---

## 2. Enroll and scan the QR code with your phone

Log in normally to get a bearer token:

```bash
TOKEN=$(curl -s -X POST http://localhost:3000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"YOUR_ADMIN_PASSWORD"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
```

Begin enrollment and save the QR code as a viewable PNG:

```bash
curl -s -X POST http://localhost:3000/auth/mfa/enroll \
  -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json, base64
data = json.load(sys.stdin)
print('secret (manual-entry fallback):', data['secret'])
print('otpauth uri:', data['otpauth_uri'])
png = base64.b64decode(data['qr_code_data_uri'].split(',', 1)[1])
open('mfa_qr.png', 'wb').write(png)
print('QR saved to mfa_qr.png')
"
open mfa_qr.png   # macOS; xdg-open on Linux, start on Windows
```

On your phone: open the authenticator app → **+** / "Add account" → **Scan a
QR code** → point the camera at `mfa_qr.png` on screen. Confirm an entry
appears labeled `ORBIT (admin)` (or whatever `issuer_name`/username you
configured) showing a rotating 6-digit code.

**Also confirm the manual-entry fallback works**, since not every device can
scan a screen: add a second entry by hand, entering the printed `secret` as
the setup key (time-based, default algorithm). Confirm both entries in the
app produce the **same** code at the same moment — proving the QR and the
raw secret encode the identical TOTP seed.

Re-run `POST /auth/mfa/enroll` a second time (still unconfirmed) and confirm
it returns a **different** secret/QR — a fresh enrollment attempt overwrites
the pending one rather than accumulating multiple pending secrets.

---

## 3. Confirm enrollment

Using the **current** code shown in the app:

```bash
curl -s -X POST http://localhost:3000/auth/mfa/confirm \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"code":"000000"}'   # replace with the live code
```

Expect `{"recovery_codes": [...]}` — ten single-use codes, shown exactly this
once. Save them somewhere safe for §5.

**Confirm the invalid-code guard first**, before using a real code: submit
an obviously wrong 6-digit code and expect a 400 with *"Invalid code, or no
enrollment is pending"*, and confirm `GET /auth/mfa/status` still reports
`enabled: false` — an incorrect confirmation must never flip the account
into a protected state.

```bash
curl -s http://localhost:3000/auth/mfa/status -H "Authorization: Bearer $TOKEN"
# -> {"enabled": true}
```

**Confirm re-enrollment is refused once enabled:**

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:3000/auth/mfa/enroll \
  -H "Authorization: Bearer $TOKEN"
```

Expect **400** *"2FA is already enabled for this account"* — disable first
(§7) if you want to re-enroll with a fresh secret.

---

## 4. The two-step login exchange

Simulate a fresh login (a new terminal/session, not the token from above):

```bash
curl -s -X POST http://localhost:3000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"YOUR_ADMIN_PASSWORD"}'
```

Expect `{"token":"<pending_token>","user":{...},"mfa_required":true}` — note
this token is **not** a session: confirm it's rejected by an authenticated
route before completing 2FA:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/auth/me \
  -H "Authorization: Bearer <pending_token>"
```

Expect **401**. Now complete it with the live code from your phone:

```bash
curl -s -X POST http://localhost:3000/auth/login/2fa \
  -H 'Content-Type: application/json' \
  -d '{"pending_token":"<pending_token>","code":"<live code>"}'
```

Expect a real session `token`. Confirm it now works against `/auth/me`.

**Confirm a wrong code is rejected** without completing the login (401,
*"Invalid or expired two-factor code"*), and that the pending token is still
usable afterward — one bad guess must not burn the whole pending login,
only the rate-limit budget (§6).

**Confirm expiry**: begin a new password login, wait 5+ minutes without
completing it, then submit the correct code. Expect 401 — the pending token
has expired and a fresh `POST /auth/login` is required.

---

## 5. Recovery codes

Simulate losing your phone: use one of the codes saved in §3 instead of a
TOTP code.

```bash
curl -s -X POST http://localhost:3000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"YOUR_ADMIN_PASSWORD"}'
# -> new pending_token

curl -s -X POST http://localhost:3000/auth/login/2fa \
  -H 'Content-Type: application/json' \
  -d '{"pending_token":"<pending_token>","code":"<a recovery code>"}'
```

Expect success. **Now reuse the same code** against a fresh pending login:

```bash
curl -s -X POST http://localhost:3000/auth/login \
  -H 'Content-Type: application/json' -d '{"username":"admin","password":"YOUR_ADMIN_PASSWORD"}'
curl -s -X POST http://localhost:3000/auth/login/2fa \
  -H 'Content-Type: application/json' \
  -d '{"pending_token":"<new pending_token>","code":"<same recovery code as above>"}'
```

Expect **401** — each recovery code is single-use, consumed rather than
deleted (auditable). Confirm the remaining nine codes still work.

---

## 6. Second-factor rate limiting

With `auth.two_factor.rate_limit.max_attempts: 5`, submit six consecutive
wrong codes against the **same account** (a fresh `pending_token` each time
— password login succeeds every time since only the second factor is being
tested):

```bash
for i in $(seq 1 6); do
  PT=$(curl -s -X POST http://localhost:3000/auth/login \
    -H 'Content-Type: application/json' \
    -d '{"username":"admin","password":"YOUR_ADMIN_PASSWORD"}' \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:3000/auth/login/2fa \
    -H 'Content-Type: application/json' -d "{\"pending_token\":\"$PT\",\"code\":\"000000\"}"
done
```

Expect the 6th attempt to return **429**, even though each attempt used a
**brand-new** pending token. This is the important property to verify: the
throttle is keyed by account (+ IP), not by the pending token itself — a
fresh token per request must not hand out a fresh guessing budget. (This is
exactly the P1 finding this feature's review caught and fixed; if you ever
see unlimited fresh attempts succeed here, that's a regression.)

Wait out `window_seconds` (default 60s) and confirm attempts are allowed
again.

---

## 7. "Remember this device"

```bash
PT=$(curl -s -X POST http://localhost:3000/auth/login \
  -H 'Content-Type: application/json' -d '{"username":"admin","password":"YOUR_ADMIN_PASSWORD"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

curl -s -X POST http://localhost:3000/auth/login/2fa \
  -H 'Content-Type: application/json' \
  -d "{\"pending_token\":\"$PT\",\"code\":\"<live code>\",\"remember_device\":true}"
```

Expect a `device_token` in the response. Now log in again, presenting it:

```bash
curl -s -X POST http://localhost:3000/auth/login \
  -H 'Content-Type: application/json' -H "X-Device-Token: <device_token>" \
  -d '{"username":"admin","password":"YOUR_ADMIN_PASSWORD"}'
```

Expect a **full session token directly**, `mfa_required` absent/false — the
second factor was skipped because the device is remembered. Confirm an
**unrecognized** device token (or none at all) still gets challenged.

Set `remember_device_days: 0` and confirm `remember_device: true` in the
request now returns no `device_token` — the feature is fully disabled, not
silently accepted.

---

## 8. `required_for_roles` and the self-disable guard

Set `required_for_roles: ["admin"]` and restart — you're already enrolled
from §3, so this should not lock you out. Confirm a **second**, unenrolled
admin-role account cannot log in at all:

```bash
orbit user create --username admin2 --password 'Sup3r$ecretPass!' --role admin
curl -s -X POST http://localhost:3000/auth/login \
  -H 'Content-Type: application/json' -d '{"username":"admin2","password":"Sup3r$ecretPass!"}'
```

Expect **403**, *"Your role requires two-factor authentication... Contact an
administrator."* — no token of any kind is issued.

**Confirm you can't disable your own way into that trap.** As the enrolled
`admin` account:

```bash
curl -s -X POST http://localhost:3000/auth/mfa/disable \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"current_password":"YOUR_ADMIN_PASSWORD"}'
```

Expect **400** — disabling 2FA while your role requires it is refused, since
it would lock out every future login for that account with no way back
short of another admin's help.

---

## 9. Admin recovery

Simulate `admin2` (unenrolled, blocked by §8) losing access to ever
enrolling by having an admin reset any hypothetical stuck state — or more
realistically, simulate an **enrolled** user losing their phone and recovery
codes. Enroll a throwaway user, then:

```bash
curl -s -X DELETE http://localhost:3000/auth/users/<user_id>/mfa \
  -H "Authorization: Bearer $TOKEN"
```

Expect `{"message":"Two-factor authentication reset","user_id":"..."}`, and
confirm `GET /auth/mfa/status` for that user (once they can log in again)
reports `enabled: false`. Confirm this requires `users.manage` — retry with
a token that lacks it and expect **403**.

With `internal_services.audit.admin_events.enabled: true`, confirm this
produced an `auth.mfa.admin_reset` event (Admin panel → Audit tab, or
`GET /admin/audit/events`) — this is a sensitive override and must always be
traceable to the acting administrator.

---

## 10. The dashboard (browser) flow

Everything above uses the JSON API; confirm the cookie-based dashboard login
behaves the same way for an enrolled admin account.

1. Open `http://localhost:3000/admin` in a browser, log in with
   username/password.
2. Instead of redirecting to the dashboard, expect a plain HTML page titled
   "Two-Factor Authentication" asking for a code (this is a minimal inline
   form, not the styled login page — that's deliberate, it's a stopgap until
   a proper frontend step is built).
3. Enter the current code from your phone (optionally check "Remember this
   device") and submit.
4. Expect a redirect into the dashboard, with a `dashboard_token` cookie set.

Confirm a wrong code re-renders the same form with an error message rather
than redirecting, and that the pending token embedded in the form's hidden
field survives the retry (no need to log in again after one bad guess).

**XSS regression check** (this was a P1 finding in review): confirm the
`next` query param can't inject markup into that inline form.

```
http://localhost:3000/admin/login?next=%2F%3F%22%3E%3Cscript%3Ealert(1)%3C%2Fscript%3E
```

Log in with this URL, reach the 2FA form, and confirm no alert fires and no
raw `<script>` tag appears in the page source — the `next` value must come
through HTML/attribute-escaped.

---

## 11. Run the automated checks

```bash
venv/bin/python -m pytest server/tests/test_auth/test_mfa.py -v
```

All ten should pass, including the concurrent recovery-code race test and
the pending-token rate-limit-identity test — those two exist specifically
because manual testing alone won't reliably reproduce a race condition.

---

## Troubleshooting

- **Enrollment fails with a 500 / `FileEncryptionError`.** `ORBIT_MFA_ENCRYPTION_KEY`
  is missing or not valid base64. Generate one:
  `python utils/scripts/generate_mfa_encryption_key.py --write-env`, restart.
- **I'm locked out of my own admin account.** You enabled `required_for_roles`
  for a role that has no enrolled accounts left. Recovery requires direct
  database access: use `utils/scripts/reset_admin_password.py`-style offline
  access to clear the `user_mfa` row for that user (or temporarily set
  `required_for_roles: []`, restart, log in, and re-enroll).
- **A code from my authenticator app is always rejected.** Check the
  server's clock — `pyotp` validates within a ±1 time-step window (30s
  default), so significant clock drift on either side breaks every code.
- **`/auth/login/2fa` returns 429 immediately on a fresh account.** The rate
  limit is keyed by account, not by pending token — if you were testing §6
  moments ago on the same account, you're still inside `window_seconds`.
- **The QR scans but the app shows a different code than manual entry
  suggests it should.** Re-check you copied the entire `secret` string
  (base32, no padding characters dropped) — a truncated secret still
  "works" but produces different codes than the QR's full seed.
- **Recovery code accepted but I still have codes I never got.** Recovery
  codes are generated once, at confirmation, and never regenerated
  automatically — re-enrolling (disable, then enroll+confirm again) is the
  only way to get a fresh set.
- **`remember_device` returns no `device_token`.** Check
  `auth.two_factor.remember_device_days` isn't `0` — that value disables the
  feature outright rather than issuing a token that expires instantly.
