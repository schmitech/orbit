"""
MySQL Database Datasource Implementation
"""

import logging
from typing import Any, Dict, Optional
from ...base.base_datasource import BaseDatasource

logger = logging.getLogger(__name__)


class MySQLDatasource(BaseDatasource):
    """MySQL database datasource implementation."""
    
    @property
    def datasource_name(self) -> str:
        """Return the name of this datasource for config lookup."""
        return 'mysql'
    
    async def initialize(self) -> None:
        """Initialize the MySQL database connection."""
        mysql_config = self.config.get('datasources', {}).get('mysql', {})
        
        try:
            import mysql.connector
            from mysql.connector import Error
        except ImportError:
            logger.warning("mysql-connector-python not available. Install with: pip install mysql-connector-python")
            self._client = None
            self._initialized = True
            return
        
        # Extract connection parameters
        host = mysql_config.get('host', 'localhost')
        port = mysql_config.get('port', 3306)
        database = mysql_config.get('database', 'mysql')
        username = mysql_config.get('username', 'root')
        password = mysql_config.get('password', '')
        
        try:
            logger.info(f"Initializing MySQL connection to {host}:{port}/{database}")
            
            # Create connection
            self._client = mysql.connector.connect(
                host=host,
                port=port,
                database=database,
                user=username,
                password=password,
                autocommit=True
            )
            
            # Test the connection
            cursor = self._client.cursor()
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()
            cursor.close()
            
            if version:
                logger.info(f"MySQL connection successful: {version[0]}")
            
            self._initialized = True
            
        except Error as e:
            logger.error(f"Failed to connect to MySQL database: {str(e)}")
            logger.error(f"Connection details: {host}:{port}/{database} (user: {username})")
            raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to MySQL: {str(e)}")
            raise
    
    async def health_check(self) -> bool:
        """Perform a health check on the MySQL connection."""
        if not self._initialized or not self._client:
            return False
            
        try:
            cursor = self._client.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception as e:
            logger.error(f"MySQL health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Close the MySQL connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._initialized = False
            logger.info("MySQL connection closed")
