import express from "express";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { z } from "zod";
import { data, money, normalize } from "./data.js";

const PORT = Number(process.env.PORT || 9999);
const HOST = process.env.HOST || "127.0.0.1";
const MCP_PATH = process.env.MCP_PATH || "/mcp";
const REQUIRED_TOKEN = process.env.MCP_TOKEN || process.argv.find((arg) => arg.startsWith("--token="))?.slice("--token=".length) || "test-secret";
const DEFAULT_LIMIT = 10;
const MAX_LIMIT = 25;

function requireBearerToken(req, res, next) {
  if (!REQUIRED_TOKEN) {
    next();
    return;
  }

  const expected = `Bearer ${REQUIRED_TOKEN}`;
  if (req.get("authorization") !== expected) {
    res.status(401).json({ error: "Unauthorized" });
    return;
  }
  next();
}

function createMcpServer() {
  const server = new McpServer({
    name: "orbit-business-sample",
    version: "0.1.0"
  });

  server.tool(
    "list_customers",
    "List synthetic customers with useful CRM fields. Filter by region, segment, industry, owner, health score, or ARR.",
    {
      region: z.string().optional().describe("Case-insensitive region filter, for example North America, EMEA, APAC, LATAM."),
      segment: z.string().optional().describe("Case-insensitive segment filter: SMB, Mid-Market, or Enterprise."),
      industry: z.string().optional().describe("Case-insensitive industry filter."),
      owner: z.string().optional().describe("Case-insensitive account owner filter."),
      minHealthScore: z.number().int().min(0).max(100).optional(),
      minArr: z.number().int().min(0).optional().describe("Minimum annual recurring revenue in USD."),
      limit: z.coerce.number().int().optional().describe("Maximum number of customers to return. Values above 25 are clamped to 25.")
    },
    async ({ region, segment, industry, owner, minHealthScore, minArr, limit }) => {
      const resultLimit = clampLimit(limit);
      const rows = data.customers
        .filter((customer) => !region || normalize(customer.region) === normalize(region))
        .filter((customer) => !segment || normalize(customer.segment) === normalize(segment))
        .filter((customer) => !industry || normalize(customer.industry) === normalize(industry))
        .filter((customer) => !owner || normalize(customer.owner).includes(normalize(owner)))
        .filter((customer) => minHealthScore == null || customer.healthScore >= minHealthScore)
        .filter((customer) => minArr == null || customer.annualRecurringRevenue >= minArr)
        .sort((a, b) => b.annualRecurringRevenue - a.annualRecurringRevenue)
        .slice(0, resultLimit)
        .map((customer) => ({
          id: customer.id,
          name: customer.name,
          region: customer.region,
          segment: customer.segment,
          industry: customer.industry,
          owner: customer.owner,
          arr: money(customer.annualRecurringRevenue),
          healthScore: customer.healthScore,
          renewalDate: customer.renewalDate,
          openSupportCases: customer.openSupportCases
        }));

      return textResult({ count: rows.length, customers: rows });
    }
  );

  server.tool(
    "get_customer_health",
    "Get a detailed health snapshot for one synthetic customer, including risk signals and related open opportunities.",
    {
      customerId: z.string().describe("Customer id returned by list_customers, for example cus_0007.")
    },
    async ({ customerId }) => {
      const customer = data.customers.find((row) => row.id === customerId);
      if (!customer) {
        return textResult({ error: `Customer '${customerId}' was not found.` }, true);
      }

      const opportunities = data.opportunities
        .filter((opportunity) => opportunity.customerId === customer.id)
        .sort((a, b) => b.weightedAmount - a.weightedAmount)
        .slice(0, 5);

      return textResult({
        customer,
        annualRecurringRevenueFormatted: money(customer.annualRecurringRevenue),
        opportunities: opportunities.map(formatOpportunity),
        recommendedAttention: customer.healthScore < 60 || customer.riskSignals.length >= 2
          ? "High"
          : customer.healthScore < 75
            ? "Medium"
            : "Normal"
      });
    }
  );

  server.tool(
    "search_opportunities",
    "Search synthetic sales opportunities by stage, region, owner, value, or close date.",
    {
      stage: z.string().optional().describe("Case-insensitive stage, for example Proposal or Negotiation."),
      region: z.string().optional(),
      owner: z.string().optional(),
      minAmount: z.number().int().min(0).optional(),
      closeBefore: z.string().optional().describe("ISO date string, for example 2026-09-30."),
      limit: z.coerce.number().int().optional().describe("Maximum number of opportunities to return. Values above 25 are clamped to 25.")
    },
    async ({ stage, region, owner, minAmount, closeBefore, limit }) => {
      const resultLimit = clampLimit(limit);
      const rows = data.opportunities
        .filter((opportunity) => !stage || normalize(opportunity.stage) === normalize(stage))
        .filter((opportunity) => !region || normalize(opportunity.region) === normalize(region))
        .filter((opportunity) => !owner || normalize(opportunity.owner).includes(normalize(owner)))
        .filter((opportunity) => minAmount == null || opportunity.amount >= minAmount)
        .filter((opportunity) => !closeBefore || opportunity.closeDate <= closeBefore)
        .sort((a, b) => b.weightedAmount - a.weightedAmount)
        .slice(0, resultLimit)
        .map(formatOpportunity);

      return textResult({ count: rows.length, opportunities: rows });
    }
  );

  server.tool(
    "summarize_pipeline",
    "Summarize synthetic revenue pipeline by region, segment, and stage.",
    {
      region: z.string().optional(),
      segment: z.string().optional(),
      includeClosed: z.boolean().default(false)
    },
    async ({ region, segment, includeClosed }) => {
      const rows = data.opportunities
        .filter((opportunity) => includeClosed || !opportunity.stage.startsWith("Closed"))
        .filter((opportunity) => !region || normalize(opportunity.region) === normalize(region))
        .filter((opportunity) => !segment || normalize(opportunity.segment) === normalize(segment));

      const byStage = groupSum(rows, "stage");
      const byRegion = groupSum(rows, "region");
      const totalAmount = rows.reduce((sum, row) => sum + row.amount, 0);
      const weightedAmount = rows.reduce((sum, row) => sum + row.weightedAmount, 0);

      return textResult({
        filters: { region: region || "all", segment: segment || "all", includeClosed },
        opportunityCount: rows.length,
        totalPipeline: money(totalAmount),
        weightedPipeline: money(weightedAmount),
        byStage,
        byRegion
      });
    }
  );

  server.tool(
    "build_account_plan",
    "Build a short account follow-up plan for a customer and business objective.",
    {
      customerId: z.string(),
      objective: z.string().describe("Example: renewal save, executive expansion, support escalation, procurement follow-up.")
    },
    async ({ customerId, objective }) => {
      const customer = data.customers.find((row) => row.id === customerId);
      if (!customer) {
        return textResult({ error: `Customer '${customerId}' was not found.` }, true);
      }

      return textResult({
        customer: {
          id: customer.id,
          name: customer.name,
          owner: customer.owner,
          primaryContact: customer.primaryContact,
          healthScore: customer.healthScore,
          renewalDate: customer.renewalDate
        },
        objective,
        plan: [
          `Confirm ${objective} success criteria with ${customer.primaryContact.name}.`,
          `Review health score ${customer.healthScore} and address ${customer.openSupportCases} open support case(s).`,
          `Prepare an executive summary covering ARR ${money(customer.annualRecurringRevenue)}, active seats, and renewal timeline.`,
          customer.riskSignals.length
            ? `Mitigate risk signals: ${customer.riskSignals.join(", ")}.`
            : "Identify one expansion or adoption metric to create a proactive next step."
        ],
        nextMeetingAgenda: [
          "Business outcome recap",
          "Current risks and blockers",
          "Commercial timeline",
          "Owners and dates for next actions"
        ]
      });
    }
  );

  return server;
}

function textResult(payload, isError = false) {
  return {
    isError,
    content: [
      {
        type: "text",
        text: JSON.stringify(payload, null, 2)
      }
    ]
  };
}

function clampLimit(value) {
  if (value == null) {
    return DEFAULT_LIMIT;
  }
  return Math.min(Math.max(value, 1), MAX_LIMIT);
}

function formatOpportunity(opportunity) {
  return {
    id: opportunity.id,
    name: opportunity.name,
    customerId: opportunity.customerId,
    customerName: opportunity.customerName,
    owner: opportunity.owner,
    region: opportunity.region,
    segment: opportunity.segment,
    stage: opportunity.stage,
    amount: money(opportunity.amount),
    probability: `${opportunity.probability}%`,
    weightedAmount: money(opportunity.weightedAmount),
    closeDate: opportunity.closeDate,
    nextStep: opportunity.nextStep
  };
}

function groupSum(rows, key) {
  return Object.fromEntries(
    Object.entries(
      rows.reduce((acc, row) => {
        acc[row[key]] ??= { count: 0, totalAmount: 0, weightedAmount: 0 };
        acc[row[key]].count += 1;
        acc[row[key]].totalAmount += row.amount;
        acc[row[key]].weightedAmount += row.weightedAmount;
        return acc;
      }, {})
    ).map(([name, value]) => [
      name,
      {
        count: value.count,
        totalPipeline: money(value.totalAmount),
        weightedPipeline: money(value.weightedAmount)
      }
    ])
  );
}

const app = express();
app.use(express.json({ limit: "1mb" }));

app.get("/health", (_req, res) => {
  res.json({
    ok: true,
    name: "orbit-business-sample",
    transport: "streamable-http",
    mcpPath: MCP_PATH,
    auth: REQUIRED_TOKEN ? "bearer-required" : "disabled"
  });
});

app.all(MCP_PATH, requireBearerToken, async (req, res) => {
  if (req.method !== "POST") {
    res.set("Allow", "POST").status(405).json({ error: "Method Not Allowed" });
    return;
  }

  const server = createMcpServer();
  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: undefined
  });

  res.on("close", () => {
    transport.close();
    server.close();
  });

  try {
    await server.connect(transport);
    await transport.handleRequest(req, res, req.body);
  } catch (error) {
    console.error("[mcp-server] request failed", error);
    if (!res.headersSent) {
      res.status(500).json({ jsonrpc: "2.0", error: { code: -32603, message: "Internal server error" }, id: null });
    }
  }
});

const httpServer = app.listen(PORT, HOST, () => {
  console.log(`[mcp-server] listening on http://${HOST}:${PORT}${MCP_PATH}`);
  if (REQUIRED_TOKEN) {
    console.log("[mcp-server] requiring Authorization: Bearer <token>");
  }
});

httpServer.on("error", (error) => {
  console.error(`[mcp-server] failed to listen on ${HOST}:${PORT}: ${error.message}`);
  process.exitCode = 1;
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    httpServer.close(() => {
      process.exit(0);
    });
  });
}
