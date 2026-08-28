---
name: crm-pipeline-playbook
description: How to answer pipeline, renewal, and account-health questions using the CRM tools.
mcp_tools:
  - "business-sample__*"
enabled: true
version: "1.0"
priority: 0
---

## Finding a customer

Always resolve the customer id with `list_customers` before calling
`build_account_plan` — the plan tool takes an id, never a name.

## Limits

`search_opportunities` rejects `limit` above 25. Page instead of raising it.

## Output

Group opportunities by owner and render as a markdown table: Owner | Account |
Stage | ARR | Close date.
