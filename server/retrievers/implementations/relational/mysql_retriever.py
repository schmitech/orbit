"""
MySQL implementation of AbstractSQLRetriever
"""

import logging
from typing import Dict, Any, List, Optional
from ...base.sql_retriever import AbstractSQLRetriever
from ...base.base_retriever import RetrieverFactory

logger = logging.getLogger(__name__)

class MySQLRetriever(AbstractSQLRetriever):
    """
    MySQL-specific implementation of AbstractSQLRetriever.
    
    Demonstrates how to leverage MySQL's features like full-text search,
    JSON functions, and optimized queries.
    """

    def __init__(self, 
                config: Dict[str, Any],
                connection: Any = None,
                **kwargs):
        """
        Initialize MySQLRetriever.
        
        Args:
            config: Configuration dictionary
            connection: Optional MySQL connection (e.g., mysql-connector-python or PyMySQL)
            **kwargs: Additional arguments
        """
        super().__init__(config=config, connection=connection, **kwargs)
        
        # MySQL-specific configuration
        mysql_config = self.datasource_config
        self.host = mysql_config.get('host', 'localhost')
        self.port = mysql_config.get('port', 3306)
        self.database = mysql_config.get('database', 'mysql')
        self.username = mysql_config.get('username', 'root')
        self.password = mysql_config.get('password', '')
        
        # MySQL-specific features
        self.use_full_text_search = mysql_config.get('use_full_text_search', True)
        self.engine = mysql_config.get('engine', 'InnoDB')

    def _get_datasource_name(self) -> str:
        """Return the datasource name for config lookup."""
        return 'mysql'

    # Required abstract method implementations
    async def execute_query(self, sql: str, params: List[Any] = None) -> List[Dict[str, Any]]:
        """
        Execute MySQL query and return results.
        
        Args:
            sql: SQL query string
            params: Query parameters
            
        Returns:
            List of rows as dictionaries
        """
        if not self.connection:
            raise ValueError("MySQL connection not initialized")
            
        if params is None:
            params = []
            
        try:
            if self.verbose:
                logger.info(f"Executing MySQL query: {sql}")
                logger.info(f"Parameters: {params}")
            
            # Example with mysql-connector-python
            cursor = self.connection.cursor(dictionary=True)  # MySQL returns dicts directly
            cursor.execute(sql, params)
            
            # Fetch all rows as dictionaries
            result = cursor.fetchall()
            
            if self.verbose:
                logger.info(f"MySQL query returned {len(result)} rows")
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing MySQL query: {str(e)}")
            logger.error(f"SQL: {sql}, Params: {params}")
            return []

    async def initialize(self) -> None:
        """
        Initialize MySQL database and verify structure.
        """
        try:
            if not self.connection:
                # Example connection creation (would need mysql-connector-python)
                # import mysql.connector
                # self.connection = mysql.connector.connect(
                #     host=self.host,
                #     port=self.port,
                #     database=self.database,
                #     user=self.username,
                #     password=self.password
                # )
                logger.warning("MySQL connection initialization not implemented")
                
            # Verify database structure
            await self._verify_database_structure()
            
            logger.info(f"MySQLRetriever initialized for database: {self.database}")
            
        except Exception as e:
            logger.error(f"Failed to initialize MySQLRetriever: {str(e)}")
            raise

    async def close(self) -> None:
        """
        Close MySQL connection and cleanup resources.
        """
        try:
            if self.connection:
                self.connection.close()
                self.connection = None
                logger.info("MySQL connection closed")
                
        except Exception as e:
            logger.error(f"Error closing MySQL connection: {str(e)}")

    # MySQL-specific helper methods
    async def _verify_database_structure(self) -> None:
        """Verify that required tables exist in MySQL database."""
        try:
            cursor = self.connection.cursor()
            
            # Check if collection table exists (MySQL-specific syntax)
            cursor.execute("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = %s 
                AND table_name = %s
            """, (self.database, self.collection))
            
            exists = cursor.fetchone()[0] > 0
            if not exists:
                logger.warning(f"Table '{self.collection}' not found in MySQL database")
                
        except Exception as e:
            logger.error(f"Error verifying MySQL database structure: {str(e)}")
            raise

    def _get_search_query(self, query: str, collection_name: str) -> Dict[str, Any]:
        """
        Generate MySQL-optimized search query with full-text search.
        
        MySQL offers FULLTEXT indexes and MATCH() AGAINST() for text search.
        """
        if self.use_full_text_search:
            # MySQL full-text search implementation
            query_tokens = self._tokenize_text(query)
            
            if query_tokens:
                # Use MySQL's FULLTEXT search with MATCH() AGAINST()
                search_config = {
                    "sql": f"""
                        SELECT *, 
                               MATCH(content, question) AGAINST(%s IN NATURAL LANGUAGE MODE) as relevance_score
                        FROM {collection_name} 
                        WHERE MATCH(content, question) AGAINST(%s IN NATURAL LANGUAGE MODE)
                        ORDER BY relevance_score DESC
                        LIMIT %s
                    """,
                    "params": [query, query, self.max_results],
                    "fields": self.default_search_fields + ['relevance_score']
                }
                
                if self.verbose:
                    logger.info("Using MySQL FULLTEXT search")
                
                return search_config
        
        # Fallback to parent implementation with LIKE search
        if self.verbose:
            logger.info("Using standard SQL search (FULLTEXT search disabled)")
        
        # MySQL-optimized LIKE search
        query_tokens = self._tokenize_text(query)
        if query_tokens:
            like_conditions = []
            params = []
            
            for token in query_tokens[:5]:  # Limit to avoid too many conditions
                like_conditions.append("(content LIKE %s OR question LIKE %s)")
                params.extend([f"%{token}%", f"%{token}%"])
            
            if like_conditions:
                search_config = {
                    "sql": f"""
                        SELECT * FROM {collection_name} 
                        WHERE {' OR '.join(like_conditions)}
                        LIMIT %s
                    """,
                    "params": params + [self.max_results],
                    "fields": self.default_search_fields
                }
                return search_config
        
        return super()._get_search_query(query, collection_name)


# Register MySQL retriever with factory
RetrieverFactory.register_retriever('mysql', MySQLRetriever) 