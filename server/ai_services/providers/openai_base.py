"""
OpenAI-specific base class for all OpenAI services.

Extends OpenAICompatibleBaseService with OpenAI-specific defaults so that
the common infrastructure (client setup, connection lifecycle, error handling)
lives in one place.
"""

from typing import Dict, Any
import logging

from ..base import ServiceType
from ..errors import raise_sanitized
from .openai_compatible_base import OpenAICompatibleBaseService

logger = logging.getLogger(__name__)


class OpenAIBaseService(OpenAICompatibleBaseService):
    """
    Base class for all native OpenAI services.

    Adds OpenAI-specific defaults on top of OpenAICompatibleBaseService:
    - API key env var: OPENAI_API_KEY (via provider-name fallback)
    - Base URL: https://api.openai.com/v1
    - Service-type-specific model defaults
    - Simplified verify_connection (OpenAI always supports /models)
    """

    DEFAULT_BASE_URLS = {
        **OpenAICompatibleBaseService.DEFAULT_BASE_URLS,
        "openai": "https://api.openai.com/v1",
    }

    _MODEL_DEFAULTS = {
        ServiceType.EMBEDDING: "text-embedding-3-small",
        ServiceType.INFERENCE: "gpt-4o-mini",
        ServiceType.MODERATION: "text-moderation-latest",
        ServiceType.VISION: "gpt-5",
    }

    def __init__(
        self,
        config: Dict[str, Any],
        service_type: ServiceType = None,
        provider_name: str = "openai"
    ):
        super().__init__(config, service_type or ServiceType.INFERENCE, provider_name)

    def _setup_openai_compatible_config(self) -> None:
        """Run standard compatible setup then apply service-type model defaults."""
        super()._setup_openai_compatible_config()
        if not self.model:
            self.model = self._MODEL_DEFAULTS.get(self.service_type)

    def _get_temperature(self, default: float = 0.1) -> float:
        provider_config = self._extract_provider_config()
        return provider_config.get('temperature', default)

    async def verify_connection(self) -> bool:
        """OpenAI always supports the /models endpoint; no chat-completion fallback needed."""
        try:
            if not self.client:
                logger.error("OpenAI client is not initialized. Cannot verify connection.")
                return False
            await self.client.models.list()
            logger.debug("OpenAI connection verified successfully")
            return True
        except Exception as e:
            logger.error(f"OpenAI connection verification failed: {str(e)}")
            return False

    def _handle_openai_error(self, error: Exception, operation: str = "operation") -> None:
        """Handle OpenAI errors. The openai package is guaranteed to be importable here."""
        from openai import APIError, APIConnectionError, RateLimitError, AuthenticationError

        if isinstance(error, AuthenticationError):
            logger.error(f"OpenAI authentication failed during {operation}: Invalid API key")
        elif isinstance(error, RateLimitError):
            logger.warning(f"OpenAI rate limit exceeded during {operation}")
        elif isinstance(error, APIConnectionError):
            logger.error(f"OpenAI connection error during {operation}: {str(error)}")
        elif isinstance(error, APIError):
            logger.error(f"OpenAI API error during {operation}: {str(error)}")
        else:
            logger.error(f"Unexpected error during {operation}: {str(error)}")

        raise_sanitized(error, provider=self.provider_name, operation=operation)
