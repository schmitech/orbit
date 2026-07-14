# Example 11: Web Search and Automatic Skill Routing

Two related features that both let a conversational adapter do more than plain chat without the client sending an explicit `skill` field: the **web search** skill (provider-native search grounding) and **automatic skill routing** (ChatGPT-style intent detection that infers a skill from plain language). Both are already enabled on `simple-chat` in this repo — no config changes needed to try them.

## Part 1 — Web search skill

The `web-search` skill lets a request answer with up-to-date information by enabling the inference provider's native web search for that one call — no separate search API, no dedicated adapter type.

[`config/adapters/web-search.yaml`](../../config/adapters/web-search.yaml) exposes a `web-search-chat` adapter with `capabilities.web_search: true` and `expose_as_skill: true`. Try it explicitly:

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: orbit_YOUR_SIMPLE_CHAT_KEY" \
  -d '{
    "messages": [{"role": "user", "content": "What are the top news headlines today?"}],
    "skill": "web-search"
  }'
```

The response is normal text with inline citations the model produced from its search. Only `gemini`, `openai`, and `xai` support provider-native web search; the skill adapter pins one of these regardless of the calling adapter's own provider.

> Need a provider-agnostic search (DuckDuckGo, Brave, Serper, Tavily, ...) instead of relying on the LLM provider's built-in search? See [`config/adapters/web-search-providers.yaml`](../../config/adapters/web-search-providers.yaml) and [Web Search](../adapters/web-search.md).

## Part 2 — Automatic skill routing

Instead of the client naming a skill, ORBIT can infer it from the message itself — "turn this into a PDF", "read it aloud", "search the web for X" — the same per-turn, model-decides behavior ChatGPT and Claude have.

This requires two switches, both already on in `config/config.yaml` and `config/adapters/passthrough.yaml` for `simple-chat`:

```yaml
# config/config.yaml — global gate
skill_routing:
  auto_detect: true
```

```yaml
# config/adapters/passthrough.yaml — per-adapter opt-in
capabilities:
  auto_skill_routing: true
  auto_routable_skills:
    - "Image"
    - "web-search"
    # ...
```

### Try it

With your `simple-chat` API key, send a message with **no** `skill` field:

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: orbit_YOUR_SIMPLE_CHAT_KEY" \
  -d '{"messages": [{"role": "user", "content": "search the web for the latest news on AI regulation"}]}'
```

Confirm the response is grounded with current information even though `skill` was never sent — ORBIT's embedding pre-filter matched the phrase to `web-search`, and a small confirm LLM call selected it.

Contrast with a message that shouldn't route anywhere:

```bash
curl -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: orbit_YOUR_SIMPLE_CHAT_KEY" \
  -d '{"messages": [{"role": "user", "content": "What is retrieval-augmented generation?"}]}'
```

Confirm this returns a plain conversational answer — the embedding pre-filter found no matching skill, so no extra LLM call happened and no routing occurred.

### How it works

1. **Embedding pre-filter** — the message is embedded and compared against each candidate skill's description/routing phrases. If nothing clears `embedding_threshold`, the turn is answered normally with no extra LLM call.
2. **LLM confirm** — a small, constrained call picks exactly one surviving candidate or `NONE`, disambiguating similar skills and rejecting false positives ("draft an email *about* PDFs" shouldn't trigger the PDF skill).
3. **Explicit always wins.** If the request carries a `skill` field, detection never runs.
4. **Coexists with opportunistic MCP** ([Example 10](mcp-tool-calling.md)) — skill detection runs first; a matched skill preempts the MCP loop for that turn.

`simple-chat` intentionally keeps auto-routable skills (`Image`, `Audio`, `PDF`, `web-search`, ...) out of `available_skills`, so a client can't invoke them directly via `skill=` or the `/` picker — ORBIT can only reach them by inferring intent from plain language. Retrieval skills (`HR`, `business-analytics`, `mcp-agent`) stay explicit-only in `available_skills` and are never auto-routed.

See [Skills — Cross-Adapter Capabilities](../adapters/skills.md#automatic-intent-detection) for the full mechanism and config reference, [Automatic Skill Intent Detection](../adapters/auto-skill-intent-detection.md) for the design rationale, and [`docs/adapters/playbook-auto-skill-routing.md`](../adapters/playbook-auto-skill-routing.md) for a full manual verification checklist.

---

[Tutorial home](../tutorial.md) | [Previous: Example 10: Opportunistic MCP Tool Calling](mcp-tool-calling.md) | [Next: Example 12: Message Queue (Async) Requests](message-queue-async.md)

---
