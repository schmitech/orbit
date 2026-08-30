---
name: sales-performance-playbook
description: How to present sales rep performance results.
mcp_tools:
  - "business-sample__get_sales_rep_performance"
enabled: true
version: "1.0"
priority: -1
---

## Ranking

Rank reps by attainment percentage (closed amount / quota), not raw closed
amount, unless the user explicitly asks for a raw-bookings ranking.

The tool returns `attainmentPct` as a formatted percentage string. Compare its
numeric percentage value when ranking; do not derive a different percentage
from formatted currency strings.

## Output

Always include quota, closed amount, and attainment % as columns. Flag any
rep below 70% attainment as at-risk in a short note under the table. Also
include active pipeline, unresolved support tickets, and SLA-breached tickets
when interpreting workload or execution risk. Do not describe a rep as
at-risk solely because they have support tickets unless their attainment is
below 70% or the user asks for workload risk.
