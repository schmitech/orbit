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
npm run sla        # listens on http://localhost:8081
```

## Running as a Daemon (pm2)

To keep the SLA Metrics API running continuously in the background, you can deploy it using `pm2`.

> **Note:** The SLA server runs on port **8081** with process name `orbit-sla-server`, while the main MCP server runs on port **9999** with process name `orbit-mcp-server`. Both can run concurrently via `pm2` without any port or process name conflicts.

### Install pm2

```bash
sudo npm install -g pm2
```

### Production / Daemon Setup

Build the project first, then start the SLA server process via `pm2`:

```bash
cd examples/mcp-server
npm run build

# Option A: Run via npm script (default port 8081)
npx pm2 start npm --name "orbit-sla-server" -- run sla

# Option B: Specify port via environment variable
SLA_PORT=8081 npx pm2 start npm --name "orbit-sla-server" -- run sla

# Option C: Pass port via CLI arguments
npx pm2 start npm --name "orbit-sla-server" -- run sla -- --port=8081

npx pm2 save
npx pm2 startup
```

Run the command printed by `pm2 startup` (requires sudo) to enable auto-start on reboot.

### Common pm2 commands

```bash
npx pm2 status                  # check running processes
npx pm2 logs orbit-sla-server   # tail logs
npx pm2 restart orbit-sla-server # restart the server
npx pm2 stop orbit-sla-server    # stop the server
```

## Endpoints

- `GET /customers/:customerId/sla` — SLA status for one customer
  ```bash
  curl http://localhost:8081/customers/cus_0007/sla
  ```
- `GET /sla/breaches?minBreaches=1&limit=10` — customers with SLA breaches
  ```bash
  curl "http://localhost:8081/sla/breaches?minBreaches=1"
  ```
- `GET /sla/summary?segment=Enterprise&region=APAC` — portfolio-level SLA summary
  ```bash
  curl "http://localhost:8081/sla/summary?segment=Enterprise"
  ```

No authentication is required.

## Related example

Used by the `intent-http-sla-metrics` adapter, composed with the
`intent-sql-sqlite-billing` adapter via ORBIT's composite intent retriever.
See `examples/customer-360-composite/README.md`.
