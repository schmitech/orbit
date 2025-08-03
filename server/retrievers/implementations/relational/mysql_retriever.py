"""
MySQL implementation using the new BaseSQLDatabaseRetriever.
Significantly reduced code duplication.
"""

import logging
from typing import Dict, Any, List, Optional

from retrievers.base.base_sql_database import BaseSQLDatabaseRetriever
from retrievers.base.base_retriever import RetrieverFactory

logger = logging.getLogger(__name__)

class MySQLRetriever(BaseSQLDatabaseRetriever):
    """
    MySQL-specific implementation using unified base.
    Demonstrates significant code reduction while maintaining functionality.
    """
    
    def __init__(self, config: Dict[str, Any], connection: Any = None, **kwargs):
        """Initialize MySQL retriever."""
        super().__init__(config=config, connection=connection, **kwargs)
        
        # MySQL-specific settings
        self.use_full_text_search = self.datasource_config.get('use_full_text_search', True)
        self.engine = self.datasource_config.get('engine', 'InnoDB')
        self.charset = self.datasource_config.get('charset', 'utf8mb4')
        self.sql_mode = self.datasource_config.get('sql_mode', 'STRICT_TRANS_TABLES')

    def _get_datasource_name(self) -> str:
        """Return the datasource name."""
        return 'mysql'
    
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
        try:
            # Try to import mysql-connector-python first
            try:
                import mysql.connector
                connection = mysql.connector.connect(
                    host=self.connection_params['host'],
                    port=self.connection_params['port'],
                    database=self.connection_params['database'],
                    user=self.connection_params['username'],
                    password=self.connection_params['password'],
                    charset=self.charset,
                    sql_mode=self.sql_mode
                )
            except ImportError:
                # Fallback to PyMySQL
                try:
                    import pymysql
                    connection = pymysql.connect(
                        host=self.connection_params['host'],
                        port=self.connection_params['port'],
                        database=self.connection_params['database'],
                        user=self.connection_params['username'],
                        password=self.connection_params['password'],
                        charset=self.charset,
                        cursorclass=pymysql.cursors.DictCursor
                    )
                except ImportError:
                    logger.error("Neither mysql-connector-python nor PyMySQL available. Install with: pip install mysql-connector-python or pip install PyMySQL")
                    raise
            
            # Test connection
            cursor = connection.cursor()
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()
            cursor.close()
            
            if version and self.verbose:
                version_str = version.get('VERSION()') if isinstance(version, dict) else version[0]
                logger.info(f"MySQL connection successful: {version_str}")
            
            return connection
            
        except Exception as e:
            logger.error(f"Failed to connect to MySQL: {e}")
            raise
    
    def get_test_query(self) -> str:
        """MySQL test query."""
        return "SELECT 1 as test"
    
    async def _execute_raw_query(self, query: str, params: Optional[Any] = None) -> List[Any]:
        """Execute MySQL query and return raw results."""
        cursor = None
        try:
            cursor = self.connection.cursor()
            
            # Handle different parameter formats
            if isinstance(params, dict):
                # Named parameters (mysql-connector-python format)
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
        """Close MySQL connection."""
        if self.connection:
            self.connection.close()

    async def initialize(self) -> None:
        """Initialize MySQL database."""
        try:
            if not self.connection:
                self.connection = await self.create_connection()
            
            # Verify table structure
            await self._verify_database_structure()
            
            logger.info(f"MySQLRetriever initialized for database: {self.connection_params['database']}")
            
        except Exception as e:
            logger.error(f"Failed to initialize MySQLRetriever: {e}")
            raise
    
    async def _verify_database_structure(self) -> None:
        """Verify required tables exist."""
        try:
            result = await self.execute_query("""
                SELECT COUNT(*) as count
                FROM information_schema.tables 
                WHERE table_schema = %s 
                AND table_name = %s
            """, [self.connection_params['database'], self.collection])
            
            exists = result[0]['count'] > 0 if result else False
            if not exists:
                logger.warning(f"Table '{self.collection}' not found in MySQL database")
                
        except Exception as e:
            logger.error(f"Error verifying MySQL database structure: {e}")
            raise

    def _get_search_query(self, query: str, collection_name: str) -> Dict[str, Any]:
        """Generate MySQL-optimized search query with full-text search."""
        if self.use_full_text_search:
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
        
        # Fallback to parent implementation
        return super()._get_search_query(query, collection_name)


# Register MySQL retriever with factory
RetrieverFactory.register_retriever('mysql', MySQLRetriever) 