"""
Pinecone store implementation for vector operations.
"""

import logging
from typing import Dict, Any, Optional, List
import time

from ..base.base_vector_store import BaseVectorStore
from ..base.base_store import StoreConfig, StoreStatus

logger = logging.getLogger(__name__)


class PineconeStore(BaseVectorStore):
    """
    Pinecone store implementation providing vector storage and similarity search.

    This implementation provides:
    - Vector storage and retrieval
    - Similarity search with various distance metrics
    - Collection (index) management
    - Metadata filtering and search
    - Cloud-based serverless and pod-based storage options
    """

    def __init__(self, config: StoreConfig):
        """
        Initialize Pinecone store.

        Args:
            config: Store configuration
        """
        super().__init__(config)

        # Pinecone-specific configuration
        self.api_key = config.connection_params.get('api_key')
        self.host = config.connection_params.get('host')  # Optional, for pod-based indexes
        self.namespace = config.connection_params.get('namespace', '')
        self.index_name = config.connection_params.get('index_name', 'orbit-index')

        # Connection and state
        self._client = None
        self._index = None
        self._collections_cache = None  # Cache for collection list
        self._cache_timestamp = None  # Cache timestamp

    async def connect(self) -> bool:
        """
        Establish connection to Pinecone.

        Returns:
            True if connection successful, False otherwise
        """
        if self.status == StoreStatus.CONNECTED:
            return True

        self.status = StoreStatus.CONNECTING

        try:
            from pinecone import Pinecone

            # Initialize Pinecone client
            init_kwargs = {'api_key': self.api_key}

            # Add host if provided (for specific index connections)
            if self.host:
                init_kwargs['host'] = self.host

            self._client = Pinecone(**init_kwargs)

            self.status = StoreStatus.CONNECTED
            logger.info(f"Pinecone store {self.config.name} connected successfully")
            return True

        except ImportError:
            logger.error("Pinecone not available. Install with: pip install pinecone-client")
            self.status = StoreStatus.ERROR
            return False
        except Exception as e:
            logger.error(f"Error connecting to Pinecone: {e}")
            self.status = StoreStatus.ERROR
            return False

    async def disconnect(self) -> None:
        """Close Pinecone connection and cleanup resources."""
        if self._client:
            try:
                # Pinecone doesn't require explicit disconnection
                self._client = None
                self._index = None
                self.status = StoreStatus.DISCONNECTED
                logger.info(f"Pinecone store {self.config.name} disconnected")

            except Exception as e:
                logger.error(f"Error disconnecting from Pinecone: {e}")
                self.status = StoreStatus.ERROR

    async def health_check(self) -> bool:
        """
        Check if Pinecone connection is healthy.

        Returns:
            True if healthy, False otherwise
        """
        try:
            if not self._client:
                return False

            # Try to list indexes as a health check
            self._client.list_indexes()
            return True

        except Exception as e:
            logger.error(f"Pinecone health check failed: {e}")
            return False

    async def add_vectors(self,
                         vectors: List[List[float]],
                         ids: List[str],
                         metadata: Optional[List[Dict[str, Any]]] = None,
                         collection_name: Optional[str] = None,
                         documents: Optional[List[str]] = None) -> bool:
        """
        Add vectors to Pinecone index.

        Args:
            vectors: List of vector embeddings
            ids: Unique identifiers for each vector
            metadata: Optional metadata for each vector
            collection_name: Name of the collection (index) to add to
            documents: Optional list of text documents to store with vectors

        Returns:
            True if successful, False otherwise
        """
        await self.ensure_connected()
        self.update_access_time()

        try:
            index_name = collection_name or self.index_name

            # Check if index exists, create if not
            if not await self.collection_exists(index_name):
                # Get dimension from first vector
                dimension = len(vectors[0]) if vectors else 768
                logger.info(f"Creating Pinecone index {index_name} with dimension {dimension}")
                await self.create_collection(index_name, dimension)

            # Get or create index reference
            if not self._index or self._index._config.index_name != index_name:
                self._index = self._client.Index(index_name)

            # Prepare vectors for upsert
            vectors_to_upsert = []
            for i, (vector_id, vector) in enumerate(zip(ids, vectors)):
                vector_data = {
                    "id": vector_id,
                    "values": vector
                }

                # Prepare metadata with document text if provided
                vector_metadata = {}
                if metadata and i < len(metadata):
                    vector_metadata = metadata[i].copy()

                # Add document text to metadata if provided
                if documents and i < len(documents):
                    vector_metadata["text"] = documents[i]
                    vector_metadata["content"] = documents[i]  # For compatibility
                elif metadata and i < len(metadata):
                    # Try to extract text from existing metadata if documents not provided
                    if "text" not in vector_metadata and "content" not in vector_metadata:
                        # Check for common text fields
                        text = metadata[i].get('text') or metadata[i].get('content') or metadata[i].get('document')
                        if text:
                            vector_metadata["text"] = text
                            vector_metadata["content"] = text

                if vector_metadata:
                    vector_data["metadata"] = vector_metadata

                vectors_to_upsert.append(vector_data)

            # Upsert vectors to Pinecone
            self._index.upsert(vectors=vectors_to_upsert, namespace=self.namespace)

            logger.debug(f"Added {len(vectors)} vectors to Pinecone index {index_name}")
            return True

        except Exception as e:
            logger.error(f"Error adding vectors to Pinecone: {e}")
            return False

    async def search_vectors(self,
                           query_vector: List[float],
                           limit: int = 10,
                           collection_name: Optional[str] = None,
                           filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Search for similar vectors in Pinecone.

        Args:
            query_vector: Query vector for similarity search
            limit: Maximum number of results to return
            collection_name: Name of the collection (index) to search
            filter_metadata: Optional metadata filters

        Returns:
            List of search results with scores and metadata
        """
        await self.ensure_connected()
        self.update_access_time()

        try:
            index_name = collection_name or self.index_name

            # Get or create index reference
            if not self._index or self._index._config.index_name != index_name:
                self._index = self._client.Index(index_name)

            # Perform search
            search_results = self._index.query(
                vector=query_vector,
                top_k=limit,
                include_metadata=True,
                namespace=self.namespace,
                filter=filter_metadata
            )

            # Format results
            results = []
            for match in search_results.get('matches', []):
                metadata = match.get('metadata', {})

                # Extract text from metadata for file chunking support
                text = metadata.get('text', metadata.get('content', ''))

                result = {
                    'id': match['id'],
                    'score': match['score'],
                    'metadata': metadata,
                    'text': text,  # For file adapter compatibility
                    'content': text  # Alternative field for compatibility
                }
                results.append(result)

            return results

        except Exception as e:
            logger.error(f"Error searching vectors in Pinecone: {e}")
            return []

    async def get_vector(self,
                        vector_id: str,
                        collection_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get a specific vector by ID from Pinecone.

        Args:
            vector_id: ID of the vector to retrieve
            collection_name: Name of the collection (index)

        Returns:
            Vector data with metadata or None if not found
        """
        await self.ensure_connected()
        self.update_access_time()

        try:
            index_name = collection_name or self.index_name

            # Get or create index reference
            if not self._index or self._index._config.index_name != index_name:
                self._index = self._client.Index(index_name)

            # Fetch vector
            result = self._index.fetch(ids=[vector_id], namespace=self.namespace)

            if vector_id in result.get('vectors', {}):
                vector_data = result['vectors'][vector_id]
                return {
                    'id': vector_id,
                    'vector': vector_data.get('values', []),
                    'metadata': vector_data.get('metadata', {})
                }

            return None

        except Exception as e:
            logger.error(f"Error getting vector from Pinecone: {e}")
            return None

    async def update_vector(self,
                           vector_id: str,
                           vector: Optional[List[float]] = None,
                           metadata: Optional[Dict[str, Any]] = None,
                           collection_name: Optional[str] = None) -> bool:
        """
        Update a vector and/or its metadata in Pinecone.

        Args:
            vector_id: ID of the vector to update
            vector: New vector embeddings (optional)
            metadata: New metadata (optional)
            collection_name: Name of the collection (index)

        Returns:
            True if successful, False otherwise
        """
        await self.ensure_connected()
        self.update_access_time()

        try:
            index_name = collection_name or self.index_name

            # Get or create index reference
            if not self._index or self._index._config.index_name != index_name:
                self._index = self._client.Index(index_name)

            # Pinecone uses upsert for updates
            update_data = {"id": vector_id}

            if vector:
                update_data["values"] = vector

            if metadata:
                update_data["metadata"] = metadata

            self._index.upsert(vectors=[update_data], namespace=self.namespace)

            logger.debug(f"Updated vector {vector_id} in Pinecone index {index_name}")
            return True

        except Exception as e:
            logger.error(f"Error updating vector in Pinecone: {e}")
            return False

    async def delete_vector(self,
                           vector_id: str,
                           collection_name: Optional[str] = None) -> bool:
        """
        Delete a vector from Pinecone.

        Args:
            vector_id: ID of the vector to delete
            collection_name: Name of the collection (index)

        Returns:
            True if successful, False otherwise
        """
        await self.ensure_connected()
        self.update_access_time()

        try:
            index_name = collection_name or self.index_name

            # Get or create index reference
            if not self._index or self._index._config.index_name != index_name:
                self._index = self._client.Index(index_name)

            self._index.delete(ids=[vector_id], namespace=self.namespace)

            logger.debug(f"Deleted vector {vector_id} from Pinecone index {index_name}")
            return True

        except Exception as e:
            logger.error(f"Error deleting vector from Pinecone: {e}")
            return False

    async def list_collections(self) -> List[str]:
        """
        List all collections (indexes) in Pinecone.

        Returns:
            List of collection names
        """
        await self.ensure_connected()

        try:
            import time

            # Use cache if available and fresh (within 5 seconds)
            if self._collections_cache is not None and self._cache_timestamp is not None:
                if time.time() - self._cache_timestamp < 5:
                    return self._collections_cache

            # Fetch fresh list
            indexes = self._client.list_indexes()
            index_names = [idx.name for idx in indexes]

            # Update cache
            self._collections_cache = index_names
            self._cache_timestamp = time.time()

            return index_names
        except Exception as e:
            logger.error(f"Error listing Pinecone indexes: {e}")
            return []

    async def collection_exists(self, collection_name: str) -> bool:
        """
        Check if a collection (index) exists in Pinecone.

        Args:
            collection_name: Name of the collection (index) to check

        Returns:
            True if exists, False otherwise
        """
        await self.ensure_connected()

        try:
            # Try to describe the specific index instead of listing all
            self._client.describe_index(collection_name)
            return True
        except Exception:
            # Index doesn't exist or error occurred
            return False

    async def create_collection(self,
                               collection_name: str,
                               dimension: int,
                               distance_metric: str = 'cosine') -> bool:
        """
        Create a new collection (index) in Pinecone.

        Args:
            collection_name: Name of the collection (index) to create
            dimension: Dimension of the vectors
            distance_metric: Distance metric to use

        Returns:
            True if successful, False otherwise
        """
        await self.ensure_connected()

        try:
            from pinecone import ServerlessSpec

            # Check if index already exists
            if await self.collection_exists(collection_name):
                logger.info(f"Pinecone index {collection_name} already exists")
                return True

            # Create index with serverless spec
            self._client.create_index(
                name=collection_name,
                dimension=dimension,
                metric=distance_metric,
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )

            # Wait for index to be ready
            logger.info(f"Waiting for Pinecone index {collection_name} to be ready...")
            while not self._client.describe_index(collection_name).status['ready']:
                time.sleep(1)

            # Invalidate cache
            self._collections_cache = None
            self._cache_timestamp = None

            logger.info(f"Created Pinecone index {collection_name}")
            return True

        except Exception as e:
            logger.error(f"Error creating Pinecone index: {e}")
            return False

    async def delete_collection(self, collection_name: str) -> bool:
        """
        Delete a collection (index) from Pinecone.

        Args:
            collection_name: Name of the collection (index) to delete

        Returns:
            True if successful, False otherwise
        """
        await self.ensure_connected()

        try:
            if await self.collection_exists(collection_name):
                self._client.delete_index(collection_name)

                # Invalidate cache
                self._collections_cache = None
                self._cache_timestamp = None

                logger.info(f"Deleted Pinecone index {collection_name}")
                return True
            else:
                logger.warning(f"Pinecone index {collection_name} does not exist")
                return False

        except Exception as e:
            logger.error(f"Error deleting Pinecone index: {e}")
            return False

    async def clear_collection(self, collection_name: str) -> bool:
        """
        Clear all vectors from a collection (index) in Pinecone.

        Args:
            collection_name: Name of the collection (index) to clear

        Returns:
            True if successful, False otherwise
        """
        await self.ensure_connected()

        try:
            # Get or create index reference
            if not self._index or self._index._config.index_name != collection_name:
                self._index = self._client.Index(collection_name)

            # Delete all vectors in the namespace
            self._index.delete(delete_all=True, namespace=self.namespace)

            logger.info(f"Cleared Pinecone index {collection_name}")
            return True

        except Exception as e:
            logger.error(f"Error clearing Pinecone index: {e}")
            return False

    async def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        """
        Get information about a Pinecone collection (index).

        Args:
            collection_name: Name of the collection (index)

        Returns:
            Dictionary with collection information
        """
        await self.ensure_connected()

        try:
            # Check if collection exists first
            if not await self.collection_exists(collection_name):
                logger.warning(f"Index {collection_name} does not exist")
                return {'error': 'Index not found', 'name': collection_name}

            index_desc = self._client.describe_index(collection_name)

            # Get or create index reference to get stats
            if not self._index or self._index._config.index_name != collection_name:
                self._index = self._client.Index(collection_name)

            stats = self._index.describe_index_stats()

            return {
                'name': collection_name,
                'dimension': index_desc.dimension,
                'metric': index_desc.metric,
                'count': stats.get('total_vector_count', 0),
                'metadata': {
                    'dimension': index_desc.dimension,
                    'host': index_desc.host,
                    'status': index_desc.status
                }
            }

        except Exception as e:
            logger.error(f"Error getting Pinecone index info: {e}")
            return {'error': str(e), 'name': collection_name}

    async def similarity_search_with_threshold(self,
                                              query_vector: List[float],
                                              threshold: float,
                                              limit: int = 10,
                                              collection_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for similar vectors with a minimum similarity threshold.

        Args:
            query_vector: Query vector
            threshold: Minimum similarity threshold
            limit: Maximum number of results
            collection_name: Name of the collection (index)

        Returns:
            List of results above threshold
        """
        results = await self.search_vectors(query_vector, limit, collection_name)
        return [r for r in results if r['score'] >= threshold]
