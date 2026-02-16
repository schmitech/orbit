"""
OpenAI-compatible base class for providers that implement OpenAI-compatible APIs.

This module provides a unified base class for all providers that offer OpenAI-compatible
APIs (Groq, Mistral, DeepSeek, Fireworks, Perplexity, Together, OpenRouter, xAI).

These providers use the same API structure as OpenAI but with different:
- Base URLs
- API key environment variables
- Model names
- Some minor parameter variations
"""

from typing import Dict, Any
import asyncio
from openai import AsyncOpenAI
import httpx
import logging

from ..base import ProviderAIService, ServiceType
from ..connection import ConnectionManager, RetryHandler



logger = logging.getLogger(__name__)
class OpenAICompatibleBaseService(ProviderAIService):
    """
    Base class for all OpenAI-compatible services.

    This class consolidates:
    - API key resolution and validation (provider-specific)
    - AsyncOpenAI client initialization pointing to provider's API
    - Base URL configuration (provider-specific)
    - Connection verification
    - Common error handling patterns

    Providers using this base class:
    - Groq
    - Mistral
    - DeepSeek
    - Fireworks
    - Perplexity
    - Together
    - OpenRouter
    - xAI (Grok)
    """

    # Default base URLs for known providers
    # These can be overridden in configuration
    DEFAULT_BASE_URLS = {
        "groq": "https://api.groq.com/openai/v1",
        "mistral": "https://api.mistral.ai/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "fireworks": "https://api.fireworks.ai/inference/v1",
        "perplexity": "https://api.perplexity.ai",
        "together": "https://api.together.xyz/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "xai": "https://api.x.ai/v1",
    }

    # Default API key environment variable names
    API_KEY_ENV_VARS = {
        "groq": "GROQ_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "fireworks": "FIREWORKS_API_KEY",
        "perplexity": "PERPLEXITY_API_KEY",
        "together": "TOGETHER_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "xai": "XAI_API_KEY",
    }

    def __init__(
        self,
        config: Dict[str, Any],
        service_type: ServiceType,
        provider_name: str
    ):
        """
        Initialize the OpenAI-compatible base service.

        Args:
            config: Configuration dictionary
            service_type: Type of AI service
            provider_name: Name of the provider (groq, mistral, etc.)
        """
        super().__init__(config, service_type, provider_name)
        self._setup_openai_compatible_config()

    def _setup_openai_compatible_config(self) -> None:
        """
        Set up OpenAI-compatible configuration.

        This method:
        1. Resolves the API key from environment or config (provider-specific)
        2. Sets the base URL (provider-specific with default)
        3. Gets the model configuration
        4. Initializes the AsyncOpenAI client pointing to the provider's API
        """
        # Resolve API key using provider-specific environment variable
        api_key_env_var = self.API_KEY_ENV_VARS.get(
            self.provider_name,
            f"{self.provider_name.upper()}_API_KEY"
        )
        self.api_key = self._resolve_api_key(api_key_env_var)

        if not self.api_key:
            raise ValueError(
                f"{self.provider_name.title()} API key is required. "
                f"Set {api_key_env_var} environment variable or provide in configuration."
            )

        # Get base URL with provider-specific default
        default_base_url = self.DEFAULT_BASE_URLS.get(
            self.provider_name,
            f"https://api.{self.provider_name}.com/v1"
        )
        self.base_url = self._get_base_url(default_base_url)

        # Get model
        self.model = self._get_model()

        # Get endpoint (optional, some providers may use this)
        self.endpoint = self._get_endpoint("/chat/completions")  # Default for inference

        # Initialize AsyncOpenAI client with optimized httpx settings for streaming
        # HTTP/2 provides better multiplexing and connection reuse
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
            api_key=self.api_key,
            base_url=self.base_url,
            http_client=http_client
        )

        # Setup connection manager for additional HTTP operations
        self.connection_manager = ConnectionManager(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout_ms=self._get_timeout_config()['total']
        )

        self.connection_verified = False
        self._verification_attempted = False
        self._verification_inflight = False

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
        Initialize the OpenAI-compatible service.

        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            if self.initialized:
                return True

            self.initialized = True

            if not self._verification_attempted:
                self._verification_attempted = True
                self._verification_inflight = True
                try:
                    asyncio.create_task(self._run_connection_verification())
                except RuntimeError:
                    await self._run_connection_verification()
            else:
                logger.debug(
                    "Skipping %s verification; already attempted during this lifecycle",
                    self.provider_name,
                )

            if self.connection_verified:
                logger.info(
                    f"Initialized {self.provider_name.title()} "
                    f"{self.service_type.value} service with model {self.model}"
                )
            elif self._verification_inflight:
                logger.info(
                    f"Initialized {self.provider_name.title()} "
                    f"{self.service_type.value} service with model {self.model} "
                    f"(verification running asynchronously)"
                )
            else:
                logger.info(
                    f"Initialized {self.provider_name.title()} "
                    f"{self.service_type.value} service with model {self.model} "
                    f"(verification skipped or failed)"
                )
            return True
        except Exception as e:
            logger.error(
                f"Failed to initialize {self.provider_name.title()} service: {str(e)}"
            )
            return False

    async def verify_connection(self) -> bool:
        """
        Verify connection to the OpenAI-compatible provider.

        Note: Not all providers support the /models endpoint, so we use a simple
        test request if listing models fails.

        Returns:
            True if the connection is working, False otherwise
        """
        try:
            # Check if client is initialized
            if not self.client:
                logger.error(
                    f"{self.provider_name.title()} client is not initialized. Cannot verify connection."
                )
                return False
            
            # Try to list models (some providers support this)
            try:
                await self.client.models.list()
                logger.debug(
                    f"{self.provider_name.title()} connection verified successfully"
                )
                return True
            except Exception:
                # If models endpoint doesn't work, try a minimal test request
                logger.debug(
                    f"{self.provider_name.title()} models endpoint not available, "
                    f"trying test request"
                )

                # Make a minimal test request
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": "test"}],
                    max_tokens=1,
                    temperature=0
                )

                if response and response.choices:
                    logger.debug(
                        f"{self.provider_name.title()} connection verified via test request"
                    )
                    return True

                return False

        except Exception as e:
            logger.error(
                f"{self.provider_name.title()} connection verification failed: {str(e)}"
            )
            return False

    async def _run_connection_verification(self) -> None:
        """Run connection verification without blocking the caller."""
        try:
            self.connection_verified = await self.verify_connection()
            if self.connection_verified:
                logger.debug(
                    "%s verification completed successfully (async)",
                    self.provider_name.title(),
                )
            else:
                logger.debug(
                    "%s verification completed with negative result (async)",
                    self.provider_name.title(),
                )
        except Exception as verify_error:
            self.connection_verified = False
            logger.warning(
                "%s verification raised an exception; continuing without health check: %s",
                self.provider_name.title(),
                str(verify_error),
            )
        finally:
            self._verification_inflight = False

    async def close(self) -> None:
        """
        Close the OpenAI-compatible service and release resources.
        """
        if self.client:
            await self.client.close()
            self.client = None

        if self.connection_manager:
            await self.connection_manager.close()

        self.initialized = False
        self._verification_attempted = False
        self.connection_verified = False
        self._verification_inflight = False
        logger.debug(f"Closed {self.provider_name.title()} service")

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

    def _get_temperature(self, default: float = 0.7) -> float:
        """
        Get temperature configuration.

        Args:
            default: Default value if not configured

        Returns:
            Temperature value
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('temperature', default)

    def _get_top_p(self, default: float = 1.0) -> float:
        """
        Get top_p configuration.

        Args:
            default: Default value if not configured

        Returns:
            Top P value
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

    def _handle_openai_compatible_error(
        self,
        error: Exception,
        operation: str = "operation"
    ) -> None:
        """
        Handle OpenAI-compatible API errors with appropriate logging.

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

            provider_title = self.provider_name.title()

            if isinstance(error, AuthenticationError):
                logger.error(
                    f"{provider_title} authentication failed during {operation}: "
                    f"Invalid API key"
                )
            elif isinstance(error, RateLimitError):
                logger.warning(
                    f"{provider_title} rate limit exceeded during {operation}"
                )
            elif isinstance(error, APIConnectionError):
                logger.error(
                    f"{provider_title} connection error during {operation}: {str(error)}"
                )
            elif isinstance(error, APIError):
                logger.error(
                    f"{provider_title} API error during {operation}: {str(error)}"
                )
            else:
                logger.error(
                    f"Unexpected error during {operation} with {provider_title}: "
                    f"{str(error)}"
                )
        except ImportError:
            # If openai exceptions aren't available, just log the error
            logger.error(
                f"Error during {operation} with {self.provider_name.title()}: "
                f"{str(error)}"
            )
