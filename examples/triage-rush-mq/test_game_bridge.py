"""Contract checks for the game's plain and structured decision requests."""

import asyncio
import json
import unittest
from types import SimpleNamespace

from game_bridge import Bridge, validate_publish


class Exchange:
    def __init__(self):
        self.messages = []

    async def publish(self, message, routing_key):
        self.messages.append((json.loads(message.body), routing_key))


class BridgeContractTest(unittest.TestCase):
    def setUp(self):
        self.args = SimpleNamespace(
            adapter="ticket-triage", allowed_adapters="ticket-triage",
            api_key="example-key", requests_queue="orbit.requests",
        )
        self.bridge = Bridge(self.args)
        self.exchange = Exchange()
        self.bridge.channel = SimpleNamespace(default_exchange=self.exchange)
        self.bridge.reply_queue = SimpleNamespace(name="reply")
        self.bridge.aio_pika = SimpleNamespace(Message=lambda **kwargs: SimpleNamespace(**kwargs))

    def test_plain_ticket_stays_plain(self):
        item = {"id": "one", "text": "Please refund the duplicate charge"}
        self.assertIsNone(validate_publish({"items": [item]}, self.bridge.allowed_adapters, self.args.adapter)[2])
        asyncio.run(self.bridge.publish([item], self.args.adapter))
        request, routing_key = self.exchange.messages[0]
        self.assertEqual(request["message"], item["text"])
        self.assertEqual(routing_key, "orbit.requests")

    def test_resource_case_keeps_state_and_question(self):
        item = {
            "id": "two", "text": "Checkout is down",
            "state": {"ticket": "Checkout is down", "resources": "Platform · 0 free", "policy": "Escalate critical work without a specialist"},
            "questions": {"action": {"type": "choice", "instructions": "Next action?", "criteria": {"escalate": "Seek backup", "dispatch": "Use available specialist"}}},
        }
        self.assertIsNone(validate_publish({"items": [item]}, self.bridge.allowed_adapters, self.args.adapter)[2])
        asyncio.run(self.bridge.publish([item], self.args.adapter))
        request, _ = self.exchange.messages[0]
        self.assertEqual(json.loads(request["message"]), {"state": item["state"], "questions": item["questions"]})

    def test_rejects_incomplete_or_duplicate_structured_input(self):
        item = {"id": "one", "text": "Checkout is down", "state": {"ticket": "Checkout is down"}}
        self.assertIn("state and questions", validate_publish({"items": [item]}, self.bridge.allowed_adapters, self.args.adapter)[2])
        plain = {"id": "one", "text": "Checkout is down"}
        self.assertIn("duplicate", validate_publish({"items": [plain, plain]}, self.bridge.allowed_adapters, self.args.adapter)[2])


if __name__ == "__main__":
    unittest.main()
