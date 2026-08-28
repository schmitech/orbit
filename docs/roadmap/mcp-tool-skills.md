# MCP Tool Skills — Procedural Skills Attached to MCP Tools

**Status:** Phase 0 complete — decisions locked (§8) · Phase 1 not started
**Owner:** TBD
**Related:** [`docs/adapters/mcp-agent.md`](../adapters/mcp-agent.md), [`docs/tutorial/mcp-tool-calling.md`](../tutorial/mcp-tool-calling.md)

---

## 1. What is being asked

Today ORBIT gives the model a **tool list** (name, description, JSON schema) and
nothing else. Everything the model knows about *how* to use a tool comes from
the MCP server's own `description` field — which ORBIT cannot improve, and which
`docs/adapters/mcp-agent.md` already names as "the single biggest lever and it's
set by the MCP server, not ORBIT".

The request is to add a second layer next to the schema: a **skill** — an
admin-authored `SKILL.md` document (YAML frontmatter + markdown body) carrying
the *procedural* knowledge for a tool or a family of tools. "When summarizing
the pipeline, always call `list_customers` first and filter by region; never pass
`limit` above 25; format the result as a table with these columns." The model
loads that document when it becomes relevant, exactly the way agentic coding
tools load skills today.

### Terminology warning — two different things are called "skill"

| Term | Meaning | This document |
|------|---------|---------------|
| **ORBIT skill** | An adapter with `capabilities.expose_as_skill: true` (`mcp-agent`, `image-generation`, `web-search`). A *routing* mechanism: `skill: "x"` swaps `context.adapter_name`. | unchanged |
| **Tool skill** (this doc) | A `SKILL.md` procedural document bound to one or more MCP tools, injected into model context. Not an adapter, no routing, no adapter swap. | **the new thing** |

They do not collide at runtime: a tool skill lives *inside* a turn that may or
may not have been routed by an ORBIT skill. To keep this unambiguous in code and
UI, the proposal names the new concept **tool skill** throughout, with the wire
name `tool_skill` and the admin tab labelled "Tool Skills".

> **Resolved in Phase 0 (§8, Q1).** A second reading of the request would be
> "expose ORBIT skills *as* MCP tools" — i.e. give the tool loop a synthetic
> `orbit__generate_image` tool that dispatches to the `image-generation` adapter.
> That is a different feature (skills as callable tools, not documents attached
> to tools). **Confirmed: this document's reading — procedural playbooks
> attached to tools — is what's being built.** Skills-as-callable-tools is
> deferred to a future roadmap item, not folded into this one.

---

## 2. Design

### 2.1 The skill document

```markdown
---
name: crm-pipeline-playbook
description: How to answer pipeline, renewal, and account-health questions using the CRM tools.
mcp_tools:
  - "business-sample__*"
  - "github__search_issues"
enabled: true
version: "1.0"
priority: 0
---

## Finding a customer

Always resolve the customer id with `list_customers` before calling
`build_account_plan` — the plan tool takes an id, never a name.

## Limits

`search_opportunities` rejects `limit` above 25. Page instead of raising it.

## Output

Group opportunities by owner and render as a markdown table: Owner | Account |
Stage | ARR | Close date.
```

`mcp_tools` is a glob list matched against the namespaced tool names ORBIT
already builds in `MCPClientManager._to_openai_tool` (`<server>__<tool>`), so
`"business-sample__*"` binds a whole server and
`"github__search_issues"` binds one tool. Binding lives in the **skill**, not in
`mcp_clients.yaml` — one authoring surface, and the MCP server entry stays
untouched.

**File name and frontmatter shape.** The document is named `SKILL.md`
(uppercase, matching the agentic-skills convention this proposal is deliberately
following) consistently across code, docs, and the panel — not "skill.md" in
some places and "SKILL.md" in others. `name` and `description` are the only
frontmatter keys a conventional skill document defines; `mcp_tools`, `enabled`,
`version`, and (§7 below) `priority` are **ORBIT-specific extensions** layered
on top for tool-binding and lifecycle management. State this explicitly in the
authoring docs so an author familiar with the general SKILL.md convention isn't
surprised by ORBIT-only fields, and isn't misled into thinking `mcp_tools` is
part of some external standard.

**Matching and conflict rules (must be nailed down in Phase 0, not discovered
in code review):**

- Matching uses `fnmatch`-style globs (`*`, `?`, `[seq]`) — not `pathlib`
  path-matching, which has different `/`-boundary semantics that don't apply to
  a flat `<server>__<tool>` string. Case-sensitive, matching the tool names
  themselves (server/tool names are already constrained to a lowercase slug
  pattern by the MCP server-creation validation in `routes/admin/mcp.py`, so
  case sensitivity should never surprise an author in practice).
- Skill `name` must itself be a lowercase slug (same pattern the MCP server
  name field already enforces), and the `orbit__` prefix is reserved — no
  skill or bound tool name may start with it, since that's the synthetic
  loader's own namespace.
- Multiple skills may match the same tool. All matches surface in the Level 1
  catalog and are independently loadable; ORBIT does not attempt to merge or
  pick one. If two loaded skills give contradictory guidance, that is an
  authoring problem for the admin to resolve, not something ORBIT arbitrates
  at runtime — Phase 4's eval harness (§4) is the intended way to catch this
  before it reaches production, not runtime conflict resolution.
- Catalog and dispatcher listings are sorted by `priority` (integer, default
  `0`, higher first) then by `name`, so ordering is deterministic across
  requests and workers rather than depending on dict/filesystem iteration
  order. `priority` also feeds the Phase 2 injection budget (§3): when more
  matched skills exist than the budget allows, lowest-priority skills are
  dropped first, and the drop is logged (§4 Phase 2 tests).
- A skill may bind tools from a server the requesting adapter cannot reach
  (outside its `mcp_servers` allowlist). This is not an error at authoring
  time — the same skill file may be shared across adapters with different
  scopes — but §2.5's "resolve which skills match the *filtered* tool list"
  step means such a skill simply never surfaces for that adapter. No warning
  is needed; this is the intended behavior of per-adapter scoping (§2.7).

### 2.2 How a skill reaches the model — progressive disclosure

Three levels, matching the agentic-skills paradigm. Levels 1 and 2 are Phase 1;
level 3 is Phase 2.

**The matched set and the surfaced set.** Two distinct things are computed per
turn, and it matters which one each piece of the mechanism uses:

- The **matched set** — every skill whose `mcp_tools` glob matches at least one
  tool in this turn's filtered tool list (§2.5), unbounded.
- The **surfaced set** — the matched set truncated to a cap (proposed: 10),
  sorted by `priority` then `name` (§2.1) so the same skills win a spot
  deterministically turn over turn.

**The surfaced set, and only the surfaced set, drives all three of:** the
Level 1 catalog listing, the Level 2 loader's `name` enum, and the Level 2
dispatcher's server-side authorization check. Using one capped set for all
three — rather than capping the catalog listing alone while leaving the enum
and authorization boundary unbounded — is required, not optional: a skill
omitted from the catalog must also be unloadable and unnamed in the schema, or
the cap is cosmetic (a skill the operator chose to hide from the catalog would
still cost enum tokens on every turn, and would still be loadable by a model
that somehow names it despite never seeing it listed).

**Level 3 explicitly does not consult the surfaced set — it uses the full
matched set.** This is a deliberate, stated exception, not an oversight: Level
3 injection is triggered by the model *actually invoking* a specific bound
tool, so there is no listing, no enum, and no token cost to cap in the first
place — the only content added to context is the one skill body attached to
that one tool's own result. Capping Level 3 to the surfaced set would mean a
skill silently dropped from the catalog (because a higher-priority skill
crowded it out) also loses its JIT correction on a tool it is bound to,
without the operator ever having decided that. The cap exists to bound
*listing and token* cost per turn; it was never meant to bound *which tools a
skill can attach behavioral guidance to* once that tool is actually called.

```
Available tool playbooks (call load_tool_skill to read one in full):
- crm-pipeline-playbook: How to answer pipeline, renewal, and account-health questions using the CRM tools.
```

Any excess beyond the surfaced-set cap is simply omitted — not an error, not
logged at per-request volume. See below for where a warning about oversized
matched sets is actually emitted (not at request time).

**Level 2 — on demand (the agentic path).** A synthetic tool is added to the
tool list handed to `generate_with_tools`, with the `name` parameter constrained
to an **enum of exactly the turn's surfaced set**:

```json
{"type":"function","function":{"name":"orbit__load_tool_skill",
 "description":"Read the full playbook for using a set of tools.",
 "parameters":{"type":"object","properties":{
   "name":{"type":"string","enum":["crm-pipeline-playbook"]}
 },"required":["name"]}}}
```

The enum is a UX aid (most providers will refuse to generate an out-of-enum
value, and some surface it as a hint in the UI), not the security boundary. The
dispatcher independently re-checks the requested `name` against that same
surfaced set server-side before loading anything — a model that emits a
guessed or hallucinated name, or the name of a matched-but-capped-out skill,
must not be able to read it; the dispatcher returns an error result for it
exactly like an unknown MCP tool name, never a lookup against the matched set
or the global registry. Rebuilding the surfaced set from scratch on every turn
is also what keeps this consistent with §2.7's per-adapter scoping: a skill an
adapter can't see never enters the matched set at all, so it can never reach
the surfaced set either.

When the model calls it, ORBIT returns the skill body **as a tool result**. No
provider change, no new loop — it rides the existing
`run_tool_calling_loop` exactly like an MCP tool. This is the whole mechanism.

**Idempotence and the injection budget.** A single skill is only ever loaded
once per turn, in Level 2 or Level 3 alike, and both draw from the same
per-turn budget (§3) — a determined or confused model calling
`orbit__load_tool_skill` repeatedly for the same skill cannot re-inflate
context by re-requesting it, and cannot exceed the turn's total skill-content
budget by combining Level 2 calls with Level 3's auto-injection. A second (or
later) request for an already-loaded skill returns a short fixed result (e.g.
`"crm-pipeline-playbook already loaded this turn."`) instead of the body
again — cheap enough that a retry loop can't be used to inflate cost, and
still a valid tool result rather than an error. The loop's per-turn state for
this (which skills have been delivered, in which form) lives alongside the
existing `sources` accumulator so it doesn't need new plumbing through
`run_tool_calling_loop`'s signature.

**Level 3 — just-in-time (Phase 2).** Small models often never think to call
`orbit__load_tool_skill`. So: the first time a bound tool is actually invoked in
a turn, inject its skill body once, unprompted. Level 2 remains for models that
ask first.

**Message representation.** The injection is *not* a bare `role: "system"`
message spliced mid-conversation (many providers only expect one system
message, at position zero, and a mid-thread system message is not a portable
pattern) and it is *not* an unmatched `role: "tool"` message either — a `tool`
message with no corresponding `tool_calls` entry on the preceding assistant
turn is exactly the kind of malformed history several providers validate
against and will reject. Instead, the skill body is appended, clearly
delimited and separately from the tool's own output, to the **existing**
`role: "tool"` message that already carries that call's real result — the one
`run_tool_calling_loop` already appends at `mcp_tool_loop.py:183`. Concretely:

```
<tool_result>
{actual MCP tool output}
</tool_result>
<trusted_skill name="crm-pipeline-playbook">
{skill body}
</trusted_skill>
```

This piggybacks on a message the loop already sends — no new message role, no
mid-thread system message, no risk of an unmatched `tool_call_id`. The two
tags are visually and structurally distinct on purpose (§3): the tool-result
content stays wrapped as untrusted server output; the skill body is delimited
separately and is never treated as if it came from the MCP server.

**Sibling tool calls in one assistant turn.** A single assistant turn can
request more than one tool call at once (e.g. two `summarize_pipeline` calls
for different regions, per `docs/adapters/mcp-agent.md`'s multi-region
example). If a bound tool and an unrelated MCP tool are both requested in that
same turn, Level 3's injection — attached to the bound tool's own result
message — cannot retroactively influence the *sibling* call, because both
calls were already generated by the model before either result comes back.
This is the same limitation as the first-call gap above, just triggered by
concurrent calls within one turn rather than by call ordering across turns;
it is not a new failure mode requiring separate mitigation, and the same
documentation callout in `docs/adapters/mcp-agent.md` (§4 Phase 2 exit
criteria) should name both cases together rather than only the sequential one.

> **Limitation: Level 3 cannot guide the *first* call to a bound tool.** By
> construction, the injection fires only after the model has already invoked
> the tool, so a constraint like "never pass `limit` above 25" arrives too late
> to shape that first call's arguments — it can only correct the *next* one (the
> model sees the tool's own validation error plus the skill body and retries).
> Level 3 is a genuine help for follow-up calls and for output formatting, but it
> is not a substitute for Level 2 when a skill must constrain the very first
> invocation. Three ways to close that gap, not adopted here but worth naming:
> (a) rely on Level 2 and accept that small models may skip it; (b) unconditionally
> inject matching skills before the *first* inference call of a turn, which is
> simple but reintroduces the per-turn token cost Level 3 was meant to avoid;
> (c) intercept the first call to a bound tool, return the skill body *instead of*
> executing it, and let the model retry with the skill in hand — closest to "just
> in time" but adds real branching to the loop. Phase 2 ships (a) + the
> after-the-fact version of Level 3 only; document the limitation in
> `docs/adapters/mcp-agent.md` rather than silently overselling JIT.

### 2.3 Runtime hook — one dispatcher shim

`run_tool_calling_loop` currently hardcodes execution:

```python
tool_result_text = await await_or_cancel(mcp_manager.call_tool(tool_name, arguments), cancel_event)
```
`server/inference/pipeline/mcp_tool_loop.py:168`

Phase 1 replaces `mcp_manager.call_tool` with an injected `dispatch` callable
defaulting to it, so `orbit__*` names route to local handlers and everything
else is unchanged. Both call sites (`MCPAgentStep._run_agent_loop` and
`LLMInferenceStep._run_inline_mcp_tools`) build the dispatcher. That is the only
edit to the loop — the return-value contract for `dispatch` is in §2.8, since
what it returns (not just that it's pluggable) is what keeps this change from
sprawling into logging and `sources`.

### 2.4 Prompt-cache interaction — do not get this wrong

`PromptInstructionBuilder.build_system_message` returns
`(content, cache_prefix_len)`, and `MCPAgentStep` forwards that breakpoint to
every provider call in the loop. The Level 1 catalog varies with the tool list,
which varies with the turn.

**Rule: the catalog goes *after* `cache_prefix_len`, never inside it.** Skill
bodies (Level 2 results, Level 3 injections) are conversation messages, so they
are naturally outside it. Getting this backwards silently invalidates
Anthropic prompt caching on every turn — a cost regression with no visible
symptom. Phase 1 needs an explicit test asserting `cache_prefix_len` is
unchanged by skill injection.

This requires reordering `MCPAgentStep._run_agent_loop`'s current sequence,
not just appending a string. Today's order is
`_build_initial_messages` (builds the system message and `cache_prefix_len`)
→ `_select_relevant_tools` (filters tools) → `run_tool_calling_loop`. Phase 1's
order is:

```
discover tools → filter tools (§2.5) → resolve matching skills (§2.1)
→ build system message + cache_prefix_len (unchanged call)
→ append the Level 1 catalog to the system message, after cache_prefix_len
→ append orbit__load_tool_skill to the (already-filtered) tool list
→ run the loop
```

i.e. tool discovery and skill resolution move *before* `_build_initial_messages`
so the catalog can be built in the same step that produces the system message,
still landing after the returned breakpoint. `cache_prefix_len` itself continues
to mark only the stable prefix ORBIT already computes; nothing about how that
value is derived needs to change.

### 2.5 Interaction with `MCPToolSelector`

`services/mcp_tool_selector.py` drops tools below an embedding threshold once
the count exceeds `tool_selection.max_tools`. Rather than teaching the selector
to special-case a synthetic name, `orbit__load_tool_skill` is added **after**
selection runs, never handed to it at all:

```
1. discover MCP tools
2. relevance-filter the MCP tools (MCPToolSelector, unmodified)
3. resolve the matched set: skills matching the *filtered* tool list (§2.1)
4. truncate to the surfaced set (§2.2's cap, sorted by priority/name)
5. if the surfaced set is non-empty, append orbit__load_tool_skill,
   enum = surfaced-set names, to the tool list
6. build the Level 1 catalog from that same surfaced set
7. run the loop (Level 3, when it fires, reads the full matched set — §2.2)
```

This keeps the selector's contract untouched (it only ever ranks real MCP
tools) and makes exemption unnecessary — the loader is structurally outside
what could be filtered. It also fixes a real bug the original ordering would
have introduced: `max_tool_iterations_for()` and `servers_in_tools()`
(`MCPAgentStep._run_agent_loop`) must be computed from the **MCP tool list**,
before `orbit__load_tool_skill` is appended — `servers_in_tools` parses server
names out of the `<server>__<tool>` prefix, and a synthetic `orbit__*` entry
has no corresponding server-level `max_tool_iterations` override to resolve.

**Where the "matched set exceeds the cap" warning actually fires.** It cannot
be computed at request time and logged there — the *matched* set already
depends on which tools survived per-request relevance filtering (step 2 above,
itself query-dependent), so "did this adapter's matched set exceed the cap"
has no single fixed answer to log once, and logging it per-request would spam
at request volume for what is really a static authoring problem. Instead:
`ToolSkillRegistry` computes it against each adapter's **statically reachable
tool set** — the full tool list `MCPClientManager` has cached for the servers
in that adapter's `mcp_servers` allowlist (§2.7), independent of any one
turn's query or relevance filtering — and (re-)checks it whenever that cached
tool set changes: at MCP tool-discovery refresh (`refresh_tool_cache`,
`services/mcp_client_service.py:375`) and whenever the skill registry itself
reloads (§2.6/§4 Phase 3's hot-reload path). A log line per affected adapter,
not per request, names which skills would be dropped from the surfaced set
under the worst case (every one of that adapter's bound tools appearing in a
single turn) so an operator can see the problem without ever needing a live
request to trigger it.

### 2.6 Storage — files first, database second

| | Phase 1 (files) | Phase 3 (database) |
|---|---|---|
| Location | `config/skills/<name>/SKILL.md` | `tool_skills` collection |
| Matches | ORBIT's YAML-first convention, `config/adapters/*.yaml` | `PromptService` / `system_prompts` (`server/services/prompt_service.py`) |
| Edited by | git | admin panel |

Both end up loaded by one `ToolSkillRegistry`. Precedence when a name exists in
both: **database wins**, file version is shown in the UI as the on-disk default
(same shape as an MCP server override, and legible in the panel). Phase 3
decides whether to also allow "revert to file", mirroring the MCP tab's
"Use default".

### 2.7 Per-adapter scoping

A new `AdapterCapabilities` field (`server/adapters/capabilities.py`), alongside
the existing `mcp_servers` allowlist:

```yaml
capabilities:
  mcp_servers: ["business-sample"]
  tool_skills: ["crm-pipeline-playbook"]   # omit = every skill matching a visible tool
```

> **Default when `tool_skills` is omitted is security-sensitive.** "Every skill
> matching a visible tool" means a newly-authored skill becomes visible to
> every adapter that can already reach the bound tool, the moment it's saved —
> no adapter-side opt-in required. That is the right default for a trusted
> single-tenant deployment (matches how `mcp_servers` itself defaults to "all
> enabled servers"), but is a meaningfully wider blast radius in a multi-tenant
> or tightly-governed deployment, where a skill author and an adapter owner may
> not be the same trust boundary. Document this explicitly next to the field in
> `capabilities.py` and in the admin panel's help text — do not let it read as
> an oversight later.

### 2.8 Dispatcher contract and result provenance

§2.3 replaces the loop's hardcoded `mcp_manager.call_tool(...)` with an
injected `dispatch` callable. To avoid the local-vs-remote distinction leaking
into ad-hoc `if tool_name.startswith("orbit__")` checks scattered across
logging, `sources`, persistence, and Phase 2's JIT path, `dispatch` returns a
small structured result rather than a bare string.

A single `trusted: bool` on the whole result is not expressive enough for
Level 3: that path produces **mixed-trust content** in one message — the
tool's own (untrusted) output plus the (trusted) skill body attached to it —
and one boolean cannot say "wrap the first part, don't wrap the second." The
contract instead separates the untrusted body from zero or more trusted
segments attached to it:

```python
@dataclass
class TrustedContext:
    name: str          # e.g. the skill's `name`
    body: str          # the trusted content itself (e.g. the skill body)
    kind: str = "tool_skill"   # namespace for future non-skill trusted attachments
    version: str | None = None  # per-item version, since one dispatch may carry several

@dataclass
class ToolDispatchResult:
    content: str                          # untrusted text — the tool's own output
    source_type: str = "mcp_tool_call"    # "mcp_tool_call" | "tool_skill_load" | future local kinds
    trusted_context: list[TrustedContext] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)  # dispatch-level extras only, e.g. call timing
```

`version` lives on `TrustedContext` itself, not in `ToolDispatchResult.metadata`
— `metadata` is one dict per dispatch, but `trusted_context` is a *list*, and a
single Level 3 dispatch can in principle carry more than one matched skill
attached to the same tool call (§2.1 already allows multiple skills to match
one tool). A dispatch-level `metadata` field cannot represent "skill A is at
version 2, skill B is at version 1" for two list entries; per-item `version`
can, so each `sources` entry built from a `TrustedContext` (below) carries its
own correct version regardless of how many ride along together.

The default dispatcher (unchanged behavior) wraps `mcp_manager.call_tool`'s
string result into `ToolDispatchResult(content=..., source_type="mcp_tool_call")`
with an empty `trusted_context`. Two dispatchers produce non-empty results,
covering Level 2 and Level 3 respectively:

- **Level 2** (the model explicitly calls `orbit__load_tool_skill`): the whole
  result *is* trusted content and there is no untrusted MCP output to carry
  alongside it, so this returns `ToolDispatchResult(content="",
  source_type="tool_skill_load", trusted_context=[TrustedContext(name=skill.name,
  body=skill.body, version=skill.version)])` — an
  empty `content` rather than repurposing it, so "no untrusted output on this
  particular result" stays structurally distinct from "empty output the MCP
  server actually returned."
- **Level 3** (auto-injection attached to a bound tool's own call): the
  dispatcher that executes the real MCP tool call returns
  `ToolDispatchResult(content=mcp_result, source_type="mcp_tool_call",
  trusted_context=[TrustedContext(name=skill.name, body=skill.body,
  version=skill.version)])` — one dispatch, one result, both segments present,
  because the trusted skill body and the untrusted tool output are two parts of
  the same event, not two separate dispatches. If more than one matched skill
  is bound to that tool, `trusted_context` holds one `TrustedContext` entry per
  skill, each independently versioned.

The loop renders `content` inside `<tool_result>` exactly as it does today,
then appends each `trusted_context` entry inside its own `<trusted_skill
name="...">` tag (§2.2), all within the same `role: "tool"` message — never
promoting either segment to another message or another role. This is what
makes the message-representation fix in §2.2 (no unmatched `tool` message, no
mid-thread `system` message) mechanically correct: there is exactly one
`ToolDispatchResult` per tool call, so exactly one `tool`-role message is
produced regardless of how many trusted segments ride along with it.

Two concrete consequences of doing this instead of reusing the MCP shape:

- **`sources` gets its own entry kind.** Today's loop unconditionally appends
  `{"type": "mcp_tool_call", "tool": ..., "result_preview": ...}`
  (`mcp_tool_loop.py:191`). Left unchanged, a skill load would masquerade as an
  MCP server call, get persisted into `mcp_tools_used`-style aggregates, and
  could leak the full skill body through `result_preview`'s 2000-character
  window. Phase 1 instead appends a `{"type": "tool_skill_load", "skill": name,
  "version": version}` entry for every non-empty `trusted_context` item — no
  body preview, no MCP-shaped fields — separately from (not instead of) the
  normal `mcp_tool_call` entry when `content` is also non-empty (the Level 3
  case), so a Level 3 turn's `sources` shows both the real tool call and the
  skill load it carried, and any reporting/analytics code that currently
  assumes every `sources` entry with `type == "mcp_tool_call"` came from an
  external server keeps that invariant.
- **The `<tool_result>` wrapping in §2.2/§3 applies only to `content`.**
  Trusted segments are delivered inside their own `<trusted_skill>` tag, never
  the `<tool_result>` one; untrusted content (actual MCP server output,
  including the tool-side validation error that triggers a Level 3 correction)
  keeps the existing wrapping unconditionally, regardless of whether trusted
  segments are attached to the same result.

Non-goal for Phase 1: `metadata`, `kind`, and the list shape (rather than a
single optional field) exist so a future local or trusted-attachment tool can
reuse the same dispatcher shape without another round of "special-case this
new name" edits — no such second tool is being built yet.

---

## 3. Security

Skill bodies are **trusted, admin-authored procedural context** — not
privileged instructions, and not tool output. Two things follow from that,
in opposite directions:

- Unlike tool results — which the loop deliberately wraps in `<tool_result>`
  tags because MCP server content is untrusted — a skill body is authored by an
  admin, so it never needs that untrusted-content wrapping.
- But delivering it with `role: "tool"` (Level 2) does **not** elevate its
  authority the way `role: "system"` would. Models generally weight
  system/developer instructions above tool-role content; a skill riding the
  tool channel inherits that lower priority, and this is the correct behavior,
  not a defect to fix. A skill must never be able to override the adapter's
  system prompt, safety/guardrail instructions, or tenancy/authorization
  constraints — it should only ever add procedural detail on top of them. Do
  not describe skill bodies as "privileged" in code comments or the panel copy;
  say "trusted procedural context" instead, so a future change doesn't try to
  "fix" this by promoting skills to `role: "system"`.

That difference drives the rest of this section:

- **Admin-only authorship.** CRUD sits behind the same `config_auth` dependency
  as the MCP endpoints (`server/routes/admin/mcp.py`). No request-time skill
  supply, ever — same posture as `mcp_clients.yaml` server definitions.
- **No MCP server may author a skill.** A skill is never derived from a tool
  description or a tool result.
- **Audit every write.** Create/update/delete land in the audit log with the
  full body diff; a skill body is as security-relevant as a system prompt.
- **Size caps.** Per-skill body cap (proposed 32 KB) and a per-turn injection
  budget (proposed: 3 skills / 24 KB) so a large library cannot blow the context
  window or the token bill.
- **No `${VAR}` expansion in bodies.** MCP connection fields expand env vars;
  skill bodies must not, or a skill becomes a secret-exfiltration primitive.
- **Never recorded or wrapped as an `mcp_tool_call`.** A Level 2 load is a
  *local* dispatch, not a call to an external MCP server, and must not be
  logged, sourced, or shaped as if it were one — see §2.8 for the concrete
  provenance fix.

---

## 4. Phases

Each phase is independently shippable and independently testable.

### Phase 0 — Decisions ✅ complete

All six decisions in §8 are locked. Summary (details and rationale in §8):

- **Semantics:** procedural playbooks attached to MCP tools (not skills-exposed-as-tools).
- **Binding location:** skill frontmatter (`mcp_tools` glob list), `mcp_clients.yaml` untouched.
- **Storage order:** files first (`config/skills/*/SKILL.md`) in Phase 1; DB + admin panel in Phase 3.
- **JIT default (Phase 2):** Level 3 auto-injection on by default once it ships.
- **Budget numbers:** accepted as proposed — 32 KB max per skill body, 3 skills / 24 KB per turn (Level 2/3 injection budget), 10 lines (Level 1 catalog cap).
- **Allowlist default:** omitting `capabilities.tool_skills` surfaces every skill matching the adapter's visible tools (matches `mcp_servers`' own default).

**Exit:** this document updated with all six answers recorded; Phase 1 unblocked.

### Phase 1 — Runtime core, file-based (≈3–4 days)

| Change | File |
|---|---|
| `ToolSkillRegistry` — load `config/skills/*/SKILL.md`, parse frontmatter, validate, glob-match tools, sort by priority/name | `server/services/tool_skill_service.py` (new) |
| `ToolDispatchResult` dataclass + dispatcher shim (`dispatch` param, default wraps `mcp_manager.call_tool`) | `server/inference/pipeline/mcp_tool_loop.py` |
| Build dispatcher + catalog *before* `_build_initial_messages`; append catalog after `cache_prefix_len`; append `tool_skill_load`-typed (not `mcp_tool_call`-typed) `sources` entries | `server/inference/pipeline/steps/mcp_agent.py` |
| `orbit__load_tool_skill` appended after selection runs, not exempted from it (§2.5) | `server/services/mcp_tool_selector.py` (unmodified) / `mcp_agent.py` |
| Example skill for the bundled CRM server | `config/skills/crm-pipeline-playbook/SKILL.md` |

**Tests** (`server/tests/`, `unit` marker unless noted):
- Registry: frontmatter parse, missing/invalid `name`, reserved `orbit__` prefix rejected, oversize body rejected, glob matching (`*`, exact, no-match, case-sensitive), `enabled: false` ignored, priority/name sort order deterministic.
- Dispatcher: `orbit__load_tool_skill` returns `ToolDispatchResult(content="", source_type="tool_skill_load", trusted_context=[...])`; unknown `orbit__*` returns an error result rather than raising; every other name reaches `mcp_manager.call_tool` unchanged and comes back `source_type="mcp_tool_call"` with an empty `trusted_context`; a Level 3 result (once Phase 2 lands) carries both non-empty `content` and a non-empty `trusted_context` in one dispatch.
- Loop: model calls the skill tool → body returned as tool result → next round proceeds (extend `test_inference/test_mcp_tool_loop.py`).
- **Provenance:** a skill load appends `{"type": "tool_skill_load", "skill": ..., "version": ...}` to `sources` — never `mcp_tool_call`, never a `result_preview` of the body — and does not get `<tool_result>`-wrapped.
- Catalog: only skills in the *surfaced set* appear (matched set truncated to the cap); empty registry adds nothing.
- **Cache:** `cache_prefix_len` identical with and without skills (§2.4), verifying the reordered `_run_agent_loop` sequence.
- Selector: `MCPToolSelector` never receives `orbit__load_tool_skill` as input, and its behavior on the real MCP tools is unchanged from today (regression test, not a new selector code path).
- Scoping: skills for servers outside `mcp_servers` never enter the matched set, so they never surface (no warning expected — see §2.1).
- `max_tool_iterations_for()`/`servers_in_tools()` computed from the MCP tool list only, unaffected by whether `orbit__load_tool_skill` was appended.
- **Surfaced-set consistency:** with a matched set larger than the cap, the catalog, the loader's `name` enum, and what the dispatcher will authorize are all built from the identical truncated surfaced set — a skill outside it is absent from all three, not just the catalog listing.
- **Enum authorization:** a request for a name outside the surfaced set (simulated directly against the dispatcher, bypassing the enum as a hostile/buggy client would) is rejected server-side rather than resolved against the matched set or the global registry — including a name that *is* in the matched set but was truncated out of the surfaced set.
- **Idempotence:** a second `orbit__load_tool_skill` call for the same skill in the same turn returns the fixed "already loaded" result, not the body again; verified this holds regardless of whether the first load was Level 2 or (once Phase 2 lands) Level 3.
- **Cap-vs-warning boundary:** the matched-set-exceeds-cap warning is asserted to fire only from tool-discovery-refresh/registry-reload paths against an adapter's statically reachable tool set (§2.5), never from a per-request code path — a test driving many differently-shaped requests against an oversized matched set must produce zero additional log lines beyond what discovery/reload already emitted.

**Exit:** with `skill: "mcp-agent"` and one `SKILL.md` on disk, a live request
shows an `orbit__load_tool_skill` call in `sources` followed by a tool-informed
answer. No UI.

### Phase 2 — Just-in-time injection + opportunistic parity (≈2–3 days)

- Level 3 auto-injection **after** the first bound-tool invocation, once per
  skill per turn — explicitly documented as unable to shape that first call's
  arguments (§2.2's limitation note); not sold as a full JIT guarantee.
- Same path wired into `LLMInferenceStep._run_inline_mcp_tools` so opportunistic
  mode gets skills too.
- `capabilities.tool_skills` allowlist (§2.7), including the security-sensitive
  default called out there.
- Injection budget caps (§3), dropping lowest-`priority` skills first (§2.1)
  with a log line naming what was dropped.

**Tests:** JIT fires once and only once per turn, and only after (never before) the bound tool's own call; a test asserting the first call to a bound tool is *not* preceded by its skill body, to lock in the documented limitation rather than silently regress it either direction; a test with two sibling tool calls in one assistant turn (one bound, one not) asserting the sibling call's arguments are unaffected; the injection is appended to the existing `role: "tool"` message for that call, not a new message, and a malformed-history check (no unmatched `tool_call_id`, no mid-thread `role: "system"`) runs against at least one provider's real message-validation path; a Level 2 call and a Level 3 injection for the same skill in the same turn count against one shared budget and one shared "already loaded" state; budget cap drops the lowest-priority skill and logs it; opportunistic path reaches parity with the explicit path; adapter allowlist honored; a turn calling no bound tool injects nothing.

**Exit:** a 4B local Ollama model benefits from a skill on its second and later
calls to a bound tool, without ever calling `orbit__load_tool_skill` — and the
mcp-agent docs state plainly that the first call isn't covered by this path.

### Phase 3 — Admin API + panel (≈4–5 days)

- `ToolSkillService` — DB CRUD + cache, modeled on `PromptService`.
- `server/routes/admin/skills.py` — list/create/update/delete/validate, `config_auth`, audit, size caps. Modeled on `routes/admin/prompts.py`.
- Hot reload + multi-worker convergence, reusing the MCP reload machinery
  (`_reload_mcp_clients`, `services/reload`, ≤5s cross-worker poll).
- `server/admin/admin_panel/tabs/skills.js` — master-detail like `mcp.js`:
  list on the left, frontmatter fields + markdown body on the right, a "Bound
  tools" section resolving globs against live discovery so an author sees
  immediately that `business-sample__*` matches 6 real tools (or zero, because
  the server is unreachable).
- `mcp.js`: read-only "Playbooks" row in each server's detail listing the skills
  bound to its tools, linking across to the Skills tab.
- File-vs-DB precedence surfaced in the UI (§2.6).

**Tests:** endpoint auth (401/403 without `config.write`), validation rejects bad frontmatter/oversize bodies, audit rows written, DB-over-file precedence, reload picks up a write without restart, and an `integration` test for the multi-worker path.

**Exit:** an admin authors and binds a skill end-to-end in the panel, with no restart.

### Phase 4 — Optional, only if Phases 1–3 prove out

- Bundled resources (extra files beside `SKILL.md`, loaded on a second call) — the full progressive-disclosure story.
- Skill versioning + an eval harness measuring tool-selection accuracy with and without a skill. This is the only honest way to know a skill helps.
- Tool skills for non-MCP tools (intent/function-calling adapters).

---

## 5. Effort

| Phase | Estimate | Ships value alone |
|---|---|---|
| 0 | 0.5 d | decisions |
| 1 | 3–4 d | yes — YAML-authored skills work end to end |
| 2 | 2–3 d | yes — small models benefit |
| 3 | 4–5 d | yes — non-engineers can author |
| 4 | open | optional |

**≈10–13 days to a complete Phase 1–3 feature.**

---

## 6. What this deliberately does not do

- No skill execution. A skill is text, never code.
- No request-time skill supply (same restriction MCP servers carry today).
- No change to any provider's `generate_with_tools`.
- No change to the ORBIT skill/adapter-swap routing mechanism.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| Prompt-cache invalidation from a per-turn catalog | §2.4 — catalog after the breakpoint; asserted by test |
| Token cost of the catalog on every turn (worst in opportunistic mode, where schemas already ship every turn) | one line per skill; only skills matching the filtered tool list; capped independently by its own catalog entry limit (§2.2), distinct from the Level 2/3 injection budget (§3), which governs loaded skill *bodies*, not catalog *listings* |
| Small models never call `orbit__load_tool_skill`, and JIT (Level 3) can't shape the first call to a bound tool either | Phase 2 Level 3 JIT injection after the first call, with the first-call gap explicitly documented rather than papered over (§2.2) |
| Skills contradict each other or the system prompt | per-adapter allowlist; skill content is subordinate to the system prompt by construction, not by convention (§3); budget cap; Phase 4 eval harness |
| A skill body is mistaken for privileged/system-level instruction in code or docs | consistently described as "trusted procedural context," never "privileged" (§3) |
| A skill load is misrecorded as an MCP server call, leaking its body via `result_preview` or polluting MCP-call analytics | dedicated `tool_skill_load` source type, no body preview (§2.8) |
| Two concepts named "skill" confuse operators and code | wire name `tool_skill`, UI label "Tool Skills" (§1) |
| DB/file precedence surprises | precedence stated in §2.6 and surfaced in the panel |
| Omitted `tool_skills` allowlist silently exposes a new skill to every adapter reaching its tools | documented as a security-sensitive default, not a neutral convenience default (§2.7) |
| A model guesses/hallucinates a skill name — or names a skill that matched but was truncated out of the surfaced set — and reads a skill it shouldn't | loader's `name` enum, and the dispatcher's server-side authorization, are both built from the same capped surfaced set (§2.2); a name outside it is rejected regardless of source |
| Catalog cap is cosmetic because the enum/authorization boundary stays unbounded | one surfaced set drives the catalog, the enum, and authorization together — never capped in one place and left open in another (§2.2) |
| Startup/reload warning for an oversized matched set can't be computed against a per-request filtered set | computed against each adapter's statically reachable tool set, emitted from tool-discovery-refresh and registry-reload paths, not per request (§2.5) |
| Repeated `orbit__load_tool_skill` calls (or Level 2 + Level 3 for the same skill) inflate context/cost within one turn | one shared per-turn budget across both levels; idempotent — a repeat load returns a fixed short result, not the body again (§2.2) |
| An unmatched `role: "tool"` message or a mid-thread `role: "system"` message is rejected by a provider's history validation | Level 3 appends the skill body to the existing tool-result message for that call, not a new message (§2.2) |
| Sibling tool calls generated in the same assistant turn can't be influenced by a same-turn skill injection | documented as the same class of limitation as the first-call gap, not a separate defect (§2.2) |

---

## 8. Decisions (Phase 0 — closed)

1. **Semantics** — ✅ **documents-attached-to-tools.** Procedural playbooks bound to MCP tools, not ORBIT-skills-exposed-as-tools (§1). This was the single most important question, since the two readings share almost no implementation; skills-as-callable-tools is deferred to a separate future roadmap item.
2. **Binding location** — ✅ **skill frontmatter.** `mcp_tools` glob list lives in the `SKILL.md` document; `mcp_clients.yaml` server entries are untouched.
3. **Storage order** — ✅ **files first.** `config/skills/*/SKILL.md` in Phase 1; `ToolSkillService` (DB) + admin panel in Phase 3.
4. **Injection default** — ✅ **on by default** once Level 3 (Phase 2) ships. Per §2.2, this only covers the second-and-later call to a bound tool, never the first — that limitation is documented, not silently accepted as a gap.
5. **Budget numbers** — ✅ **accepted as proposed.** 32 KB max per skill body; 3 skills / 24 KB per turn for the Level 2/3 injection budget; 10 lines for the separate Level 1 catalog cap (§2.2). These are config constants, tunable later against real usage.
6. **`tool_skills` allowlist default** — ✅ **omit-means-all-matching**, consistent with `mcp_servers`' own default (§2.7). Documented in `capabilities.py` and the admin panel's help text as a security-sensitive default (§2.7), not a neutral convenience one — worth revisiting per-deployment if a future multi-tenant use case needs the stricter opt-in variant.

---

## 9. Summary for the client

> ORBIT can support admin-authored `SKILL.md` playbooks associated with MCP
> tools, letting the model discover and load detailed procedural guidance
> before or during its tool-calling loop, without modifying the MCP servers
> themselves. This is distinct from having an MCP tool launch another ORBIT
> adapter or agent — confirmed (§8, Q1) as the intended scope; the
> launch-another-adapter variant is a separate, deferred idea. Phase 0 is
> complete; Phase 1 (runtime core, file-based, no UI) is ready to start.
