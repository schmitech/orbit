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

## Reading before writing

Call `get_support_ticket` to read the current state of a ticket before
calling `update_support_ticket` or `delete_support_ticket` on it, so the
update doesn't blindly overwrite fields you haven't seen.

## Deleting

Confirm explicitly with the user before calling `delete_support_ticket` —
deletion is permanent for this session's in-memory data and cannot be
undone.
