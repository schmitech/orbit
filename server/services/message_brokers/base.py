"""
Message Broker Base
===================

Defines the MessageBroker interface that every broker backend (RabbitMQ, ...)
must implement, so the message consumer depends on generic messaging semantics
instead of a specific vendor's client API.

To add a new backend:
1. Implement a MessageBroker subclass in its own module (see rabbitmq_provider.py).
2. Register it in factory.py's provider map.
3. Add its connection settings under messaging.<name> in config.yaml.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional

from utils.config_utils import is_true_value


def is_messaging_enabled(config: Dict[str, Any]) -> bool:
    """Master switch: messaging.enabled. Defaults to False (opt-in surface)."""
    return is_true_value((config.get('messaging', {}) or {}).get('enabled', False))


@dataclass
class BrokerMessage:
    """A single inbound message handed to the consumer handler.

    reply_to is the destination the response envelope should be published to.
    When absent, the broker falls back to its configured results queue.
    """
    body: bytes
    correlation_id: Optional[str] = None
    reply_to: Optional[str] = None
    headers: Dict[str, Any] = field(default_factory=dict)


# Handler invoked once per inbound message. Returning normally acks the message;
# raising rejects it (routing to the dead-letter queue).
MessageHandler = Callable[[BrokerMessage], Awaitable[None]]


class MessageBroker(ABC):
    """Common interface for MQ-style request/response brokers."""

    @abstractmethod
    async def connect(self) -> None:
        """Open the connection and declare the request/result/dead-letter queues."""

    @abstractmethod
    async def consume(self, handler: MessageHandler) -> None:
        """Begin consuming from the requests queue, invoking handler per message.

        The broker acks the message when the handler returns normally, and rejects
        it without requeue (routing to the dead-letter queue) when the handler raises.
        """

    @abstractmethod
    async def publish(
        self,
        destination: Optional[str],
        body: bytes,
        correlation_id: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Publish a response. A None destination targets the configured results queue."""

    @abstractmethod
    async def close(self) -> None:
        """Close the connection."""
