# Manual/Integration Check: Identity Allowlist (Pre-clearing External Logins)

End-to-end verification of **deny-by-default access control for external
identities**, plus the `admin_users` email-verification fix that shipped with it:

- **Part 1 — the gate:** under `auth.providers.access_control: allowlist`, an
  Entra/Auth0 subject that matches no rule is never provisioned an ORBIT account
  at all — not on inference, not on the admin panel.
- **Part 2 — the admin panel UI:** the Users tab's new **Allowed Identities**
  panel, and that the existing **Blocked Identities** panel still behaves
  identically after both were refactored onto one shared builder.
- **Part 3 — withdrawal:** removing or narrowing a rule revokes live sessions,
  including the *opaque* `dashboard_token` sessions admin SSO mints.
- **Part 4 — the email-verification fix:** an `admin_users` email entry no longer
  matches an unverified address, so nobody can claim an allowlisted admin
  identity by registering that email at the IdP.

The automated tests (`test_user_allowlist.py`, `test_admin_sso_callback.py`,
`test_admin_sso.py`, `test_external_auth.py`) already cover the logic with fake
JWKS and a real SQLite backend. This playbook exercises what they can't: real
provider round-trips, the browser UI, cookie sessions, multi-worker cache
propagation, and the **migration behavior on a database that already has
external users** — the thing most likely to surprise an operator.

Prerequisites:
- The `auth-providers` profile installed and at least one provider configured
  and working — do [`playbook-external-auth.md`](playbook-external-auth.md)
  first if you haven't. This playbook assumes you can already complete both a
  bearer-JWT call and an admin-panel SSO login.
- ORBIT at `http://localhost:3000`, default admin password account intact.
- `orbit` CLI configured against that server.

> **Take a database backup before Part 5.** That section deliberately denies
> existing users.

---

## 0. Reference: what decides access

Two independent questions, answered in this order. Confusing them is the main
source of false bug reports, so keep this open:

| # | Question | Decided by | Failure shows as |
|---|---|---|---|
| 1 | Is this identity **blocked**? | `user_blacklist` rules | denied everywhere |
| 2 | Is this identity **cleared**? | `user_allowlist` rules + `admin_users` | denied everywhere; SSO shows `not_cleared`; **no `users` row created** |
| 3 | Does it have a **panel role**? | `users.roles` (see [RBAC playbook](playbook-rbac-roles-permissions.md)) | SSO shows `not_authorized`; account *does* exist |

**Deny beats allow.** A blacklist rule always wins over an allowlist rule
covering the same identity.

**Local password users are never gated by #2.** Only rows with
`users.provider` set are checked. The bootstrap `admin` always works.

Allowlist vs. blacklist, inverted where it matters:

| | `user_blacklist` | `user_allowlist` |
|---|---|---|
| No rules at all | blocks nobody | **admits nobody** (when enforcing) |
| Adding a rule | denies; revokes sessions | grants; revokes nothing |
| Removing a rule | restores access; no revocation | **withdraws** access; revokes sessions |
| Self-lockout guard | on create + edit | on **delete** + narrowing edit |

Enforcement requires **both** `auth.providers.enabled: true` **and**
`access_control: allowlist`. With no provider enabled there are no external
identities to gate and the table is inert — that is deliberate, not a bug.

---

## 1. Confirm the starting posture

```yaml
# config/config.yaml
auth:
  providers:
    enabled: true
    access_control: allowlist     # the default
    default_role: "user"
    admin_sso:
      enabled: true
      admin_users: ["you@yourdomain.com"]
```

Restart and read the startup log. You must see one of these two lines:

```
INFO  Identity allowlist is enforcing (N existing external users, all cleared)
WARN  Identity allowlist is enforcing: M of N existing external users match no
      rule and can no longer sign in. Run 'orbit user allowlist seed-from-existing' ...
```

If you instead see:

```
WARN  auth.providers.access_control is 'open': any identity an enabled provider
      authenticates is provisioned an ORBIT account.
```

…you are not enforcing — fix the config before continuing.

Confirm the rule set is empty:

```bash
orbit login --username admin
orbit user allowlist list
```

Expect the warning *"No allowlist rules. Under access_control: allowlist this
means no external identity can sign in (apart from admin_users entries)."*

**Also confirm the `default_role` guard.** Temporarily set
`default_role: "operator"`, restart, and confirm this warning appears:

```
WARN  auth.providers.default_role is 'operator', which carries admin-panel
      permissions: EVERY externally authenticated user will be granted them
      at first login.
```

Set it back to `"user"` and restart. This is a one-word footgun; the warning is
the only thing standing between it and a wide-open panel.

---

# Part 1 — The gate (API + provisioning)

## 2. An uncleared identity gets nothing

Use a **second** provider account — one that is *not* in `admin_users`. Obtain
its access token exactly as in the external-auth playbook §2, then:

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $STRANGER_JWT" \
  http://localhost:3000/auth/me
```

Expect **401**.

Now the part that actually matters — confirm **no account was created**:

```bash
orbit user list | grep -iE "entra:|auth0:"
```

The stranger's `{provider}:{subject}` must **not** appear. A 401 with a row
created would mean the gate is only cosmetic; the whole point of hooking
provisioning is that an unapproved identity leaves no trace.

Check the server log for:

```
WARN  Refused to provision external user not on the identity allowlist:
      auth0:<sub> (email='stranger@...')
```

## 3. Clearing by email domain

```bash
orbit user allowlist add \
  --pattern '*@yourdomain.com' --entry-type email \
  --reason 'Employees'

orbit user allowlist list
```

Retry §2's curl with the same stranger token — but only if that account's email
is on `yourdomain.com`. Expect **200** now, and:

```bash
orbit user list | grep -iE "entra:|auth0:"
```

The account now exists, with `roles: ["user"]`.

> If your stranger account is on a different domain (e.g. a personal Gmail),
> that's a *better* test — it should still be 401. Add a rule matching it
> explicitly to see the flip.

## 4. Clearing by provider subject

Subjects are the durable identifier — an email can change at the IdP, a `sub`
cannot. Remove the email rule and clear by subject instead:

```bash
orbit user allowlist remove --rule-id <email-rule-id>
orbit user allowlist add \
  --pattern "auth0:<the-subject>" --entry-type username \
  --reason 'Contractor, by subject'
```

Retry the curl — expect **200**. Then confirm a wildcard subject rule works:

```bash
orbit user allowlist add --pattern 'entra:approved-*' --entry-type username
```

## 5. Migration: the seed command

**This is the section that breaks a running deployment if mishandled.** Back up
your database first.

Add a few external users while in `open` mode (set `access_control: open`,
restart, sign in with two or three provider accounts), then flip back to
`allowlist` and restart. The startup warning should now name a non-zero count.

Confirm those users are actually denied:

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $EXISTING_USER_JWT" \
  http://localhost:3000/auth/me     # expect 401
```

Now grandfather them:

```bash
orbit user allowlist seed-from-existing --dry-run
```

Expect a list of every `{provider}:{subject}` it would clear, and *"Dry run —
nothing was written."* **Read the list.** Signing in once was never an approval
decision — this is the one command that can quietly bless an account that
shouldn't have had one.

```bash
orbit user allowlist seed-from-existing
```

Expect the same list, then a confirmation prompt. Answer `n` first and confirm
*"Aborted; nothing was written."* Then re-run and answer `y`.

Verify:
- `orbit user allowlist list` shows one `username`-type rule per external user.
- The previously-denied token now returns **200**.
- Re-running `seed-from-existing` is **idempotent** — it reports every user
  already has a rule and writes nothing (the unique `(entry_type, pattern)`
  index makes this a no-op, not an error).
- Restarting the server now logs the *"all cleared"* variant.

---

# Part 2 — Admin panel UI

## 6. The Allowed Identities panel

Log into `/admin` as the default admin (password) → **Users** tab. Confirm:

- Two panels are present: **Allowed Identities** *above* **Blocked Identities**.
- The Allowed panel's description explains that an empty list admits nobody, and
  that local accounts and `admin_users` are unaffected.
- With no rules, the empty state reads **"No allowed identities"** with a 🔑
  icon (the Blocked panel's is 🚫 — confirm they're distinct, since both panels
  are now rendered by the same builder and a shared-state bug would show up
  here first).

Exercise the form:

| Action | Expected |
|---|---|
| **Add Rule** → Match On = Email, Pattern = `*@yourdomain.com` | Confirm dialog says *"Pre-clear …"*, **not** "Block". Confirm button reads **Allow** |
| Confirm | Status *"Identity allowed"* — with **no** "N sessions revoked" suffix, because adding an allow rule revokes nothing |
| Change Match On to Username | Placeholder updates to `entra:00000000-...` style, not the blacklist's `baduser or entra:abc*` |
| Pattern = `*` alone, Add | Rejected: *"Pattern must contain at least one literal character."* Clearing everyone is a **mode** (`access_control: open`), not a rule |
| Pencil (edit) → change only the Reason → Save | Saves immediately with **no** confirm dialog (a reason-only edit doesn't change who is covered) |
| Pencil → change the Pattern → Save | Confirm dialog *"Change this rule to allow …? Anyone it stops covering is signed out immediately."* |
| X (remove) | Confirm dialog *"Stop allowing …? Users cleared only by this rule are signed out immediately"* — and it is styled as a **danger** action, unlike removing a blacklist rule |

## 7. Regression: the Blocked Identities panel

Both panels now share one builder, so re-run the blacklist basics to prove
nothing regressed in the refactor:

| Action | Expected |
|---|---|
| Add `*@spam-domain.com` (Email) | Confirm says *"Block …"*, button **Block**, danger-styled |
| Confirm | Status *"Identity blocked"* — **with** the *"N users matched, M sessions revoked"* suffix when it matches existing users |
| Edit pattern | Confirm *"Change this rule to block …"* |
| Remove | Confirm *"Stop blocking …? Previously revoked sessions are not restored."* — **not** danger-styled, and no revocation counts |
| Refresh buttons | Each panel's refresh reloads only its own table |

Then confirm the two are genuinely independent:

- Add the **same** pattern (`*@yourdomain.com`, Email) to *both* panels. Both
  accept it — the unique index is per-table.
- Confirm the affected user is now **denied** (deny wins), and that the server
  logs the blacklist reason, not the allowlist one.
- Remove the blacklist rule; the user is admitted again.

## 8. Permission gating

The allowlist endpoints require `users.manage`. Using tokens from the
[RBAC playbook](playbook-rbac-roles-permissions.md):

```bash
for T in ADMIN USER_MANAGER OPERATOR; do
  TOKEN_VAR="TOKEN_$T"; echo -n "$T: "
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "Authorization: Bearer ${!TOKEN_VAR}" \
    http://localhost:3000/auth/allowlist
done
```

Expect `admin`/`user-manager` → **200**, `operator` → **403** (these routes use
`require_permission`, so 403 not 401 — see the RBAC playbook §0 asymmetry note).
Confirm `operator` logging into the panel sees no Users tab at all.

---

# Part 3 — Withdrawal and session revocation

## 9. Removing a rule cuts off a live bearer session

1. Ensure a cleared external user can call `/auth/me` (200).
2. Remove the rule that clears them.
3. Retry immediately.

Expect **401** within `auth.allowlist.cache_ttl` seconds (default 30; set
`cache_ttl: 0` to make this instant while testing). The server logs:

```
WARN  Denied external user auth0:<sub>: not on the identity allowlist
```

## 10. Removing a rule cuts off an opaque SSO session

**This is the case that was broken in review** and is worth testing carefully,
because admin SSO does *not* use a JWT — it mints an opaque `dashboard_token`
cookie, which resolves down a different branch of `validate_token`.

1. Add an allowlist rule covering a second provider account, then **provision
   that account**, then give it a panel role so it can actually get in:
   ```bash
   orbit user allowlist add --pattern 'ops@yourdomain.com' --entry-type email

   # A rule grants clearance; it does not create a row. Provision by
   # authenticating once with the ops identity's own JWT:
   curl -s -o /dev/null -w "%{http_code}\n" \
     -H "Authorization: Bearer $OPS_JWT" http://localhost:3000/auth/me   # 200

   orbit user set-roles --username 'auth0:<ops-sub>' --roles operator
   ```
   Ordering matters: `set-roles` resolves the username via
   `GET /auth/users/by-username`, which **404s** if no row exists yet. Running it
   before the provisioning call fails with "User not found".
2. In a **separate browser profile / incognito window**, sign into `/admin` via
   SSO as that account. Confirm you reach the panel.
3. Back in your admin session, **remove** that allowlist rule.
4. In the ops window, click any tab or reload.

Expect the session to be rejected and bounced to the login page. Note the
session *row* may still exist in the database — it is the **per-request**
clearance check that denies, which is what makes removal reliable even for a
session created after revocation ran (an SSO callback still in flight, or a
worker with a stale rule cache).

To make the API response explicit:

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  -b "dashboard_token=<the-cookie-value>" \
  http://localhost:3000/admin/api/token       # expect 401
```

> **This step alone does not isolate the per-request check.** Deleting the rule
> through the API also runs `_revoke_uncleared`, which *deletes* that session
> row — so the 401 above is explained by the session no longer existing, and
> you would see it even with the clearance check removed. §10a is the step that
> actually reproduces the reviewed race. Keep this one anyway: it verifies the
> ordinary revocation path end to end, which is what covers the common case.
>
> (The automated test `test_removing_a_rule_denies_an_opaque_sso_session` does
> isolate the check — it calls the service's `delete_rule()` directly rather
> than the route, so no revocation runs and the session row survives.)

## 10a. A session minted *after* revocation, by a stale-cache worker

The race the per-request check exists for: worker A deletes a rule and revokes
sessions, while worker B — whose rule cache hasn't refreshed — completes an SSO
callback and mints a `dashboard_token` for an identity that is no longer
cleared. That session was created after revocation ran, so nothing ever deleted
it. Without a per-request check it stays usable until it expires (12h by
default).

Uvicorn gives you no way to choose which worker serves a request, so drive it
with **two processes on different ports sharing one database** — which is
exactly what two workers are, minus the routing lottery:

Set this in **both** config files (B's is the one that decides the window):

```yaml
auth:
  allowlist:
    cache_ttl: 300        # a 5-minute window to work inside
```

Use Postgres or MongoDB for the shared backend. SQLite works via WAL but two
processes on one file can hit lock contention that muddies the result.

The port comes from `general.port` in the config file and there is no CLI or
environment override (`server/main.py` accepts only `--config`), so instance B
needs its own config file — a copy with just the port changed:

```bash
cp config/config.yaml /tmp/orbit-b.yaml
# edit /tmp/orbit-b.yaml:  general.port: 3001
python3 -c "print(open('/tmp/orbit-b.yaml').read().count('port: 3001'))"   # expect 1
```

Keep everything else identical — crucially the same `internal_services.backend`,
so both processes share one database, and the same `auth.allowlist.cache_ttl`.

```bash
# Instance A
python3 server/main.py --config config/config.yaml      # :3000
# Instance B, same database, different port
python3 server/main.py --config /tmp/orbit-b.yaml       # :3001
```

Register `http://localhost:3001/admin/auth/<provider>/callback` as an additional
allowed callback URL at the provider. Leave `admin_sso.base_url` unset in both
configs so each instance auto-detects its own origin from the request — if
`base_url` is set, B would build a redirect URI pointing at A and the callback
would land on the wrong process, defeating the whole setup.

Setup — an ops identity cleared *only* by a rule (not by `admin_users`), holding
a panel role:

```bash
orbit user allowlist add --pattern 'ops@yourdomain.com' --entry-type email
```

Now the sequence. **Order matters** — steps 1–3 are setup, and the race is
step 5 happening *after* step 4.

1. **Provision the ops row, and warm B's cache, in one call.** Authenticate once
   against **B** with the ops identity's own JWT:
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" \
     -H "Authorization: Bearer $OPS_JWT" http://localhost:3001/auth/me   # 200
   ```
   This does three things at once: it JIT-provisions the `auth0:<ops-sub>` row
   (an allowlist rule grants clearance but never creates a row), it populates
   **B's** in-memory rule cache, and it confirms the rule works. Note that
   `orbit user allowlist list` would *not* warm the cache — `list_rules()` reads
   the database directly and bypasses it — so a real authentication is required,
   and it must be against B, not A.

2. **Give it a panel role**, now that the row exists:
   ```bash
   orbit user set-roles --username 'auth0:<ops-sub>' --roles operator
   ```
   Run this *after* step 1: `set-roles` resolves the username via
   `GET /auth/users/by-username`, which **404s** ("User not found") if the row
   hasn't been provisioned yet.

3. **Confirm SSO works** — in an incognito window, sign into
   `http://localhost:3001/admin`. Then **log out**, so no pre-existing session
   confuses the result.

4. **Delete the rule through A:**
   ```bash
   curl -s -X DELETE -H "Authorization: Bearer $TOKEN_ADMIN" \
     http://localhost:3000/auth/allowlist/<rule-id>
   ```
   Expect `"revoked_sessions": 0` — and note `"matched_users"` may well be `1`
   (the ops identity *is* now uncleared; it simply had no live session to cut).
   Nothing was revoked, which is precisely the hole this step opens. Confirm the
   rule is gone: `orbit user allowlist list`.
5. **Within the 5-minute window, sign in again through B** (`:3001`). It
   **succeeds**, because B is still matching against its stale cache. You now
   hold a `dashboard_token` for an identity with no clearance, created after
   revocation ran, that no revocation pass will ever touch.

Confirm that state directly — a live session row for an uncleared user:

```bash
# Postgres
psql ... -c "SELECT token, username FROM sessions WHERE username LIKE 'auth0:%';"
```

6. **Immediately** retry the cookie against B:
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" \
     -b "dashboard_token=<cookie>" http://localhost:3001/admin/api/token
   ```
   Expect **200**. This is correct and is not the bug — it is the documented
   `cache_ttl` bound. B has not yet learned the rule is gone.
7. **Wait out the TTL** (5 minutes), then retry the same cookie against B.
   Expect **401**. This is the fix: B refreshed its rules, the per-request
   clearance check now fails, and the session is dead despite never having been
   revoked. Without the check this would stay **200** until expiry.

**Deterministic final assertion.** Rather than waiting on a clock, force it —
editing **`/tmp/orbit-b.yaml`**, not `config/config.yaml`. B reads only its own
file, so changing A's config leaves B at 300 and the check appears not to fire:

```yaml
# /tmp/orbit-b.yaml
auth:
  allowlist:
    cache_ttl: 0          # re-read rules on every authentication
```

Restart **B only** (leave A running), and retry the same cookie:

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  -b "dashboard_token=<cookie>" http://localhost:3001/admin/api/token
```

Expect **401** immediately, with the server log line:

```
WARN  Denied external user auth0:<ops-sub>: not on the identity allowlist
```

Confirm the session row is **still present** in the database. That is the
signature of this fix working: the credential is intact and unrevoked, and the
request is refused purely by the check on the opaque-session branch of
`validate_token`.

To see the failure mode for yourself, comment out the `_is_cleared` call in that
branch (`server/services/auth_service.py`, the session path of
`validate_token`), restart B, and retry — the cookie returns **200** again. Put
it back.

## 11. Revocation counts and the inverted lockout guard

Removing a rule should *report* what it cut off:

```bash
orbit user allowlist remove --rule-id <id>
```

Expect *"Revoked N session(s) for M user(s) this rule was clearing"* when it had
live sessions, and no such line when it had none.

**Now try to lock yourself out.** As an *external* (SSO) admin whose only
clearance comes from an allowlist rule, attempt to delete that rule:

```
400  This change would revoke your own access. Add a rule covering your
     identity first, or make the change from a local admin account.
```

Then confirm the guard correctly does **not** fire for a local password admin —
they are never gated, so no rule change can lock them out. And confirm it does
not fire for an external admin whose clearance comes from `admin_users`, since
that clearance is implicit and survives any rule deletion.

## 12. Multi-worker cache propagation

Set `performance.workers: 4`, restart, and set
`auth.allowlist.cache_ttl: 30`.

Remove a rule, then poll a cleared user's token repeatedly:

```bash
for i in $(seq 1 40); do
  curl -s -o /dev/null -w "%{http_code} " \
    -H "Authorization: Bearer $JWT" http://localhost:3000/auth/me
  sleep 1
done; echo
```

Expect a mix of 200 and 401 initially as workers pick up the change at
different points, converging to all-401 within the TTL. Then confirm
`cache_ttl: 0` makes it immediate on every worker.

> Session revocation itself is **not** subject to this delay — it's a database
> delete. The TTL only bounds how long a stale worker keeps honoring a
> newly-removed rule for a *newly presented* credential.

## 13. Audit trail

With `internal_services.audit.admin_events.enabled: true`, perform an add, an
edit, and a delete, then open the **Audit** tab (or query
`GET /admin/audit/events` as `auditor`). Confirm three events:

| Event type | Action | Resource type |
|---|---|---|
| `auth.allowlist.create` | CREATE | `allowlist_rule` |
| `auth.allowlist.update` | UPDATE | `allowlist_rule` |
| `auth.allowlist.delete` | DELETE | `allowlist_rule` |

Confirm the create event's `resource_id` is the **stored** rule id and its
summary records the **normalized** pattern. Submit `"  *@YOURDOMAIN.com  "` and
confirm the audit summary shows `*@yourdomain.com` — searching the ledger for
the stored value must find the event that created it.

---

# Part 4 — The `admin_users` email-verification fix

## 14. An unverified email cannot claim admin

This closes a real privilege-escalation path: `admin_users` matches on the email
claim, and on an Auth0 database/social connection a user can assert an address
the IdP never verified.

```yaml
auth:
  providers:
    auth0:
      require_verified_email: true      # the default
    admin_sso:
      admin_users: ["boss@yourdomain.com"]
```

In Auth0, create a database-connection user with the address
`boss@yourdomain.com` and leave it **unverified** (Auth0 dashboard →
User Management → the user → `email_verified` = false). Sign into `/admin` via
SSO as that user.

Expect: **not** promoted to admin. The login page shows an authorization error
and the server logs:

```
WARN  Admin allowlist email match for auth0 rejected: boss@yourdomain.com is not
      a verified address on this id_token (email_verified=False). Use
      "auth0:<sub>" in admin_users to allowlist this identity by subject instead.
```

Verify the account's role directly — the account may exist (the email is
implicitly cleared by the allowlist), but it must **not** be `admin`:

```bash
orbit user list | grep -i "auth0:"
```

Then set `email_verified` to true at the IdP, sign in again, and confirm
promotion to `admin` now happens.

## 15. Subject entries are never gated on verification

Replace the email entry with the subject form:

```yaml
      admin_users: ["auth0:<the-sub>"]
```

Sign in as the **unverified** user again. Expect **admin access granted** — a
`sub` is IdP-assigned and unspoofable, so it doesn't need email verification.
This is why the docs recommend the subject form.

## 16. Entra defaults, and the case boundary

Entra id_tokens carry no `email_verified` claim, so
`entra.require_verified_email` defaults to **false**. Confirm an `admin_users`
email entry still matches an Entra login (its address comes from the directory,
not user self-assertion). Then set it to `true` and confirm the same login is
now refused — proving the flag is honored per provider.

**Subject case sensitivity** (also a review finding). Set:

```yaml
      admin_users: ["entra:AdminSub"]
```

Confirm:
- `entra:AdminSub` is cleared and promoted.
- `entra:adminsub` is **not** cleared — it is a *different* OIDC identity, and
  treating it as the same one would hand it clearance plus any panel role
  assigned to it.
- `ENTRA:AdminSub` **is** cleared — the provider prefix is normalized, only the
  subject is case-exact.

Since you can't usually choose a real IdP's `sub` casing, verify this with the
CLI/API against the allowlist's implicit matching rather than a live login:

```bash
orbit user allowlist list      # confirm no explicit rule is doing the work
```

…then sign in with the real subject and confirm the account is cleared, and
confirm the automated test covers the negative case:

```bash
venv/bin/python -m pytest server/tests/test_auth/test_user_allowlist.py \
  -k "implicit_subject_match_is_case_sensitive" -v
```

---

# Part 5 — Regressions that must NOT appear

Run all of these; each guards against a way this feature could break something
that previously worked.

### A. Local password auth is untouched

With `access_control: allowlist` and **zero** rules:

```bash
orbit login --username admin        # must succeed
orbit me
```

Confirm the bootstrap admin, and every password account you created for the RBAC
playbook, still log in and reach the panel. If enforcement ever gates a local
user, that is a **P0** — it locks operators out of the panel that manages the
allowlist.

### B. `open` mode restores the previous behavior exactly

Set `access_control: open`, restart, and confirm a brand-new provider account is
JIT-provisioned with `roles: ["user"]` on first bearer call — the pre-allowlist
behavior. Confirm the startup log warns that the posture is open.

### C. Providers disabled ⇒ allowlist inert

Set `auth.providers.enabled: false`, restart. Confirm no allowlist warning is
logged and that password auth is unaffected. The table exists but gates nothing.

### D. Blacklist still cuts off in-flight users

This exercises a bug the review found in **existing** blacklist code: session
revocation used hardcoded `users`/`sessions` collection names, so on a MongoDB
deployment with custom collection names it silently revoked nothing.

```yaml
internal_services:
  backend: { type: mongodb }
  mongodb:
    users_collection: "orbit_users"
    sessions_collection: "orbit_sessions"
```

With a user signed in, add a blacklist rule matching them and confirm the API
response reports a **non-zero** `revoked_sessions`, and that their live session
is actually dead. Before the fix this reported `0` while claiming success. Then
repeat for an allowlist rule **removal** on the same deployment.

If you don't run Mongo, this is covered by
`test_collection_names_follow_mongo_config`.

### E. Blacklist self-lockout guard still fires

Confirm that adding a blacklist rule matching your own identity is still
rejected with 400 — the allowlist work added an inverted guard, and both must
coexist.

### F. External-auth playbook still passes end to end

Re-run [`playbook-external-auth.md`](playbook-external-auth.md) **with a rule in
place** clearing your test identity. Every scenario there (JIT provisioning,
re-use not duplicate, tampered token rejected, wrong audience, deactivation,
logout no-op, case-sensitive subjects, CSRF/state) must still behave identically.
Scenario **H** ("non-allowlisted user is rejected") now has two distinct
flavors — confirm you can tell them apart on the login page:

| Situation | Error shown |
|---|---|
| No allowlist rule covers them | *"This identity has not been granted access to this ORBIT instance."* (`not_cleared`) |
| Cleared, but no panel role | *"Your account is not authorized for admin access."* (`not_authorized`) |

Conflating these two was the point of adding a separate error string; if both
show the same message, the callback's clearance pre-check isn't running.

### G. Inference surfaces respect the gate

With `auth.require_authenticated_user: true` and an uncleared identity, confirm
`POST /v1/chat/completions` with that bearer token plus a valid `X-API-Key` is
rejected. Then confirm that with the flag **off**, an API key alone still works —
the allowlist gates *identities*, and (like the blacklist) it cannot constrain a
caller who presents no identity at all. That limitation is documented, not a
regression.

---

## 17. Run the automated checks

```bash
venv/bin/python -m pytest \
  server/tests/test_auth/test_user_allowlist.py \
  server/tests/test_auth/test_admin_sso_callback.py \
  server/tests/test_auth/test_admin_sso.py \
  server/tests/test_auth/test_external_auth.py \
  server/tests/test_auth/test_user_blacklist.py \
  server/tests/test_auth/test_require_authenticated_user.py -v
```

All should pass. Plus the broader auth-adjacent sweep:

```bash
venv/bin/python -m pytest server/tests/test_auth/ server/tests/test_middleware/ -q
```

> Note: `server/tests/test_routes/test_admin_permission_guards.py` has one
> pre-existing failure on `main`
> (`test_api_key_bypasses_permission_or_api_key_routes_but_not_conversations`)
> unrelated to this feature. Confirm it fails identically on a clean checkout
> before chasing it.

---

## Troubleshooting

- **Every external login is refused right after upgrading.** Expected — the
  default is now deny. Check the startup warning for the count, then
  `orbit user allowlist seed-from-existing`, or set `access_control: open`.
- **A rule I just added isn't taking effect.** Wait out
  `auth.allowlist.cache_ttl` (default 30s), or set it to `0`. Under
  `performance.workers > 1` each worker caches independently, so behavior can
  differ per request until every worker refreshes.
- **I removed a rule but the user is still in.** Two possibilities: (a) they are
  also cleared by `admin_users`, which is implicit and survives rule deletion —
  check that list; (b) another rule still matches them (`orbit user allowlist
  list` and check for a broader wildcard).
- **`orbit user allowlist list` is empty but external logins still work.**
  Either `access_control: open`, or `auth.providers.enabled: false`, or the
  identity is in `admin_users`. Check the startup log line — it states the
  posture unambiguously.
- **SSO login shows `not_authorized`, and I expected `not_cleared`.** The
  identity *is* cleared (probably via `admin_users` or a broader rule) and is
  failing the role check instead. See §0's three-question table.
- **My SSO user's role keeps reverting to `admin`.** Unrelated to the allowlist —
  they're in `admin_users`, which re-promotes on every login. See
  `docs/authentication.md`.
- **A pattern I added does nothing.** Patterns are lowercased and matched with
  `fnmatch` against one field only, chosen by `entry_type`. An `email` rule never
  matches a username. For external users the username is
  `{provider}:{subject}` — use `entry_type: username` for those.
- **Deleting a rule returns 400 about my own access.** You're an external admin
  whose only clearance is that rule. Add a rule covering yourself, add yourself
  to `admin_users`, or make the change from a local password admin.
- **`seed-from-existing` says "No external users found".** It identifies them by
  the `entra:`/`auth0:` username prefix. If you added a *new* provider, that
  prefix needs adding to `_external_users()` in
  `bin/orbit/commands/allowlist.py`.
