"""
PostgreSQL Datasource Implementation
"""

import logging
from typing import Any, Dict, Optional
from ...base.base_datasource import BaseDatasource

logger = logging.getLogger(__name__)


class PostgreSQLDatasource(BaseDatasource):
    """PostgreSQL database datasource implementation."""
    
    @property
    def datasource_name(self) -> str:
        """Return the name of this datasource for config lookup."""
        return 'postgres'
    
    async def initialize(self) -> None:
        """Initialize the PostgreSQL database connection."""
        postgres_config = self.config.get('datasources', {}).get('postgres', {})
        
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            
            # Extract connection parameters
            host = postgres_config.get('host', 'localhost')
            port = postgres_config.get('port', 5432)
            database = postgres_config.get('database', 'postgres')
            username = postgres_config.get('username', 'postgres')
            password = postgres_config.get('password', '')
            sslmode = postgres_config.get('sslmode', 'prefer')
            
            logger.info(f"Initializing PostgreSQL connection to {host}:{port}/{database}")
            
            # Create connection
            self._client = psycopg2.connect(
                host=host,
                port=port,
                database=database,
                user=username,
                password=password,
                sslmode=sslmode,
                cursor_factory=RealDictCursor  # Use dict cursor by default
            )
            
            # Test the connection
            cursor = self._client.cursor()
            cursor.execute("SELECT version();")
            version = cursor.fetchone()
            cursor.close()
            
            if version:
                logger.info(f"PostgreSQL connection successful: {version['version']}")
            
            self._initialized = True
            
        except ImportError:
            logger.error("psycopg2 not available. Install with: pip install psycopg2-binary")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL database: {str(e)}")
            logger.error(f"Connection details: {host}:{port}/{database} (user: {username})")
            raise
    
    async def health_check(self) -> bool:
        """Perform a health check on the PostgreSQL connection."""
        if not self._initialized or not self._client:
            return False
            
        try:
            cursor = self._client.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception as e:
            logger.error(f"PostgreSQL health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Close the PostgreSQL connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._initialized = False
            logger.info("PostgreSQL connection closed")
