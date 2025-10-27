"""
MariaDB Database Datasource Implementation
"""

from typing import Any, Dict, Optional
from ...base.base_datasource import BaseDatasource


class MariaDBDatasource(BaseDatasource):
    """MariaDB database datasource implementation."""
    
    @property
    def datasource_name(self) -> str:
        """Return the name of this datasource for config lookup."""
        return 'mariadb'
    
    async def initialize(self) -> None:
        """Initialize the MariaDB database connection."""
        mariadb_config = self.config.get('datasources', {}).get('mariadb', {})
        
        try:
            import mysql.connector
            from mysql.connector import Error
        except ImportError:
            self.logger.warning("mysql-connector-python not available. Install with: pip install mysql-connector-python")
            self._client = None
            self._initialized = True
            return
        
        # Extract connection parameters
        host = mariadb_config.get('host', 'localhost')
        port = mariadb_config.get('port', 3306)
        database = mariadb_config.get('database', 'mysql')
        username = mariadb_config.get('username', 'root')
        password = mariadb_config.get('password', '')
        
        try:
            self.logger.info(f"Initializing MariaDB connection to {host}:{port}/{database}")
            
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
                self.logger.info(f"MariaDB connection successful: {version[0]}")
            
            self._initialized = True
            
        except Error as e:
            self.logger.error(f"Failed to connect to MariaDB database: {str(e)}")
            self.logger.error(f"Connection details: {host}:{port}/{database} (user: {username})")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error connecting to MariaDB: {str(e)}")
            raise
    
    async def health_check(self) -> bool:
        """Perform a health check on the MariaDB connection."""
        if not self._initialized or not self._client:
            return False
            
        try:
            cursor = self._client.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception as e:
            self.logger.error(f"MariaDB health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Close the MariaDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._initialized = False
            self.logger.info("MariaDB connection closed")
