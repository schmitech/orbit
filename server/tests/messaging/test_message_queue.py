"""Unit tests for the broker-native MQ surface (message_brokers + message_consumer)."""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from services.message_brokers import (
    BrokerMessage,
    MessageBroker,
    create_message_broker,
    get_messaging_config,
    is_messaging_enabled,
)
from services.message_brokers.rabbitmq_provider import RabbitMQBroker
from services.messaging import MessageConsumerService


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class FakeBroker(MessageBroker):
    """In-memory MessageBroker that records published envelopes."""

    def __init__(self):
        self.published = []
        self.connected = False
        self.closed = False
        self.handler = None

    async def connect(self):
        self.connected = True

    async def consume(self, handler):
        self.handler = handler

    async def publish(self, destination, body, correlation_id=None, headers=None):
        self.published.append({
            "destination": destination,
            "envelope": json.loads(body),
            "correlation_id": correlation_id,
        })

    async def close(self):
        self.closed = True


def make_msg(payload, correlation_id="corr-1", reply_to="client.replies", headers=None):
    return BrokerMessage(
        body=json.dumps(payload).encode(),
        correlation_id=correlation_id,
        reply_to=reply_to,
        headers=headers or {},
    )


def make_consumer(process_result=None, adapter=("hr", None), with_key_service=True, process_side_effect=None):
    chat_service = MagicMock()
    chat_service.process_chat = AsyncMock(
        return_value=process_result if process_result is not None else {"response": "hello", "sources": [], "metadata": {}},
        side_effect=process_side_effect,
    )

    api_key_service = None
    if with_key_service:
        api_key_service = MagicMock()
        api_key_service.get_adapter_for_api_key = AsyncMock(return_value=adapter)

    consumer = MessageConsumerService(
        config={},
        broker=FakeBroker(),
        chat_service=chat_service,
        api_key_service=api_key_service,
        adapter_manager=MagicMock() if with_key_service else None,
    )
    return consumer, chat_service, api_key_service


# ---------------------------------------------------------------------------
# Factory / config
# ---------------------------------------------------------------------------

class TestFactory:
    def test_selects_rabbitmq(self):
        broker = create_message_broker({"messaging": {"provider": "rabbitmq"}})
        assert isinstance(broker, RabbitMQBroker)

    def test_defaults_to_rabbitmq(self):
        assert get_messaging_config({})[0] == "rabbitmq"

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError):
            create_message_broker({"messaging": {"provider": "nope"}})

    def test_is_messaging_enabled(self):
        assert is_messaging_enabled({"messaging": {"enabled": True}}) is True
        assert is_messaging_enabled({"messaging": {"enabled": False}}) is False
        assert is_messaging_enabled({}) is False


# ---------------------------------------------------------------------------
# Consumer handling
# ---------------------------------------------------------------------------

class TestConsumerHandle:
    async def test_success_publishes_completed_envelope(self):
        consumer, chat_service, _ = make_consumer(
            process_result={"response": "hi there", "sources": [{"s": 1}], "metadata": {"m": 2}}
        )
        await consumer._handle(make_msg({"id": "r1", "message": "hello", "api_key": "k", "session_id": "s1"}))

        chat_service.process_chat.assert_awaited_once()
        kwargs = chat_service.process_chat.await_args.kwargs
        assert kwargs["message"] == "hello"
        assert kwargs["adapter_name"] == "hr"
        assert kwargs["session_id"] == "s1"
        # key-derived context is threaded through, matching /v1/chat
        assert kwargs["api_key"] == "k"
        assert kwargs["system_prompt_id"] is None

        assert len(consumer.broker.published) == 1
        pub = consumer.broker.published[0]
        assert pub["destination"] == "client.replies"
        assert pub["correlation_id"] == "corr-1"
        assert pub["envelope"] == {
            "id": "r1",
            "status": "completed",
            "response": "hi there",
            "sources": [{"s": 1}],
            "error": None,
            "metadata": {"m": 2},
        }

    async def test_session_id_defaults_to_correlation_id(self):
        consumer, chat_service, _ = make_consumer()
        await consumer._handle(make_msg({"id": "r1", "message": "hey", "api_key": "k"}, correlation_id="corr-x"))
        assert chat_service.process_chat.await_args.kwargs["session_id"] == "corr-x"

    async def test_pipeline_error_result_publishes_failed_and_acks(self):
        consumer, _, _ = make_consumer(process_result={"error": "boom"})
        await consumer._handle(make_msg({"id": "r1", "message": "hello", "api_key": "k"}))
        env = consumer.broker.published[0]["envelope"]
        assert env["status"] == "failed"
        assert env["error"] == "boom"

    async def test_missing_api_key_publishes_failed_without_calling_pipeline(self):
        consumer, chat_service, _ = make_consumer()
        await consumer._handle(make_msg({"id": "r1", "message": "hello"}))  # no api_key
        chat_service.process_chat.assert_not_awaited()
        env = consumer.broker.published[0]["envelope"]
        assert env["status"] == "failed"
        assert "Missing API key" in env["error"]

    async def test_invalid_api_key_publishes_failed(self):
        consumer, chat_service, api_key_service = make_consumer()
        api_key_service.get_adapter_for_api_key = AsyncMock(side_effect=RuntimeError("401"))
        await consumer._handle(make_msg({"id": "r1", "message": "hello", "api_key": "bad"}))
        chat_service.process_chat.assert_not_awaited()
        assert consumer.broker.published[0]["envelope"]["status"] == "failed"

    async def test_empty_message_publishes_failed(self):
        consumer, chat_service, _ = make_consumer()
        await consumer._handle(make_msg({"id": "r1", "message": "   ", "api_key": "k"}))
        chat_service.process_chat.assert_not_awaited()
        env = consumer.broker.published[0]["envelope"]
        assert env["status"] == "failed"
        assert "must not be empty" in env["error"]

    async def test_pipeline_exception_propagates_for_dlq(self):
        consumer, _, _ = make_consumer(process_side_effect=RuntimeError("kaboom"))
        with pytest.raises(RuntimeError):
            await consumer._handle(make_msg({"id": "r1", "message": "hello", "api_key": "k"}))
        # Nothing published — the message is rejected to the DLQ instead.
        assert consumer.broker.published == []

    async def test_unparseable_body_propagates_for_dlq(self):
        consumer, _, _ = make_consumer()
        with pytest.raises(Exception):
            await consumer._handle(BrokerMessage(body=b"not json", correlation_id="c", reply_to="r"))

    async def test_key_system_prompt_id_threaded_through(self):
        consumer, chat_service, _ = make_consumer(adapter=("hr", "PROMPT123"))
        await consumer._handle(make_msg({"id": "r1", "message": "hi", "api_key": "k"}))
        kwargs = chat_service.process_chat.await_args.kwargs
        assert kwargs["system_prompt_id"] == "PROMPT123"
        assert kwargs["api_key"] == "k"

    async def test_adapter_override_applied_after_key_validation(self):
        consumer, chat_service, api_key_service = make_consumer(adapter=("hr", "PROMPT123"))
        await consumer._handle(make_msg({"id": "r1", "message": "hi", "api_key": "k", "adapter": "sales"}))
        # key still validated, but the per-message override wins for the adapter;
        # the key's system prompt id is still preserved
        api_key_service.get_adapter_for_api_key.assert_awaited_once()
        kwargs = chat_service.process_chat.await_args.kwargs
        assert kwargs["adapter_name"] == "sales"
        assert kwargs["system_prompt_id"] == "PROMPT123"

    async def test_no_key_service_uses_override_or_default(self):
        consumer, chat_service, _ = make_consumer(with_key_service=False)
        await consumer._handle(make_msg({"id": "r1", "message": "hi", "adapter": "sales"}))
        assert chat_service.process_chat.await_args.kwargs["adapter_name"] == "sales"

        consumer2, chat2, _ = make_consumer(with_key_service=False)
        await consumer2._handle(make_msg({"id": "r2", "message": "hi"}))
        assert chat2.process_chat.await_args.kwargs["adapter_name"] == "default"

    async def test_reply_to_none_falls_back_to_broker_default(self):
        consumer, _, _ = make_consumer()
        await consumer._handle(make_msg({"id": "r1", "message": "hi", "api_key": "k"}, reply_to=None))
        assert consumer.broker.published[0]["destination"] is None

    async def test_api_key_from_header(self):
        consumer, chat_service, _ = make_consumer()
        await consumer._handle(make_msg({"id": "r1", "message": "hi"}, headers={"x-api-key": "k"}))
        chat_service.process_chat.assert_awaited_once()

    async def test_start_and_stop_delegate_to_broker(self):
        consumer, _, _ = make_consumer()
        await consumer.start()
        assert consumer.broker.connected is True
        assert consumer.broker.handler == consumer._handle
        await consumer.stop()
        assert consumer.broker.closed is True
