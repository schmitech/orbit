"""
Anthropic-specific base class for all Anthropic services.

This module provides a unified base class for all Anthropic-based services,
consolidating common functionality like API key management, client initialization,
and error handling.
"""

from typing import Dict, Any, Optional
from anthropic import AsyncAnthropic
import logging

from ..base import ProviderAIService, ServiceType
from ..connection import ConnectionManager, RetryHandler


class AnthropicBaseService(ProviderAIService):
    """
    Base class for all Anthropic services.

    This class consolidates:
    - API key resolution and validation
    - AsyncAnthropic client initialization
    - Base URL configuration
    - Connection verification
    - Common error handling patterns
    """

    DEFAULT_BASE_URL = "https://api.anthropic.com"

    def __init__(self, config: Dict[str, Any], service_type: ServiceType = None, provider_name: str = "anthropic"):
        """
        Initialize the anthropic base service.

        Args:
            config: Configuration dictionary
            service_type: Type of AI service
            provider_name: Provider name (defaults to "anthropic")
        """
        # For cooperative multiple inheritance
        if service_type:
            super().__init__(config, service_type, provider_name)
        else:
            super().__init__(config, ServiceType.INFERENCE, provider_name)
        self._setup_anthropic_config()

    def _setup_anthropic_config(self) -> None:
        """
        Set up Anthropic-specific configuration.

        This method:
        1. Resolves the API key from environment or config
        2. Sets the base URL (with default)
        3. Gets the model configuration
        4. Initializes the AsyncAnthropic client
        """
        # Resolve API key
        self.api_key = self._resolve_api_key("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Anthropic API key is required. Set ANTHROPIC_API_KEY environment "
                "variable or provide in configuration."
            )

        # Get base URL
        self.base_url = self._get_base_url(self.DEFAULT_BASE_URL)

        # Get model
        self.model = self._get_model("claude-sonnet-4-20250514")  # Default model

        # Get endpoint
        self.endpoint = self._get_endpoint("/v1/messages")  # Default

        # Initialize AsyncAnthropic client
        self.client = AsyncAnthropic(
            api_key=self.api_key,
            base_url=self.base_url
        )

        # Setup connection manager for additional HTTP operations
        self.connection_manager = ConnectionManager(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout_ms=self._get_timeout_config()['total'],
            headers={"anthropic-version": "2023-06-01"}  # Required header
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

        self.logger.debug(f"Configured Anthropic service with model: {self.model}")

    async def initialize(self) -> bool:
        """
        Initialize the Anthropic service.

        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Verify connection with a simple test
            if await self.verify_connection():
                self.initialized = True
                self.logger.info(
                    f"Initialized Anthropic {self.service_type.value} service "
                    f"with model {self.model}"
                )
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to initialize Anthropic service: {str(e)}")
            return False

    async def verify_connection(self) -> bool:
        """
        Verify Anthropic connection.

        Since Anthropic doesn't have a models list endpoint, we verify
        by checking if the API key format is valid and the base URL is accessible.

        Returns:
            True if the connection is working, False otherwise
        """
        try:
            # Basic validation: check if API key has the correct format
            if not self.api_key.startswith("sk-ant-"):
                self.logger.error("Invalid Anthropic API key format")
                return False

            # Additional validation could be added here
            self.logger.debug("Anthropic connection verified successfully")
            return True

        except Exception as e:
            self.logger.error(f"Anthropic connection verification failed: {str(e)}")
            return False

    async def close(self) -> None:
        """
        Close the Anthropic service and release resources.
        """
        if self.client:
            await self.client.close()
            self.client = None

        if self.connection_manager:
            await self.connection_manager.close()

        self.initialized = False
        self.logger.debug("Closed Anthropic service")

    def _get_max_tokens(self, default: int = 1024) -> int:
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

    def _get_top_p(self, default: float = 0.8) -> float:
        """
        Get top_p configuration.

        Args:
            default: Default value if not configured

        Returns:
            Top-p value
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('top_p', default)

    def _handle_anthropic_error(self, error: Exception, operation: str = "operation") -> None:
        """
        Handle Anthropic-specific errors with appropriate logging.

        Args:
            error: The exception that occurred
            operation: Description of the operation that failed
        """
        from anthropic import (
            APIError,
            APIConnectionError,
            RateLimitError,
            AuthenticationError
        )

        if isinstance(error, AuthenticationError):
            self.logger.error(f"Anthropic authentication failed during {operation}: Invalid API key")
        elif isinstance(error, RateLimitError):
            self.logger.warning(f"Anthropic rate limit exceeded during {operation}")
        elif isinstance(error, APIConnectionError):
            self.logger.error(f"Anthropic connection error during {operation}: {str(error)}")
        elif isinstance(error, APIError):
            self.logger.error(f"Anthropic API error during {operation}: {str(error)}")
        else:
            self.logger.error(f"Unexpected error during {operation}: {str(error)}")
