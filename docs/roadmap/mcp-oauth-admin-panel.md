# MCP OAuth — Admin Panel Support

## Summary

Outbound MCP servers that require browser-based OAuth (Google Drive,
Cloudflare, Firecrawl, Microsoft 365, and similar) are supported via an
`auth: {type: oauth2}` block in `config/mcp_clients.yaml`, alongside the
existing static-bearer-token `headers:` path. Login is CLI-only today
(`./bin/orbit.sh mcp login <name>` / `mcp status`) — see "Shipped" below.
Backend config validation/YAML-patching/serialization for `auth:` is also
already shipped. What's left: a credential-status model with somewhere real
to record a failure (none exists today), token lifecycle safety when config
changes, secret handling in the admin API, and the frontend editor/status UI.

## Shipped (for reference — no longer tracked here)

- **Token storage**: `server/services/mcp_oauth_token_storage.py`
  (`FileTokenStorage`) — one JSON file per server under
  `~/.orbit/mcp_oauth/<name>.json` (0600 perms, atomic write), satisfying the
  `mcp.client.auth.oauth2.TokenStorage` protocol, plus non-protocol
  extensions used by ORBIT: `get_token_expiry`/`get_oauth_metadata` (restore
  real expiry and the discovered authorization-server metadata across
  restarts) and the module-level `build_static_client_info` helper (skip
  RFC 7591 dynamic client registration when `auth.client_id` is configured).
  Shared identically by the running server and the CLI.
- **Config schema**: `auth: {type: oauth2, scopes, client_id?, client_secret?,
  redirect_port?}` on an HTTP server entry in `config/mcp_clients.yaml`,
  mutually exclusive with `headers:`. No `authorization_endpoint`/
  `token_endpoint` keys needed — `mcp.client.auth.OAuthClientProvider`
  already does RFC 9728/8414 discovery.
- **Connection wiring**: `MCPClientManager._build_oauth_provider` /
  `_create_connection` (`server/services/mcp_client_service.py`) — builds the
  provider with no redirect/callback handler, pre-warms it from disk
  (tokens, expiry, client info, authorization-server metadata) so a restored
  session survives a process restart, and turns a missing/refresh-failed
  token into a clear `RuntimeError` + WARNING log via `_find_oauth_error`
  (which also unwraps the `BaseExceptionGroup` `streamable_http_client`'s
  anyio task group can wrap it in).
- **CLI**: `bin/orbit/commands/mcp.py` (`MCPLoginCommand`, `MCPStatusCommand`),
  wired into `bin/orbit/cli.py`'s `_add_mcp_commands`. Local-filesystem-only
  (reads `config/mcp_clients.yaml`, writes `~/.orbit/mcp_oauth/`) — no admin
  API surface for "run a loopback OAuth flow from the CLI process." Expands
  `${VAR}` references in `auth.client_id`/`client_secret` itself
  (`_load_server_config` is a raw `yaml.safe_load`, unlike the server's own
  config loading).
- **Admin API — config CRUD for `auth:`** (`server/routes/admin/mcp.py`):
  `_validate_mcp_auth`, mutual-exclusion validation against the *resulting*
  state in `_validate_mcp_connection`, `_patch_yaml_auth` +
  `_render_yaml_scalar_or_list` (YAML-preserving write, keeps `redirect_port`
  an int and `scopes` a real list), wired into `_insert_mcp_server` (create)
  and `update_mcp_server`'s nested-field patch loop (update), and
  `list_mcp_servers`'s per-server `connection.auth` field (currently the
  **full unredacted config**, including a literal `client_secret` if one is
  set — see "Secret contract" below, this is a gap to close).
- **Tests**: `server/tests/test_services/test_mcp_oauth_token_storage.py`,
  `test_mcp_client_service.py` (`TestBuildOAuthProvider`,
  `TestFindOAuthError`), `test_mcp_cli_oauth.py`, and
  `test_admin_mcp_connection.py` (`TestValidateMcpConnectionAuth`,
  `TestValidateMcpConnectionMutualExclusion`, `TestPatchYamlAuth`, plus
  create/update integration tests for `auth:`).

## Remaining work

### 1. Two separate status fields — credentials vs. connectivity

Credential validity and reachability are independent and must not be
conflated into one enum: a server can have a perfectly good token and still
be unreachable (network/DNS), or have a revoked refresh token on an
otherwise-reachable server. They also come from different places — the CLI
never talks to the running server or its circuit breaker, so it can only
ever know about credentials, never reachability.

- **`oauth_status`** (both CLI and admin panel report this, and must agree
  — see "`last_error` semantics" below for exactly how each value is
  computed):
  - `not_configured` — no `auth:` block (not an OAuth server).
  - `not_logged_in` — `auth:` configured, no token file at all, and no
    `last_error` recorded (i.e. genuinely never attempted).
  - `ready` — a token is stored, valid for the server's *current* config
    (see "Token lifecycle"), and no `last_error` is recorded. (Access-token
    expiry isn't its own state: refresh is transparent and automatic — see
    `_build_oauth_provider` — so an expired-but-refreshable access token
    still reads `ready`.)
  - `needs_relogin` — **a recorded credential failure exists**, full stop,
    regardless of whether any token fields still happen to be present in
    the file. This single definition covers both a rejected/revoked refresh
    token (`refresh_rejected`) and a stored token that no longer matches the
    server's current config (`fingerprint_mismatch`) — see "Token lifecycle"
    for why those two cases are collapsed into one `oauth_status` value with
    two distinct underlying `last_error` codes, rather than one meaning
    `not_logged_in` and the other `needs_relogin` as an earlier draft of
    this doc had it.
- **`connection_status`** (server/admin panel only — the CLI has no way to
  determine this locally):
  - `not_checked` — no connection attempt observed yet this process.
  - `reachable` — last attempt succeeded
    (`ServerConnectionPool.is_reachable()`/breaker closed).
  - `unreachable` — last attempt failed, **for any reason**, OAuth or not.
    `ServerConnectionPool`'s circuit breaker trips on every failed `build()`
    call regardless of cause (`server/services/mcp_connection_pool.py`), so
    it cannot itself distinguish "network down" from "OAuth rejected" — and
    this doc doesn't ask it to. `connection_status: unreachable` only ever
    means "the last attempt failed"; **`oauth_status` is the authoritative
    signal for whether that failure was a credential problem.** The admin
    panel's rendering must reflect this precedence explicitly (see Task
    list below) — never show a bare "Unreachable — check network"
    message when `oauth_status` is `needs_relogin`; show the
    credential-specific message instead. Introducing a second, typed
    "last failure reason" purely to keep `connection_status` "clean" would
    duplicate what `last_error` already records — not worth the extra
    state to maintain.

`list_mcp_servers` computes and returns both fields for `auth.type ==
"oauth2"` servers. This is separate from `_serialize_mcp_tools`, which only
serializes cached tool schemas and has no role in this work — don't touch it
for this.

### 2. Token lifecycle safety on configuration changes

`FileTokenStorage` is keyed only by server *name*. If an admin changes a
server's `url`, swaps its `client_id`, changes `scopes`, or changes
`redirect_port`, the old stored token is currently still loaded and used
as-is — a bearer token (or a dynamically-registered client, which RFC 7591
ties to the exact `redirect_uri` it registered) minted for one
endpoint/grant/redirect combination can end up reused against a different
one.

**Fingerprint.** A canonical, versioned fingerprint of the identity a stored
token/client registration is valid for:

```python
# server/services/mcp_oauth_token_storage.py
def compute_fingerprint(url: str, client_id: str | None, scopes: list[str], redirect_port: int) -> str:
    payload = {
        "v": 1,  # bump on any change to this shape; a version mismatch is
                 # itself treated as "no match" (see legacy handling below)
        "url": url,
        "client_id": client_id or "",
        "scopes": sorted(scopes),
        "redirect_port": redirect_port,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
```

`redirect_port` is included: it determines the effective
`redirect_uri` (`http://127.0.0.1:<port>/callback`), which a dynamically
registered client (no static `client_id` configured) is bound to by the
authorization server. `url`, `client_id`, and `scopes` are included for the
reasons already given above.

**Where the fingerprint is computed and passed in.** The `mcp.client.auth`
SDK calls `TokenStorage.set_tokens(tokens)` with only the token — it has no
notion of ORBIT's fingerprint, so `set_tokens` can't take it as a parameter
without breaking the protocol. Instead, `FileTokenStorage.__init__` gains an
optional `fingerprint: str | None` argument; both `_build_oauth_provider`
and `MCPLoginCommand._login` compute it from the server's current `auth:`
config and pass it in when constructing `FileTokenStorage(server_name,
fingerprint=...)`. `set_tokens`/`set_client_info` then write
`self._fingerprint` into the file alongside whatever they're storing —
sourced from constructor context, not the SDK call.

**On every load** (`_build_oauth_provider`'s pre-warm, and `mcp
login`/`mcp status`): recompute the fingerprint from the server's *current*
config and compare against what's stored.
- **Match** → use the stored token normally; `oauth_status` follows the
  normal `ready`/`needs_relogin` rules from `last_error`.
- **Mismatch (including a file with no fingerprint at all — see "Legacy
  files" below)** → the stored credentials are for a different identity and
  must not be used. Clear the credential fields (`tokens`, `client_info`)
  from the file, but **do not delete the file**, and record
  `last_error: {code: "fingerprint_mismatch", at: <timestamp>}` in it. This
  makes `oauth_status` read `needs_relogin` — not `not_logged_in` — because
  `needs_relogin` is defined above as "a recorded credential failure
  exists," which this is: there *was* a credential, it's just no longer
  valid for the current config. `not_logged_in` stays reserved for "this
  server has never had a token at all." Log the mismatch at WARNING so it's
  not a silent credential loss.

**Legacy files with no fingerprint.** Any token file written before this
fingerprint mechanism existed (i.e. everything shipped so far in this
feature, prior to this section landing) has no fingerprint field. Treat a
missing fingerprint exactly like a mismatch — conservative invalidation, not
a crash or a silent pass-through — going through the same clear-credentials
+ `fingerprint_mismatch` path above, with a WARNING log calling out that
this was a pre-fingerprint file specifically (distinct wording from an
ordinary mismatch, so an admin isn't confused into thinking their config
just changed when actually this is a one-time migration side effect).

**Server deleted, or auth mode switched away from OAuth entirely**
(`DELETE /mcp/servers/{name}`, or `auth:` replaced by `headers:` /
removed via update): unlike an in-place identity-relevant edit above, this
is not a "maybe I'll switch back to the same config" situation — the
`auth:` block is gone, so there's no fingerprint to preserve a tombstone
against, and continuing to hold the token file serves no purpose but risk.
**Delete the token file outright** as part of that operation (both the
admin API route and the CLI, wherever each can trigger it). The admin
panel's mode-switch UI must warn about this plainly before the switch: something like *"Switching away from OAuth will permanently delete the
stored credentials for this server. Switching back to OAuth later will
require logging in again."* — not the earlier ("credentials might be
silently reused later") framing, which described the opposite of the
behavior this section actually specifies.

### 3. `last_error` — precise semantics

- **Classification is state-based, not string-based.** `_find_oauth_error`
  finds *that* an `OAuthFlowError` occurred, not *why* — don't infer the
  reason from the exception message. `_create_connection` already knows,
  immediately before it builds the provider, whether a stored token existed
  for this server at all. Combined with the fingerprint check in "Token
  lifecycle," there are exactly three cases that can produce a `last_error`,
  each with its own bounded code:
  - No token existed at all → **not an error to record.** This is the
    ordinary `not_logged_in` case (see below).
  - A token existed, matched the current fingerprint, but the connection
    attempt still failed for an OAuth reason (refresh rejected/revoked) →
    `last_error: {code: "refresh_rejected", at: ...}`.
  - A token existed but didn't match the current fingerprint (config
    changed, or a legacy pre-fingerprint file) → `last_error: {code:
    "fingerprint_mismatch", at: ...}`, written at load time per "Token
    lifecycle," not at connection-attempt time.
- **Never persist a `last_error` for the "no token, no prior error" case.**
  Recording anything to disk here would create
  `~/.orbit/mcp_oauth/<name>.json` for a server nobody has ever logged into,
  breaking the intended meaning of "no token file, no `last_error`" =
  `not_logged_in`.
- **Store only the bounded code + timestamp — never the raw exception
  message.** It may echo back provider response bodies, which can include
  detail not appropriate to store unredacted on disk or return from an
  admin API.
- **Clear `last_error` only after a real successful connection**, i.e. once
  `_create_connection`'s `session.initialize()` actually returns — never
  during `_build_oauth_provider`'s pre-warm. Loading a token from disk
  proves nothing about whether it still works; only a completed handshake
  does.
- **Precedence when a later failure is non-OAuth.** A non-OAuth failure
  (network/DNS/unrelated non-2xx) must **not** touch `last_error` or
  `oauth_status` at all — see "Two separate status fields" above for how
  this is reflected purely in `connection_status` instead. An existing
  `needs_relogin` must survive an unrelated network blip; a working
  credential must not be reported as broken just because the server was
  briefly unreachable for an unrelated reason.

**Tasks:**
- [ ] Add `compute_fingerprint`, and `last_error`/fingerprint get-set, to
      `FileTokenStorage`; accept `fingerprint` as a constructor argument.
- [ ] Update `_build_oauth_provider`'s pre-warm to: compute the current
      fingerprint, compare against the stored one, and run the
      clear-credentials + `fingerprint_mismatch` path on any mismatch
      (including a missing/legacy fingerprint) before doing anything else.
- [ ] Update `_create_connection` to: check token existence up front (for
      classification), record `last_error: refresh_rejected` only in the
      "token existed, matched, still failed" case, and clear `last_error`
      only on a successful `session.initialize()`.
- [ ] Update `MCPStatusCommand` (CLI) and `MCPLoginCommand` (on successful
      login: clear `last_error`, write the current fingerprint) to use this
      same logic — the CLI currently only checks token presence and
      displays the token's original `expires_in` at issuance, not current
      validity or any recorded failure.
- [ ] Extend `list_mcp_servers` to return `oauth_status` (per the state
      table above) and `connection_status` (breaker-derived, see "Two
      separate status fields") as two separate fields per OAuth-configured
      server.
- [ ] Wire token-file deletion into `DELETE /mcp/servers/{name}` and into
      `update_mcp_server` whenever an update changes a server's `auth:`
      block from set to absent/replaced-by-headers (per "Token lifecycle").
- [ ] Frontend: render `oauth_status` and `connection_status` as separate
      indicators, with `oauth_status` taking rendering precedence for the
      failure message whenever both indicate a problem.
- [ ] Skip automatic discovery/ping for servers whose `oauth_status` is
      `not_logged_in` or `needs_relogin` when the panel loads or the MCP tab
      opens — pinging a server known to have no usable credentials just
      produces a predictable, noisy failure on every page load.
      `list_mcp_servers` already treats an undiscovered server specially
      (status `None` until first discovered/pinged); extend that gate to
      cover these two `oauth_status` values explicitly.
- [ ] Decide whether `needs_relogin` should also surface as a general
      admin-panel notification/badge, not just inline on the MCP servers
      page — check for an existing "needs attention" affordance (adapter/
      datasource health checks) to reuse before adding a new one.

### 4. Admin panel: create/edit an `auth:` block

Backend validation, mutual exclusion, and YAML patching for the config shape
itself are done (see "Shipped"). Two more pieces of backend work are needed
specifically to support the secret contract below (they don't exist yet —
this isn't just a frontend task), plus the frontend form.

**Secret contract** for `client_secret` (exact API shape — applies to every
response that can include it: create, update/reload, and error payloads,
not just `list_mcp_servers`):
- Reads (`list_mcp_servers`, and the response body of a successful
  create/update) return `client_secret_set: true`/`false` — **never** the
  literal `client_secret` value, at any point.
- Update: omitting `client_secret` from the payload **preserves** the
  currently-stored value unchanged.
- Update: `client_secret: null` explicitly **removes** it (server becomes a
  public/PKCE-only OAuth client).
- Create: there is nothing to preserve yet, so "omit to preserve" doesn't
  apply — omitting it on create simply means "no secret," identical to an
  explicit `null`.
- `headers:` values have the same raw-value exposure today (`Authorization`
  is returned unredacted) — a pre-existing, separate gap. Note it, don't fix
  it here: headers conventionally hold `${VAR}` references while
  `client_secret` has no such existing convention forcing that, so the
  exposure risk isn't equivalent.

**This contract needs real backend changes, not just response filtering:**
- `_validate_mcp_auth` currently rejects `client_secret: null` outright
  (`isinstance(value, str)` fails for `None`) — it must special-case `None`
  as the explicit-deletion signal for that one field, distinct from the key
  being absent.
- `_patch_yaml_auth` replaces the entire `auth:` block with whatever dict
  it's given — it has no merge semantics. "Omit `client_secret` to
  preserve it" therefore cannot be implemented inside the patcher; the
  *route* (`update_mcp_server`) must merge an omitted `client_secret` in
  from the existing on-disk entry into the dict it hands to
  `_validate_mcp_auth`/`_patch_yaml_auth`, before either runs. (This mirrors
  how `headers:`/`env:` are already documented as full-replace, not diffed —
  `client_secret` needs the opposite default specifically because it's a
  write-only secret an admin can't be expected to retype on every edit.)
- The create route's response currently returns the full `entry` dict
  verbatim (`return {"message": ..., "server": entry, ...}`) — this must be
  redacted to `client_secret_set` the same as `list_mcp_servers`, along with
  any other response path that can echo back a server's `auth:` block.

**Tasks:**
- [ ] Backend: `_validate_mcp_auth` accepts `client_secret: null` as deletion.
- [ ] Backend: `update_mcp_server` merges an omitted `client_secret` from the
      existing entry before validation/patching.
- [ ] Backend: redact `client_secret` to `client_secret_set` in every
      response that can include a server's `auth:` block (create, update,
      list) — not just `list_mcp_servers`.
- [ ] Frontend: add an "OAuth 2.0" option alongside the existing
      bearer-token header form, with fields for scopes / client id / client
      secret / redirect port, mutually exclusive with the headers form in
      the UI. The client-secret field renders empty with a "leave blank to
      keep the current value" hint when `client_secret_set: true`, per the
      contract above.
- [ ] **Atomic mode switching — send both fields in one request.** The
      backend's mutual-exclusion check looks at the *resulting* state
      (existing entry + this payload), so two sequential calls (clear
      headers, then separately set auth) would not necessarily be *rejected*
      by that check — but it would leave a real, if brief, window where the
      server entry has **neither** `headers:` nor `auth:`, i.e. an
      unauthenticated connection config a concurrent tool call could hit.
      That's the reason for atomicity, not a validation failure:
      - Headers → OAuth: send `headers: {}` **and** the new `auth` object in
        one update call.
      - OAuth → Headers: send `auth: null` **and** the new `headers` object
        in one call — and per "Token lifecycle," this also deletes the
        stored token file server-side. Warn before the switch, per the
        exact wording given there.

### 5. Out of scope (deliberate, not because it's technically impossible)

- **Admin panel does not run the browser OAuth login flow itself.** This is
  a deployment/security choice — a server-side OAuth callback route the
  admin's browser round-trips through is technically buildable (the admin
  API already runs in the same process as everything else). Deferred
  because: (a) it needs a stable callback URL reachable by whatever browser
  the admin is using, which may not be the ORBIT host itself; (b) the CLI
  flow already covers one-time setup cleanly via a local loopback listener
  that never needs to be exposed; (c) it adds a second, admin-panel-specific
  OAuth callback surface to secure and maintain for marginal benefit over
  the CLI. Revisit if there's a concrete operational need (e.g. admins who
  never have shell access to the ORBIT host).
- **Per-end-user OAuth** (each chat user connecting their own account) is
  out of scope. Current design is admin-driven, one-time setup per server,
  matching how `github`/`business-sample`'s static bearer tokens work today.

## Acceptance criteria for this work

- [ ] Create an OAuth-configured server through the admin panel; verify the
      resulting YAML and that CLI `mcp status` agrees with the panel's
      `oauth_status`.
- [ ] Edit an existing OAuth server's `scopes`/`client_id`/`redirect_port`
      through the panel; verify only the `auth:` block changes on disk, and
      that the *next load* invalidates the old credential (fingerprint
      mismatch): `oauth_status` reads `needs_relogin` with `last_error.code
      == "fingerprint_mismatch"`, the token file still exists but its
      credential fields are cleared, and it is **not** deleted.
- [ ] A legacy token file with no fingerprint field is treated as a
      mismatch on load (same outcome as above) rather than trusted or
      crashing the load.
- [ ] Switch a server from `headers:` to `auth:` and back; verify each
      switch is a single atomic request (no intermediate unauthenticated
      window), that the UI's deletion warning appears before an OAuth→
      headers switch, and that the token file is actually deleted once that
      switch completes.
- [ ] Delete an OAuth server's config entirely; verify the stored token file
      is deleted.
- [ ] No API response (create, update, reload/error payloads, list) ever
      contains a literal `client_secret` — only `client_secret_set`.
      Omitting `client_secret` on update preserves the stored value;
      `client_secret: null` removes it; creating without one sets
      `client_secret_set: false`.
- [ ] `oauth_status` and `connection_status` render as separate, independent
      indicators in the panel, and `mcp status` (CLI) agrees with the
      panel's `oauth_status` for the same server. When both indicate a
      problem, the panel shows the `oauth_status`-specific message, not a
      generic "unreachable" one.
- [ ] A rejected/revoked refresh token transitions the server from `ready`
      to `needs_relogin` (`last_error.code == "refresh_rejected"`) **on the
      next real connection/tool-call attempt** against that server — there
      is no background polling or scheduled refresh job, so this is only
      observed the next time something actually tries to use the server
      (a tool call, a discovery refresh, or a manual ping).
- [ ] Running `mcp login <name>` again after `needs_relogin` (either cause)
      clears `last_error`, writes the current fingerprint, and restores
      `ready` on both the CLI and the panel.
- [ ] Opening the MCP servers tab does not itself trigger an OAuth attempt
      for a `not_logged_in` or `needs_relogin` server.
- [ ] A non-OAuth failure (simulate: point the server at an unreachable
      host) sets `connection_status: unreachable` without changing an
      existing `needs_relogin`/`ready` `oauth_status`.
