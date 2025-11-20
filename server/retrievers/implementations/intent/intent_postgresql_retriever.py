"""
PostgreSQL Intent Retriever using the new unified base classes.
Demonstrates massive code reduction - from ~200 lines to ~50 lines.
"""

import logging
from typing import Dict, Any, List, Optional

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from psycopg2 import pool
    _OperationalError = psycopg2.OperationalError
except ImportError:  # pragma: no cover - optional dependency for tests
    psycopg2 = None
    RealDictCursor = None
    pool = None

    class _OperationalError(Exception):
        """Fallback when psycopg2 is unavailable."""

from retrievers.base.intent_sql_base import IntentSQLRetriever
from retrievers.base.base_retriever import RetrieverFactory

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
        self.connection_pool = None
    
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
        """Create PostgreSQL connection or connection pool."""
        try:
            if psycopg2 is None:
                raise ImportError("psycopg2 not available. Install with: pip install psycopg2-binary")

            if self.use_connection_pool and not self.connection_pool:
                # Create connection pool
                self.connection_pool = psycopg2.pool.SimpleConnectionPool(
                    1,  # minconn
                    self.pool_size,  # maxconn
                    host=self.connection_params['host'],
                    port=self.connection_params['port'],
                    database=self.connection_params['database'],
                    user=self.connection_params['username'],
                    password=self.connection_params['password'],
                    sslmode=self.sslmode,
                    cursor_factory=RealDictCursor
                )
                
                logger.debug(f"Created PostgreSQL connection pool with size {self.pool_size}")
                
                # Get a connection from the pool
                connection = self.connection_pool.getconn()
            else:
                # Create single connection
                connection = psycopg2.connect(
                    host=self.connection_params['host'],
                    port=self.connection_params['port'],
                    database=self.connection_params['database'],
                    user=self.connection_params['username'],
                    password=self.connection_params['password'],
                    sslmode=self.sslmode,
                    cursor_factory=RealDictCursor,
                    connect_timeout=self.connection_timeout
                )
                
                # Set autocommit to False to manage transactions properly
                connection.autocommit = False
            
            # Test connection
            cursor = connection.cursor()
            cursor.execute("SELECT version();")
            version = cursor.fetchone()
            cursor.close()
            
            if version:
                logger.debug(f"PostgreSQL connection successful: {version['version']}")
            
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
    
    def _is_connection_alive(self) -> bool:
        """Check if PostgreSQL connection is still alive."""
        try:
            if not self.connection:
                return False
            # Check if connection is closed
            if self.connection.closed:
                return False
            # Try a simple query to verify connection is working
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            return True
        except:
            return False
    
    async def _execute_raw_query(self, query: str, params: Optional[Any] = None) -> List[Any]:
        """Execute PostgreSQL query with intent-specific handling."""
        cursor = None
        try:
            # Check connection health before executing
            if not self._is_connection_alive():
                raise _OperationalError("connection already closed")
            
            cursor = self.connection.cursor()
            cursor.execute(query, params)
            
            if query.strip().upper().startswith("SELECT"):
                return cursor.fetchall()
            else:
                self.connection.commit()
                return [{"affected_rows": cursor.rowcount}]
                
        except Exception as e:
            if self.connection and not self.connection.closed:
                self.connection.rollback()
            raise
        finally:
            if cursor:
                cursor.close()
    
    async def _close_connection(self) -> None:
        """Close PostgreSQL connection or return to pool."""
        if self.connection:
            if self.use_connection_pool and self.connection_pool:
                # Return connection to pool
                self.connection_pool.putconn(self.connection)
                logger.debug("Returned connection to pool")
            else:
                # Close single connection
                self.connection.close()
        
        # Close the pool if needed
        if self.connection_pool:
            self.connection_pool.closeall()
            self.connection_pool = None
            logger.debug("Closed PostgreSQL connection pool")


# Register the new intent PostgreSQL retriever
RetrieverFactory.register_retriever('intent_postgresql', IntentPostgreSQLRetriever)
