"""
Mistral-specific base class for all Mistral services.

This module provides a unified base class for all Mistral-based services,
consolidating common functionality like API key management, client initialization,
and error handling.
"""

from typing import Dict, Any, Optional
from mistralai import Mistral
import logging

from ..base import ProviderAIService, ServiceType
from ..connection import ConnectionManager, RetryHandler


class MistralBaseService(ProviderAIService):
    """
    Base class for all Mistral services.

    This class consolidates:
    - API key resolution and validation
    - Mistral client initialization
    - Base URL configuration
    - Connection verification
    - Common error handling patterns
    """

    DEFAULT_BASE_URL = "https://api.mistral.ai"

    def __init__(self, config: Dict[str, Any], service_type: ServiceType = None, provider_name: str = "mistral"):
        """
        Initialize the Mistral base service.

        Args:
            config: Configuration dictionary
            service_type: Type of AI service
            provider_name: Provider name (defaults to "mistral")
        """
        # For cooperative multiple inheritance
        if service_type:
            super().__init__(config, service_type, provider_name)
        else:
            super().__init__(config, ServiceType.INFERENCE, provider_name)
        self._setup_mistral_config()

    def _setup_mistral_config(self) -> None:
        """
        Set up Mistral-specific configuration.

        This method:
        1. Resolves the API key from environment or config
        2. Sets the base URL (with default)
        3. Gets the model configuration
        4. Initializes the Mistral client
        """
        # Resolve API key
        self.api_key = self._resolve_api_key("MISTRAL_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Mistral API key is required. Set MISTRAL_API_KEY environment "
                "variable or provide in configuration."
            )

        # Get base URL
        self.base_url = self._get_base_url(self.DEFAULT_BASE_URL)

        # Get model
        self.model = self._get_model("mistral-embed")  # Default model

        # Get endpoint
        self.endpoint = self._get_endpoint("/v1/embeddings")  # Default

        # Initialize Mistral client
        self.client = Mistral(api_key=self.api_key)

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

        self.logger.info(f"Configured Mistral service with model: {self.model}")

    async def initialize(self) -> bool:
        """
        Initialize the Mistral service.

        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Verify connection
            if await self.verify_connection():
                self.initialized = True
                self.logger.info(
                    f"Initialized Mistral {self.service_type.value} service "
                    f"with model {self.model}"
                )
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to initialize Mistral service: {str(e)}")
            return False

    async def verify_connection(self) -> bool:
        """
        Verify Mistral connection.

        Returns:
            True if the connection is working, False otherwise
        """
        try:
            # Basic validation: check if API key has the correct format
            if not self.api_key or len(self.api_key) < 10:
                self.logger.error("Invalid Mistral API key format")
                return False

            self.logger.debug("Mistral connection verified successfully")
            return True

        except Exception as e:
            self.logger.error(f"Mistral connection verification failed: {str(e)}")
            return False

    async def close(self) -> None:
        """
        Close the Mistral service and release resources.
        """
        # Mistral client doesn't have explicit close method
        self.client = None

        if self.connection_manager:
            await self.connection_manager.close()

        self.initialized = False
        self.logger.debug("Closed Mistral service")

    def _get_dimensions(self) -> Optional[int]:
        """
        Get embedding dimensions configuration.

        Returns:
            Dimensions or None if not configured
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('dimensions', 1024)  # Default for mistral-embed

    def _get_batch_size(self, default: int = 16) -> int:
        """
        Get batch size configuration.

        Args:
            default: Default value if not configured

        Returns:
            Batch size
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('batch_size', default)

    def _get_temperature(self, default: float = 0.7) -> float:
        """
        Get temperature configuration.

        Args:
            default: Default value if not configured

        Returns:
            Temperature value
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('temperature', default)

    def _get_top_p(self, default: float = 1.0) -> float:
        """
        Get top_p configuration.

        Args:
            default: Default value if not configured

        Returns:
            Top-p value
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('top_p', default)

    def _get_max_tokens(self, default: int = 1000) -> int:
        """
        Get max_tokens configuration.

        Args:
            default: Default value if not configured

        Returns:
            Maximum number of tokens
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('max_tokens', default)

    def _handle_mistral_error(self, error: Exception, operation: str = "operation") -> None:
        """
        Handle Mistral-specific errors with appropriate logging.

        Args:
            error: The exception that occurred
            operation: Description of the operation that failed
        """
        error_str = str(error)

        if "api_key" in error_str.lower() or "unauthorized" in error_str.lower():
            self.logger.error(f"Mistral authentication failed during {operation}: Invalid API key")
        elif "rate limit" in error_str.lower():
            self.logger.warning(f"Mistral rate limit exceeded during {operation}")
        elif "connection" in error_str.lower():
            self.logger.error(f"Mistral connection error during {operation}: {str(error)}")
        else:
            self.logger.error(f"Mistral error during {operation}: {str(error)}")
