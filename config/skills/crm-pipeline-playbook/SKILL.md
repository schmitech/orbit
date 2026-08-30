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

When asked for a segment or region (e.g. "Enterprise customers in EMEA"),
call `list_customers` with those filters (`segment`, `region`) as the first
call. Never guess at customer ids by iterating `cus_0001`, `cus_0002`, ...
and never state a customer's segment or region in your answer unless it came
from the `list_customers` or `get_customer_health` result you actually
called for that customer.

## Limits

`search_opportunities` clamps `limit` values above 25 to 25. Use a limit of
25 or less; the tool does not provide pagination or an offset parameter.

## Output

Group opportunities by owner and render as a markdown table: Owner | Account |
Stage | ARR | Close date.
