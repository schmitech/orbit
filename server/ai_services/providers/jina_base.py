"""
Jina AI-specific base class for all Jina services.

This module provides a unified base class for all Jina AI-based services,
consolidating common functionality like API key management, client initialization,
and error handling.
"""

from typing import Dict, Any, Optional
import aiohttp
import asyncio
import logging

from ..base import ProviderAIService, ServiceType
from ..connection import ConnectionManager, RetryHandler


class JinaBaseService(ProviderAIService):
    """
    Base class for all Jina AI services.

    This class consolidates:
    - API key resolution and validation
    - HTTP session management
    - Base URL configuration
    - Connection verification
    - Common error handling patterns
    """

    DEFAULT_BASE_URL = "https://api.jina.ai/v1"

    def __init__(self, config: Dict[str, Any], service_type: ServiceType = None, provider_name: str = "jina"):
        """
        Initialize the Jina base service.

        Args:
            config: Configuration dictionary
            service_type: Type of AI service
            provider_name: Provider name (defaults to "jina")
        """
        # For cooperative multiple inheritance
        if service_type:
            super().__init__(config, service_type, provider_name)
        else:
            super().__init__(config, ServiceType.EMBEDDING, provider_name)
        self._setup_jina_config()

    def _setup_jina_config(self) -> None:
        """
        Set up Jina-specific configuration.

        This method:
        1. Resolves the API key from environment or config
        2. Sets the base URL (with default)
        3. Gets the model configuration
        4. Initializes HTTP session management
        """
        # Resolve API key
        self.api_key = self._resolve_api_key("JINA_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Jina API key is required. Set JINA_API_KEY environment "
                "variable or provide in configuration."
            )

        # Get base URL
        self.base_url = self._get_base_url(self.DEFAULT_BASE_URL)

        # Get model
        self.model = self._get_model()
        if not self.model:
            self.model = "jina-embeddings-v3"  # Default model

        # Get endpoint
        self.endpoint = self._get_endpoint("/embeddings")  # Default

        # Initialize session
        self.session = None
        self._session_lock = asyncio.Lock()

        # Setup connection manager
        self.connection_manager = ConnectionManager(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout_ms=self._get_timeout_config()['total']
        )

        # Setup retry handler
        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(
            max_retries=retry_config['max_retries'],
            initial_wait_ms=retry_config['initial_wait_ms'],
            max_wait_ms=retry_config['max_wait_ms'],
            exponential_base=retry_config['exponential_base'],
            enabled=retry_config['enabled']
        )

        self.logger.info(f"Configured Jina service with model: {self.model}")

    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Get or create an aiohttp client session.
        Uses a lock to prevent multiple session creations.

        Returns:
            An aiohttp ClientSession
        """
        async with self._session_lock:
            if self.session is None or self.session.closed:
                # Configure TCP connector with limits
                connector = aiohttp.TCPConnector(
                    limit=10,  # Limit total number of connections
                    limit_per_host=5,  # Limit connections per host
                    ttl_dns_cache=300,  # Cache DNS results for 5 minutes
                )
                timeout = aiohttp.ClientTimeout(total=30)  # 30 seconds total timeout
                self.session = aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout
                )
            return self.session

    async def initialize(self) -> bool:
        """
        Initialize the Jina service.

        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Create session if not already created
            await self._get_session()

            # Verify connection
            if await self.verify_connection():
                self.initialized = True
                self.logger.info(
                    f"Initialized Jina {self.service_type.value} service "
                    f"with model {self.model}"
                )
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to initialize Jina service: {str(e)}")
            return False

    async def verify_connection(self) -> bool:
        """
        Verify Jina connection.

        Returns:
            True if the connection is working, False otherwise
        """
        try:
            session = await self._get_session()
            url = f"{self.base_url}{self.endpoint}"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }

            # Simple payload for testing
            payload = {
                "model": self.model,
                "input": ["test connection"]
            }

            self.logger.info(f"Verifying connection to Jina API with model {self.model}")

            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"Error connecting to Jina API: {error_text}")
                    return False

                data = await response.json()

                # Verify the response structure
                if "data" in data and len(data["data"]) > 0 and "embedding" in data["data"][0]:
                    embedding = data["data"][0]["embedding"]
                    self.logger.info(f"Successfully verified connection to Jina API. Got embedding with {len(embedding)} dimensions.")
                    return True
                else:
                    self.logger.error(f"Unexpected response structure from Jina API: {data}")
                    return False

        except Exception as e:
            self.logger.error(f"Jina connection verification failed: {str(e)}")
            return False

    async def close(self) -> None:
        """
        Close the Jina service and release resources.
        """
        if self.session:
            await self.session.close()
            self.session = None

        if self.connection_manager:
            await self.connection_manager.close()

        self.initialized = False
        self.logger.debug("Closed Jina service")

    def _get_task(self, default: str = "text-matching") -> str:
        """
        Get task configuration for embeddings.

        Args:
            default: Default value if not configured

        Returns:
            Task type string
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('task', default)

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

    def _get_dimensions(self) -> Optional[int]:
        """
        Get embedding dimensions configuration.

        Returns:
            Dimensions or None if not configured
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('dimensions')

    def _handle_jina_error(self, error: Exception, operation: str = "operation") -> None:
        """
        Handle Jina-specific errors with appropriate logging.

        Args:
            error: The exception that occurred
            operation: Description of the operation that failed
        """
        error_str = str(error)

        if "api_key" in error_str.lower() or "unauthorized" in error_str.lower():
            self.logger.error(f"Jina authentication failed during {operation}: Invalid API key")
        elif "rate limit" in error_str.lower():
            self.logger.warning(f"Jina rate limit exceeded during {operation}")
        elif "connection" in error_str.lower():
            self.logger.error(f"Jina connection error during {operation}: {str(error)}")
        else:
            self.logger.error(f"Jina error during {operation}: {str(error)}")
