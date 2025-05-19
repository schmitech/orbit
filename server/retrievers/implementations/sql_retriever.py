"""
Base SQL retriever class that defines the interface for SQL-based retrievers
"""

from typing import Dict, Any, List, Optional
import logging
from abc import abstractmethod
from retrievers.base.sql_retriever import SQLRetriever as BaseSQLRetriever

# Configure logging
logger = logging.getLogger(__name__)
logger.info("LOADING SQLRetriever MODULE")

class SQLRetriever(BaseSQLRetriever):
    """
    Base class for SQL retrievers that extends the core SQLRetriever.
    This class provides additional functionality and defines the interface
    that specific SQL implementations must follow.
    """
    
    def __init__(self, 
                 config: Dict[str, Any],
                 connection: Any = None,
                 **kwargs):
        """
        Initialize the SQL retriever.
        
        Args:
            config: Configuration dictionary
            connection: Database connection
            **kwargs: Additional keyword arguments
        """
        super().__init__(config=config, connection=connection, **kwargs)
        
        # SQL-specific settings
        self.relevance_threshold = self.datasource_config.get('relevance_threshold', 0.5)
        self.max_results = self.datasource_config.get('max_results', 10)
        self.return_results = self.datasource_config.get('return_results', 3)
        
        logger.info(f"SQLRetriever INITIALIZED with relevance_threshold={self.relevance_threshold}")
    
    @abstractmethod
    async def execute_query(self, sql: str, params: List[Any] = None) -> List[Dict[str, Any]]:
        """
        Execute SQL query and return results.
        This method must be implemented by specific SQL providers.
        
        Args:
            sql: SQL query string
            params: Query parameters
            
        Returns:
            List of rows as dictionaries
        """
        raise NotImplementedError("Subclasses must implement execute_query()")
    
    @abstractmethod
    def _get_search_query(self, query: str, collection_name: str) -> Dict[str, Any]:
        """
        Generate a SQL query based on the user's query.
        This method must be implemented by specific SQL providers.
        
        Args:
            query: The user's query
            collection_name: The collection/table name
            
        Returns:
            Dict with SQL query, parameters, and fields
        """
        raise NotImplementedError("Subclasses must implement _get_search_query()")
    
    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize required services and verify database structure.
        This method must be implemented by specific SQL providers.
        """
        raise NotImplementedError("Subclasses must implement initialize()")
    
    @abstractmethod
    async def close(self) -> None:
        """
        Close any open services and connections.
        This method must be implemented by specific SQL providers.
        """
        raise NotImplementedError("Subclasses must implement close()") 