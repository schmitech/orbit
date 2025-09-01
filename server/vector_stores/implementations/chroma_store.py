"""
ChromaDB store implementation for vector operations.
"""

import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from ..base.base_vector_store import BaseVectorStore
from ..base.base_store import StoreConfig, StoreStatus

logger = logging.getLogger(__name__)


class ChromaStore(BaseVectorStore):
    """
    ChromaDB store implementation providing vector storage and similarity search.
    
    This implementation provides:
    - Vector storage and retrieval
    - Similarity search with various distance metrics
    - Collection management
    - Metadata filtering and search
    - Persistent and ephemeral storage options
    """
    
    def __init__(self, config: StoreConfig):
        """
        Initialize ChromaDB store.
        
        Args:
            config: Store configuration
        """
        super().__init__(config)
        
        # ChromaDB-specific configuration
        self.persist_directory = config.connection_params.get('persist_directory')
        self.allow_reset = config.connection_params.get('allow_reset', False)
        
        # Connection and state
        self._client = None
        self._collections = {}  # Cache for collection objects
        
        # Create persist directory if specified
        if self.persist_directory:
            Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
    
    async def connect(self) -> bool:
        """
        Establish connection to ChromaDB.
        
        Returns:
            True if connection successful, False otherwise
        """
        if self.status == StoreStatus.CONNECTED:
            return True
        
        self.status = StoreStatus.CONNECTING
        
        try:
            import chromadb
            from chromadb.config import Settings
            
            # Configure ChromaDB client
            if self.persist_directory:
                # Persistent client
                self._client = chromadb.PersistentClient(
                    path=self.persist_directory,
                    settings=Settings(
                        allow_reset=self.allow_reset,
                        anonymized_telemetry=False
                    )
                )
            else:
                # Ephemeral client
                self._client = chromadb.EphemeralClient(
                    settings=Settings(
                        allow_reset=self.allow_reset,
                        anonymized_telemetry=False
                    )
                )
            
            self.status = StoreStatus.CONNECTED
            logger.info(f"ChromaDB store {self.config.name} connected successfully")
            return True
            
        except ImportError:
            logger.error("ChromaDB not available. Install with: pip install chromadb")
            self.status = StoreStatus.ERROR
            return False
        except Exception as e:
            logger.error(f"Error connecting to ChromaDB: {e}")
            self.status = StoreStatus.ERROR
            return False
    
    async def disconnect(self) -> None:
        """Close ChromaDB connection and cleanup resources."""
        if self._client:
            try:
                # Clear collection cache
                self._collections.clear()
                
                # ChromaDB client doesn't need explicit disconnection
                self._client = None
                self.status = StoreStatus.DISCONNECTED
                logger.info(f"ChromaDB store {self.config.name} disconnected")
                
            except Exception as e:
                logger.error(f"Error disconnecting from ChromaDB: {e}")
                self.status = StoreStatus.ERROR
    
    async def health_check(self) -> bool:
        """
        Check if ChromaDB connection is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            if not self._client:
                return False
            
            # Try to list collections as a health check
            self._client.list_collections()
            return True
            
        except Exception as e:
            logger.error(f"ChromaDB health check failed: {e}")
            return False
    
    async def add_vectors(self, 
                         vectors: List[List[float]], 
                         ids: List[str], 
                         metadata: Optional[List[Dict[str, Any]]] = None,
                         collection_name: Optional[str] = None) -> bool:
        """
        Add vectors to ChromaDB collection.
        
        Args:
            vectors: List of vector embeddings
            ids: Unique identifiers for each vector
            metadata: Optional metadata for each vector
            collection_name: Name of the collection to add to
            
        Returns:
            True if successful, False otherwise
        """
        await self.ensure_connected()
        self.update_access_time()
        
        collection_name = collection_name or self._default_collection
        
        try:
            collection = await self._get_or_create_collection(collection_name, len(vectors[0]) if vectors else 768)
            
            # Prepare documents (ChromaDB expects string documents)
            documents = [f"vector_{i}" for i in range(len(vectors))]
            
            # Add to collection
            collection.add(
                embeddings=vectors,
                documents=documents,
                metadatas=metadata or [{}] * len(vectors),
                ids=ids
            )
            
            logger.info(f"Added {len(vectors)} vectors to collection {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding vectors to ChromaDB: {e}")
            return False
    
    async def search_vectors(self, 
                           query_vector: List[float], 
                           limit: int = 10,
                           collection_name: Optional[str] = None,
                           filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Search for similar vectors in ChromaDB.
        
        Args:
            query_vector: Query vector for similarity search
            limit: Maximum number of results to return
            collection_name: Name of the collection to search
            filter_metadata: Optional metadata filters
            
        Returns:
            List of search results with scores and metadata
        """
        await self.ensure_connected()
        self.update_access_time()
        
        collection_name = collection_name or self._default_collection
        
        try:
            collection = await self._get_collection(collection_name)
            if not collection:
                logger.warning(f"Collection {collection_name} not found")
                return []
            
            # Perform search
            results = collection.query(
                query_embeddings=[query_vector],
                n_results=limit,
                where=filter_metadata,
                include=['embeddings', 'metadatas', 'distances']
            )
            
            # Format results
            formatted_results = []
            if results['ids'] and results['ids'][0]:
                # Get distance function to properly convert to similarity
                collection_metadata = collection.metadata or {}
                distance_function = collection_metadata.get('hnsw:space', 'cosine')
                
                for i, vector_id in enumerate(results['ids'][0]):
                    distance = results['distances'][0][i]
                    
                    # Convert distance to similarity score based on metric
                    if distance_function == 'cosine':
                        # Cosine distance range: [0, 2], where 0 is identical
                        # Convert to similarity: [0, 1], where 1 is identical
                        score = max(0, 1.0 - (distance / 2.0))
                    elif distance_function == 'l2':
                        # L2 distance: [0, inf), use exponential decay
                        score = 1.0 / (1.0 + distance)
                    elif distance_function == 'ip':
                        # Inner product: higher is better, can be negative
                        score = distance  # Already a similarity measure
                    else:
                        # Default: assume smaller distance is better
                        score = max(0, 1.0 - distance)
                    
                    result_item = {
                        'id': vector_id,
                        'score': score,
                        'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                        'vector': results['embeddings'][0][i] if results['embeddings'] else None
                    }
                    formatted_results.append(result_item)
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error searching vectors in ChromaDB: {e}")
            return []
    
    async def get_vector(self, 
                        vector_id: str, 
                        collection_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get a specific vector by ID from ChromaDB.
        
        Args:
            vector_id: ID of the vector to retrieve
            collection_name: Name of the collection
            
        Returns:
            Vector data with metadata or None if not found
        """
        await self.ensure_connected()
        self.update_access_time()
        
        collection_name = collection_name or self._default_collection
        
        try:
            collection = await self._get_collection(collection_name)
            if not collection:
                return None
            
            # Get vector by ID
            results = collection.get(
                ids=[vector_id],
                include=['embeddings', 'metadatas']
            )
            
            if results['ids'] and len(results['ids']) > 0:
                return {
                    'id': results['ids'][0],
                    'vector': results['embeddings'][0] if results['embeddings'] else None,
                    'metadata': results['metadatas'][0] if results['metadatas'] else {}
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting vector from ChromaDB: {e}")
            return None
    
    async def update_vector(self, 
                           vector_id: str, 
                           vector: Optional[List[float]] = None,
                           metadata: Optional[Dict[str, Any]] = None,
                           collection_name: Optional[str] = None) -> bool:
        """
        Update a vector and/or its metadata in ChromaDB.
        
        Args:
            vector_id: ID of the vector to update
            vector: New vector embeddings (optional)
            metadata: New metadata (optional)
            collection_name: Name of the collection
            
        Returns:
            True if successful, False otherwise
        """
        await self.ensure_connected()
        self.update_access_time()
        
        collection_name = collection_name or self._default_collection
        
        try:
            collection = await self._get_collection(collection_name)
            if not collection:
                return False
            
            update_params = {'ids': [vector_id]}
            
            if vector:
                update_params['embeddings'] = [vector]
                update_params['documents'] = [f"vector_updated"]
            
            if metadata:
                update_params['metadatas'] = [metadata]
            
            # ChromaDB uses upsert for updates
            collection.upsert(**update_params)
            
            logger.info(f"Updated vector {vector_id} in collection {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating vector in ChromaDB: {e}")
            return False
    
    async def delete_vector(self, 
                           vector_id: str, 
                           collection_name: Optional[str] = None) -> bool:
        """
        Delete a vector from ChromaDB.
        
        Args:
            vector_id: ID of the vector to delete
            collection_name: Name of the collection
            
        Returns:
            True if successful, False otherwise
        """
        await self.ensure_connected()
        self.update_access_time()
        
        collection_name = collection_name or self._default_collection
        
        try:
            collection = await self._get_collection(collection_name)
            if not collection:
                return False
            
            collection.delete(ids=[vector_id])
            
            logger.info(f"Deleted vector {vector_id} from collection {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting vector from ChromaDB: {e}")
            return False
    
    async def create_collection(self, 
                               collection_name: str, 
                               dimension: int,
                               **kwargs) -> bool:
        """
        Create a new ChromaDB collection.
        
        Args:
            collection_name: Name of the collection
            dimension: Vector dimension (stored in metadata)
            **kwargs: Additional collection parameters
            
        Returns:
            True if successful, False otherwise
        """
        await self.ensure_connected()
        
        try:
            # Get distance function from config or use cosine as default
            distance_function = self.config.connection_params.get('distance_function', 'cosine')
            
            collection = self._client.create_collection(
                name=collection_name,
                metadata={"dimension": dimension, "hnsw:space": distance_function, **kwargs}
            )
            
            # Cache the collection
            self._collections[collection_name] = collection
            
            logger.info(f"Created ChromaDB collection: {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating ChromaDB collection: {e}")
            return False
    
    async def delete_collection(self, collection_name: str) -> bool:
        """
        Delete a ChromaDB collection.
        
        Args:
            collection_name: Name of the collection to delete
            
        Returns:
            True if successful, False otherwise
        """
        await self.ensure_connected()
        
        try:
            self._client.delete_collection(name=collection_name)
            
            # Remove from cache
            if collection_name in self._collections:
                del self._collections[collection_name]
            
            logger.info(f"Deleted ChromaDB collection: {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting ChromaDB collection: {e}")
            return False
    
    async def list_collections(self) -> List[str]:
        """
        List all ChromaDB collections.
        
        Returns:
            List of collection names
        """
        await self.ensure_connected()
        
        try:
            collections = self._client.list_collections()
            return [col.name for col in collections]
        except Exception as e:
            logger.error(f"Error listing ChromaDB collections: {e}")
            return []
    
    async def collection_exists(self, collection_name: str) -> bool:
        """
        Check if a ChromaDB collection exists.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            True if exists, False otherwise
        """
        collections = await self.list_collections()
        return collection_name in collections
    
    async def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        """
        Get information about a ChromaDB collection.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            Collection information dictionary
        """
        await self.ensure_connected()
        
        try:
            collection = await self._get_collection(collection_name)
            if not collection:
                return {'error': 'Collection not found'}
            
            # Get collection count
            count = collection.count()
            
            return {
                'name': collection_name,
                'count': count,
                'metadata': collection.metadata or {}
            }
            
        except Exception as e:
            logger.error(f"Error getting ChromaDB collection info: {e}")
            return {'error': str(e)}
    
    # ChromaDB-specific helper methods
    
    async def _get_collection(self, collection_name: str):
        """Get a ChromaDB collection object."""
        # Check cache first
        if collection_name in self._collections:
            return self._collections[collection_name]
        
        try:
            collection = self._client.get_collection(name=collection_name)
            self._collections[collection_name] = collection
            return collection
        except Exception:
            return None
    
    async def _get_or_create_collection(self, collection_name: str, dimension: int):
        """Get existing collection or create new one."""
        collection = await self._get_collection(collection_name)
        
        if collection is None:
            # Try to create the collection
            success = await self.create_collection(collection_name, dimension)
            if success:
                collection = await self._get_collection(collection_name)
        
        return collection