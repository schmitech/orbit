"""
Abstract vector database retriever implementation.

This provides the foundation for all vector database implementations,
similar to how AbstractSQLRetriever works for SQL databases.
"""

from typing import List, Dict, Any, Optional
from abc import abstractmethod
import logging
from .base_retriever import BaseRetriever

logger = logging.getLogger(__name__)

class AbstractVectorRetriever(BaseRetriever):
    """
    Abstract base class for vector database retrievers.

    This class provides common vector database functionality while leaving
    database-specific implementation details to concrete subclasses.

    Uses the datasource registry pattern - retrievers receive a datasource instance
    and lazily initialize the connection when needed.
    """

    def __init__(self,
                config: Dict[str, Any],
                embeddings: Optional[Any] = None,
                datasource: Any = None,
                domain_adapter=None,
                **kwargs):
        """
        Initialize the abstract vector retriever.

        Args:
            config: Configuration dictionary containing retriever settings
            embeddings: Embeddings service or model
            datasource: Datasource instance from the registry
            domain_adapter: Optional domain adapter for document handling
            **kwargs: Additional arguments
        """
        super().__init__(config=config, domain_adapter=domain_adapter, **kwargs)

        # Ensure logger is initialized (in case parent didn't do it)
        if not hasattr(self, 'logger'):
            self.logger = logging.getLogger(self.__class__.__name__)

        # Store datasource reference from registry
        self._datasource = datasource
        self._datasource_initialized = False

        # Store embeddings
        self.embeddings = embeddings

        # Vector DB specific settings
        self.relevance_threshold = self.datasource_config.get('relevance_threshold', 0.5)
        self.distance_scaling_factor = self.datasource_config.get('distance_scaling_factor', 200.0)

        # Flag for new embedding service
        self.using_new_embedding_service = False

        # Vector database client will be obtained from datasource when needed
        self._vector_client = None
    
    @property
    def vector_client(self) -> Any:
        """
        Get the vector database client from the datasource.
        Lazily initializes the datasource if needed.

        Returns:
            Vector database client from the datasource
        """
        if self._vector_client is None and self._datasource is not None:
            # Get client from datasource
            self._vector_client = self._datasource.get_client()
        return self._vector_client

    async def _ensure_datasource_initialized(self) -> None:
        """
        Ensure the datasource is initialized before use.
        This method lazily initializes the datasource on first use.
        """
        if not self._datasource_initialized and self._datasource is not None:
            if not self._datasource.is_initialized:
                await self._datasource.initialize()
            self._datasource_initialized = True
            if self.verbose:
                logger.info(f"Datasource initialized for {self._get_datasource_name()}")

    async def initialize(self) -> None:
        """Initialize required services including embeddings and datasource."""
        # Initialize base services first
        await super().initialize()

        # Check if embedding is enabled
        embedding_enabled = self.config.get('embedding', {}).get('enabled', True)

        # Skip initialization if embeddings are disabled
        if not embedding_enabled:
            self.embeddings = None
            return

        # Initialize embeddings if not provided in constructor
        if self.embeddings is None:
            await self._initialize_embeddings()

        # Initialize datasource lazily (will happen on first use)
        # We don't initialize here to support lazy loading
    
    async def _initialize_embeddings(self) -> None:
        """Initialize the embedding service or model."""
        embedding_provider = self.config.get('embedding', {}).get('provider')
        
        # Use new embedding service architecture if specified
        if embedding_provider and 'embeddings' in self.config:
            from embeddings.base import EmbeddingServiceFactory
            self.embeddings = EmbeddingServiceFactory.create_embedding_service(
                self.config, embedding_provider)
            # Only initialize if not already initialized (singleton may be pre-initialized)
            if not self.embeddings.initialized:
                await self.embeddings.initialize()
            else:
                self.logger.debug(f"Embedding service already initialized, skipping initialization")
            self.using_new_embedding_service = True
        else:
            # Fall back to legacy Ollama embeddings
            from langchain_ollama import OllamaEmbeddings
            ollama_conf = self.config.get('ollama', {})
            if not ollama_conf and 'inference' in self.config and 'ollama' in self.config['inference']:
                # Handle new config structure
                ollama_conf = self.config.get('inference', {}).get('ollama', {})
                
            self.embeddings = OllamaEmbeddings(
                model=ollama_conf.get('embed_model', 'nomic-embed-text'),
                base_url=ollama_conf.get('base_url', 'http://localhost:11434')
            )
            self.using_new_embedding_service = False
    
    async def close(self) -> None:
        """Close any open services including embedding service and datasource."""
        # Close parent services
        await super().close()

        # Close embedding service if using new architecture
        if self.using_new_embedding_service and self.embeddings:
            await self.embeddings.close()

        # Close datasource
        if self._datasource is not None and self._datasource.is_initialized:
            await self._datasource.close()
            self._datasource_initialized = False
            self._vector_client = None
            if self.verbose:
                logger.info(f"Datasource closed for {self._get_datasource_name()}")
    
    async def embed_query(self, query: str) -> List[float]:
        """
        Generate an embedding for a query using the appropriate embedding service.
        
        Args:
            query: The query to embed
            
        Returns:
            A list of floats representing the embedding vector
            
        Raises:
            ValueError: If embeddings are not available
        """
        if not self.embeddings:
            raise ValueError("Embeddings are disabled or not initialized")
            
        if self.using_new_embedding_service:
            # Use the new embedding service API
            return await self.embeddings.embed_query(query)
        else:
            # Use the legacy Ollama embeddings
            # For langchain OllamaEmbeddings, embed_query is also a coroutine 
            # that needs to be awaited
            return await self.embeddings.embed_query(query)
    
    def format_document(self, doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format document using domain adapter if available.
        This provides compatibility with domain adapter pattern.
        
        Args:
            doc: The document text
            metadata: The document metadata
            
        Returns:
            A formatted context item
        """
        if self.domain_adapter and hasattr(self.domain_adapter, 'format_document'):
            return self.domain_adapter.format_document(doc, metadata)
        
        # Fall back to basic formatting if no adapter
        return {
            "raw_document": doc,
            "metadata": metadata.copy(),
            "content": doc
        }
    
    def apply_domain_filtering(self, context_items: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """
        Apply domain-specific filtering if domain adapter is available.
        Otherwise return items as-is.
        
        Args:
            context_items: List of context items to filter/rerank
            query: The original query
            
        Returns:
            Filtered/reranked list of context items
        """
        if self.domain_adapter and hasattr(self.domain_adapter, 'apply_domain_filtering'):
            return self.domain_adapter.apply_domain_filtering(context_items, query)
        
        return context_items
    
    def calculate_similarity_from_distance(self, distance: float) -> float:
        """
        Convert distance to similarity score.
        Different vector databases use different distance metrics.
        
        Args:
            distance: Distance value from vector database
            
        Returns:
            Similarity score between 0 and 1
        """
        # Default sigmoid-like conversion that works well for L2 distance
        # Override in subclasses for database-specific distance metrics
        return 1.0 / (1.0 + (distance / self.distance_scaling_factor))
    
    # Abstract methods that concrete implementations must provide
    @abstractmethod
    async def vector_search(self, query_embedding: List[float], top_k: int) -> List[Dict[str, Any]]:
        """
        Perform vector similarity search.
        
        Args:
            query_embedding: The query embedding vector
            top_k: Number of results to return
            
        Returns:
            List of search results with documents, metadata, and distances/scores
        """
        raise NotImplementedError("This method should be implemented by specific vector database implementations")
    
    @abstractmethod
    async def set_collection(self, collection_name: str) -> None:
        """
        Set the current collection for retrieval.
        
        Args:
            collection_name: Name of the collection to use
        """
        raise NotImplementedError("This method should be implemented by specific vector database implementations")
    
    @abstractmethod
    async def initialize_client(self) -> None:
        """
        Initialize the vector database client/connection.
        This method must be implemented by specific vector database providers.
        """
        raise NotImplementedError("Subclasses must implement initialize_client()")
    
    @abstractmethod
    async def close_client(self) -> None:
        """
        Close the vector database client/connection.
        This method must be implemented by specific vector database providers.
        """
        raise NotImplementedError("Subclasses must implement close_client()")
    
    # Common implementation methods
    async def get_relevant_context(self,
                           query: str,
                           api_key: Optional[str] = None,
                           collection_name: Optional[str] = None,
                           **kwargs) -> List[Dict[str, Any]]:
        """
        Retrieve and filter relevant context from the vector database.

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

            # Ensure datasource is initialized
            await self._ensure_datasource_initialized()

            # Check for embeddings
            if not self.embeddings:
                logger.warning("Embeddings are disabled, no vector search can be performed")
                return []
            
            # 1. Generate embedding for query
            query_embedding = await self.embed_query(query)
            
            if not query_embedding or len(query_embedding) == 0:
                logger.error("Received empty embedding, cannot perform vector search")
                return []
            
            if debug_mode:
                logger.info(f"Generated {len(query_embedding)}-dimensional embedding for query")
            
            # 2. Perform vector search
            search_results = await self.vector_search(query_embedding, self.max_results)
            
            if debug_mode:
                logger.info(f"Vector search returned {len(search_results)} results")
            
            # 3. Process and filter results
            context_items = []
            
            for result in search_results:
                # Extract data from result
                doc = result.get('document', '')
                metadata = result.get('metadata', {})
                distance = result.get('distance', float('inf'))
                score = result.get('score')  # Some DBs return similarity score directly
                
                # Calculate similarity score
                if score is not None:
                    # Use provided score if available
                    similarity = float(score)
                else:
                    # Convert distance to similarity
                    similarity = self.calculate_similarity_from_distance(distance)
                
                # Only include results that meet threshold
                if similarity >= self.confidence_threshold:
                    # Format document using domain adapter
                    item = self.format_document(doc, metadata)
                    item["confidence"] = similarity
                    item["metadata"]["source"] = self._get_datasource_name()
                    item["metadata"]["collection"] = self.collection
                    item["metadata"]["similarity"] = similarity
                    
                    if distance != float('inf'):
                        item["metadata"]["distance"] = distance
                    
                    context_items.append(item)
                    
                    if debug_mode:
                        logger.info(f"Accepted result with confidence: {similarity:.4f}")
                else:
                    if debug_mode:
                        logger.info(f"Rejected result with confidence: {similarity:.4f} (threshold: {self.confidence_threshold})")
            
            # 4. Sort by confidence
            context_items = sorted(context_items, key=lambda x: x.get("confidence", 0), reverse=True)
            
            # 5. Apply domain-specific filtering
            context_items = self.apply_domain_filtering(context_items, query)
            
            # 6. Apply final limit
            context_items = context_items[:self.return_results]
            
            if debug_mode:
                logger.info(f"Retrieved {len(context_items)} relevant context items")
                
            return context_items
                
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            return [] 