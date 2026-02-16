"""Hugging Face base class."""

import logging
from typing import Dict, Any
from ..base import ProviderAIService, ServiceType
from ..connection import RetryHandler

logger = logging.getLogger(__name__)

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

        # The 'provider' parameter controls which inference backend the HF client
        # routes to. Without it, the client auto-resolves via the model's
        # inferenceProviderMapping — if the model has no mapping, no inference
        # call is made and the response is silently empty.
        # Default to "hf-inference" (HF's own serverless API) unless overridden.
        self.hf_provider = hf_config.get("provider", "hf-inference")

        from huggingface_hub import AsyncInferenceClient

        client_kwargs: Dict[str, Any] = {
            "model": self.model,
            "token": self.api_key,
            "provider": self.hf_provider,
        }
        if self.endpoint_url:
            client_kwargs["base_url"] = self.endpoint_url

        self.client = AsyncInferenceClient(**client_kwargs)

        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(**retry_config)
        logger.info(f"Configured Hugging Face with model: {self.model}, provider: {self.hf_provider}")

    async def initialize(self) -> bool:
        try:
            if not self.api_key:
                logger.error("Hugging Face API key is not configured")
                return False
            self.initialized = True
            logger.info(f"Hugging Face service initialized with model: {self.model}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Hugging Face: {str(e)}")
            return False

    async def verify_connection(self) -> bool:
        try:
            await self.client.get_endpoint_info()
            logger.info(f"Hugging Face connection verified for model: {self.model}")
            return True
        except Exception as e:
            logger.warning(f"Hugging Face connection verification failed: {str(e)}")
            # Return True anyway — model may still work via serverless inference
            # even if get_endpoint_info fails (e.g. for non-dedicated endpoints)
            return True

    async def close(self) -> None:
        self.initialized = False

    def _handle_huggingface_error(self, error: Exception, operation: str = "operation") -> None:
        from huggingface_hub.utils import HfHubHTTPError
        error_str = str(error)

        if isinstance(error, HfHubHTTPError):
            if "401" in error_str or "403" in error_str:
                logger.error(f"Hugging Face authentication failed during {operation}: check API key")
            elif "429" in error_str:
                logger.warning(f"Hugging Face rate limit exceeded during {operation}")
            elif "404" in error_str:
                logger.error(f"Hugging Face model not found during {operation}: {self.model}")
            else:
                logger.error(f"Hugging Face HTTP error during {operation}: {error_str}")
        else:
            logger.error(f"Hugging Face error during {operation}: {error_str}")
