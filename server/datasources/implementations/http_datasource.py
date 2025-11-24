"""
HTTP Datasource Implementation

Placeholder datasource for HTTP-based adapters. Unlike SQL or Elasticsearch datasources,
HTTP adapters manage their own HTTP clients per adapter (since each API has different
base URLs, authentication, etc.). This datasource exists to satisfy the datasource
registry pattern and eliminate warnings.
"""

import logging
from typing import Dict, Any, Optional

from ..base.base_datasource import BaseDatasource

logger = logging.getLogger(__name__)


class HTTPDatasource(BaseDatasource):
    """
    HTTP datasource placeholder for registry integration.

    Note: HTTP adapters manage their own httpx.AsyncClient instances via base_url
    configuration. This datasource exists for registry pattern consistency only.
    """

    def __init__(self, config: Dict[str, Any], logger_instance: Optional[logging.Logger] = None):
        """
        Initialize HTTP datasource placeholder.

        Args:
            config: Full configuration dictionary
            logger_instance: Logger instance for logging operations
        """
        super().__init__(config, logger_instance)

        # HTTP adapters don't use centralized configuration
        # Each adapter has its own base_url, auth, timeout, etc.
        logger.debug("HTTP datasource initialized (placeholder for registry pattern)")

    @property
    def datasource_name(self) -> str:
        """Return the datasource name for registry lookup."""
        return "http"

    async def initialize(self) -> None:
        """
        Initialize the HTTP datasource.

        Since HTTP adapters manage their own clients, this is a no-op.
        """
        if self._initialized:
            logger.debug("HTTP datasource already initialized")
            return

        try:
            # No actual connection to initialize - HTTP adapters manage their own clients
            logger.debug("HTTP datasource initialized (no centralized connection needed)")
            self._initialized = True

        except Exception as e:
            logger.error(f"Failed to initialize HTTP datasource: {e}")
            raise

    async def close(self) -> None:
        """
        Close the HTTP datasource.

        Since HTTP adapters manage their own clients, this is a no-op.
        """
        if self._initialized:
            logger.debug("HTTP datasource closed (no centralized connection to close)")
            self._initialized = False

    def get_cache_key(self) -> str:
        """
        Generate a cache key for the HTTP datasource.

        Since HTTP adapters are adapter-specific (each has its own base_url),
        we use a generic key. Individual adapters cache their own HTTP clients.

        Returns:
            Cache key string for this datasource
        """
        return "http:placeholder"

    async def health_check(self) -> bool:
        """
        Perform health check on the HTTP datasource.

        Since there's no centralized connection, always return True.
        Individual HTTP adapters perform their own health checks.

        Returns:
            True (always healthy since there's no connection to check)
        """
        logger.debug("HTTP datasource health check (always healthy - placeholder datasource)")
        return True

    @property
    def client(self):
        """
        Return client (not applicable for HTTP datasource).

        HTTP adapters create their own httpx.AsyncClient instances.
        This property exists for interface compatibility only.
        """
        logger.warning(
            "HTTP datasource has no centralized client. "
            "HTTP adapters manage their own httpx.AsyncClient instances via base_url."
        )
        return None
