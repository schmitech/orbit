# SLA Metrics HTTP Adapter

Queries a small local REST API (`examples/mcp-server/src/sla-server.js`)
serving support SLA compliance metrics for the same synthetic customers used
by the billing SQLite adapter and the MCP business server. Part of the
Customer 360 composite example — see
`examples/customer-360-composite/README.md`.

## Run the mock API

```bash
cd examples/mcp-server
npm install
npm run sla   # listens on http://localhost:9998
```

## Files

- `templates/sla_metrics_domain.yaml` — entity/vocabulary domain definition
- `templates/sla_metrics_templates.yaml` — 3 intent templates: SLA status for
  one customer, SLA breach list, portfolio SLA summary

## Registered adapter

`intent-http-sla-metrics` in `config/adapters/billing-sla.yaml`.

## Try it

```
"What's the SLA compliance rate for cus_0012?"
"Which customers have SLA breaches?"
"Show me SLA summary for Enterprise customers"
```
