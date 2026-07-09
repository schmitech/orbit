"""
RabbitMQ Message Broker
=======================

aio-pika-backed implementation of MessageBroker. Consumes request messages from a
durable requests queue and publishes response envelopes to each message's reply_to
(falling back to a configured results queue). Failed deliveries are rejected without
requeue so they route to the dead-letter queue.

Resilience comes from aio-pika's connect_robust (transparent auto-reconnect); no
separate circuit breaker is needed here.

Requires the optional 'messaging' dependency profile:
    ./install/setup.sh --profile messaging
"""

import logging
from typing import Any, Dict, Optional

from .base import BrokerMessage, MessageBroker, MessageHandler

logger = logging.getLogger(__name__)


class RabbitMQBroker(MessageBroker):
    """MessageBroker backed by RabbitMQ via aio-pika."""

    def __init__(self, config: Dict[str, Any]):
        rmq = (config.get('messaging', {}) or {}).get('rabbitmq', {}) or {}
        self._url = rmq.get('url') or 'amqp://guest:guest@localhost:5672/'
        self._requests_queue = rmq.get('requests_queue', 'orbit.requests')
        self._results_queue = rmq.get('results_queue', 'orbit.results')
        self._dlq = rmq.get('dead_letter_queue', 'orbit.dlq')
        self._prefetch = int(rmq.get('prefetch', 8))
        self._durable = bool(rmq.get('durable', True))

        self._connection = None
        self._channel = None
        self._requests = None

    async def connect(self) -> None:
        try:
            import aio_pika
        except ImportError as e:
            raise ImportError(
                "aio-pika is required for RabbitMQ messaging. Install the messaging "
                "profile: ./install/setup.sh --profile messaging"
            ) from e

        self._connection = await aio_pika.connect_robust(self._url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=self._prefetch)

        # Declare the dead-letter and results queues, then the requests queue with
        # the DLQ wired as its dead-letter target (default exchange, routing_key=dlq).
        await self._channel.declare_queue(self._dlq, durable=self._durable)
        await self._channel.declare_queue(self._results_queue, durable=self._durable)
        self._requests = await self._channel.declare_queue(
            self._requests_queue,
            durable=self._durable,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": self._dlq,
            },
        )
        logger.info(
            "RabbitMQ broker connected (requests=%s, results=%s, dlq=%s, prefetch=%d)",
            self._requests_queue, self._results_queue, self._dlq, self._prefetch,
        )

    async def consume(self, handler: MessageHandler) -> None:
        async def _on_message(message) -> None:
            # process(requeue=False): acks on normal exit, rejects without requeue
            # (-> DLQ) if the handler raises.
            async with message.process(requeue=False):
                await handler(BrokerMessage(
                    body=message.body,
                    correlation_id=message.correlation_id,
                    reply_to=message.reply_to,
                    headers=dict(message.headers or {}),
                ))

        await self._requests.consume(_on_message)
        logger.info("RabbitMQ broker consuming from %s", self._requests_queue)

    async def publish(
        self,
        destination: Optional[str],
        body: bytes,
        correlation_id: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None,
    ) -> None:
        import aio_pika

        target = destination or self._results_queue
        await self._channel.default_exchange.publish(
            aio_pika.Message(
                body=body,
                correlation_id=correlation_id,
                headers=headers or {},
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=target,
        )

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            self._channel = None
            self._requests = None
