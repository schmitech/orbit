"""
PostgreSQL Intent Retriever using the new unified base classes.
Demonstrates massive code reduction - from ~200 lines to ~50 lines.
"""

import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, Any, List, Optional

from server.retrievers.base.intent_sql_base import IntentSQLRetriever
from server.retrievers.base.base_retriever import RetrieverFactory

logger = logging.getLogger(__name__)


class IntentPostgreSQLRetriever(IntentSQLRetriever):
    """
    PostgreSQL-specific intent retriever using unified base.
    Inherits all intent functionality and PostgreSQL connection handling.
    """
    
    def __init__(self, config: Dict[str, Any], domain_adapter=None, connection: Any = None, **kwargs):
        """Initialize PostgreSQL intent retriever."""
        super().__init__(config=config, domain_adapter=domain_adapter, connection=connection, **kwargs)
        
        # PostgreSQL-specific settings
        self.sslmode = self.get_config_value(self.datasource_config, 'sslmode', 'prefer')
    
    def _get_datasource_name(self) -> str:
        """Return the datasource name."""
        return "postgres"
    
    def get_default_port(self) -> int:
        """PostgreSQL default port."""
        return 5432
    
    def get_default_database(self) -> str:
        """PostgreSQL default database."""
        return 'postgres'
    
    def get_default_username(self) -> str:
        """PostgreSQL default username."""
        return 'postgres'
    
    async def create_connection(self) -> Any:
        """Create PostgreSQL connection."""
        try:
            connection = psycopg2.connect(
                host=self.connection_params['host'],
                port=self.connection_params['port'],
                database=self.connection_params['database'],
                user=self.connection_params['username'],
                password=self.connection_params['password'],
                sslmode=self.sslmode,
                cursor_factory=RealDictCursor
            )
            
            # Test connection
            cursor = connection.cursor()
            cursor.execute("SELECT version();")
            version = cursor.fetchone()
            cursor.close()
            
            if version and self.verbose:
                logger.info(f"PostgreSQL connection successful: {version['version']}")
            
            return connection
            
        except ImportError:
            logger.error("psycopg2 not available. Install with: pip install psycopg2-binary")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise
    
    def get_test_query(self) -> str:
        """PostgreSQL test query."""
        return "SELECT 1 as test"
    
    async def _execute_raw_query(self, query: str, params: Optional[Any] = None) -> List[Any]:
        """Execute PostgreSQL query with intent-specific handling."""
        cursor = None
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, params)
            
            if query.strip().upper().startswith("SELECT"):
                return cursor.fetchall()
            else:
                self.connection.commit()
                return [{"affected_rows": cursor.rowcount}]
                
        except Exception as e:
            if self.connection:
                self.connection.rollback()
            raise
        finally:
            if cursor:
                cursor.close()
    
    async def _close_connection(self) -> None:
        """Close PostgreSQL connection."""
        if self.connection:
            self.connection.close()


# Register the new intent PostgreSQL retriever
RetrieverFactory.register_retriever('intent_postgresql', IntentPostgreSQLRetriever)