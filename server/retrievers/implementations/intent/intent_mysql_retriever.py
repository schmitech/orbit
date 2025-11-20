"""
MySQL Intent Retriever using the new unified base classes.
Demonstrates how easy it is to add new database engines.
"""

import logging
from typing import Dict, Any, List, Optional

try:
    import mysql.connector
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False

from retrievers.base.intent_sql_base import IntentSQLRetriever
from retrievers.base.base_retriever import RetrieverFactory

logger = logging.getLogger(__name__)


class IntentMySQLRetriever(IntentSQLRetriever):
    """
    MySQL-specific intent retriever using unified base.
    Minimal code required for a fully functional intent retriever.
    """
    
    def __init__(self, config: Dict[str, Any], domain_adapter=None, connection: Any = None, **kwargs):
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
            
        try:
            config = {
                'host': self.connection_params['host'],
                'port': self.connection_params['port'],
                'database': self.connection_params['database'],
                'user': self.connection_params['username'],
                'password': self.connection_params['password'],
                'autocommit': self.autocommit
            }
            
            if not self.ssl_disabled:
                config['use_ssl'] = True
            
            connection = mysql.connector.connect(**config)
            
            # Test connection
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT VERSION() as version")
            version = cursor.fetchone()
            cursor.close()

            if version:
                logger.debug(f"MySQL connection successful: {version['version']}")

            return connection
            
        except Exception as e:
            logger.error(f"Failed to connect to MySQL: {e}")
            raise
    
    def get_test_query(self) -> str:
        """MySQL test query."""
        return "SELECT 1 as test"
    
    async def _execute_raw_query(self, query: str, params: Optional[Any] = None) -> List[Any]:
        """Execute MySQL query with intent-specific handling."""
        cursor = None
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            if query.strip().upper().startswith("SELECT"):
                return cursor.fetchall()
            else:
                if not self.autocommit:
                    self.connection.commit()
                return [{"affected_rows": cursor.rowcount}]
                
        except Exception as e:
            if self.connection and not self.autocommit:
                self.connection.rollback()
            raise
        finally:
            if cursor:
                cursor.close()
    
    async def _close_connection(self) -> None:
        """Close MySQL connection."""
        if self.connection:
            self.connection.close()


# Register the MySQL intent retriever
RetrieverFactory.register_retriever('intent_mysql', IntentMySQLRetriever)