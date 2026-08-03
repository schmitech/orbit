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

  const expectedTools = [
    "list_customers",
    "get_customer_health",
    "search_opportunities",
    "summarize_pipeline",
    "build_account_plan",
    "get_product_telemetry",
    "list_support_tickets",
    "get_support_ticket",
    "create_support_ticket",
    "update_support_ticket",
    "delete_support_ticket",
    "simulate_churn_risk_scenario",
    "get_sales_rep_performance"
  ];

  for (const expected of expectedTools) {
    if (!names.includes(expected)) {
      throw new Error(`Missing expected tool: ${expected}`);
    }
  }

  const listResult = await client.callTool({
    name: "list_customers",
    arguments: { region: "North America", limit: 3 }
  });
  const parsed = JSON.parse(listResult.content[0].text);
  const customerId = parsed.customers[0]?.id;
  if (!customerId) {
    throw new Error("No customer id returned from list_customers.");
  }
  console.log("✓ list_customers passed.");

  const healthResult = await client.callTool({
    name: "get_customer_health",
    arguments: { customerId }
  });
  console.log("✓ get_customer_health passed.");

  const telemetryResult = await client.callTool({
    name: "get_product_telemetry",
    arguments: { customerId }
  });
  const telemetryParsed = JSON.parse(telemetryResult.content[0].text);
  if (!telemetryParsed.seats) {
    throw new Error("Missing seats object in telemetry response.");
  }
  console.log("✓ get_product_telemetry passed.");

  const ticketsResult = await client.callTool({
    name: "list_support_tickets",
    arguments: { customerId, limit: 5 }
  });
  console.log("✓ list_support_tickets passed.");

  const createTicketResult = await client.callTool({
    name: "create_support_ticket",
    arguments: {
      customerId,
      subject: "Smoke-test ticket for CRUD verification",
      priority: "P2 - High"
    }
  });
  const createdTicket = JSON.parse(createTicketResult.content[0].text).ticket;
  if (!createdTicket?.id) {
    throw new Error("create_support_ticket did not return a ticket id.");
  }
  console.log("✓ create_support_ticket passed.");

  const getTicketResult = await client.callTool({
    name: "get_support_ticket",
    arguments: { ticketId: createdTicket.id }
  });
  if (JSON.parse(getTicketResult.content[0].text).ticket?.id !== createdTicket.id) {
    throw new Error("get_support_ticket did not return the created ticket.");
  }
  console.log("✓ get_support_ticket passed.");

  const updateTicketResult = await client.callTool({
    name: "update_support_ticket",
    arguments: { ticketId: createdTicket.id, status: "resolved", slaBreached: false }
  });
  if (JSON.parse(updateTicketResult.content[0].text).ticket?.status !== "resolved") {
    throw new Error("update_support_ticket did not persist the updated status.");
  }
  console.log("✓ update_support_ticket passed.");

  const deleteTicketResult = await client.callTool({
    name: "delete_support_ticket",
    arguments: { ticketId: createdTicket.id }
  });
  if (!JSON.parse(deleteTicketResult.content[0].text).deleted) {
    throw new Error("delete_support_ticket did not confirm deletion.");
  }
  const deletedTicketLookup = await client.callTool({
    name: "get_support_ticket",
    arguments: { ticketId: createdTicket.id }
  });
  if (!deletedTicketLookup.isError) {
    throw new Error("Deleted ticket was still returned by get_support_ticket.");
  }
  console.log("✓ delete_support_ticket passed.");

  const churnSimResult = await client.callTool({
    name: "simulate_churn_risk_scenario",
    arguments: { customerId, arrImpactPct: 80 }
  });
  const churnParsed = JSON.parse(churnSimResult.content[0].text);
  if (!churnParsed.simulationResults) {
    throw new Error("Missing simulationResults in churn scenario response.");
  }
  console.log("✓ simulate_churn_risk_scenario passed.");

  const repPerfResult = await client.callTool({
    name: "get_sales_rep_performance",
    arguments: { owner: "Avery Chen" }
  });
  console.log("✓ get_sales_rep_performance passed.");

  const oversizedLimitResult = await client.callTool({
    name: "search_opportunities",
    arguments: { stage: "Negotiation", limit: 50 }
  });
  const oversizedLimitPayload = JSON.parse(oversizedLimitResult.content[0].text);
  if (oversizedLimitPayload.count > 25) {
    throw new Error(`Expected oversized limit to be clamped to 25, got ${oversizedLimitPayload.count}`);
  }
  console.log("✓ Clamp limit assertion passed.");

  await client.close();
  console.log("\nAll smoke tests passed successfully!");
} catch (error) {
  await client.close().catch(() => {});
  console.error(error);
  process.exitCode = 1;
}
