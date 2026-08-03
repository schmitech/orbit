# ORBIT Business MCP Server Example

This is a small Streamable HTTP MCP server you can use to test `config/mcp_clients.yaml` without relying on the dummy Python test server from `docs/adapters/mcp-agent.md`.

It exposes synthetic CRM and revenue tools backed by deterministic Faker data:

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

The support-ticket tools provide a complete CRUD example. They mutate only the
server's in-memory synthetic data; restarting the server restores the seeded
dataset. `delete_support_ticket` is deliberately described as a destructive
operation so an MCP client/model can reserve it for explicit user requests.

## Run

```bash
cd examples/mcp-server
npm install
MCP_TOKEN=test-secret npm start
```

The server listens at `http://127.0.0.1:9999/mcp` by default and requires:

```http
Authorization: Bearer test-secret
```

You can override the host, port, path, and token via environment variables or CLI flags:

```bash
# Using environment variables:
PORT=8080 MCP_TOKEN=test-secret npm start

# Or using CLI flags:
npm start -- --port=8080 --token=test-secret
```

Set `MCP_TOKEN=""` to disable auth for local experiments.

---

## Running as a Daemon (pm2)

### Install pm2

```bash
sudo npm install -g pm2
```

### Production / Daemon Setup

Build the project first, then start the MCP server process via `pm2`:

```bash
cd examples/mcp-server
npm run build

# Option A: Specify port via environment variable
PORT=8080 MCP_TOKEN=test-secret npx pm2 start npm --name "orbit-mcp-server" -- run start

# Option B: Pass port via CLI arguments
MCP_TOKEN=test-secret npx pm2 start npm --name "orbit-mcp-server" -- run start -- --port=8080

npx pm2 save
npx pm2 startup
```

Run the command printed by `pm2 startup` (requires sudo) to enable auto-start on reboot.

### Common pm2 commands

```bash
npx pm2 status                  # check running processes
npx pm2 logs orbit-mcp-server   # tail logs
npx pm2 restart orbit-mcp-server # restart the server
npx pm2 stop orbit-mcp-server    # stop the server
```

---

## ORBIT Config


Use this in `config/mcp_clients.yaml`. You can replace the existing `test-server`
entry that points to `server/tests/test_services/mcp_http_test_server.py`:

```yaml
mcp_clients:
  enabled: true
  servers:
    - name: "business-sample"
      transport: "http"
      url: "http://127.0.0.1:9999/mcp"
      token: "${MCP_TOKEN}"
      enabled: true
      allow_opportunistic: true   # needed only for opportunistic (no-skill) turns
```

Then run ORBIT with the same token in the environment:

```bash
export MCP_TOKEN=test-secret
```

If you keep the server name as `business-sample`, ORBIT will namespace tool
names as:

- `business-sample__list_customers`
- `business-sample__get_customer_health`
- `business-sample__search_opportunities`
- `business-sample__summarize_pipeline`
- `business-sample__build_account_plan`
- `business-sample__get_support_ticket`
- `business-sample__create_support_ticket`
- `business-sample__update_support_ticket`
- `business-sample__delete_support_ticket`

## Smoke Test

With the server running:

```bash
cd examples/mcp-server
MCP_URL=http://127.0.0.1:9999/mcp MCP_TOKEN=test-secret npm run smoke
```

You can also check the non-MCP health endpoint:

```bash
curl http://127.0.0.1:9999/health
```

Example prompts for an MCP-enabled adapter:

- "List the top Enterprise customers in EMEA and summarize renewal risk."
- "Find open Negotiation opportunities over $100k and group them by owner."
- "Build an account plan for customer `cus_0001` focused on renewal save."
- "Create a high-priority support ticket for `cus_0001` about a login outage."
- "Resolve ticket `tkt_0001`, then confirm its final status."

## Troubleshooting

- `401 Unauthorized`: make sure the `MCP_TOKEN` used to start this server
  matches the `MCP_TOKEN` in the shell where ORBIT runs.
- `EADDRINUSE`: another process is using port `9999`; rerun with `PORT=10099`
  and update `config/mcp_clients.yaml` to match.
- `failed to listen`: your environment blocked local port binding. Run from a
  normal terminal session rather than a restricted sandbox.
