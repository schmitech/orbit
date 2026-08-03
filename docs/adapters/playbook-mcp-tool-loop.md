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
- `get_product_telemetry`
- `list_support_tickets`
- `get_support_ticket`
- `create_support_ticket`
- `update_support_ticket`
- `delete_support_ticket`
- `simulate_churn_risk_scenario`
- `get_sales_rep_performance`

## 2. Enable MCP + opportunistic mode

`config/mcp_clients.yaml` already points at this server as `business-sample`:

```yaml
mcp_clients:
  enabled: true
  servers:
    - name: "business-sample"
      transport: "http"
      url: "http://127.0.0.1:9999/mcp"
      token: "${MCP_TOKEN}"
      enabled: true
      allow_opportunistic: true    # ← set this to true
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

### F. The server-side gate overrides the per-adapter flag

Temporarily set `allow_opportunistic: false` on the `business-sample` server in
`config/mcp_clients.yaml` (leave `mcp_tools: true` on the adapter), restart,
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

### I. Multi-dimensional churn risk & telemetry audit (3+ step tool chain)

> "Find the Enterprise customer in EMEA with open P1 support cases, check their product telemetry for seat utilization, and run a churn risk simulation."

This multi-step query requires cross-tool reasoning:
1. `list_support_tickets` (priority="P1", region="EMEA") or `list_customers` (segment="Enterprise", region="EMEA").
2. `get_product_telemetry` for the target customer ID to evaluate seat utilization and active usage.
3. `simulate_churn_risk_scenario` with `arrImpactPct` to forecast potential revenue loss.

Confirm `sources` captures the sequence of tool calls and that the final synthesized response correlates the SLA breaches and product usage with the simulated churn probability.

### J. Rep performance & quota risk aggregation

> "Which sales representative in APAC has the highest revenue pipeline at risk due to open SLA breaches?"

Requires:
1. `search_opportunities` (region="APAC") or `list_support_tickets` (region="APAC", slaBreachedOnly=true).
2. `get_sales_rep_performance` to evaluate rep attainment, active deal count, and SLA breach burden.

Confirm the model aggregates rep metrics correctly and identifies the rep with highest at-risk pipeline.

### K. Comprehensive account save playbook synthesis

> "Generate an executive account plan for customer cus_0005 incorporating their recent support tickets and seat utilization trends."

Requires:
1. `get_customer_health` or `list_support_tickets` (customerId="cus_0005").
2. `get_product_telemetry` (customerId="cus_0005").
3. `build_account_plan` (customerId="cus_0005", objective="renewal save and product adoption").

Confirm that telemetry metrics (active vs purchased seats) and unresolved ticket details are merged into the final account plan structure.

### L. CRUD lifecycle: create, read, update, and delete a support ticket

The business sample also exposes a state-changing CRUD surface for **synthetic,
in-memory support tickets**. It is intended to demonstrate that MCP tools can
perform mutations as well as retrieve data. A server restart resets this data.

Run this sequence in one conversation, retaining the id returned by the create
operation:

1. > "Create a P2 support ticket for cus_0005 titled 'Unable to export the quarterly usage report.'"
2. > "Show me the ticket you just created."
3. > "Mark that ticket resolved and change its priority to P3."
4. > "Delete the ticket we just created."

Expected calls and outcomes:

- Step 1 calls `create_support_ticket`; its result contains the server-assigned
  `ticket.id` (for example, `tkt_0091`).
- Step 2 calls `get_support_ticket` using that id, unless the model can answer
  directly from the preceding tool result.
- Step 3 calls `update_support_ticket` with the same id and returns
  `updated: true` and `status: "resolved"`.
- Step 4 calls `delete_support_ticket` only after the user explicitly requests
  deletion and returns `deleted: true` with the removed ticket.

Confirm every mutation appears in `sources` as an `mcp_tool_call`, the final
answer identifies the actual ticket id, and a final `get_support_ticket` call
for the deleted id produces the normal not-found tool error. This checks both
state persistence across MCP requests and that the tool loop can carry an id
from one mutation to the next.

For a single-turn, multi-call version, ask:

> "Create a P3 support ticket for cus_0005 about export access, then retrieve it and change its status to in_progress. Do not delete it."

Confirm the model calls `create_support_ticket`, then uses the returned id for
`get_support_ticket` and `update_support_ticket`, and that it does not call the
destructive delete tool without an explicit instruction.

## Manual/Integration Check: GitHub MCP Tool

A second, hosted example for the same opportunistic tool-calling path,
using GitHub's own remote MCP server instead of a local process. Good for
verifying `http` transport, `headers`-based auth (as opposed to the
`token` shorthand `business-sample` uses), and read-only/code-search-style
tools rather than a CRM's structured-data tools.

### 1. Get a token — nothing to start locally

Unlike `business-sample`, there's no local server to run: GitHub hosts this
endpoint directly at `https://api.githubcopilot.com/mcp/`.

Create a **fine-grained, read-only** personal access token scoped to the repo
you want to test against (Contents, Issues, Pull requests: Read-only is
enough for everything below — do not grant write scopes for testing). Export
it in the shell where ORBIT runs:

```bash
export GITHUB_TOKEN=github_pat_xxx...
```

### 2. Enable MCP + opportunistic mode

`config/mcp_clients.yaml` already has a `github` entry:

```yaml
- name: "github"
  transport: "http"
  url: "https://api.githubcopilot.com/mcp/"
  headers:
    Authorization: "Bearer ${GITHUB_TOKEN}"
  enabled: true
  allow_opportunistic: true
```

Note this server authenticates via an explicit `headers.Authorization` entry,
not the `token:` shorthand `business-sample` uses — the admin panel's
Connection section reflects that: editing `token` for this server is
rejected there since `headers` already overrides it.

### 3. Enable the capability on an adapter

Add `"github"` to an adapter's `mcp_servers` allowlist (`mcp_tools: true`
must already be set):

```yaml
capabilities:
  mcp_tools: true
  mcp_servers:
    - "business-sample"
    - "github"
```

Restart ORBIT after editing `mcp_clients.yaml` or the adapter config, or
apply the change from the admin panel's MCP tab instead — server/defaults
edits there hot-reload without a restart (see the MCP Admin API section of
`docs/adapters/mcp-agent.md`).

### 4. Trigger a tool call

Point questions at a real repo you have read access to (your own fork or
`schmitech/orbit` if the PAT covers it) — the model can't answer these from
training data since it needs live repo state:

> "List the open issues in schmitech/orbit."

> "What were the last 5 commits to schmitech/orbit's main branch?"

> "Search schmitech/orbit for code that references `_validate_mcp_connection`."

Confirm:
- The response reflects actual current repo state, not a plausible-sounding
  guess (cross-check against the GitHub UI).
- `sources` contains an `mcp_tool_call` entry named `github__<tool>` (e.g.
  `github__search_issues`, `github__list_commits` — exact tool names come
  from GitHub's own MCP server and may change as it evolves; use
  `GET /admin/mcp/tools` or the panel's "Test connection" to see the current
  set).

### 5. Confirm the model declines when no tool is needed

Follow up in the same session with something that needs no live repo data:

> "What's the difference between a GitHub issue and a pull request?"

Confirm a normal conversational answer — no `sources`, no tool call.

### Additional scenarios specific to GitHub

**Nonexistent resource**: ask about an issue/PR number that doesn't exist in
the repo (e.g. "Show me PR #999999 in schmitech/orbit"). Confirm the model
reports it couldn't find the PR rather than fabricating a plausible-sounding
one — the same error-handling path as scenario B above, but worth checking
separately since GitHub's own error shape differs from the sample server's.

**Read-only scope enforcement**: with a read-only PAT, ask the model to do
something that would require a write (e.g. "Close issue #1 in
schmitech/orbit" or "Create a new issue titled ..."). Confirm the tool call
fails with a permissions error surfaced back to the model, and the model
reports it cannot perform the action — it must not claim success for an
action GitHub actually rejected.

**Multi-step chaining**: a question needing two tool calls, mirroring
scenario A above:

> "Find the most recently closed issue in schmitech/orbit and check whether
> the PR that closed it is still open or merged."

Confirm two `mcp_tool_call` entries in `sources`, in order, and that the
final answer's PR status matches what the tool actually returned.

## Troubleshooting

- `401 Unauthorized` from the MCP server: the `MCP_TOKEN` used to start
  `examples/mcp-server` must match the `MCP_TOKEN` in ORBIT's environment.
- `EADDRINUSE`: another process is using port `9999` — rerun with
  `PORT=10099` and update the `url` in `config/mcp_clients.yaml` to match.
- Health check: `curl http://127.0.0.1:9999/health`.
- Smoke test the server standalone: `cd examples/mcp-server && MCP_TOKEN=test-secret npm run smoke`.
- **GitHub server, `401`/`403`**: `GITHUB_TOKEN` is missing, expired, or lacks
  the scope for the repo/action being tested — regenerate the token and
  re-export it in ORBIT's environment (a restart or a Settings-tab reload is
  needed to pick up a changed env var, since it's read once at process start,
  unlike `mcp_clients.yaml` edits).
- **GitHub server unreachable in the panel's "Test connection"**: this is a
  hosted third-party endpoint, not a local process — check your network can
  reach `api.githubcopilot.com` before assuming a config problem.
