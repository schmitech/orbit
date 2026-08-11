# Next Steps

**Level 5 and beyond**

You've worked through the leveled path — orientation, foundations, core services, composition, and skills/MCP tools. From here, these are the deep-reference docs for going further, grouped by what you're trying to do next.

## Configuration reference

- [Configuration Reference (`config.yaml`)](../../install/default-config/config.yaml) — full, commented configuration reference
- [Adapter Configuration Management](../adapters/adapter-configuration.md) — splitting adapters across files, imports, per-key model overrides
- [Adapter Creation (SDK)](../adapters/adapter-creation.md) — scaffold adapter YAML from the admin panel or CLI instead of hand-writing it
- [Capability Reference](../adapters/capabilities/capability-reference.md) — every `capabilities:` field, by adapter type

## Deep dives on what you've already used

- [SQL Retriever Architecture](../sql-retriever-architecture.md) — intent SQL internals
- [Composite Intent Retriever](../adapters/composite-intent-retriever.md) — multi-source routing details
- [Intent Agent Retriever](../adapters/intent-agent-retriever.md) — function calling & custom tools
- [Skills — Cross-Adapter Capabilities](../adapters/skills.md) — the full skills reference
- [MCP Agent Skill](../adapters/mcp-agent.md) — the complete MCP tool-calling guide

## Advanced/production topics not yet covered

- [Grounded Real-Time Voice](../adapters/grounded-realtime-voice.md) — speech-to-speech adapters grounded against your retrievers
- [API Keys Guide](../api-keys.md) — advanced key management
- [Authentication Guide](../authentication.md) — users and roles
- [`orbitchat` chat client](../../clients/orbitchat/README.md) — CLI flags, `orbitchat.yaml` config, proxy-only mode, and the HTTP contract for custom UIs

---

[Previous: Troubleshooting](troubleshooting.md) | [Tutorial home](../tutorial.md)

---
