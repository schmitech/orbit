"""
Milvus implementation of the AbstractVectorRetriever interface
"""

import logging
from typing import Dict, Any, List, Optional
from fastapi import HTTPException

from ...base.abstract_vector_retriever import AbstractVectorRetriever
from ...base.base_retriever import RetrieverFactory

# Configure logging
logger = logging.getLogger(__name__)

class MilvusRetriever(AbstractVectorRetriever):
    """Milvus implementation of the AbstractVectorRetriever interface"""

    def __init__(self, 
                config: Dict[str, Any],
                embeddings: Optional[Any] = None,
                domain_adapter=None,
                **kwargs):
        """
        Initialize MilvusRetriever.
        
        Args:
            config: Configuration dictionary containing Milvus and general settings
            embeddings: Optional embeddings service or model
            domain_adapter: Optional domain adapter for document handling
            **kwargs: Additional arguments
        """
        # Call the parent constructor first
        super().__init__(config=config, embeddings=embeddings, domain_adapter=domain_adapter, **kwargs)
        
        # Milvus-specific settings
        self.host = self.datasource_config.get('host', 'localhost')
        self.port = int(self.datasource_config.get('port', 19530))
        self.dim = int(self.datasource_config.get('dim', 768))
        self.metric_type = self.datasource_config.get('metric_type', 'IP')  # IP, L2, COSINE
        
        # Store collection
        self.collection_name = None
        self.collection = None
        
        # Milvus client
        self.milvus_client = None

    def _get_datasource_name(self) -> str:
        """Return the name of this datasource for config lookup"""
        return 'milvus'

    async def initialize_client(self) -> None:
        """Initialize the Milvus client."""
        try:
            from pymilvus import connections, Collection
            
            # Connect to Milvus
            connections.connect(
                alias="default",
                host=self.host,
                port=self.port
            )
            
            logger.info(f"Connected to Milvus at {self.host}:{self.port}")
            
        except ImportError:
            error_msg = "pymilvus package is required for Milvus retriever. Install with: pip install pymilvus"
            logger.error(error_msg)
            raise ImportError(error_msg)
        except Exception as e:
            error_msg = f"Failed to connect to Milvus: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    async def close_client(self) -> None:
        """Close the Milvus client."""
        try:
            from pymilvus import connections
            connections.disconnect("default")
            logger.info("Milvus client closed")
        except Exception as e:
            logger.error(f"Error closing Milvus connection: {str(e)}")

    async def set_collection(self, collection_name: str) -> None:
        """
        Set the current collection for retrieval.
        
        Args:
            collection_name: Name of the collection to use
        """
        if not collection_name:
            raise ValueError("Collection name cannot be empty")
            
        try:
            from pymilvus import Collection, utility
            
            # Check if collection exists
            if not utility.has_collection(collection_name):
                error_msg = f"Collection '{collection_name}' does not exist in Milvus"
                logger.error(error_msg)
                custom_msg = self.config.get('messages', {}).get('collection_not_found', 
                            "Collection not found. Please ensure the collection exists before querying.")
                raise HTTPException(status_code=404, detail=custom_msg)
            
            # Load the collection
            self.collection_name = collection_name
            self.collection = Collection(collection_name)
            self.collection.load()
            
            if self.verbose:
                logger.info(f"Switched to collection: {collection_name}")
                
        except Exception as e:
            error_msg = f"Failed to switch collection: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    async def vector_search(self, query_embedding: List[float], top_k: int) -> List[Dict[str, Any]]:
        """
        Perform vector similarity search in Milvus.
        
        Args:
            query_embedding: The query embedding vector
            top_k: Number of results to return
            
        Returns:
            List of search results with documents, metadata, and distances/scores
        """
        if not self.collection:
            logger.error("Collection is not properly initialized")
            return []
        
        try:
            # Define search parameters
            search_params = {
                "metric_type": self.metric_type,
                "params": {"nprobe": 10}  # Default search parameter
            }
            
            # Perform the search
            results = self.collection.search(
                data=[query_embedding],
                anns_field="embedding",  # Assuming the vector field is named 'embedding'
                param=search_params,
                limit=top_k,
                output_fields=["*"]  # Return all fields
            )
            
            # Convert Milvus results to our standard format
            search_results = []
            
            if results and len(results) > 0:
                for hit in results[0]:
                    # Extract entity data
                    entity = hit.entity
                    
                    # Get document content (assuming it's in a field called 'content' or 'document')
                    doc = getattr(entity, 'content', None) or getattr(entity, 'document', '')
                    
                    # Build metadata from all other fields
                    metadata = {}
                    for field_name in entity.fields:
                        if field_name not in ['embedding', 'content', 'document']:
                            metadata[field_name] = getattr(entity, field_name)
                    
                    # Get distance/score
                    distance = hit.distance
                    
                    search_results.append({
                        'document': str(doc),
                        'metadata': metadata,
                        'distance': float(distance)
                    })
            
            return search_results
            
        except Exception as e:
            logger.error(f"Error querying Milvus: {str(e)}")
            return []

    def calculate_similarity_from_distance(self, distance: float) -> float:
        """
        Convert Milvus distance/score to similarity score.
        
        Args:
            distance: Distance or score from Milvus
            
        Returns:
            Similarity score between 0 and 1
        """
        if self.metric_type == "IP":
            # Inner Product - higher is better, can be negative
            # Normalize to 0-1 range
            return max(0.0, min(1.0, (distance + 1.0) / 2.0))
        elif self.metric_type == "COSINE":
            # Cosine similarity - higher is better, range [-1, 1]
            # Normalize to 0-1 range
            return (distance + 1.0) / 2.0
        else:  # L2
            # L2 distance - lower is better
            # Use sigmoid-like conversion
            return 1.0 / (1.0 + (distance / self.distance_scaling_factor))

# Register the retriever with the factory
RetrieverFactory.register_retriever('milvus', MilvusRetriever) 