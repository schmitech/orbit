# ORBIT Business MCP Server Example

This is a small Streamable HTTP MCP server you can use to test `config/mcp_client.yaml` without relying on the dummy Python test server from `docs/adapters/mcp-agent.md`.

It exposes synthetic CRM and revenue tools backed by deterministic Faker data:

- `list_customers`
- `get_customer_health`
- `search_opportunities`
- `summarize_pipeline`
- `build_account_plan`

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

You can override the host, port, path, and token:

```bash
HOST=127.0.0.1 PORT=9999 MCP_PATH=/mcp MCP_TOKEN=test-secret npm start
```

Set `MCP_TOKEN=""` to disable auth for local experiments.

## ORBIT Config

Use this in `config/mcp_client.yaml`. You can replace the existing `test-server`
entry that points to `server/tests/test_services/mcp_http_test_server.py`:

```yaml
mcp_client:
  enabled: true
  servers:
    - name: "business-sample"
      transport: "http"
      url: "http://127.0.0.1:9999/mcp"
      token: "${MCP_TOKEN}"
      enabled: true
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

## Smoke Test

With the server running:

```bash
cd examples/mcp-server
MCP_TOKEN=test-secret npm run smoke
```

You can also check the non-MCP health endpoint:

```bash
curl http://127.0.0.1:9999/health
```

Example prompts for an MCP-enabled adapter:

- "List the top Enterprise customers in EMEA and summarize renewal risk."
- "Find open Negotiation opportunities over $100k and group them by owner."
- "Build an account plan for customer `cus_0001` focused on renewal save."

## Troubleshooting

- `401 Unauthorized`: make sure the `MCP_TOKEN` used to start this server
  matches the `MCP_TOKEN` in the shell where ORBIT runs.
- `EADDRINUSE`: another process is using port `9999`; rerun with `PORT=10099`
  and update `config/mcp_client.yaml` to match.
- `failed to listen`: your environment blocked local port binding. Run from a
  normal terminal session rather than a restricted sandbox.
