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

Never present a bare churn probability. Always pair it with the top
contributing signals from the telemetry (e.g. declining seat utilization,
rising support-ticket volume) so the number is explainable, not a black box.
