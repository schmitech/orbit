"""Llama.cpp base class."""

from typing import Dict, Any
from ..base import ProviderAIService, ServiceType
from ..connection import RetryHandler

class LlamaCppBaseService(ProviderAIService):
    """Base class for Llama.cpp services."""

    def __init__(self, config: Dict[str, Any], service_type: ServiceType = None, provider_name: str = "llama_cpp"):
        """
        Initialize the Llama.cpp base service.

        Args:
            config: Configuration dictionary
            service_type: Type of AI service
            provider_name: Provider name (defaults to "llama_cpp")
        """
        # For cooperative multiple inheritance
        if service_type:
            super().__init__(config, service_type, provider_name)
        else:
            super().__init__(config, ServiceType.INFERENCE, provider_name)
        self._setup_llama_cpp_config()

    def _setup_llama_cpp_config(self) -> None:
        llama_config = self._extract_provider_config()
        self.base_url = llama_config.get("base_url", "http://localhost:8080")
        self.model = self._get_model()

        # Llama.cpp server is OpenAI-compatible
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key="not-needed", base_url=self.base_url)

        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(**retry_config)
        self.logger.info(f"Configured Llama.cpp at {self.base_url}")

    async def initialize(self) -> bool:
        try:
            self.initialized = True
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize Llama.cpp: {str(e)}")
            return False

    async def verify_connection(self) -> bool:
        return True

    async def close(self) -> None:
        if self.client:
            await self.client.close()
        self.initialized = False

    def _handle_llama_cpp_error(self, error: Exception, operation: str = "operation") -> None:
        self.logger.error(f"Llama.cpp error during {operation}: {str(error)}")
