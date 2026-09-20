# Manual/Integration Check: MCP OAuth Login

Steps to verify the `auth: {type: oauth2}` path for outbound MCP servers —
the browser-login alternative to the static `headers:` bearer-token path
used by `docs/adapters/playbook-mcp-tool-loop.md`'s `business-sample`/
`github` examples. See `docs/adapters/mcp-agent.md`'s "OAuth 2.0 servers"
section for the config shape, and `docs/roadmap/mcp-oauth-admin-panel.md`
for what's shipped (CLI-only) versus still admin-panel-only work.

What this feature covers, concretely:

- `server/services/mcp_oauth_token_storage.py` — `FileTokenStorage`, one
  JSON file per server under `~/.orbit/mcp_oauth/<name>.json` (tokens and
  discovered authorization-server metadata always; dynamically-registered
  client info only when the server has no static `client_id` configured —
  a preregistered `client_id`/`client_secret` like Google Drive's is never
  written to this file, it's reconstructed from `config/mcp_clients.yaml`
  on every load via `build_static_client_info`), shared identically by the
  CLI and the running server.
- `server/services/mcp_client_service.py` — `MCPClientManager
  ._build_oauth_provider` wires an `mcp.client.auth.OAuthClientProvider`
  into the HTTP transport, pre-warms it from disk so a session survives a
  restart, and `_find_oauth_error` turns a missing/failed token into a
  clear error pointing at `mcp login`.
- `bin/orbit/commands/mcp.py` — `mcp login`/`mcp status`, the only place the
  actual browser authorization flow runs (a local loopback listener catches
  the redirect; the running server process never pops a browser itself).

This is a real provider integration test, not something a bundled local
test server can fully stand in for — a real OAuth-protected MCP endpoint
and (usually) an app registration in that provider's own console are
needed for the live steps. Unit-level coverage that needs no live provider
is called out separately in step 6.

## 1. Register an OAuth app with a provider (one-time, outside ORBIT)

Pick one of the servers already sketched (commented out) in
`config/mcp_clients.yaml` — Google Drive is the most self-contained to test
against, since Cloudflare/Firecrawl/M365 examples need their own accounts
and app registrations too, but the steps are the same shape for any of
them.

For Google Drive specifically (per Google's own Drive MCP setup guide —
this is currently labeled **Developer Preview** by Google, subject to
change independent of ORBIT):

1. In [Google Cloud Console](https://console.cloud.google.com/apis/credentials),
   enable **both** `drive.googleapis.com` (the Drive API itself) and
   `drivemcp.googleapis.com` (the MCP endpoint) for the project.
2. Configure the OAuth consent screen (scopes, test users if the app is in
   testing mode).
3. Create a **Web application** OAuth client (not Desktop) under
   **Credentials** — Google's Drive MCP setup uses this client type, with an
   explicit `client_secret`, not the Desktop/public-client flow. Note both
   the `client_id` and `client_secret`.
4. Add `http://127.0.0.1:8765/callback` (or whatever `redirect_port` you'll
   use) to that client's **Authorized redirect URIs**.

> If the target provider supports RFC 7591 dynamic client registration,
> steps 3–4 can be skipped entirely — omit `client_id` in the config below
> and `mcp login` will register a client automatically on first use. Google
> does not; a preregistered Web-application `client_id`/`client_secret` pair
> is required for it, per the official setup above.

> **Known current limitation — Google refresh tokens aren't guaranteed.**
> Google only issues a `refresh_token` when the authorization request
> includes its `access_type=offline` parameter, and the installed `mcp` SDK
> has no configurable way to add that (or any other provider-specific
> authorization parameter) to the request it builds. A Google Drive login
> via this flow can succeed and still leave you with only a short-lived
> access token and no way to auto-refresh it — see the "never gets a
> `refresh_token`" entry in Troubleshooting before assuming this playbook's
> automatic-refresh claims apply unconditionally to Google specifically.

## 2. Configure the server (`config/mcp_clients.yaml`)

```yaml
mcp_clients:
  enabled: true
  servers:
    - name: "google-drive"
      transport: "http"
      url: "https://drivemcp.googleapis.com/mcp/v1"
      auth:
        type: "oauth2"
        scopes: ["https://www.googleapis.com/auth/drive"]
        client_id: "${GOOGLE_OAUTH_CLIENT_ID}"
        client_secret: "${GOOGLE_OAUTH_CLIENT_SECRET}"
      enabled: true
```

```bash
export GOOGLE_OAUTH_CLIENT_ID=xxxxxxxx.apps.googleusercontent.com
export GOOGLE_OAUTH_CLIENT_SECRET=xxxxxxxx
```

`headers:` and `auth:` are mutually exclusive on the same server —
`_build_oauth_provider` raises a config error (server startup/reload) if
both are present. Confirm this server has no `headers:` block.

## 3. Confirm there's nothing to log in with yet

```bash
./bin/orbit.sh mcp status
```

Expect a table listing `google-drive` with **Logged in: no**. Running a
chat request that reaches this server now (see step 5's shape, before
logging in) should fail clearly — check the server log for:

```
WARNING - MCP server 'google-drive': OAuth login required or refresh failed (...) — run: ./bin/orbit.sh mcp login google-drive
```

This is `MCPClientManager._find_oauth_error` doing its job: the server
process never tries to pop a browser itself (it was built with no
redirect/callback handler), so a missing token surfaces as this warning
plus a `RuntimeError` instead of hanging or crashing.

## 4. Log in via the CLI

```bash
./bin/orbit.sh mcp login google-drive
```

Confirm:

- A browser window opens to Google's consent screen (or the URL is printed
  to the terminal if a browser couldn't be opened automatically — useful
  over SSH).
- After approving, the terminal reports success:
  `✓ Logged in to 'google-drive'. Token stored; ORBIT will refresh it automatically.`
  (This message is unconditional in the CLI today — it doesn't check
  whether a `refresh_token` was actually issued. For Google specifically,
  per the Known Limitation above, confirm one actually landed before
  trusting this message — inspect `~/.orbit/mcp_oauth/google-drive.json`
  for a non-empty `tokens.refresh_token` field, or see the matching
  Troubleshooting entry below.)
- `~/.orbit/mcp_oauth/google-drive.json` now exists, mode `0600`.
- `./bin/orbit.sh mcp status` now shows **Logged in: yes**.

If the browser redirects before the CLI's loopback listener is ready (rare,
usually only with an already-active browser session completing the consent
screen instantly), the listener is bound *before* the browser is opened
specifically to avoid this race — if you do hit a connection-refused error
here, that's worth filing rather than retrying past it.

## 5. Trigger a live tool call through the OAuth-authenticated server

Add `"google-drive"` to an adapter's `mcp_servers` allowlist (either the
explicit `mcp-agent-chat` adapter or an opportunistic-mode adapter — see
`docs/adapters/mcp-agent.md`), then:

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <key for an adapter that can reach google-drive>" \
  -H "X-Session-ID: oauth-test-1" \
  -d '{
    "messages": [
      {"role": "user", "content": "List the files in my Google Drive."}
    ],
    "skill": "mcp-agent"
  }'
```

Confirm the response reflects real Drive contents and `sources` contains a
`google-drive__<tool>` entry — no manual token ever appears anywhere in the
request; the `Authorization` header is attached transparently by
`OAuthClientProvider` inside the HTTP transport.

## 6. Unit tests (no live provider needed)

```bash
/path/to/venv/bin/python -m pytest \
  server/tests/test_services/test_mcp_oauth_token_storage.py \
  server/tests/test_services/test_mcp_cli_oauth.py \
  server/tests/test_services/test_mcp_client_service.py \
  server/tests/test_routes/test_admin_mcp_connection.py \
  -k "auth" -v
```

These cover token/client-info/metadata round-tripping and file permissions
(`test_mcp_oauth_token_storage.py`), static `client_id` surviving the SDK's
lazy `_initialize()` on the first request plus `${VAR}` expansion in the
CLI (`test_mcp_cli_oauth.py`), provider construction and the
`BaseExceptionGroup`-unwrapping in `_find_oauth_error`
(`test_mcp_client_service.py`), and the admin API's config validation/
mutual-exclusion/YAML-patching for the `auth:` block
(`test_admin_mcp_connection.py`) — all without a live OAuth provider.

## 7. Confirm restart survives (token pre-warm)

```bash
./bin/orbit.sh restart
```

Repeat step 5's request without running `mcp login` again. Confirm it still
succeeds — `_build_oauth_provider` pre-warms the provider's in-memory state
(token, expiry, client info, discovered authorization-server metadata)
straight from `~/.orbit/mcp_oauth/google-drive.json` on the new process,
rather than starting cold. This is the regression `expires_in` being
relative-to-issuance (not absolute) exists to guard against — a token that
looked "still valid" by a naive re-read would otherwise be used past its
real expiry, or treated as needing a fresh login when it didn't.

## 8. Confirm a revoked/expired refresh token surfaces clearly

> **Timing note.** Google documents that revocation invalidates the issued
> access and refresh tokens, but propagation isn't instant — an immediate
> request right after revoking may still succeed while that takes effect,
> which is not a failure of this check, just timing. If you don't want to
> depend on that propagation window, edit
> `~/.orbit/mcp_oauth/google-drive.json` directly and replace the
> `refresh_token` value with a non-empty garbage string (don't delete the
> field or set it empty — `OAuthClientProvider.can_refresh_token()` requires
> a truthy `refresh_token` to even attempt a refresh; an empty/missing one
> skips straight to a full re-authorization attempt instead of exercising
> the server-side rejection this step is meant to check).

Revoke the app's access from your Google Account's
[connected apps](https://myaccount.google.com/permissions) page (or edit the
token file per the note above), then repeat step 5's request — possibly
more than once if revocation hasn't propagated yet. Confirm:

- The tool call fails, and the server log shows the same
  `"OAuth login required or refresh failed"` warning from step 3 — now for
  a *revoked* token rather than a *missing* one, but with the same
  actionable message.
- `mcp login google-drive` again (step 4) recovers it, and step 5's request
  succeeds again with no other changes.

## Troubleshooting

- **`mcp login` reports "Server '<name>' has no auth: {type: oauth2} block
  configured — nothing to log in for"**: the server in `mcp_clients.yaml`
  either doesn't exist under that name, or is still using `headers:`
  instead of `auth:`. Check `--config` points at the right file if not
  using the default `config/mcp_clients.yaml`.
- **Browser opens but the redirect fails / "invalid redirect_uri"**: the
  provider's app registration doesn't list
  `http://127.0.0.1:<redirect_port>/callback` (default port `8765`) as an
  authorized redirect URI, or `redirect_port` in the `auth:` block doesn't
  match what was registered. Use `--port` on `mcp login` or set
  `redirect_port` in config to match the registration, not the other way
  around — provider consoles don't accept wildcard loopback ports for every
  provider.
- **`mcp login` succeeds but the server still logs "requires OAuth login"
  afterward**: confirm the CLI and the running server are reading the same
  `config/mcp_clients.yaml` (matching `client_id`/`scopes`/`redirect_port`)
  and that both have access to the same `~/.orbit/mcp_oauth/` directory —
  e.g. running the CLI as a different user/home directory than the server
  process writes two different token files that never see each other.
- **`OAuthRegistrationError` / dynamic registration fails**: the provider
  doesn't support RFC 7591 dynamic client registration for this endpoint —
  a preregistered `client_id` (step 1) is required; there's no way around
  registering one in the provider's own console first.
- **`google-drive` (or any provider requiring `access_type=offline`) logs in
  successfully but never gets a `refresh_token`**: check
  `~/.orbit/mcp_oauth/<name>.json` for a `refresh_token` field after login.
  Google specifically only issues one when the authorization request
  includes `access_type=offline` (its own OAuth extension, distinct from
  the generic OIDC `offline_access` scope). **This is a current ORBIT/SDK
  limitation, not just a provider-side setting you missed**: the installed
  `mcp` SDK's authorization-request builder only adds `prompt=consent` when
  `offline_access` is present in `scope`, and has no configurable mechanism
  to add `access_type=offline` or other provider-specific authorization
  parameters (`mcp/client/auth/oauth2.py`,
  `_perform_authorization_code_grant`). Until ORBIT exposes a way to pass
  extra authorization parameters through to the SDK (or the SDK adds
  Google-specific offline-access support upstream), a Google Drive login via
  this flow may only ever get a short-lived access token with no
  `refresh_token` to auto-refresh once it expires — re-running `mcp login`
  is the only recovery in that case, not a config change here.
- **Admin panel doesn't show OAuth login status**: expected — this is
  CLI-only today. See `docs/roadmap/mcp-oauth-admin-panel.md` for the
  tracked follow-up work.
