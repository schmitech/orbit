"""
 SQLite retriever that works with the new adapter architecture
"""

import logging
import sqlite3
import string
import traceback
import os
from typing import Dict, Any, List, Optional, Union
from difflib import SequenceMatcher
from fastapi import HTTPException

from retrievers.base.base_retriever import BaseRetriever, RetrieverFactory
from utils.lazy_loader import LazyLoader

# Configure logging
logger = logging.getLogger(__name__)

class SqliteRetriever(BaseRetriever):
    """
     SQLite retriever that works with the new adapter architecture.
    This implementation is more flexible and can work with different domain adapters.
    """

    def __init__(self, 
                config: Dict[str, Any],
                domain_adapter = None,
                connection: Any = None,
                **kwargs):
        """
        Initialize SQLiteRetriever.
        
        Args:
            config: Configuration dictionary containing SQLite and general settings
            domain_adapter: Optional domain adapter for document handling
            connection: Optional SQLite connection
            **kwargs: Additional arguments
        """
        # Call the parent constructor first to set up basic retriever functionality
        super().__init__(config=config, domain_adapter=domain_adapter, **kwargs)
        
        # Extract SQLite-specific configuration
        sqlite_config = self.datasource_config
        
        # Core settings
        self.db_path = sqlite_config.get('db_path', 'sqlite_db')
        self.relevance_threshold = sqlite_config.get('relevance_threshold', 0.5)
        self.max_results = sqlite_config.get('max_results', 10)
        self.return_results = sqlite_config.get('return_results', 3)
        
        # Set default collection - this will be overridden when needed
        self.collection = sqlite_config.get('collection', 'qa_data')
        
        # Flag to track if search_tokens table exists
        self.has_token_table = False
        
        # Define standard stopwords for tokenization
        self.stopwords = {
            'the', 'a', 'an', 'and', 'is', 'are', 'in', 'on', 'at', 'to', 'for', 
            'of', 'with', 'by', 'about', 'that', 'this', 'these', 'those', 'my', 
            'your', 'his', 'her', 'its', 'our', 'their', 'can', 'be',
            'have', 'has', 'had', 'do', 'does', 'did', 'i', 'you', 'he', 'she', 
            'it', 'we', 'they', 'what', 'where', 'when', 'why', 'how'
        }
        
        # Default fields to search
        self.default_search_fields = ['id', 'content', 'question', 'answer', 'title']
        
        # Create a lazy loader for the SQLite connection
        def create_sqlite_connection():
            try:
                # Create the database directory if it doesn't exist
                db_dir = os.path.dirname(self.db_path)
                if db_dir and not os.path.exists(db_dir):
                    os.makedirs(db_dir)
                
                # Connect to the database
                conn = sqlite3.connect(self.db_path)
                # Enable column access by name
                conn.row_factory = sqlite3.Row
                
                if self.verbose:
                    logger.info(f"Connected to SQLite database at {self.db_path}")
                
                # Check if we need to create the default table
                self._create_default_table_if_needed(conn)
                
                return conn
                    
            except Exception as e:
                logger.error(f"Failed to connect to SQLite database: {str(e)}")
                raise ValueError(f"Database connection error: {str(e)}")
        
        # Create a lazy loader for the SQLite connection
        self._connection_loader = LazyLoader(create_sqlite_connection, "SQLite connection")
        
        # Initialize connection if provided
        if connection:
            self._connection_loader.set_instance(connection)

    @property
    def connection(self):
        """Lazy-loaded SQLite connection property."""
        return self._connection_loader.get_instance()

    def _get_datasource_name(self) -> str:
        """Return the name of this datasource for config lookup"""
        return 'sqlite'

    def _create_default_table_if_needed(self, conn: sqlite3.Connection) -> None:
        """Create the default table if it doesn't exist."""
        if not conn:
            return
            
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (self.collection,))
            if not cursor.fetchone():
                if self.verbose:
                    logger.info(f"Creating default table '{self.collection}'")
                
                # Create the table with appropriate structure for QA data
                cursor.execute(f'''
                    CREATE TABLE IF NOT EXISTS {self.collection} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        question TEXT,
                        answer TEXT,
                        metadata TEXT
                    )
                ''')
                conn.commit()
                
                # Insert some sample data to get started
                cursor.execute(f'''
                    INSERT INTO {self.collection} (question, answer, metadata)
                    VALUES (?, ?, ?)
                ''', (
                    "What is the purpose of this system?", 
                    "This system provides a flexible retrieval architecture with domain-specific adapters.",
                    '{"source": "documentation", "type": "overview"}'
                ))
                
                cursor.execute(f'''
                    INSERT INTO {self.collection} (question, answer, metadata)
                    VALUES (?, ?, ?)
                ''', (
                    "How do adapters work in this system?", 
                    "Adapters provide domain-specific document handling, allowing the system to process different types of data without changing the core retrieval logic.",
                    '{"source": "documentation", "type": "technical"}'
                ))
                
                conn.commit()
                
                if self.verbose:
                    logger.info(f"Created default table '{self.collection}' with sample data")
        except Exception as e:
            logger.warning(f"Could not create default table: {str(e)}")

    async def initialize(self) -> None:
        """Initialize required services and verify database structure."""
        # Call parent initialize to set up API key service
        await super().initialize()
        
        # Check for search_tokens table
        cursor = self.connection.cursor()
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='search_tokens'")
            if cursor.fetchone():
                self.has_token_table = True
                if self.verbose:
                    logger.info("Found 'search_tokens' table - will use for token-based search")
            else:
                self.has_token_table = False
                if self.verbose:
                    logger.info("'search_tokens' table not found - using string similarity only")
        except Exception as e:
            logger.warning(f"Error checking for search_tokens table: {str(e)}")
            self.has_token_table = False

    async def close(self) -> None:
        """Close any open services and connections."""
        # Close parent services
        await super().close()
        
        # Close database connection
        if hasattr(self, '_connection_loader'):
            conn = self._connection_loader.get_instance()
            if conn:
                conn.close()
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
            
        # Set the collection name
        self.collection = collection_name
        if self.verbose:
            logger.info(f"Switched to collection (table): {collection_name}")
            
        # Verify the table exists
        if self.connection:
            cursor = self.connection.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (collection_name,))
            if not cursor.fetchone():
                error_msg = f"Table '{collection_name}' not found in the database"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Update default search fields based on table structure
            cursor.execute(f"PRAGMA table_info({collection_name})")
            columns = cursor.fetchall()
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
            # Log the query and parameters if verbose mode is enabled
            if self.verbose:
                logger.info("Executing SQL query:")
                logger.info(f"SQL: {sql}")
                logger.info(f"Parameters: {params}")
            
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
            
            # Log the number of results if verbose mode is enabled
            if self.verbose:
                logger.info(f"Query returned {len(result)} rows")
                if result:
                    logger.info(f"First row columns: {list(result[0].keys())}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing query: {str(e)}")
            logger.error(f"SQL: {sql}")
            logger.error(f"Params: {params}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return []

    def _get_search_query(self, query: str, collection_name: str) -> Dict[str, Any]:
        """
        Generate a SQL query based on the user's query.
        
        Args:
            query: The user's query
            collection_name: The collection/table name
            
        Returns:
            Dict with SQL query, parameters, and fields
        """
        # Tokenize the query
        query_tokens = self._tokenize_text(query)
        
        if self.verbose:
            logger.info(f"Generating search query for: '{query}'")
            logger.info(f"Tokenized query: {query_tokens}")
            logger.info(f"Using collection: {collection_name}")
        
        if not query_tokens:
            # Fallback to basic query
            if self.verbose:
                logger.info("No valid tokens found, using basic query")
            return {
                "sql": f"SELECT * FROM {collection_name} LIMIT ?",
                "params": [self.max_results],
                "fields": self.default_search_fields
            }
        
        # For QA collections, search primarily in the question field
        if "question" in self.default_search_fields:
            # Build a search condition that checks for each token in the question field
            conditions = []
            params = []
            
            for token in query_tokens:
                if len(token) > 2:  # Only use tokens with sufficient length
                    conditions.append("question LIKE ?")
                    params.append(f"%{token}%")
            
            if conditions:
                # Use OR to be more inclusive in our search
                where_clause = " OR ".join(conditions)
                
                # Use ORDER BY to sort by relevance based on how many tokens match
                # We'll count the number of matching tokens for each result
                order_by_clause = ""
                for token in query_tokens:
                    if len(token) > 2:
                        order_by_clause += f" + (CASE WHEN question LIKE '%{token}%' THEN 1 ELSE 0 END)"
                
                if order_by_clause:
                    order_by_clause = f"ORDER BY ({order_by_clause[3:]}) DESC"
                
                # Build the final SQL query
                sql = f"""
                    SELECT * FROM {collection_name} 
                    WHERE {where_clause}
                    {order_by_clause}
                    LIMIT ?
                """
                params.append(self.max_results)
                
                if self.verbose:
                    logger.info("Generated QA-specific search query:")
                    logger.info(f"SQL: {sql}")
                    logger.info(f"Parameters: {params}")
                    logger.info(f"Search fields: {self.default_search_fields}")
                
                return {
                    "sql": sql,
                    "params": params,
                    "fields": self.default_search_fields
                }
        
        # For more generic queries, search across all text fields
        conditions = []
        params = []
        search_fields = [f for f in self.default_search_fields if f != "id"]
        
        for field in search_fields:
            for token in query_tokens:
                if len(token) > 2:  # Only use tokens with sufficient length
                    conditions.append(f"{field} LIKE ?")
                    params.append(f"%{token}%")
        
        if conditions:
            where_clause = " OR ".join(conditions)
            sql = f"""
                SELECT * FROM {collection_name} 
                WHERE {where_clause}
                LIMIT ?
            """
            params.append(self.max_results)
            
            if self.verbose:
                logger.info("Generated generic search query:")
                logger.info(f"SQL: {sql}")
                logger.info(f"Parameters: {params}")
                logger.info(f"Search fields: {search_fields}")
            
            return {
                "sql": sql,
                "params": params,
                "fields": search_fields
            }
            
        # Final fallback
        if self.verbose:
            logger.info("No valid search conditions found, using fallback query")
        
        return {
            "sql": f"SELECT * FROM {collection_name} LIMIT ?",
            "params": [self.max_results],
            "fields": self.default_search_fields
        }

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
            query: The user's query
            api_key: Optional API key for accessing the collection
            collection_name: Optional explicit collection name
            **kwargs: Additional parameters
            
        Returns:
            A list of context items filtered by relevance
        """
        try:
            # Resolve the collection
            if collection_name:
                await self.set_collection(collection_name)
            elif api_key:
                collection = await self._resolve_collection(api_key)
                await self.set_collection(collection)
            elif not self.collection:
                raise ValueError("No collection specified")
            
            # Ensure we have a connection
            if not self.connection:
                self._connection_loader.get_instance()
            
            debug_mode = self.verbose
            
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
                # Get search query from domain-specific method
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
                
                # Process if score exceeds threshold
                if combined_score >= self.relevance_threshold:
                    # Determine document content
                    raw_doc = ""
                    if "question" in row and "answer" in row:
                        raw_doc = f"Question: {row['question']}\nAnswer: {row['answer']}"
                    elif "content" in row:
                        raw_doc = row["content"]
                    elif compare_field:
                        raw_doc = compare_value
                    else:
                        continue  # Skip if no content found
                    
                    # Use domain adapter to format document
                    if self.domain_adapter and hasattr(self.domain_adapter, 'format_document'):
                        # Convert row to regular dict for metadata
                        metadata = dict(row)
                        
                        # Format the document using the domain adapter
                        context_item = self.domain_adapter.format_document(raw_doc, metadata)
                        
                        # Add confidence score
                        context_item["confidence"] = combined_score
                        
                        # Add metadata about the source
                        if "metadata" not in context_item:
                            context_item["metadata"] = {}
                        
                        context_item["metadata"]["source"] = self._get_datasource_name()
                        context_item["metadata"]["collection"] = self.collection
                        context_item["metadata"]["similarity"] = similarity
                        context_item["metadata"]["token_match_ratio"] = token_match_ratio
                        
                        results.append(context_item)
            
            # Apply domain-specific filtering if available
            if self.domain_adapter and hasattr(self.domain_adapter, 'apply_domain_specific_filtering'):
                results = self.domain_adapter.apply_domain_specific_filtering(results, query)
            
            # Sort by confidence and limit results
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


# Register the retriever with the factory
RetrieverFactory.register_retriever('sqlite', SqliteRetriever)