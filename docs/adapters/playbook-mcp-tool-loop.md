# Manual/Integration Check: Opportunistic MCP Tool Calling

Steps to verify after implementation, in order.

## 1. Start the sample MCP server

Uses the semi-realistic business/CRM sample server under `examples/mcp-server`
(synthetic customers, opportunities, and pipeline data via Faker) instead of
the dummy Python test server:

```bash
cd examples/mcp-server
npm install
MCP_TOKEN=test-secret npm start
```

This listens at `http://127.0.0.1:9999/mcp` and exposes:

- `list_customers`
- `get_customer_health`
- `search_opportunities`
- `summarize_pipeline`
- `build_account_plan`

## 2. Enable MCP + opportunistic mode

`config/mcp_client.yaml` already points at this server as `business-sample`:

```yaml
mcp_client:
  enabled: true
  allow_opportunistic: true      # ← set this to true
  servers:
    - name: "business-sample"
      transport: "http"
      url: "http://127.0.0.1:9999/mcp"
      token: "${MCP_TOKEN}"
      enabled: true
```

Export the same token in the shell where ORBIT runs:

```bash
export MCP_TOKEN=test-secret
```

## 3. Enable the capability on the adapter

Using `config/adapters/passthrough.yaml`'s `simple-chat` adapter — simpler
than `simple-chat-with-files` since there's no file-RAG/multimodal behavior
to reason about, just plain conversational + tools. Its `capabilities:`
block already has:

```yaml
mcp_tools: true
mcp_servers:
  - "business-sample"
```

`simple-chat` uses `inference_provider: "openai"`, which supports native
tool calling — no provider change needed.

Restart ORBIT after editing any of these YAML files — they're loaded at
startup.

## 4. Trigger a tool call

Send a message with **no** `skill` field:

> "List the top Enterprise customers in EMEA and summarize renewal risk."

or:

> "Find open Negotiation opportunities over $100k and group them by owner."

Confirm:
- The response includes tool-derived content (customer/opportunity data).
- `sources` contains an `mcp_tool_call` entry with a tool name like
  `business-sample__search_opportunities`.
- This works in **both** streaming and non-streaming modes.

## 5. Confirm the model declines when no tool is needed

Send a follow-up message in the same session that doesn't need a tool (e.g.
"What is retrieval-augmented generation?").

Confirm a normal conversational answer is returned — no `sources`, proving
the model isn't forced to call a tool every turn.

## 6. Run the checks

```bash
ruff check server/
pytest server/tests/
```

---

## Additional Test Scenarios

Once the basic smoke test above passes, these dig into edge cases the model
and the pipeline need to handle correctly. None of these require config
changes unless noted.

### A. Multi-step tool chaining

A single question that can't be answered by one tool call — the model has
to call one tool, read the result, then decide to call another:

> "Find the EMEA customer with the lowest health score and build a
> renewal-save account plan for them."

This needs at least two rounds: `list_customers` (region=EMEA) to find the
customer, then `build_account_plan` with that customer's id and
`objective: "renewal save"`. Confirm `sources` shows **two** `mcp_tool_call`
entries in the right order, and the final answer references the actual
customer found (not a generic/hallucinated one).

### B. Tool error handling

Ask about a customer id that doesn't exist — ids only run `cus_0001` through
`cus_0036`:

> "Get the health snapshot for customer cus_9999."

The tool returns `isError: true` with `"Customer 'cus_9999' was not found."`
That error text is fed back to the model as the tool result (wrapped in
`<tool_result>` tags — see `mcp_tool_loop.py`). Confirm the model
acknowledges the customer wasn't found in its final answer rather than
crashing, returning a raw JSON error, or hallucinating data.

### C. Model declines when the question is generic

Contrast these two, in the same session:

> "In general, what are some best practices for reducing customer renewal
> risk?"

(expect a plain conversational answer, no `sources`) vs.

> "What are the renewal risks for cus_0010 specifically?"

(expect a `get_customer_health` tool call). This is the same check as step 5
but with a closer pair of prompts — useful for judging how good the model is
at telling "generic knowledge question" from "needs live data" when the two
are topically similar.

### D. Conversation continuity without re-calling the tool

In the same session:

1. "List the top 3 Enterprise customers in North America."
2. Follow up: "What's the health score of the first one you listed?"

Watch whether turn 2 answers directly from the conversation history already
in `context_messages` (no new tool call) or calls `get_customer_health`
again for that customer id. Either is a reasonable model choice — the point
of this check is confirming conversation history from turn 1 (including the
tool results baked into the assistant's response) is actually available to
the model on turn 2, since opportunistic mode never swaps adapters or
resets context.

### E. `mcp_servers` allowlist actually scopes tool access

Temporarily remove `"business-sample"` from `simple-chat`'s `mcp_servers` in
`config/adapters/passthrough.yaml` (leave `mcp_tools: true` in place), restart,
and re-ask a business question (e.g. "List the top Enterprise customers in
EMEA"). Confirm no tool is called — plain conversational answer, no
`sources`, model says it doesn't have access to live CRM data. Restore the
allowlist afterward.

### F. Global gate overrides the per-adapter flag

Temporarily set `mcp_client.allow_opportunistic: false` in
`config/mcp_client.yaml` (leave `mcp_tools: true` on the adapter), restart,
and re-ask a business question. Confirm the tool is never called even
though the adapter capability is still enabled — this is the two-gate
design working as intended (see `docs/adapters/mcp-agent.md#opportunistic-mode`).
Restore `allow_opportunistic: true` afterward.

### G. Provider fallback when the runtime model doesn't support tool calling

`simple-chat`'s `allowed_models` includes `nemotron-3-ultra` (provider:
`openrouter`), which does **not** implement `generate_with_tools`. Send a
request with `"model": "nemotron-3-ultra"` in the body against a
business-data question. Confirm:
- The request still succeeds (no 500, no user-facing error).
- The server log shows a warning like `"Adapter 'simple-chat' has mcp_tools
  enabled but provider 'openrouter' does not support generate_with_tools;
  falling back to plain generation."` — note it names **`openrouter`** (the
  actually-resolved runtime provider), not `openai` (the adapter's static
  default). An earlier version of this fix mislabeled the warning with the
  adapter's default provider regardless of the runtime override — if you see
  `provider 'openai'` here while testing a `"model"` override, that's the
  bug this scenario is meant to catch.
- The response is a plain generated answer with no `sources` — it can't
  fabricate CRM data it never fetched.

This exercises the `NotImplementedError` fallback path described in
`docs/adapters/mcp-agent.md`'s Opportunistic Mode section.

### H. Multiple tool calls in a single turn

> "Summarize the pipeline for EMEA and separately for APAC."

This may produce two `summarize_pipeline` calls (one per region) either in
the same round or across consecutive iterations, depending on the model.
Confirm both regions' numbers appear correctly attributed in the final
answer and both show up as separate entries in `sources`.

## Troubleshooting

- `401 Unauthorized` from the MCP server: the `MCP_TOKEN` used to start
  `examples/mcp-server` must match the `MCP_TOKEN` in ORBIT's environment.
- `EADDRINUSE`: another process is using port `9999` — rerun with
  `PORT=10099` and update the `url` in `config/mcp_client.yaml` to match.
- Health check: `curl http://127.0.0.1:9999/health`.
- Smoke test the server standalone: `cd examples/mcp-server && MCP_TOKEN=test-secret npm run smoke`.
