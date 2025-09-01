"""
Base class for vector database stores.
"""

import logging
from abc import abstractmethod
from typing import Dict, Any, Optional, List
import numpy as np

from .base_store import BaseStore, StoreConfig, StoreType

logger = logging.getLogger(__name__)


class BaseVectorStore(BaseStore):
    """
    Base class for vector database stores.
    
    Provides common functionality for vector-based stores including:
    - Vector storage and retrieval
    - Similarity search operations
    - Collection management
    - Metadata handling
    """
    
    def __init__(self, config: StoreConfig):
        """Initialize the vector store."""
        super().__init__(config)
        self._default_collection = config.connection_params.get('default_collection', 'default')
        self._distance_function = config.connection_params.get('distance_function', 'cosine')
        self._store_type = StoreType.VECTOR
    
    @abstractmethod
    async def add_vectors(self, 
                         vectors: List[List[float]], 
                         ids: List[str], 
                         metadata: Optional[List[Dict[str, Any]]] = None,
                         collection_name: Optional[str] = None) -> bool:
        """
        Add vectors to the store.
        
        Args:
            vectors: List of vector embeddings
            ids: Unique identifiers for each vector
            metadata: Optional metadata for each vector
            collection_name: Name of the collection to add to
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def search_vectors(self, 
                           query_vector: List[float], 
                           limit: int = 10,
                           collection_name: Optional[str] = None,
                           filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Search for similar vectors.
        
        Args:
            query_vector: Query vector for similarity search
            limit: Maximum number of results to return
            collection_name: Name of the collection to search
            filter_metadata: Optional metadata filters
            
        Returns:
            List of search results with scores and metadata
        """
        pass
    
    @abstractmethod
    async def get_vector(self, 
                        vector_id: str, 
                        collection_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get a specific vector by ID.
        
        Args:
            vector_id: ID of the vector to retrieve
            collection_name: Name of the collection
            
        Returns:
            Vector data with metadata or None if not found
        """
        pass
    
    @abstractmethod
    async def update_vector(self, 
                           vector_id: str, 
                           vector: Optional[List[float]] = None,
                           metadata: Optional[Dict[str, Any]] = None,
                           collection_name: Optional[str] = None) -> bool:
        """
        Update a vector and/or its metadata.
        
        Args:
            vector_id: ID of the vector to update
            vector: New vector embeddings (optional)
            metadata: New metadata (optional)
            collection_name: Name of the collection
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def delete_vector(self, 
                           vector_id: str, 
                           collection_name: Optional[str] = None) -> bool:
        """
        Delete a vector from the store.
        
        Args:
            vector_id: ID of the vector to delete
            collection_name: Name of the collection
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def create_collection(self, 
                               collection_name: str, 
                               dimension: int,
                               **kwargs) -> bool:
        """
        Create a new collection.
        
        Args:
            collection_name: Name of the collection
            dimension: Vector dimension
            **kwargs: Additional collection parameters
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def delete_collection(self, collection_name: str) -> bool:
        """
        Delete a collection.
        
        Args:
            collection_name: Name of the collection to delete
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def list_collections(self) -> List[str]:
        """
        List all collections in the store.
        
        Returns:
            List of collection names
        """
        pass
    
    @abstractmethod
    async def collection_exists(self, collection_name: str) -> bool:
        """
        Check if a collection exists.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            True if exists, False otherwise
        """
        pass
    
    @abstractmethod
    async def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        """
        Get information about a collection.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            Collection information dictionary
        """
        pass
    
    async def clear_collection(self, collection_name: Optional[str] = None) -> bool:
        """
        Clear all data from a collection.
        
        Args:
            collection_name: Name of the collection to clear
            
        Returns:
            True if successful, False otherwise
        """
        collection = collection_name or self._default_collection
        try:
            # Delete and recreate the collection
            info = await self.get_collection_info(collection)
            dimension = info.get('metadata', {}).get('dimension', 768)
            
            await self.delete_collection(collection)
            await self.create_collection(collection, dimension)
            return True
        except Exception as e:
            logger.error(f"Error clearing collection {collection}: {e}")
            return False
    
    # Vector-specific utility methods
    
    def calculate_similarity(self, vector1: List[float], vector2: List[float], 
                           method: Optional[str] = None) -> float:
        """
        Calculate similarity between two vectors.
        
        Args:
            vector1: First vector
            vector2: Second vector
            method: Similarity method ('cosine', 'euclidean', 'dot')
            
        Returns:
            Similarity score
        """
        method = method or self._distance_function
        v1 = np.array(vector1)
        v2 = np.array(vector2)
        
        if method == 'cosine':
            # Cosine similarity
            dot_product = np.dot(v1, v2)
            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return float(dot_product / (norm1 * norm2))
        
        elif method == 'euclidean':
            # Euclidean distance (converted to similarity)
            distance = np.linalg.norm(v1 - v2)
            return float(1 / (1 + distance))  # Convert distance to similarity
        
        elif method == 'dot':
            # Dot product
            return float(np.dot(v1, v2))
        
        else:
            raise ValueError(f"Unknown similarity method: {method}")
    
    def normalize_vector(self, vector: List[float]) -> List[float]:
        """
        Normalize a vector to unit length.
        
        Args:
            vector: Input vector
            
        Returns:
            Normalized vector
        """
        v = np.array(vector)
        norm = np.linalg.norm(v)
        if norm == 0:
            return vector  # Return original if zero vector
        return (v / norm).tolist()
    
    async def batch_add_vectors(self, 
                               vectors_data: List[Dict[str, Any]], 
                               collection_name: Optional[str] = None,
                               batch_size: int = 100) -> Dict[str, bool]:
        """
        Add multiple vectors in batches.
        
        Args:
            vectors_data: List of vector data dictionaries (id, vector, metadata)
            collection_name: Target collection
            batch_size: Number of vectors per batch
            
        Returns:
            Dictionary of id to success status
        """
        results = {}
        collection = collection_name or self._default_collection
        
        # Process in batches
        for i in range(0, len(vectors_data), batch_size):
            batch = vectors_data[i:i + batch_size]
            
            ids = []
            vectors = []
            metadata_list = []
            
            for item in batch:
                ids.append(item['id'])
                vectors.append(item['vector'])
                metadata_list.append(item.get('metadata', {}))
            
            try:
                success = await self.add_vectors(vectors, ids, metadata_list, collection)
                for vector_id in ids:
                    results[vector_id] = success
            except Exception as e:
                logger.error(f"Error in batch add: {e}")
                for vector_id in ids:
                    results[vector_id] = False
        
        return results
    
    async def similarity_search_with_threshold(self, 
                                             query_vector: List[float],
                                             threshold: float = 0.5,
                                             limit: int = 10,
                                             collection_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for vectors above a similarity threshold.
        
        Args:
            query_vector: Query vector
            threshold: Minimum similarity threshold
            limit: Maximum results
            collection_name: Target collection
            
        Returns:
            Filtered search results
        """
        # Get more results to account for filtering
        results = await self.search_vectors(query_vector, limit * 2, collection_name)
        
        # Filter by threshold
        filtered_results = []
        for result in results:
            if result.get('score', 0) >= threshold:
                filtered_results.append(result)
                if len(filtered_results) >= limit:
                    break
        
        return filtered_results