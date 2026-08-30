---
name: churn-risk-playbook
description: How to combine product telemetry with churn-risk simulation for a customer.
mcp_tools:
  - "business-sample__get_product_telemetry"
  - "business-sample__simulate_churn_risk_scenario"
enabled: true
version: "1.0"
priority: 0
---

## Order of calls

Call `get_product_telemetry` for the customer before
`simulate_churn_risk_scenario`, so the simulation is grounded in the
customer's actual usage trends instead of the model's own assumptions.

## Presenting results

Never present a bare churn probability. Always pair it with the simulation's
key drivers and the telemetry's utilization or adoption alerts, so the number
is explainable rather than a black box. The simulation itself accounts for
open P1/P2 support escalations; telemetry does not return ticket volume.
