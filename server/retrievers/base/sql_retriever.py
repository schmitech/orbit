"""
Enhanced SQL retriever abstract class with domain adapter support
"""

import logging
import string
import traceback
from abc import abstractmethod
from typing import Dict, Any, List, Optional, Union, Set
from difflib import SequenceMatcher
from fastapi import HTTPException

from .base_retriever import BaseRetriever
from .base_retriever import RetrieverFactory

# Configure logging
logger = logging.getLogger(__name__)

class AbstractSQLRetriever(BaseRetriever):
    """
    Abstract base class for SQL-based retrievers.
    
    This class provides common SQL functionality while leaving database-specific
    implementation details to concrete subclasses.
    """
    
    def __init__(self, 
                config: Dict[str, Any],
                connection: Any = None,
                domain_adapter=None,
                **kwargs):
        """
        Initialize SQL retriever with common configuration.
        
        Args:
            config: Configuration dictionary
            connection: Database connection
            domain_adapter: Optional domain adapter for document handling
        """
        super().__init__(config=config, domain_adapter=domain_adapter, **kwargs)
        
        # SQL-specific settings with sensible defaults
        self.relevance_threshold = self.datasource_config.get('relevance_threshold', 0.5)
        self.max_results = self.datasource_config.get('max_results', 10)
        self.return_results = self.datasource_config.get('return_results', 3)
        self.connection = connection
        
        # Define standard stopwords for tokenization
        self.stopwords = {
            'the', 'a', 'an', 'and', 'is', 'are', 'in', 'on', 'at', 'to', 'for', 
            'of', 'with', 'by', 'about', 'that', 'this', 'these', 'those', 'my', 
            'your', 'his', 'her', 'its', 'our', 'their', 'can', 'be',
            'have', 'has', 'had', 'do', 'does', 'did', 'i', 'you', 'he', 'she', 
            'it', 'we', 'they', 'what', 'where', 'when', 'why', 'how'
        }
        
        # Default fields to search
        self.default_search_fields = ['id', 'content']
        
        logger.info(f"AbstractSQLRetriever initialized with relevance_threshold={self.relevance_threshold}")
        
    def _tokenize_text(self, text: str) -> List[str]:
        """
        Tokenize text for better matching.
        
        Args:
            text: Text to tokenize
            
        Returns:
            List of tokens
        """
        # Use domain adapter's tokenization if available
        if hasattr(self.domain_adapter, 'get_search_tokens'):
            tokens = self.domain_adapter.get_search_tokens(text)
            return list(tokens)
        
        # Default tokenization
        # Convert to lowercase
        text = text.lower()
        
        # Remove punctuation
        text = text.translate(str.maketrans('', '', string.punctuation))
        
        # Split into tokens
        tokens = text.split()
        
        # Remove stopwords and short tokens
        filtered_tokens = [token for token in tokens if token not in self.stopwords and len(token) > 1]
        
        return filtered_tokens
        
    def _calculate_similarity(self, query: str, text: str) -> float:
        """
        Calculate similarity between query and text.
        
        Args:
            query: The user's query
            text: The text to compare against
            
        Returns:
            Similarity score between 0 and 1
        """
        # Use SequenceMatcher for similarity calculation
        return SequenceMatcher(None, query.lower(), text.lower()).ratio()

    # Abstract methods that concrete implementations must provide
    @abstractmethod
    async def execute_query(self, sql: str, params: List[Any] = None) -> List[Dict[str, Any]]:
        """
        Execute SQL query and return results.
        This method must be implemented by specific SQL database providers.
        
        Args:
            sql: SQL query string
            params: Query parameters
            
        Returns:
            List of rows as dictionaries
        """
        raise NotImplementedError("Subclasses must implement execute_query()")
    
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
    
    def _get_search_query(self, query: str, collection_name: str) -> Dict[str, Any]:
        """
        Get domain-specific SQL search query.
        Can be overridden by subclasses for database-specific optimization.
        
        Args:
            query: User query
            collection_name: Table name
            
        Returns:
            Dict with SQL query, parameters, and fields
        """
        # Use domain adapter's SQL query generator if available
        if hasattr(self.domain_adapter, 'get_search_conditions'):
            return self.domain_adapter.get_search_conditions(query, collection_name)
        
        # Default simple search
        return {
            "sql": f"SELECT * FROM {collection_name} LIMIT ?",
            "params": [self.max_results],
            "fields": self.default_search_fields
        }
    
    async def get_relevant_context(self, 
                           query: str, 
                           api_key: Optional[str] = None, 
                           collection_name: Optional[str] = None,
                           **kwargs) -> List[Dict[str, Any]]:
        """
        Retrieve and filter relevant context from SQL database.
        
        Args:
            query: The user's query
            api_key: Optional API key for accessing the collection
            collection_name: Optional explicit collection name
            **kwargs: Additional parameters
            
        Returns:
            A list of context items filtered by relevance
        """
        try:
            # Call the parent implementation which resolves collection
            # and handles common logging/error handling
            await super().get_relevant_context(query, api_key, collection_name, **kwargs)
            
            debug_mode = self.verbose
            
            if not self.connection:
                error_msg = "Database connection not initialized"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # 1. Get domain-specific search query
            search_config = self._get_search_query(query, self.collection)
            sql_query = search_config["sql"]
            params = search_config.get("params", [])
            fields = search_config.get("fields", self.default_search_fields)
            
            if debug_mode:
                logger.info(f"Search query: {sql_query}")
                logger.info(f"Search params: {params}")
            
            # 2. Execute the query
            rows = await self.execute_query(sql_query, params)
            
            if debug_mode:
                logger.info(f"Retrieved {len(rows)} initial rows from database")
            
            # 3. Process and filter results
            results = []
            
            for row in rows:
                # Calculate similarity to improve relevance
                main_text = ""
                # Get text to compare with query from appropriate field
                if "question" in row:
                    main_text = row["question"]
                elif "title" in row:
                    main_text = row["title"]
                elif "content" in row:
                    main_text = row["content"]
                else:
                    # Use first non-id string field
                    for field, value in row.items():
                        if field != "id" and isinstance(value, str) and value:
                            main_text = value
                            break
                
                # Calculate string similarity
                similarity = self._calculate_similarity(query, main_text)
                
                # Only include results that meet threshold
                if similarity >= self.relevance_threshold:
                    # Extract raw document
                    raw_doc = ""
                    if "content" in row:
                        raw_doc = row["content"]
                    elif "question" in row and "answer" in row:
                        raw_doc = f"Question: {row['question']}\nAnswer: {row['answer']}"
                    else:
                        # Use the longest text field
                        longest = ""
                        for field, value in row.items():
                            if isinstance(value, str) and len(value) > len(longest):
                                longest = value
                        raw_doc = longest
                    
                    # Create metadata from all fields
                    metadata = {}
                    for field, value in row.items():
                        metadata[field] = value
                    
                    # Use domain adapter to format the document
                    context_item = self.format_document(raw_doc, metadata)
                    
                    # Add confidence score
                    context_item["confidence"] = similarity
                    
                    # Add source info
                    if "metadata" not in context_item:
                        context_item["metadata"] = {}
                    context_item["metadata"]["source"] = self._get_datasource_name()
                    context_item["metadata"]["collection"] = self.collection
                    
                    results.append(context_item)
            
            # 4. Apply domain-specific filtering
            results = self.apply_domain_filtering(results, query)
            
            # 5. Sort and limit results
            results.sort(key=lambda x: x.get("confidence", 0), reverse=True)
            results = results[:self.return_results]
            
            if debug_mode:
                logger.info(f"Retrieved {len(results)} relevant context items")
                if results:
                    logger.info(f"Top confidence score: {results[0].get('confidence', 0)}")
            
            return results
                
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            logger.error(traceback.format_exc())
            return []


# For backward compatibility, keep the old class name as an alias
SQLRetriever = AbstractSQLRetriever