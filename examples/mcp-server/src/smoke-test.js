import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

const url = process.env.MCP_URL || "http://127.0.0.1:9999/mcp";
const token = process.env.MCP_TOKEN || "test-secret";

const client = new Client({
  name: "orbit-business-sample-smoke-test",
  version: "0.1.0"
});

const transport = new StreamableHTTPClientTransport(new URL(url), {
  requestInit: {
    headers: {
      Authorization: `Bearer ${token}`
    }
  }
});

try {
  await client.connect(transport);

  const tools = await client.listTools();
  const names = tools.tools.map((tool) => tool.name).sort();
  console.log("Discovered tools:", names.join(", "));

  for (const expected of ["list_customers", "get_customer_health", "search_opportunities", "summarize_pipeline", "build_account_plan"]) {
    if (!names.includes(expected)) {
      throw new Error(`Missing expected tool: ${expected}`);
    }
  }

  const listResult = await client.callTool({
    name: "list_customers",
    arguments: { region: "North America", limit: 3 }
  });
  console.log("list_customers result:");
  console.log(listResult.content[0].text);

  const parsed = JSON.parse(listResult.content[0].text);
  const customerId = parsed.customers[0]?.id;
  if (!customerId) {
    throw new Error("No customer id returned from list_customers.");
  }

  const healthResult = await client.callTool({
    name: "get_customer_health",
    arguments: { customerId }
  });
  console.log("get_customer_health result:");
  console.log(healthResult.content[0].text);

  const oversizedLimitResult = await client.callTool({
    name: "search_opportunities",
    arguments: { stage: "Negotiation", limit: 50 }
  });
  const oversizedLimitPayload = JSON.parse(oversizedLimitResult.content[0].text);
  if (oversizedLimitPayload.count > 25) {
    throw new Error(`Expected oversized limit to be clamped to 25, got ${oversizedLimitPayload.count}`);
  }

  await client.close();
  console.log("Smoke test passed.");
} catch (error) {
  await client.close().catch(() => {});
  console.error(error);
  process.exitCode = 1;
}
