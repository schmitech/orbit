# Allowed MCP Servers — Picker for the Adapter Create Form

## Summary

`capabilities.mcp_tools` (opportunistic MCP tool calling) and
`capabilities.mcp_servers` (the allowlist scoping which servers' tools are
offered) are both create-form questions today on the `passthrough` and
`multimodal` specs (`server/adapter_sdk/specs.py`), but they're disconnected
from each other and from reality:

- `mcp_servers` is a free-text comma-separated `<input>` — the same pattern
  `available_skills` used before the skills picker (see `createMultiCheckboxList`
  / `adapter-chip-picker` in `server/admin/admin_panel/tabs/adapters.js`) — so an
  admin has to already know exact MCP server names defined in
  `config/mcp_clients.yaml`.
- The two fields aren't gated: `mcp_servers` is editable even when `mcp_tools`
  is off, which is meaningless — the allowlist only matters once opportunistic
  tool calling is enabled (an empty/omitted `mcp_servers` already means "all
  enabled servers" per `docs/adapters/mcp-agent.md`).

This roadmap replaces the free-text `mcp_servers` input with the same
chip-toggle picker built for skills, scanned from the servers actually
usable for **opportunistic** tool calling, and makes it follow `mcp_tools`'
on/off state in the form.

**Scope.** This roadmap covers only the opportunistic-calling pair
(`mcp_tools`/`mcp_servers` on the `passthrough` and `multimodal` specs). The
`mcp-agent` spec (`server/adapter_sdk/specs.py:387`) also has an `mcp_servers`
question, but it is a structurally different field: mcp-agent has no
`mcp_tools` toggle at all — the adapter *is* a dedicated tool-calling agent,
its allowlist is always active, and (per
`server/services/mcp_client_service.py`'s `_OVERRIDABLE["allow_opportunistic"]`
comment) is "governed only by the global `enabled` flag," not
`allow_opportunistic` — a server with `allow_opportunistic: false` is still
usable by mcp-agent. Giving it a picker is a reasonable, much smaller
follow-up (Phase 4 below, explicitly optional and separate) — it reuses the
scan but with a different, simpler filter and no gating behavior. Nothing in
Phases 1-3 touches the `mcp-agent` spec.

Reference: `docs/adapters/mcp-agent.md` (capability semantics),
`server/admin/admin_panel/tabs/mcp.js` + `server/routes/admin/mcp.py`
(existing MCP server admin surface, separate router/auth from the adapter
create form).

---

## Phase 0 — Generalize the picker's empty-state message

`createMultiCheckboxList` (`server/admin/admin_panel/tabs/adapters.js:384`)
hardcodes "No skills configured yet — add capabilities.expose_as_skill: true
to an adapter to offer it here." for every `q.multi` question — fine when it
had exactly one caller, wrong once `mcp_servers` becomes a second.

- Add an optional `empty_message: str | None` field to `Question`
  (`server/adapter_sdk/specs.py`) alongside `multi`/`options_source`.
- `available_skills`/`auto_routable_skills`: keep the existing skills message
  via `empty_message="No skills configured yet — add capabilities.expose_as_skill: true to an adapter to offer it here."`
- `mcp_servers` (Phase 2, once it exists as a `multi` question): set
  `empty_message="No MCP servers are enabled for opportunistic tool calling — see config/mcp_clients.yaml."`
- `createMultiCheckboxList`: fall back to a generic
  `"No options configured yet."` when a question sets neither, so a future
  third `multi` field doesn't silently inherit someone else's wording either.
- Do this phase first (it's a pure refactor, no new data source yet) so Phase
  1/2 land with the right message already in place instead of a follow-up fix.

## Phase 1 — Scan opportunistic-eligible MCP servers into `answer-options`

Mirror `_available_skill_options()` (`server/routes/admin/adapters.py`,
`GET /admin/adapters/answer-options`) with a new
`_available_mcp_server_options(config)` — but the eligibility check has three
gates, not one, because a server can be "configured and enabled" yet still be
unusable for *opportunistic* calling specifically:

1. **Global gate**: `config.get("mcp_clients", {}).get("enabled")` must be
   true. If MCP is globally disabled, return `[]` — don't list servers that
   can't be reached regardless of per-server settings.
2. **Per-server `enabled`**: `server.get("enabled", True)` — matches
   `MCPClientManager.__init__`'s own `{s["name"]: s for s in servers_list if
   s.get("enabled", True)}` filter (`server/services/mcp_client_service.py:156`).
3. **Effective `allow_opportunistic`**: `allow_opportunistic` is overridable
   per server, falling back to the `mcp_clients`-level default
   (`mcp_client_service.py`'s `_OVERRIDABLE`/`setting()` resolution,
   `config/mcp_clients.yaml:50`'s top-level `allow_opportunistic: false`).
   Resolve it the same way: `server.get("allow_opportunistic", config["mcp_clients"].get("allow_opportunistic", False))`.
   Only include the server if this resolves to `true` — this is the gate that
   actually determines whether `llm_inference.py`'s opportunistic path
   (`get_all_tools(..., opportunistic_only=True)`) will ever surface the
   server's tools, per `MCPClientManager.get_all_tools`/`opportunistic_servers`.

Implementation note: don't reimplement `setting()`'s full resolution (it also
handles `tool_timeout`, `pool_size`, etc. — out of scope here); a local
two-line fallback for just `allow_opportunistic` is enough and keeps this
function free of a runtime-manager dependency, consistent with
`_available_skill_options()` reading straight from `app.state.config`.

- Return `{"value": name, "label": name, "description": ""}` per eligible
  server (no server-level "description" field exists in
  `config/mcp_clients.yaml` today; leave blank rather than inventing one).
- Add `"mcp_servers": _available_mcp_server_options(config)` to the
  `answer-options` response dict.
- Tests (extend `server/tests/test_routes/test_admin_adapter_create.py`,
  alongside the existing `test_answer_options_*` skills tests):
  - global `mcp_clients.enabled: false` → `[]` even with enabled, opportunistic servers present.
  - per-server `enabled: false` → excluded.
  - per-server `allow_opportunistic: false` (with global default `true`) → excluded.
  - per-server omits `allow_opportunistic`, global default `true` → included (inherits default).
  - per-server `allow_opportunistic: true` overriding a global default of `false` → included.

## Phase 2 — Reuse the chip picker for `mcp_servers`

- `server/adapter_sdk/specs.py`: change
  `Question("mcp_servers", "Allowed MCP servers (blank = all enabled)", type="list", default=[])`
  to add `options_source="mcp_servers", multi=True,
  empty_message="No MCP servers are enabled for opportunistic tool calling — see config/mcp_clients.yaml."`
  on both the `passthrough` and `multimodal` specs — no new frontend widget
  code needed beyond Phase 0's `empty_message` plumbing, since
  `createMultiCheckboxList`/`makeQuestionInput`/`adapterQuestionField`/
  `readAnswer`/`applyDefault` already branch generically on `q.multi` (added
  for skills) rather than on a hardcoded field name.
- Update the question's help text: add
  `help="Leave empty to allow all servers enabled for opportunistic calling."`
  so the existing `questionHint()`/`q.help` line in `adapters.js` carries this
  field-specific meaning (an empty selection means "all", not "none") without
  new per-widget text logic.
- Tests: extend the preview/create tests in `test_admin_adapter_create.py` to
  confirm an `mcp_servers` selection round-trips through both Jinja templates
  unchanged — verify, don't assume, since Phase 3 below changes what actually
  reaches the template. Set `mcp_tools=True` in these tests: `passthrough.yaml.j2`
  already nests `mcp_servers` under `{%- if mcp_tools %}` (see Phase 3a), so a
  selection cannot round-trip through that template with `mcp_tools` at its
  default (`False`) — that's exactly the case Phase 3 covers instead.

## Phase 3 — Gate `mcp_servers` on `mcp_tools`, in both the UI and what gets submitted

Two distinct behaviors have to be decided and implemented together, because
the two existing templates already disagree with each other on this exact
point:

**a. Template inconsistency (pre-existing, independent of this roadmap's UI
work).** `passthrough.yaml.j2` already nests `mcp_servers` inside
`{%- if mcp_tools %}` (lines 37-44), so `mcp_tools: false` with a leftover
`mcp_servers` answer renders *no* `mcp_servers` key at all. `multimodal.yaml.j2`
does not — it emits `mcp_tools: {{ mcp_tools | lower }}` unconditionally
(line 48) and then emits `mcp_servers` as a sibling `{%- if mcp_servers %}`
block (lines 49-53), independent of `mcp_tools`'s value. Fix `multimodal.yaml.j2`
to nest `mcp_servers` under `mcp_tools` the same way `passthrough.yaml.j2`
does, so both specs behave identically and a disabled-but-populated selection
never reaches the rendered YAML as dead config.

**b. UI behavior: preserve the selection, but don't submit it while disabled.**
Per the plan's intent (an admin flipping `mcp_tools` off and back on
shouldn't lose their server selection), the chip picker's *displayed* state
should survive a disable/enable cycle — but with (a) fixed, submitting while
disabled is now harmless either way (the template drops it). Implement both
for defense in depth: keep the UI-level preserve/restore (so the picker looks
right if `mcp_tools` is re-enabled before submit), and additionally zero the
*submitted* answer when `mcp_tools` is false, in `collectAdapterAnswers()` —
`answers.mcp_servers = []` whenever `answers.mcp_tools` is falsy, right before
the function returns. This keeps the submitted payload self-consistent even
if a future template regresses the `{%- if mcp_tools %}` nesting again.

**c. Enable/disable wiring.** No existing pattern in `adapters.js` toggles one
question's enabled state based on another's live value (confirmed: the only
comparable `change` listener is `specSelect`'s whole-form rebuild). In
`buildAdapterCreateForm()`, after both `mcp_tools` and `mcp_servers` inputs
exist in `createInputs`, wire a `change` listener on the `mcp_tools` checkbox
that toggles a `disabled` state (dim + non-interactive, not hidden) on the
`mcp_servers` chip picker. `createMultiCheckboxList` doesn't have a
`.disabled` setter yet (only `createSelect` does) — add one: a
container-level disabled flag that forces every chip's `disabled` regardless
of the max-items check, and apply the same initial state on form build (start
disabled if `mcp_tools`'s initial value is `false`) and after variant/spec
rebuilds.

- This wiring is specific to the `(mcp_tools, mcp_servers)` pair — don't
  generalize into a config-driven "field X enables field Y" mechanism unless
  a second case shows up.
- Tests: extend `test_admin_adapter_create.py`'s preview tests with a case
  that sets `mcp_tools=False` and a nonempty `mcp_servers` answer, asserting
  the rendered YAML for *both* `passthrough` and `multimodal` omits
  `mcp_servers` entirely. `passthrough.yaml.j2` already passes this today (the
  `mcp_tools=False` case is exactly what Phase 2's round-trip test deliberately
  avoids); `multimodal.yaml.j2` only passes once (a)'s template fix lands —
  write the test first, confirm it fails pre-fix, then fix the template. This
  covers both the template fix in (a) and, since the backend test can't
  exercise `collectAdapterAnswers()`, documents that the template is the
  authoritative guarantee — the frontend zeroing in (b) is a UX nicety on top,
  not the only safeguard.
- Manual UI check (no automated DOM test harness in this codebase today):
  toggle `mcp_tools` off/on in the create form, confirm `mcp_servers` dims/
  un-dims and a selection made while enabled is still shown (though not yet
  submitted) after a disable→enable cycle.

## Phase 4 (optional, separate) — Picker for `mcp-agent`'s `mcp_servers`

Out of scope for the main change above, but cheap to add once Phase 1's scan
exists, if there's appetite for consistency across all three specs. Needs its
own `options_source` key, not `"mcp_servers"` reused as-is, because the
eligibility filter is different:

- Add `_available_mcp_server_options_unfiltered(config)` — global `enabled` +
  per-server `enabled` only, **no** `allow_opportunistic` check (per
  `mcp_client_service.py`'s own comment, mcp-agent isn't gated by it).
- Register it under a distinct answer-options key, e.g. `"mcp_servers_all"`,
  so the two keys don't get confused by a future reader.
- `mcp-agent`'s `Question("mcp_servers", ...)` gets
  `options_source="mcp_servers_all", multi=True` — no `mcp_tools`-style gating
  question exists or is needed on this spec, so skip Phase 3's enable/disable
  wiring entirely here.
- Do this only after Phases 0-3 ship and are confirmed working — it's additive
  and shares no code path that would block it from landing later.

## Out of scope / explicitly deferred

- **Backend validation that `mcp_servers` names reference real servers.**
  Confirmed gap today (no equivalent of `_find_skill_name_owner` exists for
  MCP server names), and the skills work shipped without adding the analogous
  check for `available_skills` either — stay consistent and leave both as
  follow-ups rather than scope-creeping this change into a validation pass.
- **Surfacing live connection status** (`server/routes/admin/mcp.py`'s
  `status`/`connection_status` fields) in the picker — out of scope; this
  picker only needs to know what's configured, enabled, and (for Phases 1-3)
  opportunistic-eligible, not what's currently reachable.
- **Any change to `docs/adapters/mcp-agent.md`'s runtime semantics** — this is
  a create-form UX change (plus the one template consistency fix in Phase 3a)
  only; the capability behavior (`mcp_tools`, `mcp_servers`, opportunistic
  mode, mcp-agent's always-on allowlist) is unchanged.
