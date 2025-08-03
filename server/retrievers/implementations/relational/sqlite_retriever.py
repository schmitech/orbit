"""
SQLite implementation using the new BaseSQLDatabaseRetriever.
Significantly reduced code duplication.
"""

import logging
import sqlite3
import os
from typing import Dict, Any, List, Optional

from server.retrievers.base.base_sql_database import BaseSQLDatabaseRetriever
from server.retrievers.base.base_retriever import RetrieverFactory

logger = logging.getLogger(__name__)

class SQLiteRetriever(BaseSQLDatabaseRetriever):
    """
    SQLite-specific implementation using unified base.
    Demonstrates significant code reduction while maintaining functionality.
    """
    
    def __init__(self, config: Dict[str, Any], connection: Any = None, **kwargs):
        """Initialize SQLite retriever."""
        super().__init__(config=config, connection=connection, **kwargs)
        
        # SQLite-specific settings
        self.db_path = self.get_config_value(self.datasource_config, 'db_path', 'sqlite_db')
        self.enable_wal_mode = self.datasource_config.get('enable_wal_mode', True)
        self.enable_foreign_keys = self.datasource_config.get('enable_foreign_keys', True)

    def _get_datasource_name(self) -> str:
        """Return the datasource name."""
        return 'sqlite'
    
    def get_default_port(self) -> int:
        """SQLite doesn't use ports."""
        return 0
    
    def get_default_database(self) -> str:
        """SQLite default database (file path)."""
        return 'sqlite_db'
    
    def get_default_username(self) -> str:
        """SQLite doesn't use usernames."""
        return ''
    
    async def create_connection(self) -> Any:
        """Create SQLite connection."""
        try:
            # Create directory if needed
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir)
            
            # Connect to SQLite database
            connection = sqlite3.connect(self.db_path)
            connection.row_factory = sqlite3.Row  # Enable column access by name
            
            # Configure SQLite settings
            if self.enable_wal_mode:
                connection.execute("PRAGMA journal_mode=WAL")
            
            if self.enable_foreign_keys:
                connection.execute("PRAGMA foreign_keys=ON")
            
            # Test connection
            cursor = connection.cursor()
            cursor.execute("SELECT sqlite_version()")
            version = cursor.fetchone()
            cursor.close()
            
            if version and self.verbose:
                logger.info(f"SQLite connection successful: {version[0]}")
            
            return connection
            
        except Exception as e:
            logger.error(f"Failed to connect to SQLite database: {e}")
            raise
    
    def get_test_query(self) -> str:
        """SQLite test query."""
        return "SELECT 1 as test"
    
    async def _execute_raw_query(self, query: str, params: Optional[Any] = None) -> List[Any]:
        """Execute SQLite query and return raw results."""
        cursor = None
        try:
            cursor = self.connection.cursor()
            
            # Handle parameters
            if params is None:
                params = []
            
            cursor.execute(query, params)
            
            # Handle different query types
            if query.strip().upper().startswith("SELECT"):
                results = cursor.fetchall()
                # Convert SQLite rows to dictionaries
                return [{key: row[key] for key in row.keys()} for row in results]
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
        """Close SQLite connection."""
        if self.connection:
            self.connection.close()

    async def initialize(self) -> None:
        """Initialize SQLite database."""
        try:
            if not self.connection:
                self.connection = await self.create_connection()
            
            # Verify table structure
            await self._verify_database_structure()
            
            logger.info(f"SQLiteRetriever initialized for database: {self.db_path}")
            
        except Exception as e:
            logger.error(f"Failed to initialize SQLiteRetriever: {e}")
            raise
    
    async def _verify_database_structure(self) -> None:
        """Verify required tables exist."""
        try:
            result = await self.execute_query(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", 
                [self.collection]
            )
            
            exists = len(result) > 0
            if not exists:
                logger.warning(f"Table '{self.collection}' not found in SQLite database")
                
        except Exception as e:
            logger.error(f"Error verifying SQLite database structure: {e}")
            raise

    def _get_search_query(self, query: str, collection_name: str) -> Dict[str, Any]:
        """Generate SQLite-optimized search query."""
        # Check if FTS is available (simplified version)
        use_fts = self.datasource_config.get('use_fts', False)
        
        if use_fts:
            query_tokens = self._tokenize_text(query)
            if query_tokens:
                # Use SQLite FTS if enabled
                search_config = {
                    "sql": f"""
                        SELECT * FROM {collection_name}_fts 
                        WHERE {collection_name}_fts MATCH ?
                        ORDER BY rank
                        LIMIT ?
                    """,
                    "params": [query, self.max_results],
                    "fields": self.default_search_fields
                }
                
                if self.verbose:
                    logger.info("Using SQLite FTS search")
                
                return search_config
        
        # Fallback to parent implementation
        return super()._get_search_query(query, collection_name)


# Register SQLite retriever with factory
RetrieverFactory.register_retriever('sqlite', SQLiteRetriever) 