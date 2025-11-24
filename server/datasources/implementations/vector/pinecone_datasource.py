"""
Pinecone Datasource Implementation
"""

import logging
from typing import Any, Dict, Optional
from ...base.base_datasource import BaseDatasource

logger = logging.getLogger(__name__)


class PineconeDatasource(BaseDatasource):
    """Pinecone vector database datasource implementation."""

    @property
    def datasource_name(self) -> str:
        """Return the name of this datasource for config lookup."""
        return 'pinecone'

    async def initialize(self) -> None:
        """Initialize the Pinecone client."""
        try:
            from pinecone import Pinecone
        except ImportError:
            logger.error("pinecone not available. Install with: pip install pinecone-client")
            raise

        pinecone_config = self.config.get('datasources', {}).get('pinecone', {})
        api_key = pinecone_config.get('api_key')

        if not api_key:
            raise ValueError("Pinecone API key is required")

        logger.info("Initializing Pinecone client...")

        # Initialize Pinecone client (new SDK v3+ API)
        self._client = Pinecone(api_key=api_key)

        self._initialized = True
        logger.info("Pinecone client initialized successfully")

    async def health_check(self) -> bool:
        """Perform a health check on the Pinecone connection."""
        if not self._initialized or not self._client:
            return False

        try:
            # Try to list indexes as a health check
            indexes = self._client.list_indexes()
            return True
        except Exception as e:
            logger.error(f"Pinecone health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close the Pinecone connection."""
        if self._client:
            # Pinecone client doesn't have explicit close method
            self._client = None
            self._initialized = False
            logger.info("Pinecone client closed")
