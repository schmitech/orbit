"""
Message Broker Factory
======================

Single extension point for MQ backends. To add a new provider:
1. Implement MessageBroker in its own module.
2. Add it to _PROVIDERS below.
3. Add its connection settings under messaging.<provider> in config.yaml.
"""

import logging
from typing import Any, Dict, Tuple

from .base import MessageBroker
from .rabbitmq_provider import RabbitMQBroker

logger = logging.getLogger(__name__)

_PROVIDERS = {
    "rabbitmq": RabbitMQBroker,
}


def get_messaging_config(config: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Resolve the configured provider name and its messaging config section."""
    messaging = config.get('messaging', {}) or {}
    provider_name = (messaging.get('provider') or 'rabbitmq').lower()
    provider_config = messaging.get(provider_name, {}) or {}
    return provider_name, provider_config


def create_message_broker(config: Dict[str, Any]) -> MessageBroker:
    """Instantiate the configured messaging provider (messaging.provider)."""
    provider_name, _ = get_messaging_config(config)

    provider_cls = _PROVIDERS.get(provider_name)
    if provider_cls is None:
        raise ValueError(
            f"Unknown messaging provider '{provider_name}', supported: {list(_PROVIDERS)}"
        )

    logger.debug(f"Using messaging provider: {provider_name}")
    return provider_cls(config)
