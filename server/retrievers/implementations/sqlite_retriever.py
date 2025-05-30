"""
SQLite implementation of AbstractSQLRetriever
"""

import logging
import sqlite3
import os
from typing import Dict, Any, List, Optional
from ..base.sql_retriever import AbstractSQLRetriever
from ..base.base_retriever import RetrieverFactory
from utils.lazy_loader import LazyLoader

logger = logging.getLogger(__name__)

class SQLiteRetriever(AbstractSQLRetriever):
    """
    SQLite-specific implementation of AbstractSQLRetriever.
    
    This shows how to implement database-specific functionality while
    leveraging the common SQL retriever infrastructure.
    """

    def __init__(self, 
                config: Dict[str, Any],
                connection: Any = None,
                **kwargs):
        """
        Initialize SQLiteRetriever.
        
        Args:
            config: Configuration dictionary
            connection: Optional SQLite connection
            **kwargs: Additional arguments
        """
        super().__init__(config=config, connection=connection, **kwargs)
        
        # SQLite-specific configuration
        sqlite_config = self.datasource_config
        self.db_path = sqlite_config.get('db_path', 'sqlite_db')
        
        # Create lazy loader for SQLite connection
        def create_sqlite_connection():
            try:
                # Create directory if needed
                db_dir = os.path.dirname(self.db_path)
                if db_dir and not os.path.exists(db_dir):
                    os.makedirs(db_dir)
                
                # Connect to SQLite database
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row  # Enable column access by name
                
                if self.verbose:
                    logger.info(f"Connected to SQLite database at {self.db_path}")
                
                return conn
                    
            except Exception as e:
                logger.error(f"Failed to connect to SQLite database: {str(e)}")
                raise ValueError(f"SQLite connection error: {str(e)}")
        
        if not connection:
            self._connection_loader = LazyLoader(create_sqlite_connection, "SQLite connection")
        else:
            self.connection = connection

    @property
    def connection(self):
        """Lazy-loaded SQLite connection."""
        if hasattr(self, '_connection_loader'):
            return self._connection_loader.get_instance()
        return self._connection

    @connection.setter
    def connection(self, value):
        """Set the connection directly."""
        self._connection = value

    def _get_datasource_name(self) -> str:
        """Return the datasource name for config lookup."""
        return 'sqlite'

    # Required abstract method implementations
    async def execute_query(self, sql: str, params: List[Any] = None) -> List[Dict[str, Any]]:
        """
        Execute SQLite query and return results.
        
        Args:
            sql: SQL query string
            params: Query parameters
            
        Returns:
            List of rows as dictionaries
        """
        if not self.connection:
            raise ValueError("SQLite connection not initialized")
            
        if params is None:
            params = []
            
        try:
            if self.verbose:
                logger.info(f"Executing SQLite query: {sql}")
                logger.info(f"Parameters: {params}")
            
            cursor = self.connection.cursor()
            cursor.execute(sql, params)
            
            # Convert SQLite rows to dictionaries
            rows = cursor.fetchall()
            result = []
            
            for row in rows:
                # SQLite3.Row supports dict-like access
                item = {key: row[key] for key in row.keys()}
                result.append(item)
            
            if self.verbose:
                logger.info(f"SQLite query returned {len(result)} rows")
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing SQLite query: {str(e)}")
            logger.error(f"SQL: {sql}, Params: {params}")
            return []

    async def initialize(self) -> None:
        """
        Initialize SQLite database and verify structure.
        """
        try:
            # Ensure connection is established
            if not self.connection:
                _ = self.connection  # Trigger lazy loading
                
            # Verify database structure
            await self._verify_database_structure()
            
            logger.info(f"SQLiteRetriever initialized for database: {self.db_path}")
            
        except Exception as e:
            logger.error(f"Failed to initialize SQLiteRetriever: {str(e)}")
            raise

    async def close(self) -> None:
        """
        Close SQLite connection and cleanup resources.
        """
        try:
            if hasattr(self, '_connection') and self._connection:
                self._connection.close()
                self._connection = None
                logger.info("SQLite connection closed")
            elif hasattr(self, '_connection_loader'):
                if self._connection_loader._instance:
                    self._connection_loader._instance.close()
                    self._connection_loader._instance = None
                    logger.info("SQLite connection closed")
                
        except Exception as e:
            logger.error(f"Error closing SQLite connection: {str(e)}")

    # SQLite-specific helper methods
    async def _verify_database_structure(self) -> None:
        """Verify that required tables exist in SQLite database."""
        try:
            cursor = self.connection.cursor()
            
            # Check if collection table exists (SQLite-specific syntax)
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", 
                (self.collection,)
            )
            
            if not cursor.fetchone():
                logger.warning(f"Table '{self.collection}' not found in SQLite database")
                # Optionally create table here
                
        except Exception as e:
            logger.error(f"Error verifying SQLite database structure: {str(e)}")
            raise

    def _get_search_query(self, query: str, collection_name: str) -> Dict[str, Any]:
        """
        Generate SQLite-optimized search query.
        
        SQLite supports FTS (Full-Text Search) which we could leverage here.
        """
        # Use parent implementation by default
        search_config = super()._get_search_query(query, collection_name)
        
        # SQLite-specific optimizations could be added here:
        # - Use FTS5 if available
        # - Use SQLite's LIKE with proper indexing
        # - Leverage SQLite's JSON functions if storing JSON data
        
        return search_config


# Register SQLite retriever with factory
RetrieverFactory.register_retriever('sqlite', SQLiteRetriever) 