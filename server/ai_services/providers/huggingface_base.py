"""Hugging Face base class."""

from typing import Dict, Any
from ..base import ProviderAIService, ServiceType
from ..connection import RetryHandler

class HuggingFaceBaseService(ProviderAIService):
    """Base class for Hugging Face services."""

    def __init__(self, config: Dict[str, Any], service_type: ServiceType = None, provider_name: str = "huggingface"):
        """
        Initialize the huggingface base service.

        Args:
            config: Configuration dictionary
            service_type: Type of AI service
            provider_name: Provider name (defaults to "huggingface")
        """
        # For cooperative multiple inheritance
        if service_type:
            super().__init__(config, service_type, provider_name)
        else:
            super().__init__(config, ServiceType.INFERENCE, provider_name)
        self._setup_huggingface_config()

    def _setup_huggingface_config(self) -> None:
        hf_config = self._extract_provider_config()
        self.api_key = hf_config.get("api_key") or self._resolve_api_key("HUGGINGFACE_API_KEY")
        self.model = self._get_model()
        self.endpoint_url = hf_config.get("endpoint_url")

        from huggingface_hub import AsyncInferenceClient
        self.client = AsyncInferenceClient(
            model=self.model,
            token=self.api_key,
            base_url=self.endpoint_url
        )

        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(**retry_config)
        self.logger.info(f"Configured Hugging Face with model: {self.model}")

    async def initialize(self) -> bool:
        try:
            self.initialized = True
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize Hugging Face: {str(e)}")
            return False

    async def verify_connection(self) -> bool:
        return True

    async def close(self) -> None:
        self.initialized = False

    def _handle_huggingface_error(self, error: Exception, operation: str = "operation") -> None:
        self.logger.error(f"Hugging Face error during {operation}: {str(error)}")
