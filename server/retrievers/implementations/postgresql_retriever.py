"""
PostgreSQL implementation of AbstractSQLRetriever
"""

import logging
from typing import Dict, Any, List, Optional
from ..base.sql_retriever import AbstractSQLRetriever
from ..base.base_retriever import RetrieverFactory

logger = logging.getLogger(__name__)

class PostgreSQLRetriever(AbstractSQLRetriever):
    """
    PostgreSQL-specific implementation of AbstractSQLRetriever.
    
    Demonstrates how to leverage PostgreSQL's advanced features like
    full-text search, JSON operations, and custom functions.
    """

    def __init__(self, 
                config: Dict[str, Any],
                connection: Any = None,
                **kwargs):
        """
        Initialize PostgreSQLRetriever.
        
        Args:
            config: Configuration dictionary
            connection: Optional PostgreSQL connection (e.g., psycopg2 connection)
            **kwargs: Additional arguments
        """
        super().__init__(config=config, connection=connection, **kwargs)
        
        # PostgreSQL-specific configuration
        pg_config = self.datasource_config
        self.host = pg_config.get('host', 'localhost')
        self.port = pg_config.get('port', 5432)
        self.database = pg_config.get('database', 'postgres')
        self.username = pg_config.get('username', 'postgres')
        self.password = pg_config.get('password', '')
        
        # PostgreSQL-specific features
        self.use_full_text_search = pg_config.get('use_full_text_search', True)
        self.text_search_config = pg_config.get('text_search_config', 'english')

    def _get_datasource_name(self) -> str:
        """Return the datasource name for config lookup."""
        return 'postgresql'

    # Required abstract method implementations
    async def execute_query(self, sql: str, params: List[Any] = None) -> List[Dict[str, Any]]:
        """
        Execute PostgreSQL query and return results.
        
        Args:
            sql: SQL query string
            params: Query parameters
            
        Returns:
            List of rows as dictionaries
        """
        if not self.connection:
            raise ValueError("PostgreSQL connection not initialized")
            
        if params is None:
            params = []
            
        try:
            if self.verbose:
                logger.info(f"Executing PostgreSQL query: {sql}")
                logger.info(f"Parameters: {params}")
            
            # Example with psycopg2
            cursor = self.connection.cursor()
            cursor.execute(sql, params)
            
            # Get column names
            column_names = [desc[0] for desc in cursor.description] if cursor.description else []
            
            # Convert rows to dictionaries
            rows = cursor.fetchall()
            result = [dict(zip(column_names, row)) for row in rows]
            
            if self.verbose:
                logger.info(f"PostgreSQL query returned {len(result)} rows")
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing PostgreSQL query: {str(e)}")
            logger.error(f"SQL: {sql}, Params: {params}")
            return []

    async def initialize(self) -> None:
        """
        Initialize PostgreSQL database and verify structure.
        """
        try:
            if not self.connection:
                # Example connection creation (would need psycopg2)
                # import psycopg2
                # self.connection = psycopg2.connect(
                #     host=self.host,
                #     port=self.port,
                #     database=self.database,
                #     user=self.username,
                #     password=self.password
                # )
                logger.warning("PostgreSQL connection initialization not implemented")
                
            # Verify database structure
            await self._verify_database_structure()
            
            logger.info(f"PostgreSQLRetriever initialized for database: {self.database}")
            
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQLRetriever: {str(e)}")
            raise

    async def close(self) -> None:
        """
        Close PostgreSQL connection and cleanup resources.
        """
        try:
            if self.connection:
                self.connection.close()
                self.connection = None
                logger.info("PostgreSQL connection closed")
                
        except Exception as e:
            logger.error(f"Error closing PostgreSQL connection: {str(e)}")

    # PostgreSQL-specific helper methods
    async def _verify_database_structure(self) -> None:
        """Verify that required tables exist in PostgreSQL database."""
        try:
            cursor = self.connection.cursor()
            
            # Check if collection table exists (PostgreSQL-specific syntax)
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = %s
                );
            """, (self.collection,))
            
            exists = cursor.fetchone()[0]
            if not exists:
                logger.warning(f"Table '{self.collection}' not found in PostgreSQL database")
                
        except Exception as e:
            logger.error(f"Error verifying PostgreSQL database structure: {str(e)}")
            raise

    def _get_search_query(self, query: str, collection_name: str) -> Dict[str, Any]:
        """
        Generate PostgreSQL-optimized search query with full-text search.
        
        PostgreSQL offers powerful full-text search capabilities with ts_vector.
        """
        if self.use_full_text_search:
            # PostgreSQL full-text search implementation
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
        if self.verbose:
            logger.info("Using standard SQL search (full-text search disabled)")
        
        return super()._get_search_query(query, collection_name)


# Register PostgreSQL retriever with factory
RetrieverFactory.register_retriever('postgresql', PostgreSQLRetriever) 