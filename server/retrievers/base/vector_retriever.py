"""
Vector database retriever implementation.
"""

from typing import List, Dict, Any, Optional
from .base_retriever import BaseRetriever

class VectorDBRetriever(BaseRetriever):
    """
    A retriever that uses vector similarity search to find relevant documents.
    """
    
    def __init__(self, 
                config: Dict[str, Any],
                embeddings: Optional[Any] = None,
                domain_adapter=None,
                **kwargs):
        """
        Initialize the vector database retriever.
        
        Args:
            config: Configuration dictionary containing retriever settings
            embeddings: Embeddings service or model
            domain_adapter: Optional domain adapter for document handling
            **kwargs: Additional arguments
        """
        super().__init__(config=config, domain_adapter=domain_adapter, **kwargs)
        
        # Store embeddings
        self.embeddings = embeddings
        
        # Vector DB specific settings
        self.relevance_threshold = self.datasource_config.get('relevance_threshold', 0.5)
        
        # Flag for new embedding service
        self.using_new_embedding_service = False
        
        # Store vector database connection
        self.vector_db = None  # Will be initialized by implementations
    
    async def initialize(self) -> None:
        """Initialize required services including embeddings."""
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
    
    def search(self, query: str, top_k: int = 5, **kwargs) -> List[Dict[str, Any]]:
        """
        Search for relevant documents using vector similarity.
        
        Args:
            query: The search query
            top_k: Number of results to return
            **kwargs: Additional search parameters
            
        Returns:
            List of relevant documents with their metadata
        """
        raise NotImplementedError("This method should be implemented by specific vector database implementations")
    
    def add_documents(self, documents: List[Dict[str, Any]], **kwargs) -> None:
        """
        Add documents to the vector database.
        
        Args:
            documents: List of documents to add
            **kwargs: Additional parameters for document addition
        """
        raise NotImplementedError("This method should be implemented by specific vector database implementations")
    
    def delete_documents(self, document_ids: List[str], **kwargs) -> None:
        """
        Delete documents from the vector database.
        
        Args:
            document_ids: List of document IDs to delete
            **kwargs: Additional parameters for document deletion
        """
        raise NotImplementedError("This method should be implemented by specific vector database implementations") 