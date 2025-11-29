"""Shimmy base class."""

from typing import Dict, Any
import logging
from openai import AsyncOpenAI
import httpx

from ..base import ProviderAIService, ServiceType
from ..connection import RetryHandler

logger = logging.getLogger(__name__)


class ShimmyBaseService(ProviderAIService):
    """
    Base class for Shimmy services.
    
    Shimmy is a 100% OpenAI-compatible inference server for GGUF models.
    It only supports API mode (no direct model loading).
    """

    def __init__(self, config: Dict[str, Any], service_type: ServiceType = None, provider_name: str = "shimmy"):
        """
        Initialize the Shimmy base service.
        
        Args:
            config: Configuration dictionary
            service_type: Type of AI service
            provider_name: Provider name (defaults to "shimmy")
        """
        # For cooperative multiple inheritance
        if service_type:
            super().__init__(config, service_type, provider_name)
        else:
            super().__init__(config, ServiceType.INFERENCE, provider_name)
        self._setup_shimmy_config()

    def _setup_shimmy_config(self) -> None:
        """Setup Shimmy configuration."""
        shimmy_config = self._extract_provider_config()
        
        # Get base URL and ensure it ends with /v1 for OpenAI compatibility
        base_url = shimmy_config.get("base_url", "http://localhost:11435")
        if not base_url.endswith('/v1'):
            self.base_url = base_url.rstrip('/') + '/v1'
        else:
            self.base_url = base_url
        
        # Get model name
        self.model = self._get_model()
        
        # Optional API key (Shimmy doesn't require authentication, but some setups might use it)
        api_key = shimmy_config.get("api_key")
        if api_key is None:
            api_key = "not-needed"  # Shimmy doesn't require authentication
        
        # Initialize OpenAI-compatible client with optimized httpx settings for streaming
        http_client = httpx.AsyncClient(
            http2=True,  # Enable HTTP/2 for better performance
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=100,
                keepalive_expiry=300.0  # Keep connections alive for 5 minutes
            ),
            timeout=httpx.Timeout(60.0, connect=5.0)
        )
        
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.base_url,
            http_client=http_client
        )
        
        # Setup retry handler
        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(**retry_config)
        
        logger.info(f"Configured Shimmy service at {self.base_url} with model: {self.model}")

    async def initialize(self) -> bool:
        """Initialize the Shimmy service."""
        try:
            if self.initialized:
                return True
            
            self.initialized = True
            logger.info(f"Initialized Shimmy service at {self.base_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Shimmy service: {str(e)}")
            return False

    async def verify_connection(self) -> bool:
        """
        Verify connection to the Shimmy server.
        
        Returns:
            True if the connection is working, False otherwise
        """
        try:
            if not self.client:
                logger.error("Shimmy client is not initialized. Cannot verify connection.")
                return False
            
            # Try to list models (Shimmy supports /v1/models endpoint)
            try:
                await self.client.models.list()
                logger.debug("Shimmy connection verified successfully")
                return True
            except Exception as models_error:
                # If models endpoint doesn't work, try a minimal test request
                logger.debug(
                    f"Shimmy models endpoint not available, trying test request: {str(models_error)}"
                )
                
                # Make a minimal test request
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": "test"}],
                    max_tokens=1,
                    temperature=0
                )
                
                if response and response.choices:
                    logger.debug("Shimmy connection verified via test request")
                    return True
                
                return False
                
        except Exception as e:
            logger.error(f"Shimmy connection verification failed: {str(e)}")
            return False

    async def close(self) -> None:
        """Close the Shimmy service and release resources."""
        if self.client:
            await self.client.close()
            self.client = None
        
        self.initialized = False
        logger.debug("Closed Shimmy service")

    def _handle_shimmy_error(self, error: Exception, operation: str = "operation") -> None:
        """
        Handle Shimmy API errors with appropriate logging.
        
        Args:
            error: The exception that occurred
            operation: Description of the operation that failed
        """
        try:
            from openai import (
                APIError,
                APIConnectionError,
                RateLimitError,
                AuthenticationError
            )

            if isinstance(error, AuthenticationError):
                logger.error(
                    f"Shimmy authentication failed during {operation}: {str(error)}"
                )
            elif isinstance(error, RateLimitError):
                logger.warning(
                    f"Shimmy rate limit exceeded during {operation}"
                )
            elif isinstance(error, APIConnectionError):
                logger.error(
                    f"Shimmy connection error during {operation}: {str(error)}. "
                    f"Make sure the Shimmy server is running at {self.base_url}"
                )
            elif isinstance(error, APIError):
                logger.error(
                    f"Shimmy API error during {operation}: {str(error)}"
                )
            else:
                logger.error(
                    f"Unexpected error during {operation} with Shimmy: {str(error)}"
                )
        except ImportError:
            # If openai exceptions aren't available, just log the error
            logger.error(
                f"Error during {operation} with Shimmy: {str(error)}"
            )

