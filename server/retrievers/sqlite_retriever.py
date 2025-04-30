"""
Enhanced SQLite implementation with domain adaptation support
"""

import logging
import sqlite3
import string
import traceback
from typing import Dict, Any, List, Optional, Union
from difflib import SequenceMatcher
from fastapi import HTTPException

from retrievers.sql_retriever import SQLRetriever, RetrieverFactory

# Configure logging
logger = logging.getLogger(__name__)

class SqliteRetriever(SQLRetriever):
    """Enhanced SQLite implementation with domain support"""

    def __init__(self, 
                config: Dict[str, Any],
                connection: Any = None,
                domain_adapter=None,
                **kwargs):
        """
        Initialize SQLiteRetriever.
        
        Args:
            config: Configuration dictionary containing SQLite and general settings
            connection: Optional SQLite connection
            domain_adapter: Optional domain adapter for document handling
        """
        # Call the parent constructor first
        super().__init__(config=config, connection=connection, domain_adapter=domain_adapter, **kwargs)
        
        # Initialize database path
        self.db_path = self.datasource_config.get('db_path', '../utils/sqllite/rag_database.db')
        
        # Flag to track if search_tokens table exists
        self.has_token_table = False

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
            if cursor.fetchone():
                self.has_token_table = True
                if self.verbose:
                    logger.info("Found 'search_tokens' table - will use for token-based search")
            else:
                self.has_token_table = False
                if self.verbose:
                    logger.info("'search_tokens' table not found - using string similarity only")
                
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
            
        # Check table structure to discover fields
        try:
            cursor = self.connection.cursor()
            cursor.execute(f"PRAGMA table_info({collection_name})")
            columns = cursor.fetchall()
            
            # Update default search fields based on table structure
            field_names = [col[1] for col in columns]
            
            # Prioritize common field names
            priority_fields = ["id", "question", "answer", "title", "content", "text", "body"]
            self.default_search_fields = [f for f in priority_fields if f in field_names]
            
            # Add remaining text fields if we don't have enough
            if len(self.default_search_fields) < 3:
                for field in field_names:
                    if field not in self.default_search_fields:
                        self.default_search_fields.append(field)
            
            if self.verbose:
                logger.info(f"Using search fields: {self.default_search_fields}")
        except Exception as e:
            logger.error(f"Error examining table structure: {str(e)}")

    async def execute_query(self, sql: str, params: List[Any] = None) -> List[Dict[str, Any]]:
        """
        Execute SQL query and return results.
        
        Args:
            sql: SQL query string
            params: Query parameters
            
        Returns:
            List of rows as dictionaries
        """
        if not self.connection:
            raise ValueError("Database connection not initialized")
            
        if params is None:
            params = []
            
        try:
            cursor = self.connection.cursor()
            cursor.execute(sql, params)
            
            # Get column names
            column_names = [description[0] for description in cursor.description] if cursor.description else []
            
            # Convert rows to dictionaries
            rows = cursor.fetchall()
            result = []
            
            for row in rows:
                # Convert row to dict by mapping column names to values
                if isinstance(row, sqlite3.Row):
                    # If sqlite3.Row factory is working, use keys
                    item = {}
                    for key in row.keys():
                        item[key] = row[key]
                else:
                    # If not, use the column names we fetched
                    item = {column_names[i]: value for i, value in enumerate(row)}
                
                result.append(item)
                
            return result
            
        except Exception as e:
            logger.error(f"Error executing query: {str(e)}")
            logger.error(f"SQL: {sql}")
            logger.error(f"Params: {params}")
            return []

    async def _search_by_tokens(self, query_tokens: List[str]) -> List[Dict[str, Any]]:
        """
        Search for relevant documents using token-based matching.
        
        Args:
            query_tokens: Tokenized query terms
            
        Returns:
            List of candidate documents with match counts
        """
        if not query_tokens or not self.connection or not self.has_token_table:
            return []
            
        try:
            # Prepare placeholders for query
            placeholders = ','.join(['?'] * len(query_tokens))
            
            # Search for matching tokens
            sql = f"""
                SELECT doc_id, COUNT(*) as match_count 
                FROM search_tokens 
                WHERE token IN ({placeholders})
                GROUP BY doc_id 
                ORDER BY match_count DESC
                LIMIT ?
            """
            
            rows = await self.execute_query(sql, query_tokens + [self.max_results])
            
            results = []
            for row in rows:
                doc_id = row["doc_id"]
                match_count = row["match_count"]
                
                # Get the actual document
                doc_rows = await self.execute_query(
                    f"SELECT * FROM {self.collection} WHERE id = ?", 
                    [doc_id]
                )
                
                if doc_rows:
                    # Add token match info to the document
                    doc = doc_rows[0]
                    doc["match_count"] = match_count
                    doc["token_match_ratio"] = match_count / len(query_tokens) if query_tokens else 0
                    results.append(doc)
            
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
        Retrieve and filter relevant context from SQLite with domain adaptation.
        
        Args:
            query: The user's query.
            api_key: Optional API key for accessing the collection.
            collection_name: Optional explicit collection name.
            **kwargs: Additional parameters
            
        Returns:
            A list of context items filtered by relevance.
        """
        try:
            # Call the parent implementation which handles common functionality
            # Use super() instead of directly referencing BaseRetriever
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
            
            # First try token-based search if available
            token_results = await self._search_by_tokens(query_tokens) if self.has_token_table else []
            
            if debug_mode:
                logger.info(f"Token search found {len(token_results)} candidate documents")
            
            # If token search yielded results, use those, otherwise use regular SQL search
            if token_results:
                rows = token_results
            else:
                # Use domain-specific search query
                search_config = self._get_search_query(query, self.collection)
                rows = await self.execute_query(search_config["sql"], search_config["params"])
            
            # Calculate similarity for each result
            results = []
            
            for row in rows:
                # Find the best field to calculate similarity against
                compare_field = None
                compare_value = None
                
                # Determine which field to use for similarity comparison
                priority_fields = ["question", "title", "content", "text", "description"]
                for field in priority_fields:
                    if field in row and row[field]:
                        compare_field = field
                        compare_value = row[field]
                        break
                
                # If no priority field found, use the first text field
                if not compare_field:
                    for field, value in row.items():
                        if isinstance(value, str) and len(value) > 10:
                            compare_field = field
                            compare_value = value
                            break
                
                # Skip if no suitable field found
                if not compare_field:
                    continue
                
                # Calculate similarity score
                similarity = self._calculate_similarity(query, compare_value)
                
                # Get token match ratio if available
                token_match_ratio = row.get("token_match_ratio", 0)
                
                # Calculate combined score
                combined_score = (0.7 * token_match_ratio) + (0.3 * similarity) if token_match_ratio > 0 else similarity
                
                # Include in results if score exceeds threshold
                if combined_score >= self.relevance_threshold:
                    # Determine raw document content
                    raw_doc = ""
                    if "content" in row:
                        raw_doc = row["content"]
                    elif "question" in row and "answer" in row:
                        raw_doc = f"Question: {row['question']}\nAnswer: {row['answer']}"
                    elif compare_field:
                        raw_doc = compare_value
                    
                    # Use domain adapter to format the document
                    context_item = self.format_document(raw_doc, dict(row))
                    context_item["confidence"] = combined_score
                    
                    # Add source info to metadata
                    if "metadata" not in context_item:
                        context_item["metadata"] = {}
                    context_item["metadata"]["source"] = self._get_datasource_name()
                    context_item["metadata"]["collection"] = self.collection
                    
                    results.append(context_item)
            
            # Apply domain-specific filtering
            results = self.apply_domain_filtering(results, query)
            
            # Sort by confidence and limit results
            results.sort(key=lambda x: x["confidence"], reverse=True)
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

# Register the retriever with the factory
RetrieverFactory.register_retriever('sqlite', SqliteRetriever)