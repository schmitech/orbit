"""
Oracle Database Datasource Implementation
"""

from typing import Any, Dict, Optional
from ...base.base_datasource import BaseDatasource


class OracleDatasource(BaseDatasource):
    """Oracle Database datasource implementation."""
    
    @property
    def datasource_name(self) -> str:
        """Return the name of this datasource for config lookup."""
        return 'oracle'
    
    async def initialize(self) -> None:
        """Initialize the Oracle database connection."""
        oracle_config = self.config.get('datasources', {}).get('oracle', {})
        
        try:
            import oracledb
        except ImportError:
            self.logger.warning("oracledb not available. Install with: pip install oracledb")
            self._client = None
            self._initialized = True
            return
        
        # Extract connection parameters
        host = oracle_config.get('host', 'localhost')
        port = oracle_config.get('port', 1521)
        service_name = oracle_config.get('service_name', 'XE')
        username = oracle_config.get('username', 'system')
        password = oracle_config.get('password', '')
        
        try:
            # Create DSN using the modern oracledb syntax
            dsn = f"{host}:{port}/{service_name}"
            
            self.logger.info(f"Initializing Oracle connection to {host}:{port}/{service_name}")
            
            # Create connection using oracledb
            self._client = oracledb.connect(user=username, password=password, dsn=dsn)
            
            # Test the connection
            cursor = self._client.cursor()
            cursor.execute("SELECT 1 FROM DUAL")
            cursor.fetchone()
            cursor.close()
            
            self.logger.info("Oracle connection successful")
            self._initialized = True
            
        except Exception as e:
            self.logger.error(f"Failed to connect to Oracle database: {str(e)}")
            self.logger.error(f"Connection details: {host}:{port}/{service_name} (user: {username})")
            raise
    
    async def health_check(self) -> bool:
        """Perform a health check on the Oracle connection."""
        if not self._initialized or not self._client:
            return False
            
        try:
            cursor = self._client.cursor()
            cursor.execute("SELECT 1 FROM DUAL")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception as e:
            self.logger.error(f"Oracle health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Close the Oracle connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._initialized = False
            self.logger.info("Oracle connection closed")
