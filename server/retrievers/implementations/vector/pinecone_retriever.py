"""
Pinecone implementation of the AbstractVectorRetriever interface
"""

import logging
from typing import Any, Optional
from fastapi import HTTPException

from ...base.abstract_vector_retriever import AbstractVectorRetriever
from ...base.base_retriever import RetrieverFactory
from utils.vector_utils import DIMENSION_MISMATCH_PATTERN

# Configure logging
logger = logging.getLogger(__name__)

class PineconeRetriever(AbstractVectorRetriever):
    """Pinecone implementation of the AbstractVectorRetriever interface"""

    def __init__(self, 
                config: dict[str, Any],
                embeddings: Optional[Any] = None,
                domain_adapter=None,
                **kwargs):
        """
        Initialize PineconeRetriever.
        
        Args:
            config: Configuration dictionary containing Pinecone and general settings
            embeddings: Optional embeddings service or model
            domain_adapter: Optional domain adapter for document handling
            **kwargs: Additional arguments
        """
        # Call the parent constructor first
        super().__init__(config=config, embeddings=embeddings, domain_adapter=domain_adapter, **kwargs)
        
        # Pinecone-specific settings
        self.api_key = self.datasource_config.get('api_key')
        self.environment = self.datasource_config.get('environment')
        self.host = self.datasource_config.get('host')
        
        # Store index and namespace
        self.index_name = None
        self.index = None
        self.namespace = self.datasource_config.get('namespace', '')
        
        # Pinecone client
        self.pinecone_client = None

    def _get_datasource_name(self) -> str:
        """Return the name of this datasource for config lookup"""
        return 'pinecone'

    async def initialize_client(self) -> None:
        """Initialize the Pinecone client."""
        try:
            from pinecone import Pinecone

            # Initialize Pinecone client with API key
            # The modern Pinecone client (v3+) uses the Pinecone class constructor
            init_kwargs = {'api_key': self.api_key}

            # Add host if provided (for specific index connections)
            if self.host:
                init_kwargs['host'] = self.host

            self.pinecone_client = Pinecone(**init_kwargs)

            logger.debug("Connected to Pinecone")

        except ImportError:
            error_msg = "pinecone package is required for Pinecone retriever. Install with: pip install pinecone>=3.0.0"
            logger.error(error_msg)
            raise ImportError(error_msg)
        except Exception as e:  # noqa: BLE001 - pinecone client boundary
            error_msg = f"Failed to initialize Pinecone client: {e!s}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    async def close_client(self) -> None:
        """Close the Pinecone client."""
        # Pinecone doesn't require explicit closure
        logger.debug("Pinecone client closed")

    async def set_collection(self, collection_name: str) -> None:
        """
        Set the current index for retrieval.
        In Pinecone, collections are called indexes.
        
        Args:
            collection_name: Name of the index to use
        """
        if not collection_name:
            raise ValueError("Index name cannot be empty")
            
        try:
            # Check if index exists using modern Pinecone API (v3+)
            indexes = self.pinecone_client.list_indexes()
            index_names = [idx.name for idx in indexes]

            if collection_name not in index_names:
                error_msg = f"Index '{collection_name}' does not exist in Pinecone"
                logger.error(error_msg)
                self._raise_collection_not_found(collection_name)

            # Connect to the index using modern API
            self.index_name = collection_name
            self.index = self.pinecone_client.Index(collection_name)

            logger.debug(f"Switched to index: {collection_name}")

        except HTTPException:
            # Re-raise HTTPExceptions as-is
            raise
        except Exception as e:  # noqa: BLE001 - pinecone client boundary
            error_msg = f"Failed to switch index: {e!s}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    async def vector_search(self, query_embedding: list[float], top_k: int) -> list[dict[str, Any]]:
        """
        Perform vector similarity search in Pinecone.
        
        Args:
            query_embedding: The query embedding vector
            top_k: Number of results to return
            
        Returns:
            List of search results with documents, metadata, and scores
        """
        if not self.index:
            logger.error("Index is not properly initialized")
            return []
        
        try:
            # Perform the search
            results = self.index.query(
                vector=query_embedding,
                top_k=top_k,
                namespace=self.namespace,
                include_metadata=True,
                include_values=False
            )
            
            # Convert Pinecone results to our standard format
            search_results = []
            
            if results and 'matches' in results:
                for match in results['matches']:
                    # Extract metadata
                    metadata = match.get('metadata', {})
                    
                    # Get document content from metadata
                    # Common field names: 'content', 'text', 'document'
                    doc = (metadata.get('content') or 
                          metadata.get('text') or 
                          metadata.get('document') or 
                          str(metadata))
                    
                    # Get score (Pinecone returns similarity scores, higher is better)
                    score = match.get('score', 0.0)
                    
                    search_results.append({
                        'document': str(doc),
                        'metadata': metadata,
                        'score': float(score)  # Use score instead of distance
                    })
            
            return search_results
            
        except Exception as e:  # noqa: BLE001 - pinecone client boundary
            error_msg = str(e)
            if DIMENSION_MISMATCH_PATTERN.search(error_msg):
                query_dim = len(query_embedding)
                logger.error(
                    f"Embedding dimension mismatch for Pinecone index '{self.index_name}': "
                    f"Query embedding has {query_dim} dimensions but index expects a different size. "
                    f"Please ensure the embedding model matches the one used to create the Pinecone index."
                )
            else:
                logger.error(f"Error querying Pinecone: {error_msg}")
            return []

    def calculate_similarity_from_distance(self, distance: float) -> float:
        """
        Convert Pinecone score to similarity score.
        Pinecone returns similarity scores directly (higher is better).

        Args:
            distance: Not used - Pinecone returns scores directly

        Returns:
            Similarity score between 0 and 1
        """
        # This method won't be called for Pinecone since we use scores directly
        # But we implement it for interface compatibility
        return distance

# Register the retriever with the factory
RetrieverFactory.register_retriever('pinecone', PineconeRetriever)
