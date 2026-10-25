"""
OpenAI-specific base class for all OpenAI services.

Extends OpenAICompatibleBaseService with OpenAI-specific defaults so that
the common infrastructure (client setup, connection lifecycle, error handling)
lives in one place.
"""

from typing import Any
import logging

from ..base import ServiceType, verify_connection_via
from ..errors import ErrorCategory, log_and_raise_sanitized
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
        config: dict[str, Any],
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

    def _get_token_parameter_name(self) -> str:
        """Return the correct token-count parameter name for the active model."""
        provider_config = self._extract_provider_config()

        # Allow explicit configuration override
        configured_name = provider_config.get("token_parameter_name") or provider_config.get("token_parameter")
        if isinstance(configured_name, str):
            configured_name = configured_name.strip()
            if configured_name:
                return configured_name

        model_name = (self.model or "").lower()

        # Newer OpenAI chat models expect max_completion_tokens when using the chat.completions API
        modern_prefixes = (
            "gpt-4.1",
            "gpt-4o",
            "gpt-5",
            "o1",
            "o2",
            "o3",
        )

        if model_name.startswith(modern_prefixes):
            return "max_completion_tokens"

        # Default to the legacy chat.completions parameter name
        return "max_tokens"

    def _resolve_token_value(self, token_param: str, kwargs: dict[str, Any]) -> int:
        """Determine the token limit value while respecting caller overrides."""
        # Pop all known token parameter variants so they don't leak into kwargs
        overrides = {
            "max_tokens": kwargs.pop("max_tokens", None),
            "max_completion_tokens": kwargs.pop("max_completion_tokens", None),
            "max_output_tokens": kwargs.pop("max_output_tokens", None),
        }

        # Caller provided the exact parameter we plan to use
        param_override = overrides.get(token_param)
        if param_override is not None:
            return param_override

        # Fall back to whichever override was provided, regardless of naming
        for value in overrides.values():
            if value is not None:
                return value

        # No override found; use configured default
        return self.max_tokens

    def _supports_temperature(self) -> bool:
        """Return whether the current model supports custom temperature values."""
        model_name = (self.model or "").lower()

        # Newer OpenAI models (gpt-5, o-series) only support default temperature (1.0)
        # and will error if you pass temperature=0.0 or any other value
        unsupported_prefixes = (
            "gpt-5",
            "o1",
            "o2",
            "o3",
        )

        return not model_name.startswith(unsupported_prefixes)

    async def verify_connection(self) -> bool:
        """OpenAI always supports the /models endpoint; no chat-completion fallback needed."""
        async def _probe() -> bool:
            if not self.client:
                logger.error("OpenAI client is not initialized. Cannot verify connection.")
                return False
            await self.client.models.list()
            logger.debug("OpenAI connection verified successfully")
            return True

        return await verify_connection_via(logger, _probe, provider="OpenAI")

    def _handle_openai_error(self, error: Exception, operation: str = "operation") -> None:
        """Handle OpenAI errors. The openai package is guaranteed to be importable here."""
        from openai import APIError, APIConnectionError, RateLimitError, AuthenticationError

        message = None
        if isinstance(error, AuthenticationError):
            category = ErrorCategory.AUTH
            message = "OpenAI authentication failed during {operation}: Invalid API key"
        elif isinstance(error, RateLimitError):
            category = ErrorCategory.RATE_LIMIT
            message = "OpenAI rate limit exceeded during {operation}"
        elif isinstance(error, APIConnectionError):
            category = ErrorCategory.CONNECTION
            message = "OpenAI connection error during {operation}: {error}"
        elif isinstance(error, APIError):
            category = ErrorCategory.API
            message = "OpenAI API error during {operation}: {error}"
        else:
            category = ErrorCategory.UNEXPECTED

        log_and_raise_sanitized(
            logger, error, provider=self.provider_name, operation=operation,
            category=category, message=message,
        )
