"""Ticket sandbox isolation. Needs the server, but no LLM and no API keys.

The CRUD cases mutate shared server state, so the sandbox is load-bearing: if
restore() is wrong, one case silently corrupts the ground truth of every case
after it. These tests mutate deliberately and assert the state comes back.
"""

from __future__ import annotations

import pytest
from mcpeval.sandbox import TicketSandbox, all_tickets

pytestmark = pytest.mark.integration


def test_snapshot_sees_every_seeded_ticket(raw_client):
    tickets = all_tickets(raw_client)
    assert len(tickets) > 50
    assert all(ticket_id.startswith("tkt_") for ticket_id in tickets)


def test_created_tickets_are_removed_on_restore(raw_client):
    sandbox = TicketSandbox.capture(raw_client)
    created = sandbox.create_disposable("cus_0005", "sandbox self-test")
    assert created["id"] in all_tickets(raw_client)

    report = sandbox.restore()
    assert created["id"] in report["deleted"]
    assert created["id"] not in all_tickets(raw_client)
    assert sandbox.drifted() == []


def test_field_changes_are_reverted_on_restore(raw_client):
    sandbox = TicketSandbox.capture(raw_client)
    target = next(iter(sandbox.before))
    original = dict(sandbox.before[target])

    flipped = "resolved" if original["status"] != "resolved" else "open"
    raw_client.call_tool(
        "update_support_ticket",
        {"ticketId": target, "status": flipped, "subject": "mutated by the sandbox self-test"},
    )
    assert target in sandbox.drifted()

    report = sandbox.restore()
    assert target in report["reverted"]
    restored = all_tickets(raw_client)[target]
    assert restored["status"] == original["status"]
    assert restored["subject"] == original["subject"]
    assert sandbox.drifted() == []


def test_restore_is_a_no_op_when_nothing_changed(raw_client):
    sandbox = TicketSandbox.capture(raw_client)
    assert sandbox.restore() == {"deleted": [], "recreated": [], "reverted": []}
    assert sandbox.drifted() == []
