"""
PostgreSQL Intent Retriever using the new unified base classes.
Demonstrates massive code reduction - from ~200 lines to ~50 lines.
"""

import logging
from typing import Any, Optional

try:
    import psycopg
    _OperationalError = psycopg.OperationalError
except ImportError:  # pragma: no cover - optional dependency for tests

    class _OperationalError(Exception):
        """Fallback when psycopg is unavailable."""

from retrievers.base.base_retriever import RetrieverFactory
from retrievers.base.intent_sql_base import IntentSQLRetriever
from retrievers.base.postgresql_connection_mixin import PostgreSQLConnectionMixin

logger = logging.getLogger(__name__)


class IntentPostgreSQLRetriever(IntentSQLRetriever, PostgreSQLConnectionMixin):
    """
    PostgreSQL-specific intent retriever using unified base.
    Inherits all intent functionality and PostgreSQL connection handling.
    """
    
    def __init__(self, config: dict[str, Any], domain_adapter=None, connection: Any = None, **kwargs):
        """Initialize PostgreSQL intent retriever."""
        super().__init__(config=config, domain_adapter=domain_adapter, connection=connection, **kwargs)

        # PostgreSQL-specific settings
        self.sslmode = self.get_config_value(self.datasource_config, 'sslmode', 'prefer')
        self.statement_timeout = self.datasource_config.get('statement_timeout', 10000)
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
        return await self._create_postgresql_connection(
            sslmode=self.sslmode,
            connect_timeout=self.connection_timeout,
            statement_timeout=self.statement_timeout,
            autocommit=False,
            use_pool=self.use_connection_pool,
            pool_size=self.pool_size,
            install_extras='binary,pool',
        )
    
    def get_test_query(self) -> str:
        """PostgreSQL test query."""
        return "SELECT 1 as test"
    
    def _is_connection_alive(self) -> bool:
        """Check if PostgreSQL connection is still alive."""
        return self._is_postgresql_connection_alive()

    async def _execute_raw_query(self, query: str, params: Optional[Any] = None) -> list[Any]:
        """Execute PostgreSQL query with intent-specific handling."""
        cursor = None
        try:
            # Check connection health before executing
            if not self._is_connection_alive():
                raise _OperationalError("connection already closed")
            
            cursor = self.connection.cursor()
            cursor.execute(query, params)
            
            if self.is_select_query(query):
                return cursor.fetchall()
            else:
                self.connection.commit()
                return [{"affected_rows": cursor.rowcount}]
                
        except Exception:
            if self.connection and not self.connection.closed:
                self.connection.rollback()
            raise
        finally:
            if cursor:
                cursor.close()
    
    async def _close_connection(self) -> None:
        """Close PostgreSQL connection or return to pool."""
        await self._close_postgresql_connection(use_pool=self.use_connection_pool)


# Register the new intent PostgreSQL retriever
RetrieverFactory.register_retriever('intent_postgresql', IntentPostgreSQLRetriever)
