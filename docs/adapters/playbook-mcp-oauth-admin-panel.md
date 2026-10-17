# Manual Check: MCP OAuth — Admin Panel UI

End-to-end verification of the **admin-panel frontend** for `auth: {type:
oauth2}` MCP servers (`docs/roadmap/complete/mcp-oauth-admin-panel.md`): the
create/edit form's OAuth 2.0 option, the `oauth_status`/`connection_status`
indicators, the client-secret write-only contract, and atomic mode
switching. `server/admin/admin_panel/tabs/mcp.js` has no automated test
runner in this repo (plain ES modules, no bundler/test harness configured),
so this playbook is what stands in for that coverage.

This phase added **no new OAuth login behavior** — logging in still only
happens via `./bin/orbit.sh mcp login <name>`, exactly as
[`playbook-mcp-oauth-login.md`](playbook-mcp-oauth-login.md) already
exercises. Do that playbook first (at least through step 4, "Log in via the
CLI") if you haven't — this one assumes you already have a configured OAuth
server and a working CLI login to react to, and focuses entirely on what the
admin panel does with that state.

Prerequisites:
- ORBIT running with the admin panel reachable (`http://localhost:3000/admin`),
  signed in as an account with `config.manage` (or equivalent) so the MCP tab
  is editable.
- One real OAuth-capable MCP server to create through the panel — Cloudflare's
  dynamic-registration servers (`playbook-mcp-oauth-login.md` §1) are the
  easiest, since there's no `client_id`/`client_secret` to obtain first. A
  deliberately-unreachable placeholder URL (e.g.
  `https://example.invalid/mcp`) is enough for the parts of this playbook
  that only exercise form behavior, not a live connection.
- The `orbit` CLI available in the same shell/host as the running server (for
  the steps that call `mcp login`/`mcp status` to react to the panel's state,
  and vice versa).

---

## 0. Reference: what the admin panel added

| Surface | New here? |
|---|---|
| MCP servers list row | Credential dot (amber ring = not logged in, solid red = needs re-login) takes over from the plain reachability dot whenever there's a credential problem; a small green "OAuth" pill otherwise |
| MCP server detail header | A status pill (`OAuth ready` / `Not logged in` / `Needs re-login`) next to the transport label |
| MCP server detail body | A colored notice box explaining the credential problem and naming the CLI fix, shown whenever `oauth_status != ready` |
| Tools section | Shows the same credential notice instead of a generic "Could not reach this server" whenever the real cause is the credential, not the network |
| Create/Edit connection form | A "Static headers" / "OAuth 2.0" toggle; OAuth mode exposes Scopes / Client ID / Client secret / Redirect port fields |
| `client_secret` field | Write-only: renders blank with a "leave blank to keep" placeholder when already set, plus an explicit "Remove stored secret" checkbox |
| Switching an existing server off OAuth | A destructive-action confirmation naming that the stored token is deleted permanently |
| Automatic discovery/ping on page load | Skipped for any server whose `oauth_status` is `not_logged_in` or `needs_relogin` — the manual Ping button still works |

Everything else (the actual OAuth handshake, token storage, fingerprint
invalidation, `last_error` semantics) is unchanged backend behavior — see
`playbook-mcp-oauth-login.md` and `docs/roadmap/complete/mcp-oauth-admin-panel.md` for
those.

---

## 1. Create an OAuth server through the panel

1. Open the **MCP** tab, click **Add server** (the `+` icon).
2. Fill in **Name** (e.g. `cloudflare-docs-ui-test`) and leave **Transport**
   as *Streamable HTTP*.
3. Enter the **URL** (e.g. `https://mcp.cloudflare.com/mcp`, or your
   placeholder).
4. Confirm the **Authentication** control defaults to *Static headers*, with
   the Headers editor and a **Test connection** button visible, and Create is
   disabled until a test passes.
5. Click **OAuth 2.0**. Confirm:
   - The Headers editor and Test connection button disappear.
   - Scopes / Client ID / Client secret / Redirect port fields appear
     instead, Redirect port pre-filled `8765`.
   - **Create server** is enabled immediately — no test-connection gate for
     this mode (there's nothing to test before a login exists).
6. Leave Scopes and Client ID blank (dynamic registration), leave Client
   secret blank, and click **Create server**. Confirm:
   - A "created and applied" toast.
   - The new server's detail view opens showing an **OAuth** pill reading
     **Not logged in**, and a notice box below the header saying so with the
     `orbit mcp login <name>` instruction.
   - `config/mcp_clients.yaml` now has an `auth: {type: oauth2, redirect_port:
     8765}` block for this server, no `headers:` key.
7. Confirm via the CLI that it agrees:
   ```bash
   ./bin/orbit.sh mcp status
   ```
   Expect this server listed with **Status: not logged in**, matching the
   panel.

---

## 2. Status indicators react to a real login

Using the server created in §1 (or any existing OAuth server you haven't
logged into yet):

1. In another terminal, log in:
   ```bash
   ./bin/orbit.sh mcp login <name>
   ```
2. Back in the still-open admin panel (don't reload the page), with that
   server's detail pane open, click **Ping server**. Confirm, without a page
   reload:
   - The **OAuth** pill changes from *Not logged in* to **OAuth ready**.
   - The credential notice box disappears.
   - The list row's dot returns to the plain reachability dot (green if the
     ping actually reached the server).

   This proves the ping-triggered refresh (`mcpRefreshServerOauthStatus`)
   updates the indicator in place rather than needing a tab reload — a prior
   defect here left the pill/notice stuck on the pre-login status after a
   manual retry.
3. This step isn't worth asserting on reliably either way: `GET
   /admin/mcp/servers` already returns this server's cached tool discovery
   (from the ping you just ran, or an earlier one), so the panel's warm-up
   has nothing left to fetch and won't send an automatic `GET
   /admin/mcp/tools?server=...` for it regardless of `oauth_status` — the
   no-automatic-ping behavior for a *not-ready* credential (§4) is only
   observable on a server that has never been discovered at all. Skip this
   step; §4 is where that behavior is actually checked.

---

## 3. Precedence: credential problem over generic "unreachable"

This exercises the explicit precedence rule: a credential problem must
always be shown in place of a generic connectivity failure, never alongside
or hidden behind it.

1. With the §1/§2 server now `ready`, force a credential failure without
   touching the network: open `~/.orbit/mcp_oauth/<name>.json` and replace
   the `refresh_token` value with a non-empty garbage string (same technique
   as `playbook-mcp-oauth-login.md` §8's note — don't empty or delete the
   field, or no refresh attempt will be made at all).
2. Back in the panel, click **Ping server** again. Confirm:
   - The pill changes to **Needs re-login** (red).
   - The notice box explains the credential was rejected and names
     `orbit mcp login <name>` as the fix — **not** a generic "Could not
     reach this server" message, even though the ping did in fact fail to
     connect.
   - The Tools section shows the same credential notice, not the plain
     "Could not reach this server" box another unreachable server would show.
3. Confirm the list row also shows the credential-specific red dot, not the
   plain down/unreachable dot.
4. Recover: `./bin/orbit.sh mcp login <name>` again, then Ping once more and
   confirm it returns to **OAuth ready**.

---

## 4. Discovery/ping is skipped for a known-bad credential

1. Use a **newly created, never-discovered** `not_logged_in` server (create
   a fresh one per §1 — don't reuse §2/§3's server here even if you push it
   back to `needs_relogin`, since it already has cached tool discovery from
   an earlier ping, and a server with cached discovery gets no automatic
   ping regardless of credential status — that would pass this check without
   actually exercising the skip gate).
2. Reload the admin panel's MCP tab from scratch with the browser's network
   tab open.
3. Confirm **no** `GET /admin/mcp/tools?server=<that name>` request fires
   automatically on load — the per-row dot should simply read its credential
   state (amber ring / red) without ever flashing "Pinging…".
4. Confirm the server's own row **Ping** button (and the detail pane's Ping
   server button) are still present and functional — click one and confirm
   it dials the server exactly as it would for any other server, this is
   only about the automatic warm-up, not a disabled feature.

---

## 5. Client-secret write-only contract

Use a server configured with a preregistered app (e.g. following
`playbook-mcp-oauth-login.md`'s Google Drive section, or any provider that
takes a `client_secret`) — or just type any non-empty string into Client
secret on a throwaway server for the purposes of this UI check.

1. Create or edit a server, switch to OAuth 2.0, and set a **Client secret**
   (e.g. `test-secret-value`). Save/create.
2. Reopen that server's edit view. Confirm:
   - The Client secret field is **blank**, with placeholder text reading
     something like *"Set — leave blank to keep"* — the real value is never
     echoed back.
   - A **"Remove stored secret"** checkbox is present (only shown once a
     secret is known to be set).
3. Change an unrelated field (e.g. a scope) and Save **without** touching
   Client secret. Confirm:
   - The save succeeds.
   - Reopening the edit view again still shows the "Set — leave blank to
     keep" placeholder — the previously-set secret was preserved, not wiped.
4. Open the browser's network tab, reopen this server's edit view, and
   inspect the `GET /admin/mcp/servers` response body for this server.
   Confirm it contains `"client_secret_set": true` and **no** `client_secret`
   key anywhere with the real value in it.
5. Now check the checkbox **Remove stored secret**, confirm the Client secret
   input disables/clears, and Save. Confirm:
   - The next `GET /admin/mcp/servers` response shows `"client_secret_set":
     false` for this server.
   - `config/mcp_clients.yaml` no longer has a `client_secret` key under this
     server's `auth:` block.

---

## 6. Atomic mode switching, with the deletion warning

Use any server currently in OAuth 2.0 mode with a real stored token (log in
first if needed).

1. Open that server's edit view. Click **Static headers**. Confirm a
   confirmation dialog appears **before anything changes**, stating plainly
   that switching away from OAuth **permanently deletes** the stored
   credentials and that switching back later requires logging in again.
2. Click **Cancel**. Confirm the form is unchanged — still showing the OAuth
   fields, Client secret, etc. — and `~/.orbit/mcp_oauth/<name>.json` still
   exists.
3. Click **Static headers** again, and this time confirm the dialog. Confirm:
   - The form now shows the Headers editor (empty) and Test connection
     button.
   - Save is enabled; add a header (or leave empty) and run Test connection,
     then **Save**.
   - `~/.orbit/mcp_oauth/<name>.json` is now gone (`ls` it, or confirm via
     `./bin/orbit.sh mcp status` no longer listing this server as an OAuth
     server at all).
   - `config/mcp_clients.yaml` shows `headers:` and no `auth:` block for this
     server — inspect the PATCH request in the network tab and confirm it
     was a **single** `PATCH /admin/mcp/servers/<name>` call carrying both
     `headers` and `auth: null`, not two separate requests.
4. Switch it back to OAuth 2.0 (no destructive warning expected this
   direction — confirm none appears), save, and confirm `mcp login <name>`
   is required again (as the earlier warning promised) before it reads
   `ready`.

---

## 7. Form validation guards

These block Create/Save client-side rather than letting the backend's 422
be the only feedback.

1. **Redirect port.** In the OAuth fields, clear Redirect port and type
   `99999`. Confirm the field is visibly marked invalid (and/or an inline
   error on submit) rather than silently being clamped to `65535` — the
   value shown and the value that would be saved must always match. Fix it
   to a valid port (e.g. `8765`) and confirm the error clears.
2. **Scope limits.** In Scopes, paste 40 short space-separated tokens (over
   the 32-scope limit). Confirm Create/Save is rejected client-side with a
   message about the scope count, not sent to the backend to 422. Reduce to
   under 32 and confirm it's accepted. Separately, try one scope over 512
   characters (e.g. `python3 -c "print('a'*600)"`) and confirm the
   per-scope-length message instead.
3. **In-progress edit survives a ping.** With an OAuth server's edit view
   open, type a new value into Scopes or Redirect port **without saving**.
   Note the detail pane's own **Ping server** button is disabled while a
   connection edit is pending (same gate as the static-headers path — it
   won't dial a server config that hasn't been saved), so use the server's
   row in the list on the left instead and click its **Ping** icon there.
   Confirm the field you were editing still shows what you typed (not reset
   to the saved value) — only the pill/notice/tools section should refresh
   from the ping, never the open form fields. This is the regression the
   ping-refresh fix in §2 was specifically checked against clobbering.

---

## 8. Run the automated checks

```bash
/path/to/venv/bin/python -m pytest \
  server/tests/test_routes/test_admin_mcp_connection.py \
  server/tests/test_services/test_mcp_oauth_token_storage.py \
  server/tests/test_services/test_mcp_client_service.py \
  server/tests/test_services/test_mcp_cli_oauth.py \
  -k "auth or oauth" -v
```

These cover everything the panel's requests ultimately rely on — the secret
contract (redaction, merge-on-omit, null-to-delete), fingerprint-based token
invalidation, and `oauth_status`/`connection_status` computation — at the API
layer. There is no automated coverage for `admin_panel/tabs/mcp.js` itself;
§1 through §7 above are what stand in for that.

---

## Troubleshooting

- **The OAuth pill never appears on a server you just created.** Confirm the
  server's `transport` is `http` — OAuth is only offered (and only computed)
  for HTTP servers; a `stdio` server has no `auth:` concept at all.
- **"Not logged in" persists after a successful CLI login, even after
  clicking Ping.** Confirm the CLI and the running server are reading the
  same `config/mcp_clients.yaml` and the same `~/.orbit/mcp_oauth/`
  directory — see the matching entry in `playbook-mcp-oauth-login.md`'s
  Troubleshooting section; this is a CLI/server environment mismatch, not an
  admin-panel bug, if the backend check in that playbook's step 3 also fails.
- **Switching to OAuth 2.0 on an existing headers-based server doesn't show
  a destructive warning.** Expected — only OAuth→headers deletes anything.
  Headers→OAuth has nothing to lose (there was no OAuth token to begin
  with), so it switches immediately without a confirmation dialog.
- **Create is stuck disabled in OAuth mode.** Unlike static headers, OAuth
  mode doesn't require Test connection — if Create still won't enable,
  check the Name field (must be a lowercase slug) and the Redirect port
  field (must be a valid 1–65535 number) for an inline validation error.
