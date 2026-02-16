"""
Elasticsearch Datasource Implementation

Provides pooled Elasticsearch client connections following the same pattern as SQL datasources.
Compatible with Elasticsearch 9.x and OpenSearch.
"""

import logging
from typing import Dict, Any, Optional
from elasticsearch import AsyncElasticsearch

from ..base.base_datasource import BaseDatasource

logger = logging.getLogger(__name__)


class ElasticsearchDatasource(BaseDatasource):
    """
    Elasticsearch datasource with connection pooling support.

    This datasource integrates with the datasource registry for automatic
    connection sharing and reference counting across multiple adapters.
    """

    def __init__(self, config: Dict[str, Any], logger_instance: Optional[logging.Logger] = None):
        """
        Initialize Elasticsearch datasource.

        Args:
            config: Full configuration dictionary containing datasources section
            logger_instance: Logger instance for logging operations
        """
        super().__init__(config, logger_instance)

        # Extract Elasticsearch-specific configuration from datasources section
        es_config = config.get('datasources', {}).get('elasticsearch', {})

        # Extract connection parameters
        # Config manager already does environment variable substitution
        self.node = es_config.get('node', 'http://localhost:9200')
        self.verify_certs = es_config.get('verify_certs', True)
        self.request_timeout = es_config.get('timeout', 30)

        # Get authentication credentials (already substituted by config manager)
        auth_config = es_config.get('auth', {})
        self.username = auth_config.get('username', '')
        self.password = auth_config.get('password', '')

    @property
    def datasource_name(self) -> str:
        """Return the datasource name for registry lookup."""
        return "elasticsearch"

    async def initialize(self) -> None:
        """Initialize the Elasticsearch client connection."""
        if self._initialized:
            logger.debug("Elasticsearch datasource already initialized")
            return

        try:
            # Build client kwargs following ES 9.x patterns from logger_service.py
            client_kwargs = {
                "request_timeout": self.request_timeout,
                "retry_on_timeout": True,
                "max_retries": 3,
                "http_compress": True  # Enable compression for better performance
            }

            # Add authentication if credentials are available
            if self.username and self.password:
                client_kwargs["basic_auth"] = (self.username, self.password)
                logger.info("Elasticsearch: Using basic authentication")
            else:
                logger.warning("Elasticsearch: No credentials found, attempting unauthenticated connection")

            # SSL/TLS configuration
            if self.node.startswith('https'):
                client_kwargs["verify_certs"] = self.verify_certs
                client_kwargs["ssl_show_warn"] = False
                if not self.verify_certs:
                    logger.warning("Elasticsearch: SSL certificate verification disabled")

            # Create the async Elasticsearch client
            self._client = AsyncElasticsearch(
                self.node,
                **client_kwargs
            )

            # Test connection
            cluster_info = await self._client.info()
            logger.info(f"Connected to Elasticsearch cluster: {cluster_info.get('cluster_name', 'unknown')} "
                           f"(version: {cluster_info.get('version', {}).get('number', 'unknown')})")

            self._initialized = True

        except Exception as e:
            logger.error(f"Failed to initialize Elasticsearch datasource: {e}")
            self._client = None
            raise

    async def close(self) -> None:
        """Close the Elasticsearch client connection."""
        if self._client:
            try:
                await self._client.close()
                logger.info("Elasticsearch datasource connection closed")
            except Exception as e:
                logger.error(f"Error closing Elasticsearch client: {e}")
            finally:
                self._client = None
                self._initialized = False

    def get_cache_key(self) -> str:
        """
        Generate a cache key for connection pooling.

        Returns:
            Cache key string for this datasource configuration
        """
        # Include node URL and username in cache key
        # This ensures different ES clusters/users get separate connections
        username = self.username or "anonymous"
        return f"elasticsearch:{self.node}:{username}"

    async def health_check(self) -> bool:
        """
        Perform health check on the Elasticsearch connection.

        Returns:
            True if the datasource is healthy and accessible, False otherwise
        """
        try:
            if not self._client:
                logger.warning("Elasticsearch health check: client not initialized")
                return False

            # Ping the cluster
            is_alive = await self._client.ping()

            if is_alive:
                # Optionally get cluster health for logging
                cluster_health = await self._client.cluster.health()
                logger.debug(
                    f"Elasticsearch cluster healthy: {cluster_health.get('cluster_name')} "
                    f"(status: {cluster_health.get('status')})"
                )
                return True
            else:
                logger.warning("Elasticsearch health check: ping failed")
                return False

        except Exception as e:
            logger.error(f"Elasticsearch health check error: {e}")
            return False
