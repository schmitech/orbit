"""Isolation for the mutating support-ticket tools.

create/update/delete_support_ticket mutate a module-level array in the sample
server's process, so changes persist across requests and would leak from one
case into the next — silently corrupting the ground truth of everything that
runs afterwards. Restarting the server restores the seed, but that is a blunt
instrument; this restores just what a case touched.

The customer ids are cus_0001..cus_0036 and each holds at most a handful of
tickets, so a full snapshot is ~36 cheap calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .protocol import RawMcpClient

CUSTOMER_IDS = tuple(f"cus_{index:04d}" for index in range(1, 37))
MUTABLE_FIELDS = ("subject", "priority", "status", "slaBreached")


def all_tickets(client: RawMcpClient) -> dict[str, dict[str, Any]]:
    """Every ticket, keyed by id.

    Paged per customer because list_support_tickets clamps limit to 25 and
    offers no offset parameter.
    """
    tickets: dict[str, dict[str, Any]] = {}
    for customer_id in CUSTOMER_IDS:
        payload = client.call_readonly("list_support_tickets", {"customerId": customer_id, "limit": 25})
        for ticket in payload.payload["tickets"]:
            tickets[ticket["id"]] = ticket
    return tickets


@dataclass
class TicketSandbox:
    """Snapshot/restore around a mutating case."""

    client: RawMcpClient
    before: dict[str, dict[str, Any]]

    @classmethod
    def capture(cls, client: RawMcpClient) -> TicketSandbox:
        return cls(client=client, before=all_tickets(client))

    def create_disposable(self, customer_id: str, subject: str, **fields: Any) -> dict[str, Any]:
        """Create a ticket the case is allowed to modify or destroy.

        Delete/update cases target one of these rather than a seeded ticket, so
        the agent can only affect something the harness owns.
        """
        result = self.client.call_tool(
            "create_support_ticket", {"customerId": customer_id, "subject": subject, **fields}
        )
        if result.is_error:
            raise RuntimeError(f"sandbox could not create a ticket: {result.payload}")
        return result.payload["ticket"]

    def restore(self) -> dict[str, list[str]]:
        """Undo everything the case changed. Returns what it had to repair."""
        after = all_tickets(self.client)
        report: dict[str, list[str]] = {"deleted": [], "recreated": [], "reverted": []}

        for ticket_id in set(after) - set(self.before):
            self.client.call_tool("delete_support_ticket", {"ticketId": ticket_id})
            report["deleted"].append(ticket_id)

        for ticket_id in set(self.before) - set(after):
            # The agent deleted a seeded ticket. Recreate it as closely as the
            # tools allow; the server assigns a fresh id, so note it loudly.
            original = self.before[ticket_id]
            self.client.call_tool(
                "create_support_ticket",
                {
                    "customerId": original["customerId"],
                    "subject": original["subject"],
                    "priority": original["priority"],
                    "status": original["status"],
                    "slaBreached": original["slaBreached"],
                },
            )
            report["recreated"].append(ticket_id)

        for ticket_id in set(self.before) & set(after):
            original, current = self.before[ticket_id], after[ticket_id]
            changed = {field: original[field] for field in MUTABLE_FIELDS if original[field] != current[field]}
            if changed:
                self.client.call_tool("update_support_ticket", {"ticketId": ticket_id, **changed})
                report["reverted"].append(ticket_id)

        return report

    def drifted(self) -> list[str]:
        """Ticket ids whose state still differs from the snapshot."""
        after = all_tickets(self.client)
        drift = [tid for tid in set(self.before) ^ set(after)]
        drift += [
            tid
            for tid in set(self.before) & set(after)
            if any(self.before[tid][f] != after[tid][f] for f in MUTABLE_FIELDS)
        ]
        return sorted(set(drift))
