"""
Qdrant store implementation for vector operations.
"""

import logging
from typing import Dict, Any, Optional, List

from ..base.base_vector_store import BaseVectorStore
from ..base.base_store import StoreConfig, StoreStatus

logger = logging.getLogger(__name__)


class QdrantStore(BaseVectorStore):
    """
    Qdrant store implementation providing vector storage and similarity search.

    This implementation provides:
    - Vector storage and retrieval
    - Similarity search with various distance metrics
    - Collection management
    - Metadata filtering and search
    - Support for local and cloud-based Qdrant instances
    - Optimized HNSW indexing and scalar quantization
    """

    def __init__(self, config: StoreConfig):
        """
        Initialize Qdrant store.

        Args:
            config: Store configuration
        """
        super().__init__(config)

        # Qdrant-specific configuration
        self.host = config.connection_params.get('host', 'localhost')
        self.port = config.connection_params.get('port', 6333)
        self.api_key = config.connection_params.get('api_key')
        self.prefer_grpc = config.connection_params.get('prefer_grpc', False)
        self.https = config.connection_params.get('https', False)

        # Connection and state
        self._client = None
        self._collections_cache = None  # Cache for collection list
        self._cache_timestamp = None  # Cache timestamp

    async def connect(self) -> bool:
        """
        Establish connection to Qdrant.

        Returns:
            True if connection successful, False otherwise
        """
        if self.status == StoreStatus.CONNECTED:
            return True

        self.status = StoreStatus.CONNECTING

        try:
            from qdrant_client import QdrantClient

            # Convert port to int if it's a string
            port = self.port
            if isinstance(port, str):
                try:
                    port = int(port)
                except ValueError:
                    logger.warning(f"Invalid port value '{port}', using default 6333")
                    port = 6333

            # Initialize Qdrant client
            init_kwargs = {
                'host': self.host,
                'port': port,
                'timeout': self.config.timeout or 60,
                'prefer_grpc': self.prefer_grpc,
                'https': self.https
            }

            # Add API key if provided
            if self.api_key:
                init_kwargs['api_key'] = self.api_key

            self._client = QdrantClient(**init_kwargs)

            # Test connection by getting collection list
            self._client.get_collections()

            self.status = StoreStatus.CONNECTED
            logger.info(f"Qdrant store {self.config.name} connected successfully to {self.host}:{port}")
            return True

        except ImportError:
            logger.error("Qdrant client not available. Install with: pip install qdrant-client")
            self.status = StoreStatus.ERROR
            return False
        except Exception as e:
            logger.error(f"Error connecting to Qdrant: {e}")
            self.status = StoreStatus.ERROR
            return False

    async def disconnect(self) -> None:
        """Close Qdrant connection and cleanup resources."""
        if self._client:
            try:
                # Qdrant client doesn't require explicit disconnection
                self._client = None
                self.status = StoreStatus.DISCONNECTED
                logger.info(f"Qdrant store {self.config.name} disconnected")

            except Exception as e:
                logger.error(f"Error disconnecting from Qdrant: {e}")
                self.status = StoreStatus.ERROR

    async def health_check(self) -> bool:
        """
        Check if Qdrant connection is healthy.

        Returns:
            True if healthy, False otherwise
        """
        try:
            if not self._client:
                return False

            # Just check if client is connected - don't list collections
            # The client connection was already verified in connect()
            return True

        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            return False

    async def add_vectors(self,
                         vectors: List[List[float]],
                         ids: List[str],
                         metadata: Optional[List[Dict[str, Any]]] = None,
                         collection_name: Optional[str] = None) -> bool:
        """
        Add vectors to Qdrant collection.

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

        try:
            from qdrant_client.models import PointStruct

            collection_name = collection_name or self._default_collection

            # Check if collection exists, create if not
            if not await self.collection_exists(collection_name):
                # Get dimension from first vector
                dimension = len(vectors[0]) if vectors else 768
                logger.info(f"Creating Qdrant collection {collection_name} with dimension {dimension}")
                await self.create_collection(collection_name, dimension)

            # Prepare points for upsert
            points = []
            for i, (vector_id, vector) in enumerate(zip(ids, vectors)):
                # Qdrant requires integer IDs or UUIDs, but we use string IDs
                # We'll use hash of the string ID for the point ID
                point_id = abs(hash(vector_id)) % (10 ** 10)  # Use positive integer ID

                payload = metadata[i] if metadata and i < len(metadata) else {}
                # Store the original string ID in the payload for retrieval
                payload['_original_id'] = vector_id

                point = PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload
                )
                points.append(point)

            # Upsert points to Qdrant
            self._client.upsert(
                collection_name=collection_name,
                points=points
            )

            logger.debug(f"Added {len(vectors)} vectors to Qdrant collection {collection_name}")
            return True

        except Exception as e:
            logger.error(f"Error adding vectors to Qdrant: {e}")
            return False

    async def search_vectors(self,
                           query_vector: List[float],
                           limit: int = 10,
                           collection_name: Optional[str] = None,
                           filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Search for similar vectors in Qdrant.

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

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            collection_name = collection_name or self._default_collection

            # Build filter if metadata filters provided
            search_filter = None
            if filter_metadata:
                conditions = []
                for key, value in filter_metadata.items():
                    conditions.append(
                        FieldCondition(
                            key=key,
                            match=MatchValue(value=value)
                        )
                    )
                search_filter = Filter(must=conditions) if conditions else None

            # Perform search
            search_results = self._client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                query_filter=search_filter,
                with_payload=True
            )

            # Format results
            results = []
            for result in search_results:
                # Extract the original ID from payload
                original_id = result.payload.get('_original_id', str(result.id))
                # Remove internal fields from metadata
                metadata = {k: v for k, v in result.payload.items() if not k.startswith('_')}

                results.append({
                    'id': original_id,
                    'score': result.score,
                    'metadata': metadata
                })

            return results

        except Exception as e:
            logger.error(f"Error searching vectors in Qdrant: {e}")
            return []

    async def get_vector(self,
                        vector_id: str,
                        collection_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get a specific vector by ID from Qdrant.

        Args:
            vector_id: ID of the vector to retrieve
            collection_name: Name of the collection

        Returns:
            Vector data with metadata or None if not found
        """
        await self.ensure_connected()
        self.update_access_time()

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            collection_name = collection_name or self._default_collection

            # Search by the original ID stored in payload
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="_original_id",
                        match=MatchValue(value=vector_id)
                    )
                ]
            )

            # Retrieve points matching the ID
            results = self._client.scroll(
                collection_name=collection_name,
                scroll_filter=search_filter,
                limit=1,
                with_payload=True,
                with_vectors=True
            )

            if results and results[0]:
                point = results[0][0]  # First result from first batch
                # Remove internal fields from metadata
                metadata = {k: v for k, v in point.payload.items() if not k.startswith('_')}

                return {
                    'id': vector_id,
                    'vector': point.vector,
                    'metadata': metadata
                }

            return None

        except Exception as e:
            logger.error(f"Error getting vector from Qdrant: {e}")
            return None

    async def update_vector(self,
                           vector_id: str,
                           vector: Optional[List[float]] = None,
                           metadata: Optional[Dict[str, Any]] = None,
                           collection_name: Optional[str] = None) -> bool:
        """
        Update a vector and/or its metadata in Qdrant.

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

        try:
            from qdrant_client.models import PointStruct

            collection_name = collection_name or self._default_collection

            # Get the numeric ID for this vector
            point_id = abs(hash(vector_id)) % (10 ** 10)

            # If updating vector, need to provide both vector and payload
            if vector:
                payload = metadata or {}
                payload['_original_id'] = vector_id

                point = PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload
                )

                self._client.upsert(
                    collection_name=collection_name,
                    points=[point]
                )
            elif metadata:
                # Update only metadata (payload)
                payload = metadata.copy()
                payload['_original_id'] = vector_id

                self._client.set_payload(
                    collection_name=collection_name,
                    payload=payload,
                    points=[point_id]
                )

            logger.debug(f"Updated vector {vector_id} in Qdrant collection {collection_name}")
            return True

        except Exception as e:
            logger.error(f"Error updating vector in Qdrant: {e}")
            return False

    async def delete_vector(self,
                           vector_id: str,
                           collection_name: Optional[str] = None) -> bool:
        """
        Delete a vector from Qdrant.

        Args:
            vector_id: ID of the vector to delete
            collection_name: Name of the collection

        Returns:
            True if successful, False otherwise
        """
        await self.ensure_connected()
        self.update_access_time()

        try:
            collection_name = collection_name or self._default_collection

            # Get the numeric ID for this vector
            point_id = abs(hash(vector_id)) % (10 ** 10)

            self._client.delete(
                collection_name=collection_name,
                points_selector=[point_id]
            )

            logger.debug(f"Deleted vector {vector_id} from Qdrant collection {collection_name}")
            return True

        except Exception as e:
            logger.error(f"Error deleting vector from Qdrant: {e}")
            return False

    async def list_collections(self) -> List[str]:
        """
        List all collections in Qdrant.

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
            collections = self._client.get_collections()
            collection_names = [col.name for col in collections.collections]

            # Update cache
            self._collections_cache = collection_names
            self._cache_timestamp = time.time()

            return collection_names
        except Exception as e:
            logger.error(f"Error listing Qdrant collections: {e}")
            return []

    async def collection_exists(self, collection_name: str) -> bool:
        """
        Check if a collection exists in Qdrant.

        Args:
            collection_name: Name of the collection to check

        Returns:
            True if exists, False otherwise
        """
        await self.ensure_connected()

        try:
            # Try to get the specific collection directly instead of listing all
            self._client.get_collection(collection_name)
            return True
        except Exception:
            # Collection doesn't exist or error occurred
            return False

    async def create_collection(self,
                               collection_name: str,
                               dimension: int,
                               distance_metric: str = 'cosine') -> bool:
        """
        Create a new collection in Qdrant.

        Args:
            collection_name: Name of the collection to create
            dimension: Dimension of the vectors
            distance_metric: Distance metric to use (cosine, l2, or dot)

        Returns:
            True if successful, False otherwise
        """
        await self.ensure_connected()

        try:
            from qdrant_client.models import Distance, VectorParams, HnswConfigDiff, ScalarQuantization, ScalarQuantizationConfig, ScalarType
            from qdrant_client.http import models

            # Check if collection already exists
            if await self.collection_exists(collection_name):
                logger.info(f"Qdrant collection {collection_name} already exists")
                return True

            # Map distance metric to Qdrant Distance enum
            distance_map = {
                'cosine': Distance.COSINE,
                'l2': Distance.EUCLID,
                'dot': Distance.DOT,
                'euclidean': Distance.EUCLID,
                'ip': Distance.DOT
            }
            qdrant_distance = distance_map.get(distance_metric.lower(), Distance.COSINE)

            # Create collection with optimized configuration
            self._client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=dimension,
                    distance=qdrant_distance,
                    on_disk=True  # Use on-disk storage for larger datasets
                ),
                # HNSW config for tuning performance-accuracy trade-off
                hnsw_config=HnswConfigDiff(
                    m=16,  # Number of bi-directional links for each new element
                    ef_construct=100  # Number of candidates for best neighbors search
                ),
                # Scalar quantization for memory optimization
                quantization_config=ScalarQuantization(
                    scalar=ScalarQuantizationConfig(
                        type=ScalarType.INT8,
                        quantile=0.99,  # Use 99th percentile for quantization
                        always_ram=True  # Keep quantized vectors in RAM
                    )
                )
            )

            # Invalidate cache
            self._collections_cache = None
            self._cache_timestamp = None

            logger.info(f"Created Qdrant collection {collection_name}")
            return True

        except Exception as e:
            logger.error(f"Error creating Qdrant collection: {e}")
            return False

    async def delete_collection(self, collection_name: str) -> bool:
        """
        Delete a collection from Qdrant.

        Args:
            collection_name: Name of the collection to delete

        Returns:
            True if successful, False otherwise
        """
        await self.ensure_connected()

        try:
            if await self.collection_exists(collection_name):
                self._client.delete_collection(collection_name)

                # Invalidate cache
                self._collections_cache = None
                self._cache_timestamp = None

                logger.info(f"Deleted Qdrant collection {collection_name}")
                return True
            else:
                logger.warning(f"Qdrant collection {collection_name} does not exist")
                return False

        except Exception as e:
            logger.error(f"Error deleting Qdrant collection: {e}")
            return False

    async def clear_collection(self, collection_name: str) -> bool:
        """
        Clear all vectors from a collection in Qdrant.

        Args:
            collection_name: Name of the collection to clear

        Returns:
            True if successful, False otherwise
        """
        await self.ensure_connected()

        try:
            from qdrant_client.models import FilterSelector

            # Delete all points in the collection
            self._client.delete(
                collection_name=collection_name,
                points_selector=FilterSelector(
                    filter=None  # No filter = delete all
                )
            )

            logger.info(f"Cleared Qdrant collection {collection_name}")
            return True

        except Exception as e:
            logger.error(f"Error clearing Qdrant collection: {e}")
            return False

    async def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        """
        Get information about a Qdrant collection.

        Args:
            collection_name: Name of the collection

        Returns:
            Dictionary with collection information
        """
        await self.ensure_connected()

        try:
            # Check if collection exists first
            if not await self.collection_exists(collection_name):
                logger.warning(f"Collection {collection_name} does not exist")
                return {'error': 'Collection not found', 'name': collection_name}

            collection_info = self._client.get_collection(collection_name)

            return {
                'name': collection_name,
                'dimension': collection_info.config.params.vectors.size,
                'metric': collection_info.config.params.vectors.distance.name,
                'count': collection_info.points_count,
                'metadata': {
                    'dimension': collection_info.config.params.vectors.size,
                    'status': collection_info.status.name,
                    'optimizer_status': collection_info.optimizer_status.name if collection_info.optimizer_status else 'unknown'
                }
            }

        except Exception as e:
            logger.error(f"Error getting Qdrant collection info: {e}")
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
            collection_name: Name of the collection

        Returns:
            List of results above threshold
        """
        results = await self.search_vectors(query_vector, limit, collection_name)
        return [r for r in results if r['score'] >= threshold]
