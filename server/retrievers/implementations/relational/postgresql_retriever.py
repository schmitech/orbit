"""
PostgreSQL implementation using the new BaseSQLDatabaseRetriever.
Significantly reduced code duplication.
"""

import logging
from typing import Dict, Any, List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

from server.retrievers.base.base_sql_database import BaseSQLDatabaseRetriever
from server.retrievers.base.base_retriever import RetrieverFactory

logger = logging.getLogger(__name__)


class PostgreSQLRetriever(BaseSQLDatabaseRetriever):
    """
    PostgreSQL-specific implementation using unified base.
    Demonstrates significant code reduction while maintaining functionality.
    """
    
    def __init__(self, config: Dict[str, Any], connection: Any = None, **kwargs):
        """Initialize PostgreSQL retriever."""
        super().__init__(config=config, connection=connection, **kwargs)
        
        # PostgreSQL-specific settings
        self.sslmode = self.get_config_value(self.datasource_config, 'sslmode', 'prefer')
        self.use_full_text_search = self.datasource_config.get('use_full_text_search', True)
        self.text_search_config = self.datasource_config.get('text_search_config', 'english')
    
    def _get_datasource_name(self) -> str:
        """Return the datasource name."""
        return 'postgresql'
    
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
        """Execute PostgreSQL query and return raw results."""
        cursor = None
        try:
            cursor = self.connection.cursor()
            
            # Handle different parameter formats
            if isinstance(params, dict):
                # Named parameters
                cursor.execute(query, params)
            elif isinstance(params, (list, tuple)):
                # Positional parameters
                cursor.execute(query, params)
            else:
                # No parameters
                cursor.execute(query)
            
            # Handle different query types
            if query.strip().upper().startswith("SELECT"):
                results = cursor.fetchall()
                return results
            else:
                # For non-SELECT queries
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
    
    async def initialize(self) -> None:
        """Initialize PostgreSQL database."""
        try:
            if not self.connection:
                self.connection = await self.create_connection()
            
            # Verify table structure
            await self._verify_database_structure()
            
            logger.info(f"PostgreSQLRetrieverV2 initialized for database: {self.connection_params['database']}")
            
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQLRetrieverV2: {e}")
            raise
    
    async def _verify_database_structure(self) -> None:
        """Verify required tables exist."""
        try:
            result = await self.execute_query("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = %s
                );
            """, [self.collection])
            
            exists = result[0]['exists'] if result else False
            if not exists:
                logger.warning(f"Table '{self.collection}' not found in PostgreSQL database")
                
        except Exception as e:
            logger.error(f"Error verifying PostgreSQL database structure: {e}")
            raise
    
    def _get_search_query(self, query: str, collection_name: str) -> Dict[str, Any]:
        """Generate PostgreSQL-optimized search query."""
        if self.use_full_text_search:
            query_tokens = self._tokenize_text(query)
            
            if query_tokens:
                # Use PostgreSQL's full-text search
                search_config = {
                    "sql": f"""
                        SELECT *, 
                               ts_rank(to_tsvector(%s, coalesce(content, '') || ' ' || coalesce(question, '')), 
                                      plainto_tsquery(%s, %s)) as rank
                        FROM {collection_name} 
                        WHERE to_tsvector(%s, coalesce(content, '') || ' ' || coalesce(question, '')) 
                              @@ plainto_tsquery(%s, %s)
                        ORDER BY rank DESC
                        LIMIT %s
                    """,
                    "params": [
                        self.text_search_config, self.text_search_config, query,
                        self.text_search_config, self.text_search_config, query,
                        self.max_results
                    ],
                    "fields": self.default_search_fields + ['rank']
                }
                
                if self.verbose:
                    logger.info("Using PostgreSQL full-text search")
                
                return search_config
        
        # Fallback to parent implementation
        return super()._get_search_query(query, collection_name)


# Register the new PostgreSQL retriever
RetrieverFactory.register_retriever('postgresql_v2', PostgreSQLRetriever)