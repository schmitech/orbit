"""
DuckDB Datasource Implementation
"""

import logging
import duckdb
from typing import Any, Dict, Optional
from ...base.base_datasource import BaseDatasource

logger = logging.getLogger(__name__)


class DuckDBDatasource(BaseDatasource):
    """DuckDB database datasource implementation for CSV/Parquet file querying."""
    
    @property
    def datasource_name(self) -> str:
        """Return the name of this datasource for config lookup."""
        return 'duckdb'
    
    async def initialize(self) -> None:
        """Initialize the DuckDB database connection."""
        duckdb_config = self.config.get('datasources', {}).get('duckdb', {})
        database = duckdb_config.get('database', ':memory:')
        read_only = duckdb_config.get('read_only', False)
        access_mode = duckdb_config.get('access_mode', 'automatic')
        threads = duckdb_config.get('threads', None)
        
        logger.info(f"Initializing DuckDB connection to {database}")
        
        try:
            # Configure connection parameters
            config_params = {}
            if access_mode and access_mode != 'automatic':
                config_params['access_mode'] = access_mode
            if threads is not None:
                config_params['threads'] = threads
            
            # Create connection
            if config_params:
                self._client = duckdb.connect(database, read_only=read_only, config=config_params)
            else:
                self._client = duckdb.connect(database, read_only=read_only)
            
            # Load HTTP/S remote file support so CSV/Parquet reads work across protocols
            try:
                self._client.execute("INSTALL httpfs;")
                self._client.execute("LOAD httpfs;")
                logger.debug("DuckDB httpfs extension loaded for remote file support")
            except Exception as extension_error:
                logger.warning(f"Failed to load DuckDB httpfs extension: {extension_error}")
            
            # Test the connection with a simple query
            result = self._client.execute("SELECT version();").fetchone()
            
            if result:
                version = result[0]
                logger.info(f"DuckDB connection successful: {version}")
            
            self._initialized = True
            logger.info("DuckDB connection established successfully")
            
        except Exception as e:
            logger.error(f"Failed to connect to DuckDB database: {str(e)}")
            raise
    
    async def health_check(self) -> bool:
        """Perform a health check on the DuckDB connection."""
        if not self._initialized or not self._client:
            return False
        
        try:
            self._client.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"DuckDB health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Close the DuckDB connection."""
        if self._client:
            try:
                self._client.close()
            except Exception as e:
                logger.warning(f"Error closing DuckDB connection: {e}")
            self._client = None
            self._initialized = False
            logger.info("DuckDB connection closed")
