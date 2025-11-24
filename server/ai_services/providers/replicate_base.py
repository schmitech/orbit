"""Replicate base class for Replicate AI services."""

import logging
from typing import Dict, Any
from ..base import ProviderAIService, ServiceType
from ..connection import RetryHandler

logger = logging.getLogger(__name__)

class ReplicateBaseService(ProviderAIService):
    """Base class for Replicate services."""

    def __init__(self, config: Dict[str, Any], service_type: ServiceType = None, provider_name: str = "replicate"):
        """
        Initialize the replicate base service.

        Args:
            config: Configuration dictionary
            service_type: Type of AI service
            provider_name: Provider name (defaults to "replicate")
        """
        # For cooperative multiple inheritance
        if service_type:
            super().__init__(config, service_type, provider_name)
        else:
            super().__init__(config, ServiceType.INFERENCE, provider_name)
        self._setup_replicate_config()

    def _setup_replicate_config(self) -> None:
        """Set up Replicate-specific configuration."""
        replicate_config = self._extract_provider_config()
        self.api_key = replicate_config.get("api_key") or self._resolve_api_key("REPLICATE_API_KEY")
        if not self.api_key:
            raise ValueError("Replicate API key required")

        self.model = self._get_model()

        # Initialize Replicate client
        import replicate as replicate_module
        self.client = replicate_module.Client(api_token=self.api_key)

        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(**retry_config)
        logger.info(f"Configured Replicate with model: {self.model}")

    async def initialize(self) -> bool:
        try:
            self.initialized = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Replicate: {str(e)}")
            return False

    async def verify_connection(self) -> bool:
        return True

    async def close(self) -> None:
        self.initialized = False

    def _handle_replicate_error(self, error: Exception, operation: str = "operation") -> None:
        logger.error(f"Replicate error during {operation}: {str(error)}")
