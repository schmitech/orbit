"""
Cohere-specific base class for all Cohere services.

This module provides a unified base class for all Cohere-based services,
consolidating common functionality like API key management, client initialization,
and error handling.
"""

from typing import Dict, Any, Optional
import warnings
import logging

# Suppress Cohere Pydantic deprecation warnings before importing cohere
warnings.filterwarnings("ignore", message=".*__fields__.*", category=DeprecationWarning)

import cohere

from ..base import ProviderAIService, ServiceType
from ..connection import ConnectionManager, RetryHandler


class CohereBaseService(ProviderAIService):
    """
    Base class for all Cohere services.

    This class consolidates:
    - API key resolution and validation
    - Cohere client initialization
    - Base URL configuration
    - Connection verification
    - Common error handling patterns
    """

    DEFAULT_BASE_URL = "https://api.cohere.ai"

    def __init__(self, config: Dict[str, Any], service_type: ServiceType = None, provider_name: str = "cohere"):
        """
        Initialize the Cohere base service.

        Args:
            config: Configuration dictionary
            service_type: Type of AI service
            provider_name: Provider name (defaults to "cohere")
        """
        # For cooperative multiple inheritance
        if service_type:
            super().__init__(config, service_type, provider_name)
        else:
            super().__init__(config, ServiceType.INFERENCE, provider_name)
        self._setup_cohere_config()

    def _setup_cohere_config(self) -> None:
        """
        Set up Cohere-specific configuration.

        This method:
        1. Resolves the API key from environment or config
        2. Sets the base URL (with default)
        3. Gets the model configuration
        4. Initializes the Cohere client
        """
        # Resolve API key
        self.api_key = self._resolve_api_key("COHERE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Cohere API key is required. Set COHERE_API_KEY environment "
                "variable or provide in configuration."
            )

        # Get base URL
        self.base_url = self._get_base_url(self.DEFAULT_BASE_URL)

        # Get model with appropriate default based on service type
        if self.service_type == ServiceType.EMBEDDING:
            default_model = "embed-english-v3.0"
        elif self.service_type == ServiceType.INFERENCE:
            default_model = "command-r-plus"
        else:
            default_model = None

        self.model = self._get_model(default_model)

        # Get endpoint
        self.endpoint = self._get_endpoint("/v1/embed")  # Default

        # Initialize Cohere client
        self.client = cohere.AsyncClient(
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

        self.logger.info(f"Configured Cohere service with model: {self.model}")

    async def initialize(self) -> bool:
        """
        Initialize the Cohere service.

        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Verify connection
            if await self.verify_connection():
                self.initialized = True
                self.logger.info(
                    f"Initialized Cohere {self.service_type.value} service "
                    f"with model {self.model}"
                )
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to initialize Cohere service: {str(e)}")
            return False

    async def verify_connection(self) -> bool:
        """
        Verify Cohere connection.

        Returns:
            True if the connection is working, False otherwise
        """
        try:
            # Basic validation: check if API key has the correct format
            if not self.api_key or len(self.api_key) < 10:
                self.logger.error("Invalid Cohere API key format")
                return False

            self.logger.debug("Cohere connection verified successfully")
            return True

        except Exception as e:
            self.logger.error(f"Cohere connection verification failed: {str(e)}")
            return False

    async def close(self) -> None:
        """
        Close the Cohere service and release resources.
        """
        if self.client:
            await self.client.close()
            self.client = None

        if self.connection_manager:
            await self.connection_manager.close()

        self.initialized = False
        self.logger.debug("Closed Cohere service")

    def _get_input_type(self, default: str = "search_document") -> str:
        """
        Get input_type configuration for embeddings.

        Args:
            default: Default value if not configured

        Returns:
            Input type string
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('input_type', default)

    def _get_truncate(self, default: str = "NONE") -> str:
        """
        Get truncate configuration.

        Args:
            default: Default value if not configured

        Returns:
            Truncate mode
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('truncate', default)

    def _get_batch_size(self, default: int = 32) -> int:
        """
        Get batch size configuration.

        Args:
            default: Default value if not configured

        Returns:
            Batch size
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('batch_size', default)

    def _get_dimensions(self) -> Optional[int]:
        """
        Get embedding dimensions configuration.

        Returns:
            Dimensions or None if not configured
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('dimensions')

    def _handle_cohere_error(self, error: Exception, operation: str = "operation") -> None:
        """
        Handle Cohere-specific errors with appropriate logging.

        Args:
            error: The exception that occurred
            operation: Description of the operation that failed
        """
        error_str = str(error)

        if "api_key" in error_str.lower() or "unauthorized" in error_str.lower():
            self.logger.error(f"Cohere authentication failed during {operation}: Invalid API key")
        elif "rate limit" in error_str.lower():
            self.logger.warning(f"Cohere rate limit exceeded during {operation}")
        elif "connection" in error_str.lower():
            self.logger.error(f"Cohere connection error during {operation}: {str(error)}")
        else:
            self.logger.error(f"Cohere error during {operation}: {str(error)}")
