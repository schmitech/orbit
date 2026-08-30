---
name: support-ticket-playbook
description: How to look up, create, and manage synthetic support tickets correctly.
mcp_tools:
  - "business-sample__list_support_tickets"
  - "business-sample__get_support_ticket"
  - "business-sample__create_support_ticket"
  - "business-sample__update_support_ticket"
  - "business-sample__delete_support_ticket"
enabled: true
version: "1.0"
priority: 5
---

## Creating tickets

These tools ARE the ticket system for this session — when asked to open,
log, or file a support ticket, call `create_support_ticket` directly. Never
decline a ticket-creation request or claim no such tool exists.

`create_support_ticket` requires a customer id. Use an id the user supplied
or ask for one when it is unavailable; never invent a `cus_...` value. Report
the server-assigned ticket id, customer, priority, status, and subject after a
successful creation.

## Reading before writing

Call `get_support_ticket` to read the current state of a ticket before
calling `update_support_ticket` or `delete_support_ticket` on it, so the
update doesn't blindly overwrite fields you haven't seen.

## Deleting

Confirm explicitly with the user before calling `delete_support_ticket` —
deletion is permanent for this session's in-memory data and cannot be
undone.

## Output

For `list_support_tickets`, render the returned tickets as a table: Ticket |
Customer | Priority | Status | SLA breached | Subject. For `get_support_ticket`,
show the current ticket fields before proposing an update or deletion. After
an update or deletion, report only the confirmed result returned by the tool;
do not claim a change succeeded when it returned an error.
