"""IBM Watson base class."""

from typing import Dict, Any
from ..base import ProviderAIService, ServiceType
from ..connection import RetryHandler

class WatsonBaseService(ProviderAIService):
    """Base class for IBM Watson services."""

    def __init__(self, config: Dict, service_type: ServiceType):
        super().__init__(config, service_type, "watson")
        self._setup_watson_config()

    def _setup_watson_config(self) -> None:
        watson_config = self._extract_provider_config()
        self.api_key = watson_config.get("api_key") or self._resolve_api_key("WATSON_API_KEY")
        self.url = watson_config.get("url") or watson_config.get("endpoint")
        if not self.api_key or not self.url:
            raise ValueError("Watson API key and URL required")
        self.model = self._get_model()
        self.project_id = watson_config.get("project_id")

        from ibm_watson_machine_learning.foundation_models import Model
        self.client = Model(
            model_id=self.model,
            credentials={"apikey": self.api_key, "url": self.url},
            project_id=self.project_id
        )
        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(**retry_config)
        self.logger.info(f"Configured Watson with model: {self.model}")

    async def initialize(self) -> bool:
        try:
            self.initialized = True
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize Watson: {str(e)}")
            return False

    async def verify_connection(self) -> bool:
        return True

    async def close(self) -> None:
        self.initialized = False

    def _handle_watson_error(self, error: Exception, operation: str = "operation") -> None:
        self.logger.error(f"Watson error during {operation}: {str(error)}")
