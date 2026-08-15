import express from "express";
import { data, normalize } from "./data.js";

const portArg = process.argv.find((arg) => arg.startsWith("--port="))?.slice("--port=".length);
const PORT = Number(process.env.SLA_PORT || portArg || 8081);
const HOST = process.env.HOST || "0.0.0.0";

const PLAN_TIER_BY_SEGMENT = {
  SMB: "Starter",
  "Mid-Market": "Growth",
  Enterprise: "Enterprise"
};

const SLA_TARGET_HOURS_BY_TIER = {
  Starter: 48,
  Growth: 24,
  Enterprise: 8
};

function buildSlaRecord(customer) {
  const planTier = PLAN_TIER_BY_SEGMENT[customer.segment] || "Starter";
  const slaTargetHours = SLA_TARGET_HOURS_BY_TIER[planTier];
  const tickets = data.supportTickets.filter((ticket) => ticket.customerId === customer.id);
  const closedLast30d = tickets.filter((ticket) => ticket.status === "resolved").length;
  const breachesLast90d = tickets.filter((ticket) => ticket.slaBreached).length;
  const complianceRatePct = tickets.length
    ? Math.round(((tickets.length - breachesLast90d) / tickets.length) * 100)
    : 100;

  return {
    customerId: customer.id,
    customerName: customer.name,
    planTier,
    slaTargetHours,
    avgFirstResponseHours: Math.round(slaTargetHours * (0.3 + (100 - customer.healthScore) / 200) * 10) / 10,
    avgResolutionHours: Math.round(slaTargetHours * (0.8 + (100 - customer.healthScore) / 100) * 10) / 10,
    ticketsOpen: tickets.filter((ticket) => ticket.status !== "resolved").length,
    ticketsClosedLast30d: closedLast30d,
    breachesLast90d,
    complianceRatePct,
    lastBreachDate: tickets.filter((ticket) => ticket.slaBreached).at(-1)?.createdAt ?? null
  };
}

const slaByCustomerId = new Map(data.customers.map((customer) => [customer.id, buildSlaRecord(customer)]));

const app = express();

app.get("/health", (_req, res) => {
  res.json({ ok: true, name: "orbit-sla-metrics-api" });
});

app.get("/customers/:customerId/sla", (req, res) => {
  const record = slaByCustomerId.get(req.params.customerId);
  if (!record) {
    res.status(404).json({ error: `Customer '${req.params.customerId}' was not found.` });
    return;
  }
  res.json(record);
});

app.get("/sla/breaches", (req, res) => {
  const minBreaches = req.query.minBreaches != null ? Number(req.query.minBreaches) : 0;
  const limit = req.query.limit != null ? Number(req.query.limit) : 25;

  const rows = Array.from(slaByCustomerId.values())
    .filter((record) => record.breachesLast90d >= minBreaches)
    .sort((a, b) => b.breachesLast90d - a.breachesLast90d)
    .slice(0, limit)
    .map((record) => ({
      customerId: record.customerId,
      customerName: record.customerName,
      breachesLast90d: record.breachesLast90d,
      complianceRatePct: record.complianceRatePct
    }));

  res.json(rows);
});

app.get("/sla/summary", (req, res) => {
  const { segment, region } = req.query;
  const customerById = new Map(data.customers.map((customer) => [customer.id, customer]));

  const rows = Array.from(slaByCustomerId.values()).filter((record) => {
    const customer = customerById.get(record.customerId);
    if (!customer) return false;
    if (segment && normalize(customer.segment) !== normalize(segment)) return false;
    if (region && normalize(customer.region) !== normalize(region)) return false;
    return true;
  });

  res.json(rows);
});

const httpServer = app.listen(PORT, HOST, () => {
  console.log(`[sla-server] listening on http://${HOST}:${PORT}`);
});

httpServer.on("error", (error) => {
  console.error(`[sla-server] failed to listen on ${HOST}:${PORT}: ${error.message}`);
  process.exitCode = 1;
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    httpServer.close(() => {
      process.exit(0);
    });
  });
}
