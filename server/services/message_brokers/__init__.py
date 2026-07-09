"""
Pluggable MQ-style message brokers (RabbitMQ, ...) behind a common MessageBroker
interface, powering ORBIT's broker-native async surface.

ORBIT consumes request messages from a broker, runs them through the inference
pipeline, and publishes response envelopes back — an alternative to the synchronous
HTTP surfaces (REST, OpenAI, A2A, MCP) for batch/decoupled workloads.
"""

from .base import BrokerMessage, MessageBroker, MessageHandler, is_messaging_enabled
from .factory import create_message_broker, get_messaging_config

__all__ = [
    "BrokerMessage",
    "MessageBroker",
    "MessageHandler",
    "is_messaging_enabled",
    "create_message_broker",
    "get_messaging_config",
]
