"""
Enhanced SQL retriever abstract class with domain adapter support
"""

import logging
import string
import traceback
from abc import abstractmethod
from typing import Dict, Any, List, Optional
from difflib import SequenceMatcher

from .base_retriever import BaseRetriever

# Configure logging
logger = logging.getLogger(__name__)

class AbstractSQLRetriever(BaseRetriever):
    """
    Abstract base class for SQL-based retrievers.

    This class provides common SQL functionality while leaving database-specific
    implementation details to concrete subclasses.

    Uses the datasource registry pattern - retrievers receive a datasource instance
    and lazily initialize the connection when needed.
    """

    def __init__(self,
                config: Dict[str, Any],
                datasource: Any = None,
                domain_adapter=None,
                **kwargs):
        """
        Initialize SQL retriever with common configuration.

        Args:
            config: Configuration dictionary
            datasource: Datasource instance from the registry
            domain_adapter: Optional domain adapter for document handling
            **kwargs: Additional keyword arguments
        """
        super().__init__(config=config, domain_adapter=domain_adapter, **kwargs)

        # Store datasource reference from registry
        self._datasource = datasource
        self._datasource_initialized = False

        # SQL-specific settings with sensible defaults
        self.relevance_threshold = self.datasource_config.get('relevance_threshold', 0.5)
        self.max_results = self.datasource_config.get('max_results', 10)
        self.return_results = self.datasource_config.get('return_results', 3)

        # Connection will be obtained from datasource when needed
        self._connection = None
        
        # Adapter granularity strategy settings
        self.query_timeout = self.datasource_config.get('query_timeout', 5000)  # Default 5 seconds
        self.approved_by_admin = self.datasource_config.get('approved_by_admin', False)
        self.security_filter = self.datasource_config.get('security_filter', None)
        self.allowed_columns = self.datasource_config.get('allowed_columns', [])
        
        # Query monitoring and safety
        self.enable_query_monitoring = self.datasource_config.get('enable_query_monitoring', True)
        self.max_query_complexity = self.datasource_config.get('max_query_complexity', 'medium')
        
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

    @property
    def connection(self) -> Any:
        """
        Get the database connection from the datasource.
        Lazily initializes the datasource if needed.

        Returns:
            Database connection/client from the datasource
        """
        if self._connection is None and self._datasource is not None:
            # Get client from datasource
            self._connection = self._datasource.get_client()
        return self._connection

    async def _ensure_datasource_initialized(self) -> None:
        """
        Ensure the datasource is initialized before use.
        This method lazily initializes the datasource on first use.
        """
        if not self._datasource_initialized and self._datasource is not None:
            if not self._datasource.is_initialized:
                await self._datasource.initialize()
            self._datasource_initialized = True
            logger.debug(f"Datasource initialized for {self._get_datasource_name()}")
    

        
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

    async def initialize(self) -> None:
        """
        Initialize required services and verify database structure.
        Default implementation initializes the datasource.
        Can be overridden by subclasses for additional initialization.
        """
        await self._ensure_datasource_initialized()

    async def close(self) -> None:
        """
        Close the datasource connection and clean up resources.
        """
        if self._datasource is not None and self._datasource.is_initialized:
            await self._datasource.close()
            self._datasource_initialized = False
            self._connection = None
            logger.debug(f"Datasource closed for {self._get_datasource_name()}")
    

    
    def _apply_safety_measures(self, search_config: Dict[str, Any], 
                              query: str, collection_name: str) -> Dict[str, Any]:
        """
        Apply safety measures to search configuration.
        
        Args:
            search_config: Original search configuration
            query: User query
            collection_name: Table name
            
        Returns:
            Modified search configuration with safety measures
        """
        sql_query = search_config.get("sql", "")
        
        # Apply security filters if configured
        if self.security_filter:
            sql_query = self._apply_security_filter(sql_query, collection_name)
            search_config["sql"] = sql_query
        
        # Apply column restrictions if configured
        if self.allowed_columns:
            sql_query = self._apply_column_restrictions(sql_query, collection_name)
            search_config["sql"] = sql_query
        
        # Ensure query timeout is applied
        if "timeout" not in search_config:
            search_config["timeout"] = self.query_timeout
        
        return search_config
    
    def _apply_security_filter(self, sql_query: str, collection_name: str) -> str:
        """Apply security filter to SQL query."""
        if not self.security_filter:
            return sql_query
        
        # If query already has WHERE clause, add AND condition
        if "WHERE" in sql_query.upper():
            return sql_query.replace("WHERE", f"WHERE {self.security_filter} AND", 1)
        else:
            # Add WHERE clause before ORDER BY or LIMIT
            if "ORDER BY" in sql_query.upper():
                return sql_query.replace("ORDER BY", f"WHERE {self.security_filter} ORDER BY", 1)
            elif "LIMIT" in sql_query.upper():
                return sql_query.replace("LIMIT", f"WHERE {self.security_filter} LIMIT", 1)
            else:
                return f"{sql_query} WHERE {self.security_filter}"
    
    def _apply_column_restrictions(self, sql_query: str, collection_name: str) -> str:
        """Apply column restrictions to SQL query."""
        if not self.allowed_columns:
            return sql_query
        
        # Replace SELECT * with specific columns
        if "SELECT *" in sql_query:
            allowed_cols = ", ".join(self.allowed_columns)
            return sql_query.replace("SELECT *", f"SELECT {allowed_cols}", 1)
        
        return sql_query
    
    def _monitor_query_execution(self, sql_query: str, execution_time: float, row_count: int):
        """Monitor query execution for performance and security."""
        if not self.enable_query_monitoring:
            return
            
        # Log slow queries
        if execution_time > 5.0:  # 5 seconds
            logger.warning(f"Slow query detected: {sql_query} ({execution_time:.2f}s)")
        
        # Log large result sets
        if row_count > 1000:
            logger.warning(f"Large result set: {sql_query} ({row_count} rows)")
        
        # Log successful query with basic stats
        logger.debug(f"Query executed: {execution_time:.2f}s, {row_count} rows")
    
    def _get_search_query(self, query: str, collection_name: str) -> Dict[str, Any]:
        """
        Get domain-specific SQL search query with granularity strategy validation.
        Can be overridden by subclasses for database-specific optimization.
        
        Args:
            query: User query
            collection_name: Table name
            
        Returns:
            Dict with SQL query, parameters, and fields
        """
        # Use domain adapter's SQL query generator if available
        if hasattr(self.domain_adapter, 'get_search_conditions'):
            search_config = self.domain_adapter.get_search_conditions(query, collection_name)
        else:
            # Default simple search
            search_config = {
                "sql": f"SELECT * FROM {collection_name} LIMIT ?",
                "params": [self.max_results],
                "fields": self.default_search_fields
            }
        
        # Apply safety measures
        if self.enable_query_monitoring:
            search_config = self._apply_safety_measures(search_config, query, collection_name)
        
        return search_config
    
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

            # Ensure datasource is initialized
            await self._ensure_datasource_initialized()

            if not self.connection:
                error_msg = "Database connection not initialized"
                logger.error(error_msg)
                raise ValueError(error_msg)

            # 1. Get domain-specific search query
            search_config = self._get_search_query(query, self.collection)
            sql_query = search_config["sql"]
            params = search_config.get("params", [])
            search_config.get("fields", self.default_search_fields)

            logger.debug(f"Search query: {sql_query}")
            logger.debug(f"Search params: {params}")
            
            # 2. Execute the query with timing and monitoring
            import time
            start_time = time.time()
            rows = await self.execute_query(sql_query, params)
            execution_time = time.time() - start_time
            
            # Monitor query execution
            self._monitor_query_execution(sql_query, execution_time, len(rows))

            logger.debug(f"Retrieved {len(rows)} initial rows from database")
            
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

            # Track original count before truncation
            original_count = len(results)
            was_truncated = original_count > self.return_results

            if was_truncated:
                logger.info(f"Truncating result set from {original_count} to {self.return_results} results based on return_results config")

            results = results[:self.return_results]

            # Add truncation metadata to all results
            for result in results:
                if "metadata" not in result:
                    result["metadata"] = {}
                result["metadata"]["total_available"] = original_count
                result["metadata"]["truncated"] = was_truncated
                result["metadata"]["result_count"] = len(results)

            logger.debug(f"Retrieved {len(results)} relevant context items" +
                      (f" (truncated from {original_count})" if was_truncated else ""))
            if results:
                logger.debug(f"Top confidence score: {results[0].get('confidence', 0)}")

            return results
                
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            logger.error(traceback.format_exc())
            return []


# For backward compatibility, keep the old class name as an alias
SQLRetriever = AbstractSQLRetriever