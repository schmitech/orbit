---
name: crm-pipeline-playbook
description: How to answer pipeline, renewal, and account-health questions using the CRM tools.
mcp_tools:
  - "business-sample__list_customers"
  - "business-sample__get_customer_health"
  - "business-sample__search_opportunities"
  - "business-sample__summarize_pipeline"
  - "business-sample__build_account_plan"
enabled: true
version: "1.0"
priority: 10
---

## Finding a customer

Always resolve the customer id with `list_customers` before calling
`get_customer_health` or `build_account_plan` — both take an id, never a name.

## Limits

`search_opportunities` rejects `limit` above 25. Page instead of raising it.

## Output

Group opportunities by owner and render as a markdown table: Owner | Account |
Stage | ARR | Close date.
