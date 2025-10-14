"""
SQL Server Database Datasource Implementation
"""

from typing import Any, Dict, Optional
from ...base.base_datasource import BaseDatasource


class SQLServerDatasource(BaseDatasource):
    """Microsoft SQL Server database datasource implementation."""
    
    @property
    def datasource_name(self) -> str:
        """Return the name of this datasource for config lookup."""
        return 'sqlserver'
    
    async def initialize(self) -> None:
        """Initialize the SQL Server database connection."""
        sqlserver_config = self.config.get('datasources', {}).get('sqlserver', {})
        
        try:
            import pymssql
        except ImportError:
            self.logger.warning("pymssql not available. Install with: pip install pymssql")
            self._client = None
            self._initialized = True
            return
        
        # Extract connection parameters
        host = sqlserver_config.get('host', 'localhost')
        port = sqlserver_config.get('port', 1433)
        database = sqlserver_config.get('database', 'master')
        username = sqlserver_config.get('username', 'sa')
        password = sqlserver_config.get('password', '')
        
        try:
            self.logger.info(f"Initializing SQL Server connection to {host}:{port}/{database}")
            
            # Create connection
            self._client = pymssql.connect(
                server=host,
                port=port,
                database=database,
                user=username,
                password=password,
                autocommit=True
            )
            
            # Test the connection
            cursor = self._client.cursor()
            cursor.execute("SELECT @@VERSION")
            version = cursor.fetchone()
            cursor.close()
            
            if version:
                self.logger.info(f"SQL Server connection successful: {version[0][:50]}...")
            
            self._initialized = True
            
        except Exception as e:
            self.logger.error(f"Failed to connect to SQL Server database: {str(e)}")
            self.logger.error(f"Connection details: {host}:{port}/{database} (user: {username})")
            raise
    
    async def health_check(self) -> bool:
        """Perform a health check on the SQL Server connection."""
        if not self._initialized or not self._client:
            return False
            
        try:
            cursor = self._client.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception as e:
            self.logger.error(f"SQL Server health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Close the SQL Server connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._initialized = False
            self.logger.info("SQL Server connection closed")
