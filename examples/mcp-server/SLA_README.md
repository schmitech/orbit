# SLA Metrics API (companion to the MCP business server)

A tiny REST/JSON API (no MCP protocol) that serves support SLA metrics for the
same synthetic customers used by the MCP business server (`src/server.js`).
It imports `data.js` directly, so customer IDs (`cus_0001`…`cus_0036`) and
names are identical across both servers — no drift, no duplication.

This exists so ORBIT's `IntentHTTPJSONRetriever` can query SLA data over
plain HTTP. It is intentionally separate from the MCP server, which is only
reachable via MCP tool-calling and cannot be routed through the composite
intent retriever.

## Run

```bash
cd examples/mcp-server
npm install
npm run sla        # listens on http://localhost:9998
```

## Endpoints

- `GET /customers/:customerId/sla` — SLA status for one customer
  ```bash
  curl http://localhost:9998/customers/cus_0007/sla
  ```
- `GET /sla/breaches?minBreaches=1&limit=10` — customers with SLA breaches
  ```bash
  curl "http://localhost:9998/sla/breaches?minBreaches=1"
  ```
- `GET /sla/summary?segment=Enterprise&region=APAC` — portfolio-level SLA summary
  ```bash
  curl "http://localhost:9998/sla/summary?segment=Enterprise"
  ```

No authentication is required.

## Related example

Used by the `intent-http-sla-metrics` adapter, composed with the
`intent-sql-sqlite-billing` adapter via ORBIT's composite intent retriever.
See `examples/customer-360-composite/README.md`.
