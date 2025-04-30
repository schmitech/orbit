"""
Template for creating new SQL database retriever implementations
Copy this file and modify it to create a new SQL-based retriever

Usage:
1. Copy this file to {your_retriever_name}_retriever.py
2. Replace SQLTemplateRetriever with your retriever class name
3. Replace 'sql_template' with your datasource name in _get_datasource_name()
4. Implement the required methods
5. Register your retriever with the factory at the end of the file
"""

import logging
import string
import traceback
from typing import Dict, Any, List, Optional, Union
from difflib import SequenceMatcher
from fastapi import HTTPException

from retrievers.base_retriever import SQLRetriever, RetrieverFactory

# Configure logging
logger = logging.getLogger(__name__)

class SQLTemplateRetriever(SQLRetriever):
    """SQL Template implementation of the SQLRetriever interface"""

    def __init__(self, 
                config: Dict[str, Any],
                connection: Any = None,
                **kwargs):
        """
        Initialize SQLTemplateRetriever.
        
        Args:
            config: Configuration dictionary
            connection: Optional database connection
            **kwargs: Additional arguments
        """
        # Call the parent constructor first
        super().__init__(config=config, connection=connection, **kwargs)
        
        # Initialize database-specific connection parameters
        db_config = self.datasource_config
        self.connection_string = db_config.get('connection_string', 'localhost/database')
        
        # Set custom stopwords for tokenization
        self.stopwords = {
            'the', 'a', 'an', 'and', 'is', 'are', 'in', 'on', 'at', 'to', 'for', 
            'of', 'with', 'by', 'about', 'that', 'this', 'these', 'those'
        }

    def _get_datasource_name(self) -> str:
        """Return the name of this datasource for config lookup"""
        return 'sql_template'  # Change this to your datasource name

    async def initialize(self) -> None:
        """Initialize required services and database connection."""
        # Call parent initialize to set up API key service
        await super().initialize()
        
        # Initialize database connection
        try:
            if not self.connection:
                # Implement your database connection here
                # Example:
                # import my_sql_module
                # self.connection = my_sql_module.connect(self.connection_string)
                pass
                
            if self.verbose:
                logger.info(f"Connected to database at {self.connection_string}")
                
            # Verify database structure (tables, schema)
            await self._check_database_structure()
        except Exception as e:
            logger.error(f"Failed to connect to database: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")

    async def _check_database_structure(self) -> None:
        """Check if the database has the required tables and structure."""
        if not self.connection:
            raise ValueError("Database connection not initialized")
            
        try:
            # Verify that the collection/table exists
            # Example:
            # cursor = self.connection.cursor()
            # cursor.execute("SELECT 1 FROM information_schema.tables WHERE table_name = %s", (self.collection,))
            # if not cursor.fetchone():
            #     error_msg = f"Table '{self.collection}' not found in the database"
            #     logger.error(error_msg)
            #     raise ValueError(error_msg)
                
            # Log success
            if self.verbose:
                logger.info(f"Database structure verified: collection '{self.collection}' found")
                
        except Exception as e:
            logger.error(f"Error checking database structure: {str(e)}")
            raise

    async def close(self) -> None:
        """Close any open services and connections."""
        # Close parent services
        await super().close()
        
        # Close database connection
        try:
            if self.connection:
                # self.connection.close()
                pass
                
            if self.verbose:
                logger.info("Closed database connection")
        except Exception as e:
            logger.error(f"Error closing database connection: {str(e)}")

    async def set_collection(self, collection_name: str) -> None:
        """
        Set the current collection (table name) for retrieval.
        
        Args:
            collection_name: Name of the table to use
        """
        if not collection_name:
            raise ValueError("Collection name cannot be empty")
            
        # Verify that the table exists
        if self.connection:
            try:
                # Verify table exists
                # Example:
                # cursor = self.connection.cursor()
                # cursor.execute("SELECT 1 FROM information_schema.tables WHERE table_name = %s", (collection_name,))
                # if not cursor.fetchone():
                #     error_msg = f"Table '{collection_name}' not found in the database"
                #     logger.error(error_msg)
                #     raise HTTPException(status_code=404, detail=error_msg)
                pass
            except Exception as e:
                error_msg = f"Error verifying table '{collection_name}': {str(e)}"
                logger.error(error_msg)
                raise HTTPException(status_code=500, detail=error_msg)
                
        # Set the collection name
        self.collection = collection_name
        if self.verbose:
            logger.info(f"Switched to collection (table): {collection_name}")

    def _tokenize_text(self, text: str) -> List[str]:
        """
        Tokenize text for better matching.
        
        Args:
            text: Text to tokenize
            
        Returns:
            List of tokens
        """
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
        
        # Alternative methods could include:
        # - Jaccard similarity on token sets
        # - TF-IDF based similarity
        # - BM25 similarity
        # - Edit distance normalized to [0,1]

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
            
            # 1. Tokenize the query for better matching
            query_tokens = self._tokenize_text(query)
            if debug_mode:
                logger.info(f"Tokenized query: {query_tokens}")
            
            # 2. Perform database query to retrieve candidates
            # Example:
            # cursor = self.connection.cursor()
            # cursor.execute(f"SELECT id, question, answer FROM {self.collection} LIMIT %s", (self.max_results,))
            # rows = cursor.fetchall()
            
            # 3. For each candidate, calculate relevance score
            results = []
            
            # Example processing:
            # for row in rows:
            #     question_text = row['question']
            #     answer_text = row['answer']
            #     
            #     # Calculate similarity score
            #     similarity = self._calculate_similarity(query, question_text)
            #     
            #     # Only include results that meet threshold
            #     if similarity >= self.relevance_threshold:
            #         context_item = {
            #             "question": question_text,
            #             "answer": answer_text,
            #             "confidence": similarity,
            #             "content": f"Question: {question_text}\nAnswer: {answer_text}",
            #             "raw_document": f"Question: {question_text}\nAnswer: {answer_text}",
            #             "metadata": {
            #                 "source": self._get_datasource_name(),
            #                 "collection": self.collection,
            #                 "similarity_score": similarity
            #             }
            #         }
            #         results.append(context_item)
            
            # 4. Sort and limit results
            if results:
                results.sort(key=lambda x: x.get("confidence", 0), reverse=True)
                results = results[:self.return_results]
            
            if debug_mode:
                logger.info(f"Retrieved {len(results)} relevant context items")
            
            return results
                
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            logger.error(traceback.format_exc())
            return []

# Uncomment to register your retriever with the factory
# RetrieverFactory.register_retriever('sql_template', SQLTemplateRetriever) 