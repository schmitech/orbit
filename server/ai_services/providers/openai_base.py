"""
OpenAI-specific base class for all OpenAI services.

This module provides a unified base class for all OpenAI-based services
(embeddings, inference, moderation, etc.), consolidating common functionality
like API key management, client initialization, and error handling.
"""

from typing import Dict, Any, Optional
from openai import AsyncOpenAI
import logging

from ..base import ProviderAIService, ServiceType
from ..connection import ConnectionManager, RetryHandler, ConnectionVerifier


class OpenAIBaseService(ProviderAIService):
    """
    Base class for all OpenAI services.

    This class consolidates:
    - API key resolution and validation
    - AsyncOpenAI client initialization
    - Base URL configuration
    - Connection verification
    - Common error handling patterns
    """

    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(self, config: Dict[str, Any], service_type: ServiceType = None, provider_name: str = "openai"):
        """
        Initialize the openai base service.

        Args:
            config: Configuration dictionary
            service_type: Type of AI service
            provider_name: Provider name (defaults to "openai")
        """
        # For cooperative multiple inheritance
        if service_type:
            super().__init__(config, service_type, provider_name)
        else:
            super().__init__(config, ServiceType.INFERENCE, provider_name)
        self._setup_openai_config()

    def _setup_openai_config(self) -> None:
        """
        Set up OpenAI-specific configuration.

        This method:
        1. Resolves the API key from environment or config
        2. Sets the base URL (with default)
        3. Gets the model configuration
        4. Initializes the AsyncOpenAI client
        """
        # Resolve API key
        self.api_key = self._resolve_api_key("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key is required. Set OPENAI_API_KEY environment "
                "variable or provide in configuration."
            )

        # Get base URL
        self.base_url = self._get_base_url(self.DEFAULT_BASE_URL)

        # Get model with appropriate default based on service type
        if self.service_type == ServiceType.EMBEDDING:
            default_model = "text-embedding-3-small"
        elif self.service_type == ServiceType.INFERENCE:
            default_model = "gpt-4o-mini"
        elif self.service_type == ServiceType.MODERATION:
            default_model = "text-moderation-latest"
        else:
            default_model = None

        self.model = self._get_model(default_model)

        # Get endpoint
        self.endpoint = self._get_endpoint("/v1/embeddings")  # Default, can be overridden

        # Initialize AsyncOpenAI client
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

        # Setup connection manager for additional HTTP operations
        self.connection_manager = ConnectionManager(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout_ms=self._get_timeout_config()['total']
        )

        # Setup retry handler
        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(
            max_retries=retry_config['max_retries'],
            initial_wait_ms=retry_config['initial_wait_ms'],
            max_wait_ms=retry_config['max_wait_ms'],
            exponential_base=retry_config['exponential_base'],
            enabled=retry_config['enabled']
        )

        self.logger.debug(f"Configured OpenAI service with model: {self.model}")

    async def initialize(self) -> bool:
        """
        Initialize the OpenAI service.

        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Verify connection
            if await self.verify_connection():
                self.initialized = True
                self.logger.info(
                    f"Initialized OpenAI {self.service_type.value} service "
                    f"with model {self.model}"
                )
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to initialize OpenAI service: {str(e)}")
            return False

    async def verify_connection(self) -> bool:
        """
        Verify OpenAI connection by listing available models.

        Returns:
            True if the connection is working, False otherwise
        """
        try:
            # Test with a simple API call
            await self.client.models.list()
            self.logger.debug("OpenAI connection verified successfully")
            return True
        except Exception as e:
            self.logger.error(f"OpenAI connection verification failed: {str(e)}")
            return False

    async def close(self) -> None:
        """
        Close the OpenAI service and release resources.
        """
        if self.client:
            await self.client.close()
            self.client = None

        if self.connection_manager:
            await self.connection_manager.close()

        self.initialized = False
        self.logger.debug("Closed OpenAI service")

    def _get_max_tokens(self, default: int = 2000) -> int:
        """
        Get max_tokens configuration.

        Args:
            default: Default value if not configured

        Returns:
            Maximum number of tokens
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('max_tokens', default)

    def _get_temperature(self, default: float = 0.1) -> float:
        """
        Get temperature configuration.

        Args:
            default: Default value if not configured

        Returns:
            Temperature value
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('temperature', default)

    def _get_batch_size(self, default: int = 10) -> int:
        """
        Get batch size configuration.

        Args:
            default: Default value if not configured

        Returns:
            Batch size
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('batch_size', default)

    def _handle_openai_error(self, error: Exception, operation: str = "operation") -> None:
        """
        Handle OpenAI-specific errors with appropriate logging.

        Args:
            error: The exception that occurred
            operation: Description of the operation that failed
        """
        from openai import (
            APIError,
            APIConnectionError,
            RateLimitError,
            AuthenticationError
        )

        if isinstance(error, AuthenticationError):
            self.logger.error(f"OpenAI authentication failed during {operation}: Invalid API key")
        elif isinstance(error, RateLimitError):
            self.logger.warning(f"OpenAI rate limit exceeded during {operation}")
        elif isinstance(error, APIConnectionError):
            self.logger.error(f"OpenAI connection error during {operation}: {str(error)}")
        elif isinstance(error, APIError):
            self.logger.error(f"OpenAI API error during {operation}: {str(error)}")
        else:
            self.logger.error(f"Unexpected error during {operation}: {str(error)}")
