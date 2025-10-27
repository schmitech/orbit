"""
QA-specialized SQLite retriever that extends SQLiteRetriever.
Updated to work with the new BaseSQLDatabaseRetriever architecture.
"""

import logging
import traceback
from typing import Dict, Any, List, Optional
from ..relational.sqlite_retriever import SQLiteRetriever
from ...base.base_retriever import RetrieverFactory

# Configure logging
logger = logging.getLogger(__name__)

class QASSQLRetriever(SQLiteRetriever):
    """
    QA-specialized SQLite retriever that extends SQLiteRetriever.
    
    This implementation adds QA-specific functionality on top of the 
    database-agnostic SQLite retriever foundation.
    """

    def __init__(self,
                config: Dict[str, Any],
                domain_adapter=None,
                datasource: Any = None,
                **kwargs):
        """
        Initialize QA SQLite retriever.

        Args:
            config: Configuration dictionary containing SQL and general settings
            domain_adapter: Optional domain adapter for document handling
            datasource: Optional SQL connection
            **kwargs: Additional arguments
        """
        # Get QA-specific adapter config if available
        adapter_config = None
        
        # First try to get adapter config from the new direct method
        if 'adapter_config' in config:
            adapter_config = config.get('adapter_config', {})
        else:
            # Fallback to searching through adapters list (backward compatibility)
            for adapter in config.get('adapters', []):
                if (adapter.get('enabled', True) and
                    adapter.get('type') == 'retriever' and 
                    adapter.get('datasource') == 'sqlite' and 
                    adapter.get('adapter') == 'qa'):
                    adapter_config = adapter.get('config', {})
                    break
        
        # Call parent constructor (SQLiteRetriever)
        super().__init__(config=config, datasource=datasource, domain_adapter=domain_adapter, **kwargs)
        
        # QA-specific settings
        self.confidence_threshold = adapter_config.get('confidence_threshold', 0.3) if adapter_config else 0.3
        
        # Set the table/collection name from adapter config
        if adapter_config and adapter_config.get('table'):
            self.collection = adapter_config.get('table')
            if self.verbose:
                logger.info(f"QASSQLRetriever using table from adapter config: {self.collection}")
        
        # Flag to track if search_tokens table exists (QA-specific optimization)
        self.has_token_table = False
        
        # QA-specific search fields prioritization
        self.default_search_fields = ['id', 'question', 'answer', 'content', 'title']
        
        logger.info(f"QASSQLRetriever initialized with confidence_threshold={self.confidence_threshold}")

    def _get_datasource_name(self) -> str:
        """Return the name of this datasource for config lookup"""
        return 'sqlite'  # Still SQLite, but QA-specialized

    async def initialize(self) -> None:
        """Initialize QA-specific features on top of SQLite initialization."""
        # Call parent initialization first
        await super().initialize()
        
        # Check for QA-specific search_tokens table optimization
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='search_tokens'")
            if cursor.fetchone():
                self.has_token_table = True
                if self.verbose:
                    logger.info("Found 'search_tokens' table - will use for QA token-based search")
            else:
                self.has_token_table = False
                if self.verbose:
                    logger.info("'search_tokens' table not found - using QA string similarity only")
        except Exception as e:
            logger.warning(f"Error checking for search_tokens table: {str(e)}")
            self.has_token_table = False

    async def set_collection(self, collection_name: str) -> None:
        """
        Set the current collection with QA-specific field detection.
        
        Args:
            collection_name: Name of the table to use
        """
        if not collection_name:
            raise ValueError("Collection name cannot be empty")
            
        # Set the collection name
        self.collection = collection_name
        if self.verbose:
            logger.info(f"Switched to QA collection (table): {collection_name}")
            
        # Verify the table exists using parent method
        if self.connection:
            cursor = self.connection.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (collection_name,))
            if not cursor.fetchone():
                error_msg = f"Table '{collection_name}' not found in the database"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # QA-specific: Update default search fields based on table structure
            cursor.execute(f"PRAGMA table_info({collection_name})")
            columns = cursor.fetchall()
            field_names = [col[1] for col in columns]
            
            # Prioritize QA-specific field names
            qa_priority_fields = ["id", "question", "answer", "title", "content", "text", "body"]
            self.default_search_fields = [f for f in qa_priority_fields if f in field_names]
            
            # Add remaining text fields if we don't have enough
            if len(self.default_search_fields) < 3:
                for field in field_names:
                    if field not in self.default_search_fields:
                        self.default_search_fields.append(field)
            
            if self.verbose:
                logger.info(f"Using QA search fields: {self.default_search_fields}")

    def _get_search_query(self, query: str, collection_name: str) -> Dict[str, Any]:
        """
        Generate QA-optimized search query.
        
        Args:
            query: The user's query
            collection_name: The collection/table name
            
        Returns:
            Dict with SQL query, parameters, and fields
        """
        # Tokenize the query using parent method
        query_tokens = self._tokenize_text(query)
        
        if self.verbose:
            logger.info(f"Generating QA search query for: '{query}'")
            logger.info(f"Tokenized query: {query_tokens}")
            logger.info(f"Using collection: {collection_name}")
        
        if not query_tokens:
            # Fallback to basic query
            if self.verbose:
                logger.info("No valid tokens found, using basic query")
            return super()._get_search_query(query, collection_name)
        
        # QA-specific: For QA collections, search primarily in the question field
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
                
                # QA-specific: Use ORDER BY to sort by relevance based on how many tokens match
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
                    logger.info("Generated QA-specific search query")
                
                return {
                    "sql": sql,
                    "params": params,
                    "fields": self.default_search_fields
                }
        
        # Fallback to parent implementation for generic searches
        return super()._get_search_query(query, collection_name)

    async def _search_by_tokens(self, query_tokens: List[str]) -> List[Dict[str, Any]]:
        """
        QA-specific token-based search optimization.
        
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
            
            # Search for matching tokens - use question_id instead of doc_id to match actual schema
            sql = f"""
                SELECT question_id, COUNT(*) as match_count 
                FROM search_tokens 
                WHERE token IN ({placeholders})
                GROUP BY question_id 
                ORDER BY match_count DESC
                LIMIT ?
            """
            
            rows = await self.execute_query(sql, query_tokens + [self.max_results])
            
            results = []
            for row in rows:
                question_id = row["question_id"]  # Use question_id instead of doc_id
                match_count = row["match_count"]
                
                # Get the actual document
                doc_rows = await self.execute_query(
                    f"SELECT * FROM {self.collection} WHERE id = ?", 
                    [question_id]
                )
                
                if doc_rows:
                    # Add QA-specific token match info to the document
                    doc = doc_rows[0]
                    doc["match_count"] = match_count
                    doc["token_match_ratio"] = match_count / len(query_tokens) if query_tokens else 0
                    results.append(doc)
            
            return results
            
        except Exception as e:
            logger.error(f"Error in QA token-based search: {str(e)}")
            return []

    def _calculate_similarity(self, query: str, text: str) -> float:
        """
        QA-enhanced similarity calculation.
        
        Args:
            query: The user's query
            text: The text to compare against
            
        Returns:
            Similarity score between 0 and 1
        """
        if not query or not text:
            return 0.0
            
        # Use parent similarity calculation as base
        base_similarity = super()._calculate_similarity(query, text)
        
        # QA-specific enhancements
        query_lower = query.lower()
        text_lower = text.lower()
        
        # Boost exact matches and partial matches (QA-specific)
        if query_lower in text_lower:
            return 1.0
        elif any(word in text_lower for word in query_lower.split()):
            # Some words match, boost the score
            return min(1.0, base_similarity * 1.2)
        
        return base_similarity

    async def get_relevant_context(self, 
                                 query: str, 
                                 api_key: Optional[str] = None, 
                                 collection_name: Optional[str] = None,
                                 **kwargs) -> List[Dict[str, Any]]:
        """
        QA-specialized context retrieval with enhanced processing.
        
        Args:
            query: The user's query
            api_key: Optional API key for accessing the collection
            collection_name: Optional explicit collection name
            **kwargs: Additional parameters
            
        Returns:
            A list of QA context items filtered by relevance
        """
        try:
            # Resolve the collection with improved logic for adapter-based system
            if collection_name:
                # Explicit collection name provided
                await self.set_collection(collection_name)
            elif api_key:
                # Try to resolve from API key (legacy behavior)
                collection = await self._resolve_collection(api_key)
                await self.set_collection(collection)
            elif self.collection:
                # Use table from adapter config (new adapter system)
                if self.verbose:
                    logger.info(f"Using table from adapter config: {self.collection}")
                # No need to call set_collection since it's already set from config
            else:
                # No collection available - this should not happen in properly configured adapters
                raise ValueError("No collection specified and no table configured in adapter")
            
            debug_mode = self.verbose
            
            # Tokenize the query
            query_tokens = self._tokenize_text(query)
            if debug_mode:
                logger.info(f"QA tokenized query: {query_tokens}")
            
            # Try QA-specific token-based search first if available
            token_results = await self._search_by_tokens(query_tokens) if self.has_token_table else []
            
            if debug_mode:
                logger.info(f"QA token search found {len(token_results)} candidate documents")
            
            # If token search yielded results, use those, otherwise use regular SQL search
            if token_results:
                rows = token_results
            else:
                # Get QA-optimized search query
                search_config = self._get_search_query(query, self.collection)
                rows = await self.execute_query(search_config["sql"], search_config["params"])
            
            # QA-specific result processing
            results = []
            
            for row in rows:
                # QA-specific: Find the best field to calculate similarity against
                compare_field = None
                compare_value = None
                
                # QA priority: question > title > content > text > description
                qa_priority_fields = ["question", "title", "content", "text", "description"]
                for field in qa_priority_fields:
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
                
                # Calculate QA-enhanced similarity score
                similarity = self._calculate_similarity(query, compare_value)
                
                # Get token match ratio if available
                token_match_ratio = row.get("token_match_ratio", 0)
                
                # QA-specific: Calculate combined score with adjusted weights
                if token_match_ratio > 0:
                    combined_score = (0.6 * token_match_ratio) + (0.4 * similarity)
                else:
                    combined_score = similarity
                
                if self.verbose:
                    logger.info(f"QA Document similarity: {similarity:.4f}, token ratio: {token_match_ratio:.4f}, combined: {combined_score:.4f}")
                
                # Process if score exceeds QA-specific threshold
                if combined_score >= self.confidence_threshold:
                    # QA-specific: Determine document content format
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
                    context_item = self.format_document(raw_doc, dict(row))
                    
                    # Add QA-specific confidence score
                    context_item["confidence"] = combined_score
                    
                    # Add QA-specific metadata
                    if "metadata" not in context_item:
                        context_item["metadata"] = {}
                    
                    context_item["metadata"]["source"] = self._get_datasource_name()
                    context_item["metadata"]["collection"] = self.collection
                    context_item["metadata"]["similarity"] = similarity
                    context_item["metadata"]["token_match_ratio"] = token_match_ratio
                    context_item["metadata"]["qa_enhanced"] = True
                    
                    results.append(context_item)
            
            # Apply domain-specific filtering
            results = self.apply_domain_filtering(results, query)
            
            # Sort by confidence and limit results
            results.sort(key=lambda x: x.get("confidence", 0), reverse=True)
            results = results[:self.return_results]
            
            if debug_mode:
                logger.info(f"Retrieved {len(results)} QA-relevant context items")
                if results:
                    logger.info(f"Top QA confidence score: {results[0].get('confidence', 0)}")
            
            return results
                
        except Exception as e:
            logger.error(f"Error retrieving QA context: {str(e)}")
            logger.error(traceback.format_exc())
            return []

    async def _create_default_table_if_needed(self) -> None:
        """Create QA-specific default table if it doesn't exist."""
        if not self.connection:
            return
            
        cursor = self.connection.cursor()
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (self.collection,))
            if not cursor.fetchone():
                if self.verbose:
                    logger.info(f"Creating QA default table '{self.collection}'")
                
                # Create QA-specific table structure
                cursor.execute(f'''
                    CREATE TABLE IF NOT EXISTS {self.collection} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        question TEXT,
                        answer TEXT,
                        metadata TEXT
                    )
                ''')
                self.connection.commit()
                
                # Insert QA-specific sample data
                cursor.execute(f'''
                    INSERT INTO {self.collection} (question, answer, metadata)
                    VALUES (?, ?, ?)
                ''', (
                    "What is the purpose of this QA system?", 
                    "This system provides a flexible QA retrieval architecture with domain-specific adapters for question-answering scenarios.",
                    '{"source": "documentation", "type": "qa_overview"}'
                ))
                
                cursor.execute(f'''
                    INSERT INTO {self.collection} (question, answer, metadata)
                    VALUES (?, ?, ?)
                ''', (
                    "How do QA adapters work in this system?", 
                    "QA adapters provide question-answer specific document handling, optimizing the system for FAQ and knowledge base scenarios.",
                    '{"source": "documentation", "type": "qa_technical"}'
                ))
                
                self.connection.commit()
                
                if self.verbose:
                    logger.info(f"Created QA default table '{self.collection}' with sample data")
        except Exception as e:
            logger.warning(f"Could not create QA default table: {str(e)}")


# Register the QA-specialized retriever with the factory
RetrieverFactory.register_retriever('qa_sql', QASSQLRetriever)