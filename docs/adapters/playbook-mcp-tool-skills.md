# Manual/Integration Check: MCP Tool Skills

Steps to verify Phase 0–3 of [`docs/roadmap/mcp-tool-skills.md`](../roadmap/mcp-tool-skills.md).
Phase 3 (§16–§19 below) added database-backed CRUD, an admin API, and the
"Tool Skills" admin panel tab — everything before that is unchanged from the
Phase 0–2 file-only mechanism.

This is the **tool skill** mechanism — an admin-authored `SKILL.md` procedural
playbook the model can load (or has auto-attached) while calling MCP tools —
not the ORBIT skill/adapter-swap routing mechanism
(`capabilities.expose_as_skill`). See `docs/roadmap/mcp-tool-skills.md` §1 for
the terminology split; nothing here touches `available_skills` or
`skill: "..."` routing.

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
- This was Level 2 only (explicit, model-initiated load), and only on the
  explicit `mcp-agent` skill path (`MCPAgentStep`).

What Phase 2 added on top, concretely (`server/inference/pipeline/tool_skills_support.py`
is the new shared module both call sites use):

- **Level 3 — just-in-time auto-injection.** The first time a bound tool is
  actually invoked in a turn, its skill body rides along as trusted context on
  that same tool call's own result — no `orbit__load_tool_skill` call needed.
  Still can't shape the arguments of that *first* call (§2.2's documented
  limitation); it corrects the model on the next call, or on formatting.
- **Opportunistic-mode parity.** `LLMInferenceStep._run_inline_mcp_tools`
  (`capabilities.mcp_tools: true`) now gets the identical catalog/loader/Level-3
  mechanism — no longer explicit-`mcp-agent`-only.
- **`capabilities.tool_skills` allowlist** — restricts which skills an
  adapter may surface or load, independent of `mcp_servers`. Omitted = every
  skill matching a visible tool (§2.7).
- **A shared per-turn injection budget** (3 skills / 24 KB) across Level 2 and
  Level 3, admitting the highest-priority candidates first — decided once, up
  front, from the turn's full matched-skill set, so which skills get dropped
  never depends on which order the model happens to call tools in.

What Phase 3 added on top, concretely (`server/services/tool_skill_service.py`'s
`ToolSkillService` + `server/routes/admin/skills.py` + `server/admin/admin_panel/tabs/skills.js`):

- **Database-backed CRUD**, alongside (not instead of) the file-based skills
  Phase 1 already supports — `POST/GET/PUT/DELETE /admin/skills` and
  `POST /admin/skills/validate`, all behind `config_auth`.
- **Database-over-file precedence.** A database skill with the same `name`
  as a `config/skills/*/SKILL.md` file wins — the file version becomes the
  shadowed "on-disk default", never deleted or edited by the override.
- **Hot reload, no restart.** Every admin CRUD write re-merges the live
  `ToolSkillRegistry` immediately, and (under `performance.workers > 1`)
  propagates to sibling workers within 5 seconds via the same
  `services/adapter_reload_state.py` generation-bump poll the MCP config
  reload already uses (`"tool_skills"` is a new reload kind alongside
  `"mcp_config"`).
- **The "Tool Skills" admin panel tab** — create/edit/delete a skill with a
  markdown-preview editor, no YAML file editing required. `mcp.js`'s
  per-server detail view also gained a read-only "Playbooks" cross-reference
  section.

Steps 1–15 below only require `skill: "mcp-agent"` (explicit path) or
`capabilities.mcp_tools: true` (opportunistic path) and are unaffected by
whether Phase 3 is in play — a file-based skill behaves exactly as before
unless a database skill of the same name overrides it. Phase 3 itself starts
at step 16.

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
tries, that's expected for smaller/less capable models — and with Phase 2
shipped, it's no longer the end of the story: step 12 below confirms Level 3
picks up the slack automatically, once the model has called a bound tool at
least once.

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
/path/to/venv/bin/python -m pytest server/tests/ -k "mcp or tool_skill or admin_skills" -v
```

All tests should pass, including the pre-existing MCP suites — Phase 1 was
built to leave `MCPToolSelector` and `LLMInferenceStep`'s opportunistic path
completely unmodified, and every pre-existing test in `test_mcp_tool_loop.py`
and `test_mcp_agent_step.py` should still pass unchanged alongside the new
ones. Phase 2 adds `test_inference/test_tool_skills_support.py` and new test
classes in both `test_mcp_agent_step.py` and `test_llm_inference_mcp_tools.py`
to that same sweep. Phase 3 adds `test_services/test_tool_skill_service_db.py`,
`test_routes/test_admin_skills.py`, and new cases in
`test_services/test_adapter_reload_state.py` — all covered by the same
`-k "mcp or tool_skill or admin_skills"` filter above.

## 12. Confirm Level 3 just-in-time injection

This is the headline Phase 2 behavior: a skill body reaching the model
**without it ever calling `orbit__load_tool_skill`**. Ask a question that
should drive the model straight to a bound tool, with no mention of a
playbook at all:

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <key for an adapter with mcp-agent in available_skills>" \
  -H "X-Session-ID: skill-test-jit-1" \
  -d '{
    "messages": [
      {"role": "user", "content": "Find the top 100 open opportunities."}
    ],
    "skill": "mcp-agent"
  }'
```

Confirm:

- `sources` contains **both** an `mcp_tool_call` entry for
  `business-sample__search_opportunities` **and** a `tool_skill_load` entry
  for `crm-pipeline-playbook` — with no `orbit__load_tool_skill` call ever
  appearing in the tool-call history, unlike step 5.
- Because Level 3 cannot shape the *first* call's arguments (§2.2's
  documented limitation), the first `search_opportunities` call may still be
  made with `limit: 100` and get the tool's own validation error back — the
  skill body arrives *attached to that same error result*, and it's the
  **next** call (or the final answer's formatting) that should reflect the
  guidance. If the model never needed a second call at all (e.g. it happened
  to pass a safe `limit` the first time), that's fine too — the injection
  still occurred, there was just nothing left to correct.

## 13. Confirm opportunistic-mode parity

Repeat the same idea against an adapter using `capabilities.mcp_tools: true`
instead of `skill: "mcp-agent"` — e.g. `simple-chat` from
`config/adapters/passthrough.yaml`, which already lists `business-sample` in
its `mcp_servers` allowlist:

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <key for an mcp_tools:true adapter>" \
  -H "X-Session-ID: skill-test-opportunistic-1" \
  -d '{
    "messages": [
      {"role": "user", "content": "Call search_opportunities and show me the first 25 open opportunities."}
    ]
  }'
```

No `"skill"` field at all — this is the plain conversational path. Be
directive about wanting the tool actually called: a vaguer prompt like "Find
the top 100 open opportunities" is a weaker check here, since a model may
answer from the tool's own schema description (e.g. "results are capped at
25") without calling anything — that produces `sources: []` and confirms
nothing about the tool-skill mechanism one way or the other (it's the
documented "a turn calling no bound tool injects nothing" case, not a
failure, but it isn't evidence of success either).

Confirmed working, `simple-chat` (`ollama_cloud`/`gpt-oss:120b` adapter
default, `gpt-5.4-mini` resolved at runtime for this request):

```json
{"done": true, "sources": [
  {"type": "tool_skill_load", "skill": "crm-pipeline-playbook", "version": "1.0"},
  {"type": "mcp_tool_call", "tool": "business-sample__search_opportunities", "arguments": {"limit": 25}, "...": "..."},
  {"type": "mcp_tool_call", "tool": "business-sample__search_opportunities", "arguments": {"stage": "Negotiation", "limit": 25}, "...": "..."},
  {"type": "mcp_tool_call", "tool": "business-sample__search_opportunities", "arguments": {"stage": "Proposal", "limit": 25}, "...": "..."},
  {"type": "mcp_tool_call", "tool": "business-sample__search_opportunities", "arguments": {"stage": "Discovery", "limit": 25}, "...": "..."},
  {"type": "mcp_tool_call", "tool": "business-sample__search_opportunities", "arguments": {"stage": "Qualification", "limit": 25}, "...": "..."}
]}
```

Confirm the same thing step 12 confirmed on the explicit path: a
`tool_skill_load` source appears alongside the real `mcp_tool_call` entries,
without the model ever calling `orbit__load_tool_skill` — plus two things
this run demonstrates that step 12 didn't: the model made *multiple*
follow-up tool calls in the same turn, each one still respecting the
skill's `limit ≤ 25` rule (it split the query by `stage` rather than ever
raising `limit`), and the final answer's table matches the skill's exact
`Owner | Account | Stage | ARR | Close date` formatting spec — direct
evidence the injected guidance, not just the tool schema, shaped the
output. This is the concrete difference Phase 2 made: before it, this exact
request would have produced zero tool-skill-related `sources` entries,
ever (see the "What NOT to expect yet" note this playbook used to carry —
now folded into Phase 3's list below).

## 14. Confirm the `capabilities.tool_skills` allowlist

Add a restrictive allowlist to `mcp-agent-chat` in
`config/adapters/mcp-agent.yaml`:

```yaml
capabilities:
  mcp_servers: ["business-sample"]
  tool_skills: []   # deny every tool skill for this adapter
```

Restart, repeat step 5's request. Confirm no `orbit__load_tool_skill` tool
ever appears in the tool list and no `tool_skill_load` source shows up, even
though `business-sample__*` tools are still fully reachable and callable —
the allowlist blocks skill surfacing/loading specifically, not tool access
(`docs/roadmap/mcp-tool-skills.md` §2.7). Restore
`tool_skills: ["crm-pipeline-playbook"]` (or remove the key entirely, which
defaults to "every skill matching a visible tool") afterward.

**Pitfall — the allowlist only applies to the adapter actually running the
turn.** A `"skill": "mcp-agent"` request swaps the active adapter to
`mcp-agent-chat` for that turn, so `tool_skills` set on some *other* adapter
(e.g. `simple-chat` in `passthrough.yaml`) has no effect on it — you'll see
the loader/skill surface exactly as before and wrongly conclude the
allowlist "isn't working." Match the request to the adapter you edited: an
allowlist on `mcp-agent-chat` needs `"skill": "mcp-agent"` in the request
(step 5's shape); an allowlist on an opportunistic adapter like
`simple-chat` needs a plain request with no `"skill"` field at all (step
13's shape) against that adapter's own API key.

## 15. Confirm multiple distinct skills — the surfaced set, priorities, and per-tool binding

`crm-pipeline-playbook` alone can't show two things Phase 0–2 both promise:
several *different* skills surfacing in the same catalog, and priority
actually mattering when more than one is in play. The bundled example now
ships four skills, each bound to a disjoint slice of `business-sample`'s
tools with different `priority` values, so this is testable live:

| Skill | Bound tools | Priority |
|---|---|---|
| `crm-pipeline-playbook` | `list_customers`, `get_customer_health`, `search_opportunities`, `summarize_pipeline`, `build_account_plan` | 10 (highest) |
| `support-ticket-playbook` | `list_support_tickets`, `get_support_ticket`, `create_support_ticket`, `update_support_ticket`, `delete_support_ticket` | 5 |
| `churn-risk-playbook` | `get_product_telemetry`, `simulate_churn_risk_scenario` | 0 (default) |
| `sales-performance-playbook` | `get_sales_rep_performance` | -1 (lowest) |

**15a. Catalog shows all four, in priority order.**

```bash
/path/to/venv/bin/python -m pytest server/tests/test_services/test_tool_skill_service.py -k "matched_for or sort" -v
```

Or live: send step 5's request as-is (any prompt is fine, since the catalog
is built before the model calls anything) and inspect the system message /
first `generate_with_tools` call's tool list — `orbit__load_tool_skill`'s
`name` enum should list all four names, ordered
`crm-pipeline-playbook, support-ticket-playbook, churn-risk-playbook,
sales-performance-playbook` (priority desc, then name).

**15b. Different tools load different skills (Level 3), independently.**

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <key for an adapter with mcp-agent in available_skills>" \
  -H "X-Session-ID: skill-test-multi-1" \
  -d '{
    "messages": [
      {"role": "user", "content": "Summarize the EMEA pipeline, then show me sales rep performance for this quarter, then list any open support tickets for cus_0005."}
    ],
    "skill": "mcp-agent"
  }'
```

Confirm `sources` contains **three** distinct `tool_skill_load` entries —
`crm-pipeline-playbook`, `sales-performance-playbook`, and
`support-ticket-playbook` — each paired with the `mcp_tool_call` for its own
bound tool, and each loaded independently (calling `get_sales_rep_performance`
doesn't also trigger `crm-pipeline-playbook`, and vice versa). This is the
live version of the "sibling tool calls are isolated" guarantee from step 12's
mechanism section — here demonstrated across three genuinely different
skills instead of one skill vs. no skill.

**15c. Priority survives call order under the budget.**

The per-turn budget admits at most 3 skills. Ask for all four bound
categories in an order that puts the lowest-priority one first:

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <key for an adapter with mcp-agent in available_skills>" \
  -H "X-Session-ID: skill-test-multi-2" \
  -d '{
    "messages": [
      {"role": "user", "content": "Show me sales rep performance for this quarter, then check product telemetry and churn risk for cus_0005, then list customers, then summarize the EMEA pipeline."}
    ],
    "skill": "mcp-agent"
  }'
```

Confirm `sources` shows exactly **three** `tool_skill_load` entries, and
`sales-performance-playbook` (priority `-1`, the lowest) is the one
**missing** — even though its bound tool was called *first* in the turn.
`crm-pipeline-playbook` (priority `10`) must be present regardless of when
its tool was actually called. If instead the *first three skills
encountered* are the ones admitted (i.e. `sales-performance-playbook` makes
it in and `crm-pipeline-playbook` doesn't), that's the exact regression the
priority-precomputation fix in `tool_skills_support.py` exists to prevent —
worth filing immediately.

Unit-level equivalents of 15c, if you'd rather not depend on model
cooperation for call order:

```bash
/path/to/venv/bin/python -m pytest server/tests/test_inference/test_tool_skills_support.py -k "priority_admission" -v
/path/to/venv/bin/python -m pytest server/tests/test_inference/test_mcp_agent_step.py -k "budget_preserves_priority" -v
```

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

### 5. Level 3 and opportunistic parity — `server/inference/pipeline/tool_skills_support.py`

Everything above (steps 1–4) is Level 2 and lived, in Phase 1, entirely
inside `MCPAgentStep`. Phase 2 pulled the matched/surfaced-set resolution,
the catalog/loader builders, and dispatch into
`server/inference/pipeline/tool_skills_support.py` so both call sites share
one implementation — `MCPAgentStep._run_agent_loop` and
`LLMInferenceStep._run_inline_mcp_tools` now call the exact same
`resolve_surfaced_skills()` / `build_dispatch()` functions, which is what
makes step 13's opportunistic-mode result identical to step 12's explicit one.

`build_dispatch()`'s returned closure does two things on every dispatched
call, not just loader calls:

```python
content = await mcp_manager.call_tool(tool_name, arguments)
result = ToolDispatchResult(content=content, source_type="mcp_tool_call")

for skill in matched_skills:              # full matched set, NOT the surfaced set
    if budget.already_loaded(skill.name):
        continue
    if not skill.matches(tool_name):      # is this call's tool one this skill binds?
        continue
    if not budget.try_reserve(skill):
        continue                          # budget-exhausted — logged, not silently lost
    result.trusted_context.append(TrustedContext(name=skill.name, body=skill.body, ...))
```

This is why Level 3 fires *after* the real tool call — it's the same
dispatch, and the model has already committed to the arguments by the time
this code runs (the documented "can't shape the first call" limitation,
step 12). It's also why sibling tool calls in one assistant turn are
unaffected by each other: each call gets its own `dispatch(tool_name, ...)`
invocation, and only skills whose `mcp_tools` glob matches *that specific*
`tool_name` are ever considered for it.

`InjectionBudget` is what makes step 15 true: it's constructed once per turn
from the *full* matched-skill set (already sorted priority-desc/name by the
registry), and it precomputes which skill names are eligible **before** any
dispatch call happens — `try_reserve()` at call time only checks membership
in that fixed set plus idempotence. That's a deliberate fix over a naive
first-come-first-served budget, which would let three low-priority tool
calls exhaust the budget before a higher-priority tool is ever invoked later
in the same turn.

## 16. Confirm database CRUD — create, edit, and delete a tool skill with no restart

Create a new skill via the admin API (any `config.manage`-permissioned
bearer token or API key):

```bash
curl -X POST http://localhost:3000/admin/skills \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <admin-token>" \
  -d '{
    "name": "db-test-playbook",
    "description": "A database-authored test playbook.",
    "mcp_tools": ["business-sample__get_sales_rep_performance"],
    "body": "Always rank reps by attainment percentage, never raw closed amount.",
    "priority": 3
  }'
```

Confirm:

- The response is `201`-shaped (`id`, `name`, ... — same fields step 3's file
  skill has) and includes the `id` you'll need for the next calls.
- `GET /admin/skills` lists the new **database-authored** skill with no
  server restart between the create and the list call. This CRUD API (and
  the Tool Skills tab) intentionally lists database-authored skills only;
  file-authored `config/skills/*/SKILL.md` entries remain available to the
  runtime registry but are not enumerated by this endpoint.
- With no `"skill"` field or `mcp-agent` routing involved yet, send a live
  request that should bind to `get_sales_rep_performance` (any adapter
  reaching `business-sample`) and confirm `sources` includes `{"type":
  "tool_skill_load", "skill": "db-test-playbook", ...}` — proof the new
  skill is live in the running server's `ToolSkillRegistry`, not just
  persisted to the database.

Then edit it:

```bash
curl -X PUT http://localhost:3000/admin/skills/<id> \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <admin-token>" \
  -d '{"priority": 20}'
```

Repeat step 15a's catalog-ordering check — `db-test-playbook` (now priority
`20`) should sort *ahead* of `crm-pipeline-playbook` (priority `10`) in the
`orbit__load_tool_skill` enum, with no restart between the edit and that
check.

Finally, delete it:

```bash
curl -X DELETE http://localhost:3000/admin/skills/<id> \
  -H "Authorization: Bearer <admin-token>"
```

Confirm `GET /admin/skills` no longer lists it, and a repeat of the live
request from above produces no `tool_skill_load` entry for
`db-test-playbook` — deletion also took effect with no restart.

Also confirm `POST /admin/skills/validate` catches bad input before you
persist it — useful for scripting a check into a CI/CD pipeline that
authors skills as code:

```bash
curl -X POST http://localhost:3000/admin/skills/validate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <admin-token>" \
  -d '{"name": "Not A Valid Slug", "description": "d", "mcp_tools": ["a__b"], "body": "b"}'
```

Confirm the response is `{"valid": false, "error": "..."}` and that nothing
was persisted (`GET /admin/skills` is unchanged) — this endpoint never
writes to the database.

## 17. Confirm database-over-file precedence

This is the core Phase 3 guarantee from `docs/roadmap/mcp-tool-skills.md`
§2.6: a database skill with the same `name` as a bundled file skill wins,
without touching or deleting the file.

```bash
curl -X POST http://localhost:3000/admin/skills \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <admin-token>" \
  -d '{
    "name": "crm-pipeline-playbook",
    "description": "DB override: pipeline questions now always page at 10, not 25.",
    "mcp_tools": ["business-sample__search_opportunities", "business-sample__summarize_pipeline"],
    "body": "Never pass limit above 10 to search_opportunities, regardless of what the user asks for.",
    "priority": 10
  }'
```

Confirm:

- The create succeeds — the name collides with a *file* skill, not another
  *database* skill, so the unique-index-on-`name` rejection from step 16
  doesn't apply here (§2.6 is specifically about this cross-source case).
- `cat config/skills/crm-pipeline-playbook/SKILL.md` still shows the
  original file content, untouched.
- Repeat step 5's or step 12's request. The catalog line, the loaded body,
  and the model's actual behavior (paging at ≤10, not ≤25) should all now
  reflect the **database** version — proof `ToolSkillRegistry.get()` served
  the DB entry, not the file one.
- Delete the database override (`DELETE /admin/skills/<id>`, using the id
  from this step's create response) and repeat the request once more.
  Confirm the *file* version's behavior returns immediately (paging at ≤25
  again) — the file skill was never lost, only shadowed while the database
  entry existed.

## 18. Confirm multi-worker hot-reload propagation (optional, only if `performance.workers > 1`)

Skip this step entirely on a single-worker deployment — no `"performance":
{"workers": N}` config, or `N` is `1`. Otherwise, with two or more workers
running behind the shared listening socket:

1. Send enough requests (or use `X-Session-ID` values you know differ) to
   get responses served by more than one worker — the worker's PID isn't
   exposed in the API response, so watch server logs for
   `"Propagated tool skill reload from another worker"` instead.
2. Create a tool skill via `POST /admin/skills` (step 16). Whichever worker
   accepts that HTTP connection applies it locally and bumps the shared
   `"tool_skills"` generation counter (`services/adapter_reload_state.py`).
3. Within roughly 5 seconds (`_POLL_INTERVAL_SECONDS`), confirm the server
   log shows every *other* worker logging `"Propagated tool skill reload
   from another worker"` — each sibling's own `ToolSkillRegistry` re-merged
   the new database skill without that worker ever having handled the
   `POST` request itself.
4. Confirm a live request that would previously have been served by any
   worker now picks up the new skill regardless of which worker happens to
   handle it.

Unit-level equivalent, if you don't have a multi-worker deployment handy:

```bash
/path/to/venv/bin/python -m pytest server/tests/test_services/test_adapter_reload_state.py -k "ToolSkillsReloadPropagation" -v
```

## 19. Confirm the "Tool Skills" admin panel tab

Open `/admin` in a browser, log in, and select **Tool Skills** in the System
group of the nav (next to **MCP**).

- **List view**: confirm database skills created in steps 16–17 appear with
  name, description, priority, and enabled state. The panel currently
  enumerates database-authored skills only; file-authored
  `config/skills/*/SKILL.md` skills remain active at runtime but are not
  shown as editable rows here.
- **Create**: use the "Create Tool Skill" form to author a new skill (name,
  description, comma-separated `mcp_tools` glob list, priority, markdown
  body). Confirm it appears in the list immediately and — per step 16 — is
  live in a request's `sources` with no restart.
- **Edit**: select a skill, choose "Edit Tool Skill", change its body or
  priority, save, and confirm the markdown preview re-renders and a repeat
  live request reflects the change.
- **Delete**: use the Danger Zone's "Delete Tool Skill", typing the skill's
  name to confirm. Confirm it disappears from the list and — if it had
  overridden a file skill by name (step 17) — the file skill's original
  behavior returns.
- **Cross-reference from MCP**: open the **MCP** tab, select the
  `business-sample` server, ping it if you haven't already this session, and
  confirm its detail view's new "Playbooks" section lists every
  database-authored tool skill currently bound to one of its tools (by glob
  match against the live discovered, already-namespaced tool list). Create or
  delete a skill bound to
  `business-sample` from the Tool Skills tab, then return to the MCP tab's
  server detail without a full page reload — confirm the Playbooks section
  reflects the change (this is the P2 stale-cache fix: `skills.js` calls
  `mcpTab.invalidatePlaybooksCache()` after every create/update/delete, so
  the MCP tab's cached skill list is invalidated instead of surviving for
  the rest of the SPA session).

---

## What Phase 3 does *not* do (Phase 4 territory)

- **No bundled resources.** A skill is a single `SKILL.md` document (or
  single database row) — no additional files loaded on a second call.
- **No versioning or eval harness.** `version` is a free-text field an
  author sets by convention; nothing tracks version history or measures
  whether a skill actually improves tool-selection accuracy.
- **No tool skills for non-MCP tools.** Binding is still `mcp_tools` globs
  against namespaced MCP tool names only — intent/function-calling adapters
  aren't covered.

If everything above checks out, Phase 0 through Phase 3 are confirmed
working end-to-end.

## Troubleshooting

- **No `orbit__load_tool_skill` ever appears, and no `tool_skill_load`
  source shows up (Level 2/loader path)**: confirm `business-sample` is in
  the adapter's `capabilities.mcp_servers` (or that allowlist is omitted
  entirely), confirm `capabilities.tool_skills` isn't set to an allowlist
  that excludes `crm-pipeline-playbook` (step 14), confirm
  `config/skills/crm-pipeline-playbook/SKILL.md` exists and its `enabled`
  field isn't `false`, and confirm the request used either
  `"skill": "mcp-agent"` or an adapter with `capabilities.mcp_tools: true` —
  a plain adapter with neither never reaches the MCP tool loop at all. A
  registry parsing failure logs a warning at startup (missing/invalid
  `name`, `description`, or `mcp_tools`, an oversize body, etc.) — check
  server startup logs for `"Skill file ... skipped"` if the skill still
  isn't showing up with everything else configured correctly.
- **A `tool_skill_load` source appears but no `orbit__load_tool_skill` call
  is in the trace (Level 3/JIT path)**: this is expected, not a bug — see
  step 12. Confirm it's paired with an `mcp_tool_call` entry for a tool the
  skill's `mcp_tools` glob actually matches; if it's paired with a
  *different* tool, or with no `mcp_tool_call` at all, that would indicate a
  real problem (a skill matching the wrong tool, or an unattached
  `TrustedContext`) worth filing.
- **The model calls the loader but the answer doesn't reflect the
  guidance**: this is a model-capability issue, not a wiring issue — see step
  5/6's notes. Try a stronger model (`gpt-4.1`, `claude-sonnet-4-6`) before
  concluding something is broken.
- **401/EADDRINUSE/health-check issues with the sample server**: see the
  Troubleshooting section of `docs/adapters/playbook-mcp-tool-loop.md` —
  identical setup, same server.
- **`POST /admin/skills` returns `500` on SQLite/Postgres** (step 16): this
  was a real bug, fixed post-review — `mcp_tools` is a Python list, and
  neither backend's driver can bind one directly to a dynamically-created
  table's `TEXT` column. `ToolSkillService._encode_doc`/`_decode_doc`
  JSON-encode/decode it transparently now (MongoDB is untouched, since it
  stores the list natively). If you see `"Error binding parameter
  'mcp_tools': type 'list' is not supported"` on a Mongo backend, that
  would indicate a real regression — file it.
- **A database skill doesn't override its file counterpart** (step 17):
  confirm the `name` fields are byte-identical (case-sensitive, no trailing
  whitespace) and that the database skill's own `enabled` is `true` — a
  disabled database skill is excluded from the merge entirely and the file
  version is served, which looks identical to "the override didn't apply"
  from the outside. Also confirm you actually created it via `POST
  /admin/skills` (or the panel) and not just edited the file — the two
  sources are never reconciled automatically.
- **A CRUD write doesn't show up in a live request** (steps 16–17):
  `_refresh_registry` (in `routes/admin/skills.py`) re-merges the
  in-process registry synchronously as part of the same request that
  performed the write — if a live check still shows stale behavior, confirm
  you're hitting the same worker process (single-worker deployments always
  are), then see the next entry for the multi-worker case.
- **Sibling workers don't pick up a Phase 3 CRUD write within ~5s** (step
  18): confirm `os.environ["ORBIT_SUPERVISOR_PID"]` is actually set in your
  deployment (single-process/dev runs never propagate, by design — there
  are no siblings to notify), and check for `"Failed to propagate tool
  skill reload to other workers"` in the logs, which means the generation
  bump itself failed (a `database_service` outage) rather than the poll
  not having run yet.
- **The MCP tab's "Playbooks" section still shows a deleted/edited skill**
  (step 19): confirm you're on the fixed build — `skills.js` must call the
  `onSkillsChanged` callback wired to `mcpTab.invalidatePlaybooksCache()`
  after create/update/delete (this was a real bug, fixed post-review). A
  full page reload always clears the stale cache as a workaround, but
  shouldn't be necessary after the fix.
