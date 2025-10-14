"""
SQLite Datasource Implementation
"""

import sqlite3
from typing import Any, Dict, Optional
from ...base.base_datasource import BaseDatasource


class SQLiteDatasource(BaseDatasource):
    """SQLite database datasource implementation."""
    
    @property
    def datasource_name(self) -> str:
        """Return the name of this datasource for config lookup."""
        return 'sqlite'
    
    async def initialize(self) -> None:
        """Initialize the SQLite database connection."""
        sqlite_config = self.config.get('datasources', {}).get('sqlite', {})
        db_path = sqlite_config.get('db_path', 'sqlite_db.db')
        
        self.logger.info(f"Initializing SQLite connection to {db_path}")

        try:
            self._client = sqlite3.connect(db_path)
            # Configure row factory to enable dictionary-like row access
            self._client.row_factory = sqlite3.Row
            self._initialized = True
            self.logger.info("SQLite connection established successfully")
        except Exception as e:
            self.logger.error(f"Failed to connect to SQLite database: {str(e)}")
            raise
    
    async def health_check(self) -> bool:
        """Perform a health check on the SQLite connection."""
        if not self._initialized or not self._client:
            return False
            
        try:
            cursor = self._client.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception as e:
            self.logger.error(f"SQLite health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Close the SQLite connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._initialized = False
            self.logger.info("SQLite connection closed")
