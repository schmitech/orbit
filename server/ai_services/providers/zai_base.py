"""
Z.AI-specific base class for all Z.AI services.

This module provides a unified base class for all Z.AI-based services
(embeddings, inference, moderation, etc.), consolidating common functionality
like API key management, client initialization, and error handling.
"""

from typing import Dict, Any
from zai import ZaiClient
import logging

from ..base import ProviderAIService, ServiceType
from ..connection import ConnectionManager, RetryHandler



logger = logging.getLogger(__name__)
class ZaiBaseService(ProviderAIService):
    """
    Base class for all Z.AI services.

    This class consolidates:
    - API key resolution and validation
    - ZaiClient initialization
    - Base URL configuration
    - Connection verification
    - Common error handling patterns
    """

    DEFAULT_BASE_URL = "https://api.z.ai/api/paas/v4/"

    def __init__(self, config: Dict[str, Any], service_type: ServiceType = None, provider_name: str = "zai"):
        """
        Initialize the Z.AI base service.

        Args:
            config: Configuration dictionary
            service_type: Type of AI service
            provider_name: Provider name (defaults to "zai")
        """
        # For cooperative multiple inheritance
        if service_type:
            super().__init__(config, service_type, provider_name)
        else:
            super().__init__(config, ServiceType.INFERENCE, provider_name)
        self._setup_zai_config()

    def _setup_zai_config(self) -> None:
        """
        Set up Z.AI-specific configuration.

        This method:
        1. Resolves the API key from environment or config
        2. Sets the base URL (with default)
        3. Gets the model configuration
        4. Initializes the ZaiClient
        """
        # Resolve API key
        self.api_key = self._resolve_api_key("ZAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Z.AI API key is required. Set ZAI_API_KEY environment "
                "variable or provide in configuration."
            )

        # Get base URL
        self.base_url = self._get_base_url(self.DEFAULT_BASE_URL)

        # Get model with appropriate default based on service type
        if self.service_type == ServiceType.EMBEDDING:
            default_model = "text-embedding-3-small"  # Z.AI doesn't have specific embedding models in docs
        elif self.service_type == ServiceType.INFERENCE:
            default_model = "glm-4.6"
        elif self.service_type == ServiceType.MODERATION:
            default_model = "glm-4.6"  # Use general model for moderation
        else:
            default_model = "glm-4.6"

        self.model = self._get_model(default_model)

        # Get endpoint
        self.endpoint = self._get_endpoint("/chat/completions")  # Default, can be overridden

        # Initialize ZaiClient
        self.client = ZaiClient(
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

        logger.debug(f"Configured Z.AI service with model: {self.model}")

    async def initialize(self) -> bool:
        """
        Initialize the Z.AI service.

        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Verify connection
            if await self.verify_connection():
                self.initialized = True
                logger.info(
                    f"Initialized Z.AI {self.service_type.value} service "
                    f"with model {self.model}"
                )
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to initialize Z.AI service: {str(e)}")
            return False

    async def verify_connection(self) -> bool:
        """
        Verify Z.AI connection by making a simple test call.

        Returns:
            True if the connection is working, False otherwise
        """
        try:
            # Test with a simple chat completion call
            await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=1
            )
            logger.debug("Z.AI connection verified successfully")
            return True
        except Exception as e:
            logger.error(f"Z.AI connection verification failed: {str(e)}")
            return False

    async def close(self) -> None:
        """
        Close the Z.AI service and release resources.
        """
        if self.client:
            # Z.AI client doesn't have a close method, but we can set it to None
            self.client = None

        if self.connection_manager:
            await self.connection_manager.close()

        self.initialized = False
        logger.debug("Closed Z.AI service")

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

    def _handle_zai_error(self, error: Exception, operation: str = "operation") -> None:
        """
        Handle Z.AI-specific errors with appropriate logging.

        Args:
            error: The exception that occurred
            operation: Description of the operation that failed
        """
        # Z.AI SDK error handling - check for common error types
        error_str = str(error).lower()
        
        if "authentication" in error_str or "unauthorized" in error_str or "api key" in error_str:
            logger.error(f"Z.AI authentication failed during {operation}: Invalid API key")
        elif "rate limit" in error_str or "quota" in error_str:
            logger.warning(f"Z.AI rate limit exceeded during {operation}")
        elif "connection" in error_str or "network" in error_str or "timeout" in error_str:
            logger.error(f"Z.AI connection error during {operation}: {str(error)}")
        elif "api" in error_str:
            logger.error(f"Z.AI API error during {operation}: {str(error)}")
        else:
            logger.error(f"Unexpected error during {operation}: {str(error)}")
