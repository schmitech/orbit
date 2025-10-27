"""
DEPRECATED: Legacy moderators package - for backward compatibility only.

This package is deprecated and maintained only for backward compatibility.
All new code should use the unified AI services architecture:

    from ai_services.factory import AIServiceFactory
    from ai_services.base import ServiceType

    moderator = AIServiceFactory.create_service(
        ServiceType.MODERATION,
        "openai",  # or "anthropic", "ollama"
        config
    )

See docs/migration/moderation-services-migration.md for details.
"""

import logging

logger = logging.getLogger(__name__)
logger.warning(
    "The 'moderators' package is deprecated. "
    "Please use 'ai_services.factory.AIServiceFactory' instead. "
    "See docs/migration/moderation-services-migration.md for migration guide."
)

# Import backward compatibility layer from base.py
from .base import (
    ModeratorFactory,
    ModerationResult,
    ModerationCategory
)

__all__ = [
    'ModeratorFactory',
    'ModerationResult',
    'ModerationCategory'
]