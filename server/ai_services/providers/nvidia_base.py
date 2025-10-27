"""NVIDIA NIM base class for NVIDIA AI services."""

from typing import Dict, Any
from ..base import ProviderAIService, ServiceType
from ..connection import RetryHandler

class NVIDIABaseService(ProviderAIService):
    """Base class for NVIDIA NIM services."""

    DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"

    def __init__(self, config: Dict[str, Any], service_type: ServiceType = None, provider_name: str = "nvidia"):
        """
        Initialize the nvidia base service.

        Args:
            config: Configuration dictionary
            service_type: Type of AI service
            provider_name: Provider name (defaults to "nvidia")
        """
        # For cooperative multiple inheritance
        if service_type:
            super().__init__(config, service_type, provider_name)
        else:
            super().__init__(config, ServiceType.INFERENCE, provider_name)
        self._setup_nvidia_config()

    def _setup_nvidia_config(self) -> None:
        """Set up NVIDIA-specific configuration."""
        nvidia_config = self._extract_provider_config()
        self.api_key = nvidia_config.get("api_key") or self._resolve_api_key("NVIDIA_API_KEY")
        if not self.api_key:
            raise ValueError("NVIDIA API key required")

        self.base_url = nvidia_config.get("base_url", self.DEFAULT_BASE_URL)
        self.model = self._get_model()

        # Use OpenAI client since NVIDIA NIM is OpenAI-compatible
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(**retry_config)
        self.logger.info(f"Configured NVIDIA NIM with model: {self.model}")

    async def initialize(self) -> bool:
        try:
            self.initialized = True
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize NVIDIA service: {str(e)}")
            return False

    async def verify_connection(self) -> bool:
        return True

    async def close(self) -> None:
        if self.client:
            await self.client.close()
        self.initialized = False

    def _handle_nvidia_error(self, error: Exception, operation: str = "operation") -> None:
        self.logger.error(f"NVIDIA error during {operation}: {str(error)}")
