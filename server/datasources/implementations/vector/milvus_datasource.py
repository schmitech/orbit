"""
Milvus Datasource Implementation
"""

import logging
from typing import Any, Dict, Optional
from ...base.base_datasource import BaseDatasource

logger = logging.getLogger(__name__)


class MilvusDatasource(BaseDatasource):
    """Milvus vector database datasource implementation."""
    
    @property
    def datasource_name(self) -> str:
        """Return the name of this datasource for config lookup."""
        return 'milvus'
    
    async def initialize(self) -> None:
        """Initialize the Milvus client."""
        milvus_config = self.config.get('datasources', {}).get('milvus', {})
        
        try:
            from pymilvus import connections, utility
        except ImportError:
            logger.warning("pymilvus not available. Install with: pip install pymilvus")
            logger.info("Milvus datasource not yet implemented")
            self._client = None
            self._initialized = True
            return
        
        # Extract connection parameters
        host = milvus_config.get('host', 'localhost')
        port = milvus_config.get('port', 19530)
        
        try:
            # Connect to Milvus
            connections.connect("default", host=host, port=port)
            
            # Test the connection
            if utility.has_connection("default"):
                logger.info(f"Milvus connection successful to {host}:{port}")
                self._client = connections.get_connection_addr("default")
                self._initialized = True
            else:
                raise Exception("Failed to establish Milvus connection")
                
        except Exception as e:
            logger.error(f"Failed to connect to Milvus: {str(e)}")
            logger.info("Milvus datasource not yet implemented")
            self._client = None
            self._initialized = True
    
    async def health_check(self) -> bool:
        """Perform a health check on the Milvus connection."""
        if not self._initialized:
            return False
            
        if self._client is None:
            return False
            
        try:
            from pymilvus import utility
            return utility.has_connection("default")
        except Exception as e:
            logger.error(f"Milvus health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Close the Milvus connection."""
        if self._client:
            try:
                from pymilvus import connections
                connections.disconnect("default")
            except Exception as e:
                logger.warning(f"Error disconnecting from Milvus: {e}")
            finally:
                self._client = None
                self._initialized = False
                logger.info("Milvus connection closed")
