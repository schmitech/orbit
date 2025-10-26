"""
Ollama-specific base class for all Ollama services.

This module provides a unified base class for all Ollama-based services,
consolidating common functionality and integrating with existing Ollama utilities.
"""

from typing import Dict, Any, Optional
import logging

from ..base import ProviderAIService, ServiceType
from ..connection import ConnectionManager, RetryHandler

# Handle imports from both server package and direct execution
try:
    from server.utils.ollama_utils import (
        OllamaConfig,
        OllamaSessionManager,
        OllamaRetryHandler,
        OllamaModelWarmer,
        OllamaConnectionVerifier
    )
except ImportError:
    from utils.ollama_utils import (
        OllamaConfig,
        OllamaSessionManager,
        OllamaRetryHandler,
        OllamaModelWarmer,
        OllamaConnectionVerifier
    )


class OllamaBaseService(ProviderAIService):
    """
    Base class for all Ollama services.

    This class consolidates:
    - Ollama configuration management
    - Session and connection management
    - Model warm-up and verification
    - Retry logic with exponential backoff
    - Connection verification

    This integrates with the existing OllamaBaseService utilities
    while providing the new unified interface.
    """

    DEFAULT_BASE_URL = "http://localhost:11434"

    def __init__(self, config: Dict[str, Any], service_type: ServiceType = None, provider_name: str = "ollama"):
        """
        Initialize the Ollama base service.

        Args:
            config: Configuration dictionary
            service_type: Type of AI service
            provider_name: Provider name (defaults to "ollama")
        """
        # For cooperative multiple inheritance, accept provider_name but use "ollama" variant
        actual_provider = provider_name if provider_name else "ollama"
        if service_type:
            super().__init__(config, service_type, actual_provider)
        else:
            super().__init__(config, ServiceType.INFERENCE, actual_provider)
        self._setup_ollama_config()

    def _setup_ollama_config(self) -> None:
        """
        Set up Ollama-specific configuration using existing utilities.

        This method:
        1. Creates an OllamaConfig instance
        2. Sets up session manager
        3. Configures retry handler
        4. Initializes model warmer
        5. Sets up connection verifier
        """
        # Use the existing OllamaConfig for compatibility
        service_type_name = self._get_service_type_name()
        self.ollama_config = OllamaConfig(self.config, service_type_name)

        # Extract common values
        self.base_url = self.ollama_config.base_url
        self.model = self.ollama_config.model

        # Setup session manager
        self.session_manager = OllamaSessionManager(
            total_timeout=self.ollama_config.total_timeout,
            connection_limit=10,
            per_host_limit=5
        )

        # Setup retry handler using existing Ollama utilities
        self.ollama_retry_handler = OllamaRetryHandler(
            self.ollama_config,
            self.logger
        )

        # Setup model warmer
        self.model_warmer = OllamaModelWarmer(
            base_url=self.base_url,
            model=self.model,
            session_manager=self.session_manager,
            retry_handler=self.ollama_retry_handler,
            logger=self.logger
        )

        # Setup connection verifier
        self.connection_verifier = OllamaConnectionVerifier(
            base_url=self.base_url,
            model=self.model,
            session_manager=self.session_manager,
            logger=self.logger
        )

        self.logger.debug(f"Configured Ollama service with model: {self.model}")

    def _get_service_type_name(self) -> str:
        """
        Get the service type name for config lookup.

        Returns:
            Service type name (e.g., 'embeddings', 'inference')
        """
        # Map ServiceType enum to config key names
        type_map = {
            ServiceType.EMBEDDING: 'embeddings',
            ServiceType.INFERENCE: 'inference',
            ServiceType.MODERATION: 'moderators',
            ServiceType.RERANKING: 'rerankers',
            ServiceType.VISION: 'vision',
            ServiceType.AUDIO: 'audio'
        }
        return type_map.get(self.service_type, self.service_type.value)

    async def initialize(self) -> bool:
        """
        Initialize the Ollama service with model warm-up.

        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Determine warmup endpoint based on service type
            warmup_endpoint = self._get_warmup_endpoint()

            # Warm up the model
            await self.model_warmer.warmup_model(
                endpoint=warmup_endpoint,
                timeout=self.ollama_config.warmup_timeout
            )

            # Verify connection
            if await self.verify_connection():
                self.initialized = True
                self.logger.info(
                    f"Initialized Ollama {self.service_type.value} service "
                    f"with model {self.model}"
                )
                return True
            return False

        except Exception as e:
            self.logger.error(f"Failed to initialize Ollama service: {str(e)}")
            return False

    def _get_warmup_endpoint(self) -> str:
        """
        Get the appropriate warmup endpoint based on service type.

        Returns:
            Warmup endpoint name
        """
        endpoint_map = {
            ServiceType.EMBEDDING: 'embeddings',
            ServiceType.INFERENCE: 'generate',
            ServiceType.MODERATION: 'chat',
            ServiceType.RERANKING: 'generate',
            ServiceType.VISION: 'chat',
            ServiceType.AUDIO: 'generate'
        }
        return endpoint_map.get(self.service_type, 'generate')

    async def verify_connection(self) -> bool:
        """
        Verify Ollama connection and model availability.

        Returns:
            True if the connection is working, False otherwise
        """
        try:
            return await self.connection_verifier.verify_connection(check_model=True)
        except Exception as e:
            self.logger.error(f"Ollama connection verification failed: {str(e)}")
            return False

    async def close(self) -> None:
        """
        Close the Ollama service and release resources.
        """
        try:
            await self.session_manager.close()
            self.initialized = False
            self.logger.debug("Closed Ollama service")
        except Exception as e:
            self.logger.error(f"Error closing Ollama service: {str(e)}")

    def _get_temperature(self, default: float = 0.1) -> float:
        """
        Get temperature configuration.

        Args:
            default: Default value if not configured

        Returns:
            Temperature value
        """
        return self.ollama_config.temperature

    def _get_dimensions(self) -> Optional[int]:
        """
        Get embedding dimensions configuration.

        Returns:
            Dimensions or None if not configured
        """
        return self.ollama_config.dimensions

    def _get_batch_size(self, default: int = 5) -> int:
        """
        Get batch size configuration.

        Args:
            default: Default value if not configured

        Returns:
            Batch size
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('batch_size', default)

    async def execute_with_retry(self, operation, *args, **kwargs):
        """
        Execute an operation with Ollama's retry logic.

        Args:
            operation: Async function to execute
            *args: Positional arguments for operation
            **kwargs: Keyword arguments for operation

        Returns:
            Result of the operation
        """
        return await self.ollama_retry_handler.execute_with_retry(
            operation,
            *args,
            **kwargs
        )
