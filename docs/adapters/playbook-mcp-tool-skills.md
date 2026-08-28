# Manual/Integration Check: MCP Tool Skills (Phase 0 + Phase 1)

Steps to verify Phase 1 of [`docs/roadmap/mcp-tool-skills.md`](../roadmap/mcp-tool-skills.md)
before starting Phase 2 (just-in-time injection, opportunistic-mode parity).

This is the **tool skill** mechanism — an admin-authored `SKILL.md` procedural
playbook the model can load while calling MCP tools — not the ORBIT
skill/adapter-swap routing mechanism (`capabilities.expose_as_skill`). See
`docs/roadmap/mcp-tool-skills.md` §1 for the terminology split; nothing here
touches `available_skills` or `skill: "..."` routing.

What Phase 1 shipped, concretely:

- `server/services/tool_skill_service.py` — loads `config/skills/*/SKILL.md`,
  matches skills to namespaced MCP tool names via `mcp_tools` globs.
- A synthetic `orbit__load_tool_skill` tool, added to the tool list only when
  at least one skill matches the turn's tools, with its `name` enum scoped to
  the *surfaced set* (matched skills, capped at 10, sorted by priority/name).
- A one-line-per-skill catalog appended to the system message, after the
  prompt-cache breakpoint.
- `ToolDispatchResult`/`TrustedContext` in `mcp_tool_loop.py` — a skill body
  reaches the model via a `<trusted_skill>`-tagged segment on the tool-result
  message, never a new message, never inside `<tool_result>`.
- A `tool_skill_load`-typed `sources` entry, distinct from `mcp_tool_call`.
- Only the explicit `mcp-agent` skill path (`MCPAgentStep`) has this wired up.
  **Opportunistic mode (`capabilities.mcp_tools: true`) does not have tool
  skills yet — that's Phase 2.**

Everything below only requires `skill: "mcp-agent"` in the request body; there
is no admin panel yet (Phase 3).

## 1. Start the sample MCP server

Same server the opportunistic-mode playbook uses
(`docs/adapters/playbook-mcp-tool-loop.md`):

```bash
cd examples/mcp-server
npm install
MCP_TOKEN=test-secret npm start
```

Listens at `http://127.0.0.1:9999/mcp` and exposes `list_customers`,
`search_opportunities`, `summarize_pipeline`, `build_account_plan`, and the
rest of the CRM tool set — see that playbook's step 1 for the full list.

## 2. Point `business-sample` at the local server

`config/mcp_clients.yaml`'s `business-sample` entry may currently point at a
shared remote instance. For this check, point it at the local one you just
started:

```yaml
mcp_clients:
  enabled: true
  servers:
    - name: "business-sample"
      transport: "http"
      url: "http://127.0.0.1:9999/mcp"
      headers:
        Authorization: "Bearer ${MCP_TOKEN}"
      enabled: true
```

`allow_opportunistic` doesn't matter for this playbook — the explicit
`mcp-agent` skill path is governed only by `mcp_clients.enabled`, not the
opportunistic gate (see `docs/adapters/mcp-agent.md`).

```bash
export MCP_TOKEN=test-secret
```

## 3. Confirm the example skill is in place

Phase 1 ships an example skill already bound to this server:

```bash
cat config/skills/crm-pipeline-playbook/SKILL.md
```

You should see frontmatter with `mcp_tools: ["business-sample__*"]` and a body
that tells the model to resolve a customer id via `list_customers` before
calling `build_account_plan`, and to never pass `limit` above 25 to
`search_opportunities`.

`config/adapters/mcp-agent.yaml`'s `mcp-agent-chat` adapter should already
list `business-sample` in `capabilities.mcp_servers` (add it if not), and
some adapter's `available_skills` should include `"mcp-agent"` — see
`docs/adapters/mcp-agent.md` steps 3–4 if that's not already configured.

Restart ORBIT after any config edit.

## 4. Confirm the catalog and loader tool exist (no live request needed)

```bash
/path/to/venv/bin/python -m pytest server/tests/test_services/test_tool_skill_service.py -v
/path/to/venv/bin/python -m pytest server/tests/test_inference/test_mcp_tool_loop.py server/tests/test_inference/test_mcp_agent_step.py -v
```

These are the unit tests written alongside Phase 1 — they exercise the
registry, the dispatcher contract, and `MCPAgentStep`'s catalog/loader/dispatch
wiring without a live server or provider. Confirm all pass before moving to
the live checks below; a live-request failure is much harder to root-cause if
the unit layer isn't already green.

## 5. Trigger a skill load explicitly

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <key for an adapter with mcp-agent in available_skills>" \
  -H "X-Session-ID: skill-test-1" \
  -d '{
    "messages": [
      {"role": "user", "content": "Read the CRM tool playbook, then summarize the pipeline for EMEA."}
    ],
    "skill": "mcp-agent"
  }'
```

Confirm:

- `sources` contains a `{"type": "tool_skill_load", "skill":
  "crm-pipeline-playbook", "version": "1.0"}` entry — no `result_preview`, no
  `tool`/`arguments` fields (that shape is reserved for `mcp_tool_call`
  entries — see `docs/roadmap/mcp-tool-skills.md` §2.8).
- That entry sits alongside (not instead of) a real `mcp_tool_call` entry for
  `business-sample__summarize_pipeline`.
- The final answer reflects actual pipeline data, not just an
  acknowledgement that a playbook was read.

Many models will call the loader on their own even without being told to —
try the same prompt without "Read the CRM tool playbook" first and see
whether the model volunteers the call. If it never does across several
tries, that's expected for smaller/less capable models (see the "Level 3
cannot guide the first call" limitation in the roadmap §2.2) and is exactly
the gap Phase 2's just-in-time injection is meant to close — not a Phase 1
bug.

## 6. Confirm the playbook actually changes behavior

The skill's real value: ask something that would otherwise trip
`search_opportunities`' own validation error.

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -H "X-Session-ID: skill-test-2" \
  -d '{
    "messages": [
      {"role": "user", "content": "Using the CRM tool playbook, find the top 100 open opportunities."}
    ],
    "skill": "mcp-agent"
  }'
```

Confirm the model pages (`limit: 25` or less) instead of first trying
`limit: 100` and hitting the tool's `"limit: too_big, maximum 25"` error —
i.e. the skill's guidance actually prevented the round-trip
error-then-correct pattern documented in `docs/adapters/mcp-agent.md`'s
"self-correcting multi-step chain" example. If the model still tries 100
first, that's plausible behavior too (see step 5's note) — but it's the
interesting case to watch either way, since it's the clearest signal of
whether the loaded skill changed anything.

## 7. Confirm prompt-cache breakpoint is unaffected

This can't be observed from the API response directly — it requires a debug
log or a quick local check. Two options:

**A. Unit test (already covers this):**

```bash
/path/to/venv/bin/python -m pytest server/tests/test_inference/test_mcp_agent_step.py -k "cache_prefix_len" -v
```

`test_catalog_is_appended_after_cache_prefix_len` and
`test_no_skills_leaves_system_message_unchanged` assert the stable prefix is
byte-identical whether or not a skill catalog is appended.

**B. Manual spot-check**, if you want to see it live: temporarily add a debug
log line in `MCPAgentStep._build_initial_messages` printing
`system_content[:cache_prefix_len]`, run the same request with and without
`config/skills/crm-pipeline-playbook/SKILL.md` present (rename it aside and
back), and confirm the printed prefix is identical in both cases even though
`system_content` as a whole differs.

## 8. Confirm idempotence — repeated loads don't re-inflate context

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -H "X-Session-ID: skill-test-3" \
  -d '{
    "messages": [
      {"role": "user", "content": "Load the CRM tool playbook. Then load it again to be sure. Then summarize the pipeline for APAC."}
    ],
    "skill": "mcp-agent"
  }'
```

Confirm `sources` shows exactly **one** `tool_skill_load` entry for
`crm-pipeline-playbook`, even if the model calls the loader twice — the
second call gets a short "already loaded this turn" result instead of the
body again (`docs/roadmap/mcp-tool-skills.md` §2.2).

## 9. Confirm the surfaced-set cap and per-adapter scoping

These are harder to trigger with just one example skill configured. Two
lower-effort ways to check them:

**Cap (unit test):** `test_surfaced_set_cap_truncates_the_loader_enum_and_catalog`
in `test_mcp_agent_step.py` already covers this with 15 fake skills — rerun it
directly if you want to see the assertion:

```bash
/path/to/venv/bin/python -m pytest server/tests/test_inference/test_mcp_agent_step.py -k "surfaced_set_cap" -v
```

**Scoping (live, optional):** temporarily remove `"business-sample"` from
`mcp-agent-chat`'s `capabilities.mcp_servers` in
`config/adapters/mcp-agent.yaml`, restart, and repeat step 5's request.
Confirm no `orbit__load_tool_skill` call happens and no `tool_skill_load`
source appears — the skill's `mcp_tools` glob never even reaches the matched
set for this adapter, since the tool it's bound to isn't in scope at all
(`docs/roadmap/mcp-tool-skills.md` §2.1, §2.7). Restore the allowlist
afterward.

## 10. Confirm the namespace-collision guard

This is a Phase 1 defensive fix, not something you're likely to hit with the
bundled sample server — but it's worth confirming the guard actually holds,
since a silent regression here would make a real MCP tool unreachable with no
obvious symptom other than "that tool never gets called anymore."

```bash
/path/to/venv/bin/python -m pytest server/tests/test_inference/test_mcp_agent_step.py -k "never_shadowed" -v
```

`test_real_mcp_tool_named_like_the_loader_is_never_shadowed` simulates an MCP
server literally named `orbit` exposing a `load_tool_skill` tool (which
namespaces to exactly `orbit__load_tool_skill`, the synthetic loader's own
name) and confirms: no duplicate tool schema, tool skills disabled for that
turn, and the real tool call reaches the real MCP server. There's no
practical way to reproduce this with `examples/mcp-server` (it isn't named
`orbit`), so the unit test is the check here — no live reproduction needed.

## 11. Run the full check

```bash
ruff check server/
/path/to/venv/bin/python -m pytest server/tests/ -k "mcp or tool_skill" -v
```

All tests should pass, including the pre-existing MCP suites — Phase 1 was
built to leave `MCPToolSelector` and `LLMInferenceStep`'s opportunistic path
completely unmodified, and every pre-existing test in `test_mcp_tool_loop.py`
and `test_mcp_agent_step.py` should still pass unchanged alongside the new
ones.

---

## What's actually going on — how `SKILL.md` gets loaded and linked to `business-sample`

The steps above confirm the behavior works; this section explains the
mechanism behind it, end to end, so a result that looks surprising (a skill
that doesn't surface, or surfaces for the wrong tools) can be traced to a
specific piece of code rather than treated as a black box.

### 1. Loading — `server/services/tool_skill_service.py`

At the start of `MCPAgentStep._run_agent_loop`, `self._get_tool_skill_registry()`
calls `get_tool_skill_registry(config)`, which builds (or reuses a cached)
`ToolSkillRegistry` pointed at `config/skills` (default; overridable via
`config.tool_skills.directory`). On construction, `ToolSkillRegistry._load()`
globs `config/skills/*/SKILL.md` — so it finds
`config/skills/crm-pipeline-playbook/SKILL.md` — splits each file on the
`---` frontmatter delimiters, parses the YAML header with `yaml.safe_load`,
and validates it (name is a lowercase slug, the `orbit__` prefix is rejected,
`description`/`mcp_tools` are present, the body is under the 32KB cap, etc.).
A valid file becomes a `ToolSkill` object holding `name`, `description`,
`mcp_tools` (the glob list), `body`, `priority`, and `version`.

For this file specifically, that's:

```yaml
name: crm-pipeline-playbook
mcp_tools: ["business-sample__*"]
```

### 2. Linking to `business-sample` — glob matching, not a hardcoded reference

The link to the `business-sample` MCP server isn't a direct pointer
anywhere — it's purely the `mcp_tools` glob, checked fresh every turn. In
`_run_agent_loop`:

```python
tools = await mcp_manager.get_all_tools(allowed_servers=allowed_servers)
...
registry.matched_for(_tool_names(tools))
```

`mcp_manager.get_all_tools()` returns the live, discovered tool schemas from
every enabled MCP server, each namespaced as `<server>__<tool>` (built in
`MCPClientManager._to_openai_tool`) — so `business-sample`'s tools show up as
`business-sample__list_customers`, `business-sample__search_opportunities`,
etc. `ToolSkillRegistry.matched_for(tool_names)` then runs
`fnmatch.fnmatchcase(tool_name, "business-sample__*")` against each of those
names — any tool from that server matches, no matter which one. That's the
entire "link": a glob pattern checked at request time against whatever tools
are currently live, not a static binding validated at config-load time.

This has real consequences worth internalizing before debugging a
surprising result:

- If `business-sample` is unreachable or disabled that turn, no tools
  starting with `business-sample__` are discovered, so the skill simply
  doesn't match anything and never surfaces — no error, no warning, it's
  just absent from the matched set.
- If the server were renamed in `mcp_clients.yaml`, the skill would silently
  stop matching — the pattern is a plain string glob, not a resolved
  reference checked against server config, so nothing would flag the
  mismatch.
- Nothing in `mcp_clients.yaml` or the MCP server itself references skills
  at all — `config/skills/*/SKILL.md` is the *only* place the binding is
  declared, in one direction (skill → tools), never the reverse.

### 3. Surfacing to the model

Once matched (and truncated to the *surfaced set* — capped at 10, sorted by
priority then name, per step 9 above), two things happen this turn:

- A line is appended to the system message, after the prompt-cache
  breakpoint (step 7): `- crm-pipeline-playbook: How to answer pipeline,
  renewal, and account-health questions using the CRM tools.`
- A synthetic tool `orbit__load_tool_skill` is appended to the tool list,
  with its `name` parameter's enum restricted to `["crm-pipeline-playbook"]`
  for this turn only — never the full registry, and never skills that
  matched but were truncated out of the surfaced set.

### 4. Dispatch — how a load actually happens

If the model calls that synthetic tool, `MCPAgentStep._build_dispatch`'s
closure intercepts the call by name (never reaching the real
`mcp_manager.call_tool`), looks `crm-pipeline-playbook` up in the surfaced
set, and returns the skill's `body` as a `TrustedContext`. `run_tool_calling_loop`
then:

- delivers that body to the model as a `<trusted_skill
  name="crm-pipeline-playbook">...</trusted_skill>` block appended to the
  *same* tool-result message for that call (never a new message, never
  inside the `<tool_result>` tag that wraps untrusted MCP output — see step
  6's error-handling contrast), and
- records it in `sources` as `{"type": "tool_skill_load", "skill":
  "crm-pipeline-playbook", "version": "1.0"}` — deliberately shaped
  differently from an `mcp_tool_call` entry (step 5), since this never
  touched an external MCP server.

**End to end:** file on disk → glob-matched against live tool discovery every
turn → catalog line + synthetic loader tool, both scoped to the surfaced
set → model-initiated load → body injected as trusted context on the
tool-result message, recorded under its own `sources` type. No step
hardcodes `"business-sample"` as a special case anywhere in the mechanism —
it's just the server whose tools happen to match this skill's glob this
turn.

---

## What NOT to expect yet (Phase 2+ territory)

- **Opportunistic mode does not see tool skills.** Setting
  `capabilities.mcp_tools: true` on `simple-chat` (as in
  `playbook-mcp-tool-loop.md`) will NOT surface the catalog or loader tool —
  only the explicit `skill: "mcp-agent"` path has this wired up in Phase 1.
  Confirm this directly: repeat step 5 with `mcp_tools: true` on
  `simple-chat` instead of `skill: "mcp-agent"` in the request, and confirm no
  catalog/loader ever appears. This is expected, not a bug — it's exactly
  what Phase 2 adds ("opportunistic parity").
- **No just-in-time (Level 3) injection.** A skill body only reaches the
  model if the model explicitly calls `orbit__load_tool_skill` — there is no
  automatic injection after a bound tool's first call yet. If a smaller model
  never calls the loader (step 5's note), the playbook simply never reaches
  it this turn. That's the gap Phase 2 closes.
- **No admin UI.** Skills are file-based only (`config/skills/*/SKILL.md`,
  git-edited, requiring a restart to pick up changes) — there's no `/admin`
  panel tab yet (Phase 3).

If everything above checks out, Phase 0 and Phase 1 are confirmed working
end-to-end and it's reasonable to move on to Phase 2.

## Troubleshooting

- **No `orbit__load_tool_skill` ever appears, and no `tool_skill_load`
  source shows up**: confirm `business-sample` is in `mcp-agent-chat`'s
  `capabilities.mcp_servers` (or that allowlist is omitted entirely), confirm
  `config/skills/crm-pipeline-playbook/SKILL.md` exists and its `enabled`
  field isn't `false`, and confirm the request actually used
  `"skill": "mcp-agent"` — opportunistic mode doesn't have this yet (see
  above). A registry parsing failure logs a warning at startup (missing/
  invalid `name`, `description`, or `mcp_tools`, an oversize body, etc.) —
  check server startup logs for `"Skill file ... skipped"` if the skill
  still isn't showing up with everything else configured correctly.
- **The model calls the loader but the answer doesn't reflect the
  guidance**: this is a model-capability issue, not a wiring issue — see step
  5/6's notes. Try a stronger model (`gpt-4.1`, `claude-sonnet-4-6`) before
  concluding something is broken.
- **401/EADDRINUSE/health-check issues with the sample server**: see the
  Troubleshooting section of `docs/adapters/playbook-mcp-tool-loop.md` —
  identical setup, same server.
