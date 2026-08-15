# Customer 360 Composite Example: Billing (SQLite) + Support SLA (HTTP)

Tutorial walkthrough: [Example 13: Customer 360 — Cross-Adapter Composition](../../docs/tutorial/customer-360-cross-adapter.md).

This directory also includes a ready-to-use persona/system prompt
([`customer-360-prompt.md`](customer-360-prompt.md)) and a suggested-questions
intro ([`customer-360-intro.md`](customer-360-intro.md)) for creating the API
key and testing this adapter in the admin panel or OrbitChat.

This example demonstrates the real value of ORBIT's composite intent
retriever: composing **genuinely related domain data** that lives in two
different systems, rather than routing across topically unrelated sources
(the other `composite.yaml` examples span HR, EV population data, movies,
and analytics — useful for showing routing mechanics, but they don't share
any data).

Here, two intent adapters share the same customer ID space
(`cus_0001`…`cus_0036`) used by the sample MCP business server in
`examples/mcp-server/`:

- **`intent-sql-sqlite-billing`** — contracts, invoices, and payments, in a
  SQLite database (`examples/intent-templates/sql-intent-template/sqlite/billing/`).
- **`intent-http-sla-metrics`** — support SLA compliance metrics, served by a
  small local REST API (`examples/mcp-server/src/sla-server.js`).

Both are wired together by `composite-customer-360` in
`config/adapters/composite.yaml`, with cross-adapter templates in
`examples/intent-templates/cross-adapter-template/billing_sla_cross_adapter_templates.yaml`
that route "customer 360" style queries to both sources in parallel and merge
the results.

## Why the MCP server isn't part of the composition

`examples/mcp-server/` (the CRM data — customers, opportunities, support
tickets) is exposed only as an **MCP tool-calling** surface
(`config/adapters/mcp-agent.yaml`). ORBIT's composite/cross-adapter retriever
only routes across `type: retriever, adapter: intent` adapters (SQL/HTTP) —
it has no mechanism for including MCP tool-calling adapters as a
`child_adapter` or `target_adapters` entry. The MCP server stays untouched
and available as its own separate skill on the same customer domain; the
billing and SLA adapters are the ones actually demonstrating cross-system
composition. Its `sla-server.js` companion, however, is a plain REST API (no
MCP protocol) built specifically so `IntentHTTPJSONRetriever` can query it.

## Setup

```bash
# 1. Start the SLA metrics mock API
cd examples/mcp-server
npm install
npm run sla                              # http://localhost:8081

# 2. Generate the billing database (in a separate terminal)
cd examples/intent-templates/sql-intent-template/sqlite/billing
python3 generate_billing_data.py --force  # creates billing.db

# 3. Restart the ORBIT server so the new adapters load
python3 server/main.py
```

## Demo queries

1. **Billing only** — "What invoices are overdue for customer cus_0007?"
   Routes solely to `intent-sql-sqlite-billing` (`list_overdue_invoices`).

2. **SLA only** — "What's the SLA compliance rate for cus_0012?"
   Routes solely to `intent-http-sla-metrics` (`get_sla_status_for_customer`),
   which calls `GET http://localhost:8081/customers/cus_0012/sla`.

3. **Cross-adapter (the payoff)** — "Show me billing and support SLA status
   for customer cus_0021"
   Matches `customer_360_billing_and_sla`, fans out to both adapters in
   parallel, and merges results `side_by_side` labeled "Billing" / "Support
   SLA".

4. **Cross-adapter portfolio query** — "Which customers have both overdue
   invoices and SLA breaches?"
   Matches `compare_overdue_billing_and_sla_breaches`, aggregating from both
   sources so the LLM can correlate customer IDs present in both result sets.

Send these through `/v1/chat/completions` targeting the
`composite-customer-360` adapter and inspect the response metadata's
`composite_routing` field to confirm which adapter(s) were selected.
