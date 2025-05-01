"""
SQLite implementation of the BaseRetriever interface
"""

import logging
import sqlite3
import string
import traceback
from typing import Dict, Any, List, Optional, Union
from difflib import SequenceMatcher
from fastapi import HTTPException

from ...base.sql_retriever import SQLRetriever
from ...base.base_retriever import RetrieverFactory

# Configure logging
logger = logging.getLogger(__name__)

class QASqliteRetriever(SQLRetriever):
    """SQLite implementation of the SQLRetriever interface"""

    def __init__(self, 
                config: Dict[str, Any],
                connection: Any = None,
                **kwargs):
        """
        Initialize SQLiteRetriever.
        
        Args:
            config: Configuration dictionary containing SQLite and general settings
            connection: Optional SQLite connection
        """
        # Call the parent constructor first
        super().__init__(config=config, connection=connection, **kwargs)
        
        # Initialize database path
        self.db_path = self.datasource_config.get('db_path', '../utils/sqllite/rag_database.db')

    def _get_datasource_name(self) -> str:
        """Return the name of this datasource for config lookup"""
        return 'sqlite'

    async def initialize(self) -> None:
        """Initialize required services."""
        # Call parent initialize to set up API key service
        await super().initialize()
        
        # Initialize database connection
        try:
            if not self.connection:
                self.connection = sqlite3.connect(self.db_path)
                # Enable column access by name
                self.connection.row_factory = sqlite3.Row
                if self.verbose:
                    logger.info(f"Connected to SQLite database at {self.db_path}")
                    
                # Verify the database structure
                await self._check_database_structure()
        except Exception as e:
            logger.error(f"Failed to connect to SQLite database: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")

    async def _check_database_structure(self) -> None:
        """Check if the database has the required tables and structure."""
        if not self.connection:
            raise ValueError("Database connection not initialized")
            
        try:
            cursor = self.connection.cursor()
            
            # Check if the collection table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (self.collection,))
            if not cursor.fetchone():
                error_msg = f"Table '{self.collection}' not found in the database at {self.db_path}"
                logger.error(error_msg)
                raise ValueError(error_msg)
                
            # Check for search_tokens table (optional but helpful)
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='search_tokens'")
            if not cursor.fetchone():
                logger.warning("'search_tokens' table not found - search capabilities will be limited to string similarity")
                
            # Log success
            if self.verbose:
                logger.info(f"Database structure verified: collection '{self.collection}' found")
                
        except Exception as e:
            logger.error(f"Error checking database structure: {str(e)}")
            raise

    async def close(self) -> None:
        """Close any open services."""
        # Close parent services
        await super().close()
        
        # Close database connection
        if self.connection:
            self.connection.close()
            if self.verbose:
                logger.info("Closed SQLite database connection")

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
            cursor = self.connection.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (collection_name,))
            if not cursor.fetchone():
                error_msg = f"Table '{collection_name}' not found in the database"
                logger.error(error_msg)
                raise HTTPException(status_code=404, detail=error_msg)
                
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
        
        # Remove stopwords (basic implementation)
        stopwords = {'the', 'a', 'an', 'and', 'is', 'are', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'about',
                    'that', 'this', 'these', 'those', 'my', 'your', 'his', 'her', 'its', 'our', 'their', 'can', 'be',
                    'have', 'has', 'had', 'do', 'does', 'did', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what',
                    'where', 'when', 'why', 'how', 'which', 'who', 'whom', 'from'}
        
        filtered_tokens = [token for token in tokens if token not in stopwords and len(token) > 1]
        
        return filtered_tokens

    def _calculate_similarity(self, query: str, text: str) -> float:
        """
        Calculate similarity between query and text using SequenceMatcher.
        
        Args:
            query: The user's query
            text: The text to compare against
            
        Returns:
            Similarity score between 0 and 1
        """
        return SequenceMatcher(None, query.lower(), text.lower()).ratio()

    def _search_by_tokens(self, query_tokens: List[str]) -> List[Dict[str, Any]]:
        """
        Search for relevant documents using token-based matching.
        
        Args:
            query_tokens: Tokenized query terms
            
        Returns:
            List of candidate documents with match counts
        """
        if not query_tokens or not self.connection:
            return []
            
        try:
            cursor = self.connection.cursor()
            
            # Check if the search_tokens table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='search_tokens'")
            if not cursor.fetchone():
                if self.verbose:
                    logger.info("search_tokens table not found, skipping token-based search")
                return []
            
            # Prepare placeholders for query
            placeholders = ','.join(['?'] * len(query_tokens))
            
            # Search for matching tokens
            cursor.execute(f"""
                SELECT city_id, COUNT(*) as match_count 
                FROM search_tokens 
                WHERE token IN ({placeholders})
                GROUP BY city_id 
                ORDER BY match_count DESC
                LIMIT ?
            """, query_tokens + [self.max_results])
            
            results = []
            for row in cursor.fetchall():
                qa_id = row[0]
                match_count = row[1]
                
                # Get the actual QA pair
                cursor.execute(f"SELECT id, question, answer FROM {self.collection} WHERE id = ?", (qa_id,))
                qa_row = cursor.fetchone()
                
                if qa_row:
                    results.append({
                        "id": qa_row[0],
                        "question": qa_row[1],
                        "answer": qa_row[2],
                        "match_count": match_count,
                        "token_match_ratio": match_count / len(query_tokens) if query_tokens else 0
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"Error in token-based search: {str(e)}")
            return []

    async def get_relevant_context(self, 
                           query: str, 
                           api_key: Optional[str] = None, 
                           collection_name: Optional[str] = None,
                           **kwargs) -> List[Dict[str, Any]]:
        """
        Retrieve and filter relevant context from SQLite.
        
        Args:
            query: The user's query.
            api_key: Optional API key for accessing the collection.
            collection_name: Optional explicit collection name.
            **kwargs: Additional parameters
            
        Returns:
            A list of context items filtered by relevance.
        """
        try:
            # Call the parent implementation first which resolves collection
            # and handles common logging/error handling
            await super().get_relevant_context(query, api_key, collection_name, **kwargs)
            
            debug_mode = self.verbose
            
            if not self.connection:
                error_msg = "Database connection not initialized"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Tokenize the query
            query_tokens = self._tokenize_text(query)
            if debug_mode:
                logger.info(f"Tokenized query: {query_tokens}")
            
            # Try token-based search first
            token_results = self._search_by_tokens(query_tokens)
            candidate_ids = [result["id"] for result in token_results]
            
            if debug_mode:
                logger.info(f"Token search found {len(token_results)} candidate documents")
            
            cursor = self.connection.cursor()
            results = []
            
            # Get all QA pairs from the database, either from token results or all if none
            if candidate_ids:
                # Get only the token search results
                placeholders = ','.join(['?'] * len(candidate_ids))
                cursor.execute(f"SELECT id, question, answer FROM {self.collection} WHERE id IN ({placeholders})", 
                              candidate_ids)
            else:
                # If no token results, get all QA pairs (limited to max_results)
                cursor.execute(f"SELECT id, question, answer FROM {self.collection} LIMIT ?", (self.max_results,))
            
            rows = cursor.fetchall()
            
            # Calculate similarity for each result
            for row in rows:
                # Extract data from row
                qa_id = row[0]
                question = row[1]
                answer = row[2]
                
                # Calculate string similarity
                string_similarity = self._calculate_similarity(query, question)
                
                # Find token match data if it exists
                token_match_ratio = 0.0
                for result in token_results:
                    if result["id"] == qa_id:
                        token_match_ratio = result["token_match_ratio"]
                        break
                
                # Calculate combined score (weighted average)
                combined_score = (0.7 * token_match_ratio) + (0.3 * string_similarity) if token_match_ratio > 0 else string_similarity
                
                # Include in results if score exceeds threshold
                if combined_score >= self.relevance_threshold:
                    context_item = {
                        "id": qa_id,
                        "question": question,
                        "answer": answer,
                        "confidence": combined_score,
                        "content": f"Question: {question}\nAnswer: {answer}",
                        "raw_document": f"Question: {question}\nAnswer: {answer}",
                        "metadata": {
                            "source": "sqlite",
                            "collection": self.collection,
                            "string_similarity": string_similarity,
                            "token_match_ratio": token_match_ratio
                        }
                    }
                    results.append(context_item)
            
            # Sort by confidence and limit results
            results.sort(key=lambda x: x["confidence"], reverse=True)
            results = results[:self.return_results]
            
            if debug_mode:
                logger.info(f"Retrieved {len(results)} relevant context items")
                if results:
                    logger.info(f"Top confidence score: {results[0].get('confidence', 0)}")
                    logger.info(f"Top result: {results[0].get('question', 'N/A')}")
                else:
                    logger.warning("NO CONTEXT ITEMS FOUND")
            
            return results
                
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            logger.error(traceback.format_exc())
            return []

# Register the retriever with the factory
RetrieverFactory.register_retriever('sqlite', QASqliteRetriever)