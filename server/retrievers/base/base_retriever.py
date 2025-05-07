"""
Enhanced base retriever interface with domain adaptation support
"""

from abc import ABC, abstractmethod
import logging
import traceback
from typing import Dict, Any, List, Optional, Type, Tuple, Union
import importlib
from fastapi import HTTPException
from utils.lazy_loader import AdapterRegistry

# Configure logging
logger = logging.getLogger(__name__)

class BaseRetriever(ABC):
    """Enhanced base abstract class that all retriever implementations should extend"""
    
    def __init__(self, 
                config: Dict[str, Any],
                domain_adapter=None,
                datasource_config: Optional[Dict[str, Any]] = None,
                **kwargs):
        """
        Initialize BaseRetriever with common configuration.
        
        Args:
            config: Configuration dictionary
            domain_adapter: Optional domain adapter instance
            datasource_config: Optional datasource-specific configuration
        """
        if not config:
            raise ValueError("Config is required for retriever initialization")
            
        self.config = config
        
        # Use provided datasource config or get it from the config
        self.datasource_config = datasource_config or self._get_datasource_config()
        
        # Common parameters across retrievers
        self.confidence_threshold = self.datasource_config.get('confidence_threshold', 0.7)
        self.verbose = config.get('general', {}).get('verbose', False)
        self.max_results = self.datasource_config.get('max_results', 10)
        self.return_results = self.datasource_config.get('return_results', 3)
        self.collection = self.datasource_config.get('collection')
        
        # Set up domain adapter - either use provided one or create from config
        self.domain_adapter = self._initialize_domain_adapter(domain_adapter)
        
        # Initialize API key service (will be done in initialize())
        self.api_key_service = None
        
        # Flag to track initialization
        self.initialized = False
    
    def _initialize_domain_adapter(self, domain_adapter):
        """Initialize domain adapter from config or use provided one"""
        if domain_adapter:
            return domain_adapter
            
        # Try to get adapter type from config
        adapter_type = self.datasource_config.get('domain_adapter', 'qa')
        
        # Import the adapter factory
        try:
            from retrievers.adapters.domain_adapters import DocumentAdapterFactory
            # Get adapter params from config
            adapter_params = self.datasource_config.get('adapter_params', {})
            
            # Add confidence threshold
            if 'confidence_threshold' not in adapter_params:
                adapter_params['confidence_threshold'] = self.confidence_threshold
                
            return DocumentAdapterFactory.create_adapter(adapter_type, **adapter_params)
        except (ImportError, ValueError) as e:
            logger.warning(f"Failed to create domain adapter: {str(e)}")
            logger.warning("Using default QA adapter")
            
            # Create a minimal adapter
            from retrievers.adapters.domain_adapters import QADocumentAdapter
            return QADocumentAdapter(confidence_threshold=self.confidence_threshold)
    
    def _get_datasource_config(self) -> Dict[str, Any]:
        """
        Get datasource-specific config, supporting both old and new config structures.
        
        Returns:
            Dict containing datasource configuration
        """
        # Must be implemented by subclasses to get their specific config section
        datasource_name = self._get_datasource_name()
        
        # Try new config structure first
        if 'datasources' in self.config and datasource_name in self.config['datasources']:
            return self.config['datasources'][datasource_name]
        
        # Fall back to old config structure
        if datasource_name in self.config:
            return self.config[datasource_name]
            
        # Return empty dict if no config found
        return {}
    
    @abstractmethod
    def _get_datasource_name(self) -> str:
        """Return the name of this datasource for config lookup"""
        pass
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize required services and connections."""
        # Import here to avoid circular imports
        from services.api_key_service import ApiKeyService
        self.api_key_service = ApiKeyService(self.config)
        await self.api_key_service.initialize()
        self.initialized = True
        
    @abstractmethod
    async def close(self) -> None:
        """Close any open services and connections."""
        if self.api_key_service:
            await self.api_key_service.close()
    
    async def _resolve_collection(self, api_key: Optional[str] = None, collection_name: Optional[str] = None) -> str:
        """
        Determine and set the appropriate collection.
        
        Priority:
          1. If an API key is provided, validate it and use its collection.
          2. If a collection name is provided directly, use it.
          3. If none is provided, try the default from config.
        
        Returns:
            The resolved collection name to use
            
        Raises:
            HTTPException: If no valid collection can be determined.
        """
        if not self.api_key_service:
            raise ValueError("API key service not initialized")
            
        if api_key:
            is_valid, resolved_collection_name = await self.api_key_service.validate_api_key(api_key)
            if not is_valid:
                raise ValueError("Invalid API key")
            if resolved_collection_name:
                return resolved_collection_name
        elif collection_name:
            return collection_name

        # Fallback to the default collection
        if self.collection:
            return self.collection
            
        # No collection available
        error_msg = ("No collection available. Ensure a default collection is configured "
                     "or a valid API key is provided.")
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)
    
    @abstractmethod
    async def set_collection(self, collection_name: str) -> None:
        """
        Set the current collection for retrieval.
        
        Args:
            collection_name: Name of the collection to use
        """
        pass
        
    def get_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        """
        Extract a direct answer from context if available.
        
        Args:
            context: List of context items
            
        Returns:
            A direct answer if found, otherwise None
        """
        # Use the domain adapter to extract a direct answer
        return self.domain_adapter.extract_direct_answer(context)

    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format document using the domain adapter.
        
        Args:
            raw_doc: Raw document text
            metadata: Document metadata
            
        Returns:
            Formatted document
        """
        return self.domain_adapter.format_document(raw_doc, metadata)
        
    def apply_domain_filtering(self, context_items: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """
        Apply domain-specific filtering to results.
        
        Args:
            context_items: List of context items
            query: Original query
            
        Returns:
            Filtered context items
        """
        return self.domain_adapter.apply_domain_specific_filtering(context_items, query)

    @abstractmethod
    async def get_relevant_context(self, 
                                  query: str, 
                                  api_key: Optional[str] = None,
                                  collection_name: Optional[str] = None,
                                  **kwargs) -> List[Dict[str, Any]]:
        """
        Retrieve relevant context for a query.
        
        Args:
            query: The user's query
            api_key: Optional API key for accessing resources
            collection_name: Optional collection/database/index name
            **kwargs: Additional parameters specific to each retriever implementation
            
        Returns:
            A list of context items filtered by relevance
        """
        try:
            # Check initialization status
            if not self.initialized:
                await self.initialize()
            
            # Set debug mode if verbose
            debug_mode = self.verbose
            
            if debug_mode:
                logger.info(f"=== Starting retrieval for query: '{query}' ===")
                logger.info(f"API Key: {'Provided' if api_key else 'None'}")
                logger.info(f"Collection name: {collection_name or 'Not specified'}")
                logger.info(f"Domain adapter: {type(self.domain_adapter).__name__}")
            
            # Resolve collection (subclasses should use this value)
            resolved_collection = await self._resolve_collection(api_key, collection_name)
            
            if debug_mode:
                logger.info(f"Resolved collection: {resolved_collection}")
                
            # Set the collection
            await self.set_collection(resolved_collection)
            
            # Subclasses should implement the actual retrieval logic
            return []
            
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            # Print more detailed error information
            logger.error(traceback.format_exc())
            return []


class VectorDBRetriever(BaseRetriever):
    """Abstract base class for vector database retrievers that use embeddings"""
    
    def __init__(self, 
                config: Dict[str, Any],
                embeddings: Optional[Any] = None,
                domain_adapter=None,
                **kwargs):
        """
        Initialize VectorDBRetriever with common vector DB configuration.
        
        Args:
            config: Configuration dictionary
            embeddings: Embeddings service or model
            domain_adapter: Optional domain adapter
        """
        super().__init__(config=config, domain_adapter=domain_adapter, **kwargs)
        
        # Store embeddings
        self.embeddings = embeddings
        
        # Vector DB specific settings
        self.relevance_threshold = self.datasource_config.get('relevance_threshold', 0.5)
        
        # Flag for new embedding service
        self.using_new_embedding_service = False
    
    async def initialize(self) -> None:
        """Initialize required services including embeddings."""
        # Initialize base services first
        await super().initialize()
        
        # Check if embedding is enabled
        embedding_enabled = self.config.get('embedding', {}).get('enabled', True)
        
        # Skip initialization if embeddings are disabled
        if not embedding_enabled:
            logger.info("Embedding services are disabled, retriever will operate in limited mode")
            self.embeddings = None
            return
        
        # Initialize embeddings if not provided in constructor
        if self.embeddings is None:
            await self._initialize_embeddings()
    
    async def _initialize_embeddings(self) -> None:
        """Initialize the embedding service or model."""
        embedding_provider = self.config.get('embedding', {}).get('provider')
        
        # Use new embedding service architecture if specified
        if embedding_provider and 'embeddings' in self.config:
            from embeddings.base import EmbeddingServiceFactory
            self.embeddings = EmbeddingServiceFactory.create_embedding_service(
                self.config, embedding_provider)
            await self.embeddings.initialize()
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
        
        if self.verbose:
            logger.info(f"Initialized embeddings: {type(self.embeddings).__name__}")
            logger.info(f"Using new embedding service: {self.using_new_embedding_service}")
    
    async def close(self) -> None:
        """Close any open services including embedding service."""
        # Close parent services
        await super().close()
        
        # Close embedding service if using new architecture
        if self.using_new_embedding_service and self.embeddings:
            await self.embeddings.close()
    
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


class SQLRetriever(BaseRetriever):
    """Abstract base class for SQL-based retrievers that use token/text matching"""
    
    def __init__(self, 
                config: Dict[str, Any],
                domain_adapter=None,
                **kwargs):
        """
        Initialize SQLRetriever with common SQL DB configuration.
        
        Args:
            config: Configuration dictionary
            domain_adapter: Optional domain adapter
        """
        super().__init__(config=config, domain_adapter=domain_adapter, **kwargs)
        
        # SQL DB specific settings
        self.relevance_threshold = self.datasource_config.get('relevance_threshold', 0.5)
        self.connection = kwargs.get('connection', None)
        
    @abstractmethod
    def _tokenize_text(self, text: str) -> List[str]:
        """
        Tokenize text for better matching.
        
        Args:
            text: Text to tokenize
            
        Returns:
            List of tokens
        """
        pass
        
    @abstractmethod
    def _calculate_similarity(self, query: str, text: str) -> float:
        """
        Calculate similarity between query and text.
        
        Args:
            query: The user's query
            text: The text to compare against
            
        Returns:
            Similarity score between 0 and 1
        """
        pass
    
class RetrieverFactory:
    """
    Factory for creating retriever instances with lazy loading support.
    """
    
    _registry = AdapterRegistry()
    _registered_retrievers: Dict[str, Type[BaseRetriever]] = {}
    
    @classmethod
    def register_retriever(cls, retriever_type: str, retriever_class: Type[BaseRetriever]):
        """
        Register a retriever class with the factory.
        
        Args:
            retriever_type: The type identifier for this retriever
            retriever_class: The retriever class to register
        """
        cls._registered_retrievers[retriever_type] = retriever_class
        logger.info(f"Registered retriever type: {retriever_type}")
    
    @classmethod
    def create_retriever(cls, retriever_type: str, **kwargs) -> BaseRetriever:
        """
        Create a retriever instance by type.
        
        Args:
            retriever_type: The type of retriever to create
            **kwargs: Arguments to pass to the retriever constructor
            
        Returns:
            An instance of the requested retriever
            
        Raises:
            ValueError: If the retriever type is not registered
        """
        # Try to get the retriever from registry first (for lazy loaded retrievers)
        if cls._registry.is_registered(retriever_type):
            return cls._registry.get(retriever_type)
        
        # Fall back to direct instantiation if not in registry
        if retriever_type not in cls._registered_retrievers:
            valid_types = list(cls._registered_retrievers.keys())
            logger.error(f"Unknown retriever type: {retriever_type}. Valid types: {valid_types}")
            raise ValueError(f"Unknown retriever type: {retriever_type}. Valid types: {valid_types}")
        
        retriever_class = cls._registered_retrievers[retriever_type]
        logger.info(f"Creating retriever of type: {retriever_type}")
        return retriever_class(**kwargs)
    
    @classmethod
    def register_lazy_retriever(cls, retriever_type: str, factory_func):
        """
        Register a factory function for lazy loading a retriever.
        
        Args:
            retriever_type: The type identifier for this retriever
            factory_func: Function that creates the retriever instance when needed
        """
        cls._registry.register(retriever_type, factory_func)
        logger.info(f"Registered lazy-loaded retriever type: {retriever_type}")
    