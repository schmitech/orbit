"""
Google Cloud-specific base class for Google AI services (Vertex AI & Gemini).

This module provides a unified base class for Google Cloud-based services,
consolidating common functionality like credential management and client initialization.
"""

from typing import Dict, Any
import logging

from ..base import ProviderAIService, ServiceType
from ..connection import RetryHandler



logger = logging.getLogger(__name__)
class GoogleBaseService(ProviderAIService):
    """
    Base class for all Google Cloud AI services (Vertex AI, Gemini).

    This class consolidates:
    - Google Cloud project and location configuration
    - Credential management
    - Common configuration patterns
    - Connection verification
    - Common Google error handling patterns
    """

    DEFAULT_LOCATION = "us-central1"

    def __init__(self, config: Dict[str, Any], service_type: ServiceType, provider_name: str):
        """
        Initialize the Google base service.

        Args:
            config: Configuration dictionary
            service_type: Type of AI service
            provider_name: Provider name ("vertexai" or "gemini")
        """
        super().__init__(config, service_type, provider_name)
        self._setup_google_config()

    def _setup_google_config(self) -> None:
        """
        Set up Google Cloud-specific configuration.

        This method:
        1. Gets the Google Cloud project ID
        2. Gets the location/region
        3. Initializes credentials if needed
        4. Gets model configuration
        """
        google_config = self._extract_provider_config()

        # Get project ID (required for Vertex AI)
        self.project_id = google_config.get("project_id") or self._resolve_api_key("GOOGLE_CLOUD_PROJECT", "project_id")

        # Get location/region
        self.location = google_config.get("location", self.DEFAULT_LOCATION)

        # Get model
        self.model = self._get_model()

        # Setup retry handler
        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(
            max_retries=retry_config['max_retries'],
            initial_wait_ms=retry_config['initial_wait_ms'],
            max_wait_ms=retry_config['max_wait_ms'],
            exponential_base=retry_config['exponential_base'],
            enabled=retry_config['enabled']
        )

        logger.info(
            f"Configured {self.provider_name.title()} service with model: {self.model}"
        )

    async def initialize(self) -> bool:
        """
        Initialize the Google Cloud service.

        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            self.initialized = True
            logger.info(
                f"Initialized {self.provider_name.title()} {self.service_type.value} service "
                f"with model {self.model}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to initialize {self.provider_name.title()} service: {str(e)}")
            return False

    async def verify_connection(self) -> bool:
        """
        Verify Google Cloud connection.

        Returns:
            True if the connection is working, False otherwise
        """
        try:
            # Basic validation
            if self.provider_name == "vertexai" and not self.project_id:
                logger.error("Vertex AI requires project_id")
                return False

            logger.debug(f"{self.provider_name.title()} connection verified")
            return True
        except Exception as e:
            logger.error(f"{self.provider_name.title()} connection verification failed: {str(e)}")
            return False

    async def close(self) -> None:
        """Close the Google Cloud service and release resources."""
        self.initialized = False
        logger.debug(f"Closed {self.provider_name.title()} service")

    def _get_max_tokens(self, default: int = 1024) -> int:
        """Get max_tokens configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('max_tokens', default)

    def _get_temperature(self, default: float = 0.7) -> float:
        """Get temperature configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('temperature', default)

    def _get_top_p(self, default: float = 1.0) -> float:
        """Get top_p configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('top_p', default)

    def _get_top_k(self, default: int = 40) -> int:
        """Get top_k configuration (Google-specific)."""
        provider_config = self._extract_provider_config()
        return provider_config.get('top_k', default)

    def _handle_google_error(self, error: Exception, operation: str = "operation") -> None:
        """
        Handle Google Cloud-specific errors with appropriate logging.

        Args:
            error: The exception that occurred
            operation: Description of the operation that failed
        """
        error_str = str(error)

        if "authentication" in error_str.lower() or "credential" in error_str.lower():
            logger.error(
                f"{self.provider_name.title()} authentication failed during {operation}: Invalid credentials"
            )
        elif "quota" in error_str.lower():
            logger.warning(
                f"{self.provider_name.title()} quota exceeded during {operation}"
            )
        elif "permission" in error_str.lower():
            logger.error(
                f"{self.provider_name.title()} permission error during {operation}: {error_str}"
            )
        else:
            logger.error(
                f"{self.provider_name.title()} error during {operation}: {error_str}"
            )
