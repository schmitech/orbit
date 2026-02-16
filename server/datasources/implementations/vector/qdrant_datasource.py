"""
Qdrant Datasource Implementation
"""

import logging
from ...base.base_datasource import BaseDatasource

logger = logging.getLogger(__name__)


class QdrantDatasource(BaseDatasource):
    """Qdrant vector database datasource implementation."""

    @property
    def datasource_name(self) -> str:
        """Return the name of this datasource for config lookup."""
        return 'qdrant'

    async def initialize(self) -> None:
        """Initialize the Qdrant client."""
        try:
            from qdrant_client import QdrantClient
        except ImportError:
            logger.error("qdrant-client not available. Install with: pip install qdrant-client")
            raise

        qdrant_config = self.config.get('datasources', {}).get('qdrant', {})
        host = qdrant_config.get('host', 'localhost')
        port = qdrant_config.get('port', 6333)
        api_key = qdrant_config.get('api_key')
        url = qdrant_config.get('url')  # Alternative to host:port

        logger.info("Initializing Qdrant client...")

        # Initialize Qdrant client
        if url:
            # Use URL if provided (for cloud instances)
            self._client = QdrantClient(url=url, api_key=api_key)
        else:
            # Use host:port for self-hosted instances
            self._client = QdrantClient(host=host, port=port, api_key=api_key)

        self._initialized = True
        logger.info("Qdrant client initialized successfully")

    async def health_check(self) -> bool:
        """Perform a health check on the Qdrant connection."""
        if not self._initialized or not self._client:
            return False

        try:
            # Try to get collections as a health check
            self._client.get_collections()
            return True
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close the Qdrant connection."""
        if self._client:
            try:
                # Close the Qdrant client connection
                self._client.close()
            except Exception as e:
                logger.warning(f"Error closing Qdrant client: {e}")
            finally:
                self._client = None
                self._initialized = False
                logger.info("Qdrant client closed")
