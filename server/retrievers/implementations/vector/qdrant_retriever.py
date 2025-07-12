"""
Qdrant implementation of the AbstractVectorRetriever interface
"""

import logging
from typing import Dict, Any, List, Optional
from fastapi import HTTPException

from ...base.abstract_vector_retriever import AbstractVectorRetriever
from ...base.base_retriever import RetrieverFactory

# Configure logging
logger = logging.getLogger(__name__)

class QdrantRetriever(AbstractVectorRetriever):
    """Qdrant implementation of the AbstractVectorRetriever interface"""

    def __init__(self, 
                config: Dict[str, Any],
                embeddings: Optional[Any] = None,
                domain_adapter=None,
                **kwargs):
        """
        Initialize QdrantRetriever.
        
        Args:
            config: Configuration dictionary containing Qdrant and general settings
            embeddings: Optional embeddings service or model
            domain_adapter: Optional domain adapter for document handling
            **kwargs: Additional arguments
        """
        # Call the parent constructor first
        super().__init__(config=config, embeddings=embeddings, domain_adapter=domain_adapter, **kwargs)
        
        # Qdrant-specific settings
        self.host = self.datasource_config.get('host', 'localhost')
        self.port = int(self.datasource_config.get('port', 6333))
        self.timeout = int(self.datasource_config.get('timeout', 30))
        self.grpc_port = self.datasource_config.get('grpc_port', None)
        self.prefer_grpc = self.datasource_config.get('prefer_grpc', False)
        self.api_key = self.datasource_config.get('api_key', None)
        self.https = self.datasource_config.get('https', False)
        
        # Distance metric configuration
        self.distance_metric = self.datasource_config.get('distance_metric', 'Cosine').lower()
        
        # Store collection
        self.collection_name = None
        
        # Get collection name from adapter config during initialization
        adapter_config = config.get('adapter_config', {})
        if adapter_config and 'collection' in adapter_config:
            self.collection_name = adapter_config['collection']
            logger.info(f"QdrantRetriever using collection from adapter config: {self.collection_name}")
        elif 'collection' in self.datasource_config:
            # Fallback to datasource config
            self.collection_name = self.datasource_config['collection']
            logger.info(f"QdrantRetriever using collection from datasource config: {self.collection_name}")
        
        # Qdrant client
        self.qdrant_client = None

    def _get_datasource_name(self) -> str:
        """Return the name of this datasource for config lookup"""
        return 'qdrant'

    async def initialize_client(self) -> None:
        """Initialize the Qdrant client."""
        try:
            from qdrant_client import QdrantClient
            
            # Initialize Qdrant client
            self.qdrant_client = QdrantClient(
                host=self.host,
                port=self.port,
                timeout=self.timeout,
                grpc_port=self.grpc_port,
                prefer_grpc=self.prefer_grpc,
                api_key=self.api_key,
                https=self.https
            )
            
            logger.info(f"Connected to Qdrant at {self.host}:{self.port}")
            
            # Test connection
            try:
                collections = self.qdrant_client.get_collections()
                logger.info(f"Successfully connected to Qdrant. Found {len(collections.collections)} collections")
            except Exception as e:
                logger.error(f"Failed to connect to Qdrant: {str(e)}")
                raise
            
            # Set collection if we have a collection name from config
            if self.collection_name:
                try:
                    await self.set_collection(self.collection_name)
                    logger.info(f"QdrantRetriever initialized with collection: {self.collection_name}")
                except Exception as e:
                    logger.error(f"Failed to set collection during initialization: {str(e)}")
                    # Don't raise here - let it be handled during actual usage
            
        except ImportError:
            error_msg = "qdrant-client package is required for Qdrant retriever. Install with: pip install qdrant-client"
            logger.error(error_msg)
            raise ImportError(error_msg)
        except Exception as e:
            error_msg = f"Failed to initialize Qdrant client: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    async def close_client(self) -> None:
        """Close the Qdrant client."""
        try:
            # Qdrant client doesn't have an explicit close method
            self.qdrant_client = None
            logger.info("Qdrant client closed")
        except Exception as e:
            logger.error(f"Error closing Qdrant client: {str(e)}")

    async def set_collection(self, collection_name: str) -> None:
        """
        Set the current collection for retrieval.
        
        Args:
            collection_name: Name of the collection to use
        """
        if not collection_name:
            raise ValueError("Collection name cannot be empty")
            
        try:
            # Check if collection exists
            try:
                collection_info = self.qdrant_client.get_collection(collection_name)
                self.collection_name = collection_name
                
                if self.verbose:
                    logger.info(f"Switched to collection: {collection_name}")
                    logger.info(f"Collection has {collection_info.points_count} vectors")
                    logger.info(f"Collection config: {collection_info.config}")
                    
            except Exception as e:
                if "Not found" in str(e) or "doesn't exist" in str(e):
                    error_msg = f"Collection '{collection_name}' does not exist in Qdrant"
                    logger.error(error_msg)
                    custom_msg = self.config.get('messages', {}).get('collection_not_found', 
                                "Collection not found. Please ensure the collection exists before querying.")
                    raise HTTPException(status_code=404, detail=custom_msg)
                else:
                    raise
                
        except HTTPException:
            raise
        except Exception as e:
            error_msg = f"Failed to switch collection: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    async def vector_search(self, query_embedding: List[float], top_k: int) -> List[Dict[str, Any]]:
        """
        Perform vector similarity search in Qdrant.
        
        Args:
            query_embedding: The query embedding vector
            top_k: Number of results to return
            
        Returns:
            List of search results with documents, metadata, and distances/scores
        """
        if not self.collection_name:
            logger.error("Collection is not properly initialized")
            return []
        
        try:
            # Perform the search
            search_results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=top_k,
                with_payload=True,
                with_vectors=False  # We don't need the vectors, just the payload
            )
            
            # Convert Qdrant results to our standard format
            formatted_results = []
            
            for result in search_results:
                # Extract payload
                payload = result.payload or {}
                
                # Get document content - check various possible field names
                doc = (payload.get('content') or 
                       payload.get('document') or 
                       payload.get('text') or 
                       '')
                
                # Remove content fields from metadata to avoid duplication
                metadata = {k: v for k, v in payload.items() 
                           if k not in ['content', 'document', 'text']}
                
                # Qdrant returns similarity scores (higher is better)
                score = float(result.score)
                
                formatted_results.append({
                    'document': str(doc),
                    'metadata': metadata,
                    'score': score,  # Qdrant provides similarity scores
                    'distance': 1.0 - score if self.distance_metric == 'cosine' else None
                })
            
            if self.verbose:
                logger.info(f"Qdrant search returned {len(formatted_results)} results")
                if formatted_results:
                    logger.info(f"Top result score: {formatted_results[0]['score']:.4f}")
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error querying Qdrant: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def calculate_similarity_from_distance(self, distance: float) -> float:
        """
        Convert Qdrant distance/score to similarity score.
        Qdrant typically returns similarity scores directly.
        
        Args:
            distance: Distance or score from Qdrant
            
        Returns:
            Similarity score between 0 and 1
        """
        # Qdrant search returns similarity scores directly (higher is better)
        # The score is already normalized between 0 and 1 for cosine similarity
        return float(distance)

# Register the retriever with the factory
RetrieverFactory.register_retriever('qdrant', QdrantRetriever)