"""
Redis (RedisSearch) implementation of the AbstractVectorRetriever interface
"""

import logging
from typing import Dict, Any, List, Optional
from fastapi import HTTPException

from ...base.abstract_vector_retriever import AbstractVectorRetriever
from ...base.base_retriever import RetrieverFactory

# Configure logging
logger = logging.getLogger(__name__)

class RedisRetriever(AbstractVectorRetriever):
    """Redis (RedisSearch) implementation of the AbstractVectorRetriever interface"""

    def __init__(self, 
                config: Dict[str, Any],
                embeddings: Optional[Any] = None,
                domain_adapter=None,
                **kwargs):
        """
        Initialize RedisRetriever.
        
        Args:
            config: Configuration dictionary containing Redis and general settings
            embeddings: Optional embeddings service or model
            domain_adapter: Optional domain adapter for document handling
            **kwargs: Additional arguments
        """
        # Call the parent constructor first
        super().__init__(config=config, embeddings=embeddings, domain_adapter=domain_adapter, **kwargs)
        
        # Redis-specific settings
        self.host = self.datasource_config.get('host', 'localhost')
        self.port = int(self.datasource_config.get('port', 6379))
        self.password = self.datasource_config.get('password')
        self.db = int(self.datasource_config.get('db', 0))
        self.use_ssl = self.datasource_config.get('use_ssl', False)
        
        # Vector field settings
        self.vector_field = self.datasource_config.get('vector_field', 'embedding')
        self.text_field = self.datasource_config.get('text_field', 'content')
        self.distance_metric = self.datasource_config.get('distance_metric', 'COSINE')  # L2, IP, COSINE
        
        # Store index
        self.index_name = None
        
        # Redis client
        self.redis_client = None

    def _get_datasource_name(self) -> str:
        """Return the name of this datasource for config lookup"""
        return 'redis'

    async def initialize_client(self) -> None:
        """Initialize the Redis client."""
        try:
            import redis
            from redis.commands.search.field import VectorField
            from redis.commands.search.query import Query
            
            # Create Redis connection
            connection_params = {
                'host': self.host,
                'port': self.port,
                'db': self.db,
                'ssl': self.use_ssl,
                'decode_responses': False  # Keep as bytes for vector operations
            }
            
            if self.password:
                connection_params['password'] = self.password
            
            self.redis_client = redis.Redis(**connection_params)
            
            # Test connection
            self.redis_client.ping()
            
            logger.info(f"Connected to Redis at {self.host}:{self.port}")
            
        except ImportError:
            error_msg = "redis package is required for Redis retriever. Install with: pip install redis"
            logger.error(error_msg)
            raise ImportError(error_msg)
        except Exception as e:
            error_msg = f"Failed to connect to Redis: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    async def close_client(self) -> None:
        """Close the Redis client."""
        try:
            if self.redis_client:
                self.redis_client.close()
            logger.info("Redis client closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {str(e)}")

    async def set_collection(self, collection_name: str) -> None:
        """
        Set the current index for retrieval.
        In Redis, collections are search indexes.
        
        Args:
            collection_name: Name of the index to use
        """
        if not collection_name:
            raise ValueError("Index name cannot be empty")
            
        try:
            from redis.commands.search.indexdefinition import IndexDefinition
            
            # Check if index exists
            try:
                index_info = self.redis_client.ft(collection_name).info()
                self.index_name = collection_name
                
                if self.verbose:
                    logger.info(f"Switched to index: {collection_name}")
                    
            except Exception:
                error_msg = f"Index '{collection_name}' does not exist in Redis"
                logger.error(error_msg)
                custom_msg = self.config.get('messages', {}).get('collection_not_found', 
                            "Collection not found. Please ensure the collection exists before querying.")
                raise HTTPException(status_code=404, detail=custom_msg)
                
        except Exception as e:
            error_msg = f"Failed to switch index: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    async def vector_search(self, query_embedding: List[float], top_k: int) -> List[Dict[str, Any]]:
        """
        Perform vector similarity search in Redis.
        
        Args:
            query_embedding: The query embedding vector
            top_k: Number of results to return
            
        Returns:
            List of search results with documents, metadata, and distances/scores
        """
        if not self.index_name:
            logger.error("Index is not properly initialized")
            return []
        
        try:
            from redis.commands.search.query import Query
            import numpy as np
            
            # Convert embedding to bytes
            query_vector = np.array(query_embedding, dtype=np.float32).tobytes()
            
            # Build the KNN query
            base_query = f"*=>[KNN {top_k} @{self.vector_field} $query_vector AS score]"
            query = Query(base_query).sort_by("score").return_fields("score", self.text_field, "*").dialect(2)
            
            # Perform the search
            results = self.redis_client.ft(self.index_name).search(
                query, 
                query_params={"query_vector": query_vector}
            )
            
            # Convert Redis results to our standard format
            search_results = []
            
            for doc in results.docs:
                # Extract document content
                content = getattr(doc, self.text_field, '')
                
                # Build metadata from all other fields
                metadata = {}
                for field_name in dir(doc):
                    if (not field_name.startswith('_') and 
                        field_name not in ['id', 'score', self.text_field, self.vector_field]):
                        try:
                            value = getattr(doc, field_name)
                            if not callable(value):
                                metadata[field_name] = value
                        except:
                            pass
                
                # Get score (Redis returns distance, lower is better for L2 and COSINE)
                distance = float(getattr(doc, 'score', 1.0))
                
                search_results.append({
                    'document': str(content),
                    'metadata': metadata,
                    'distance': distance
                })
            
            return search_results
            
        except Exception as e:
            logger.error(f"Error querying Redis: {str(e)}")
            return []

    def calculate_similarity_from_distance(self, distance: float) -> float:
        """
        Convert Redis distance to similarity score.
        
        Args:
            distance: Distance from Redis search
            
        Returns:
            Similarity score between 0 and 1
        """
        if self.distance_metric == "IP":
            # Inner Product - higher is better (but Redis might return as distance)
            # For IP, we might need to handle this differently based on Redis version
            return max(0.0, min(1.0, distance))
        elif self.distance_metric == "COSINE":
            # Cosine distance - convert to similarity
            return max(0.0, 1.0 - distance)
        else:  # L2
            # L2 distance - lower is better
            return 1.0 / (1.0 + (distance / self.distance_scaling_factor))

# Register the retriever with the factory
RetrieverFactory.register_retriever('redis', RedisRetriever) 