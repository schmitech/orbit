# Skills, MCP Tools, and Skill Routing

**Level 4 · Skills, skill routing & MCP tools**

Four terms show up together once you get past basic adapters, and they get confusing fast because they all sound like "the model does something extra": **adapter**, **skill**, **capability flag**, and **MCP tool**. This page draws the lines between them before you try any of the four numbered examples in this level ([Skills and Image Generation](skills-image-generation.md), [Opportunistic MCP Tool Calling](mcp-tool-calling.md), [Web Search and Automatic Skill Routing](auto-skill-routing.md)) — read this one first.

## The four terms

- **Adapter** — a configured endpoint in `config/adapters/*.yaml`. What you've been building since Level 1. One adapter = one `name` = one thing an API key can be bound to.
- **Capability flag** — a field under an adapter's `capabilities:` block that turns a behavior on or off (`retrieval_behavior`, `supports_threading`, `mcp_tools`, `auto_skill_routing`, ...). See [Capability Reference](../adapters/capabilities/capability-reference.md) for the full list.
- **Skill** — any adapter that's been marked invocable by *other* adapters, via two fields on itself (`capabilities.expose_as_skill: true` and `capabilities.skill_name: "..."`) and one field on the caller (`capabilities.available_skills: ["..."]`). A skill is not a new adapter type — `image-generator` (the `Image` skill) is a completely normal adapter that happens to also be callable from `simple-chat-with-files` for one message at a time, without switching API keys or adapters.
- **MCP tool** — a tool exposed by an *external* MCP server (not an ORBIT adapter at all), which a conversational adapter can call directly via `capabilities.mcp_tools: true` + `mcp_servers: [...]`. No `skill_name`, no `available_skills` entry — MCP tools are a different mechanism from skills, configured separately in `config/mcp_clients.yaml`.

## How a request gets routed

For any given chat message, one of four things happens, checked roughly in this order:

```
1. Request carries an explicit "skill": "<name>" field?
   → That skill runs. Nothing else is considered. (Example 9)

2. No explicit skill, but auto_skill_routing is on for this adapter
   and the message matches an allowed skill's routing phrases?
   → ORBIT infers the skill and routes to it, same as if the
     client had sent "skill": "<name>". (Example 11, Part 2)

3. No skill matched, but mcp_tools is on and the adapter has
   MCP servers configured?
   → The model may call any discovered MCP tool, on this turn,
     without leaving the conversational adapter. (Example 10)

4. None of the above?
   → Ordinary conversational or retrieval answer. No skill,
     no tool call.
```

Explicit `skill` always wins — auto-routing and MCP tool calling only ever run when the client didn't already say what it wanted.

## Why this needs its own page

Skills and MCP tool calling look similar from the outside (both let "one adapter do more than its usual job for one message"), but they're configured completely differently and solve different problems:

| | Skills | MCP tools (opportunistic) |
|---|---|---|
| What runs | Another ORBIT **adapter** | A tool on an **external MCP server** |
| Declared where | `capabilities.available_skills` on the caller, `expose_as_skill`/`skill_name` on the callee | `capabilities.mcp_tools` + `mcp_servers` on the adapter, server itself declared in `config/mcp_clients.yaml` |
| Invocation | Explicit `skill` field, or inferred via auto-routing | Model decides per-turn, natively, no client-side field at all |
| Typical use | Image/document generation, provider-native web search | Your own business tools — CRM lookups, internal APIs, anything with an MCP server |

If you only remember one distinction: **skills reuse ORBIT's own adapters; MCP tools reach outside ORBIT to your own tool servers.** Both can be triggered "automatically" (auto-skill-routing for skills, opportunistic mode for MCP), and both can coexist on the same adapter — auto-skill-routing is checked first, so a matched skill preempts the MCP loop for that turn.

## Where to go from here

1. [Skills and Image Generation](skills-image-generation.md) — your first skill, using the `Image` generator as the example. Also introduces the full generator cluster (documents, media) that all follow this same pattern.
2. [Opportunistic MCP Tool Calling](mcp-tool-calling.md) — wiring up an external MCP server and letting the model call it on any turn.
3. [Web Search and Automatic Skill Routing](auto-skill-routing.md) — the auto-routing mechanism from step 2 above, in practice.

For the full reference depth behind all of this, see [Skills — Cross-Adapter Capabilities](../adapters/skills.md), [Automatic Skill Intent Detection](../adapters/auto-skill-intent-detection.md) (design rationale), and [MCP Agent Skill](../adapters/mcp-agent.md) (the complete MCP guide, including the explicit `mcp-agent` skill as a third, template-free calling style not covered above).

---

[Tutorial home](../tutorial.md) | [Previous: Example 8: Agent with Function Calling](agent-function-calling.md) | [Next: Example 9: Skills and Image Generation](skills-image-generation.md)

---
