"""
MySQL Intent Retriever using the new unified base classes.
Demonstrates how easy it is to add new database engines.
"""

import logging
from typing import Any, Optional

try:
    import mysql.connector  # noqa: F401 - import itself is the availability probe
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False

from retrievers.base.base_retriever import RetrieverFactory
from retrievers.base.intent_sql_base import IntentSQLRetriever
from retrievers.base.mysql_connection_mixin import MySQLConnectionMixin

logger = logging.getLogger(__name__)


class IntentMySQLRetriever(IntentSQLRetriever, MySQLConnectionMixin):
    """
    MySQL-specific intent retriever using unified base.
    Minimal code required for a fully functional intent retriever.
    """
    
    def __init__(self, config: dict[str, Any], domain_adapter=None, connection: Any = None, **kwargs):
        """Initialize MySQL intent retriever."""
        super().__init__(config=config, domain_adapter=domain_adapter, connection=connection, **kwargs)
        
        # MySQL-specific settings
        self.ssl_disabled = self.datasource_config.get('ssl_disabled', False)
        self.autocommit = self.datasource_config.get('autocommit', True)
    
    def _get_datasource_name(self) -> str:
        """Return the datasource name."""
        return "mysql"
    
    def get_default_port(self) -> int:
        """MySQL default port."""
        return 3306
    
    def get_default_database(self) -> str:
        """MySQL default database."""
        return 'mysql'
    
    def get_default_username(self) -> str:
        """MySQL default username."""
        return 'root'
    
    async def create_connection(self) -> Any:
        """Create MySQL connection."""
        if not MYSQL_AVAILABLE:
            raise ImportError("mysql-connector-python not available. Install with: pip install mysql-connector-python")

        return await self._create_mysql_connection(
            ssl_disabled=self.ssl_disabled,
            autocommit=self.autocommit,
            use_dictionary_cursor=True,
            allow_pymysql_fallback=False,
        )
    
    def get_test_query(self) -> str:
        """MySQL test query."""
        return "SELECT 1 as test"
    
    async def _execute_raw_query(self, query: str, params: Optional[Any] = None) -> list[Any]:
        """Execute MySQL query with intent-specific handling."""
        cursor = None
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            if self.is_select_query(query):
                return cursor.fetchall()
            else:
                if not self.autocommit:
                    self.connection.commit()
                return [{"affected_rows": cursor.rowcount}]
                
        except Exception:
            if self.connection and not self.autocommit:
                self.connection.rollback()
            raise
        finally:
            if cursor:
                cursor.close()
    
    async def _close_connection(self) -> None:
        """Close MySQL connection."""
        await self._close_mysql_connection()


# Register the MySQL intent retriever
RetrieverFactory.register_retriever('intent_mysql', IntentMySQLRetriever)