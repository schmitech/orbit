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
        # Cloud mode: use 'url' parameter (e.g., https://xxx.cloud.qdrant.io:6333)
        # Self-hosted mode: use 'host' + 'port' parameters
        self.url = config.connection_params.get('url')  # For Qdrant Cloud
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

            # Determine connection mode: URL (cloud) vs host:port (self-hosted)
            if self.url:
                # Qdrant Cloud mode - use URL-based connection
                init_kwargs = {
                    'url': self.url,
                    'timeout': self.config.timeout or 60,
                    'prefer_grpc': self.prefer_grpc,
                }
                if self.api_key:
                    init_kwargs['api_key'] = self.api_key

                logger.debug(f"Connecting to Qdrant Cloud at {self.url}")
            else:
                # Self-hosted mode - use host:port connection
                # Convert port to int if it's a string
                port = self.port
                if isinstance(port, str):
                    try:
                        port = int(port)
                    except ValueError:
                        logger.warning(f"Invalid port value '{port}', using default 6333")
                        port = 6333

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
            if self.url:
                logger.debug(f"Qdrant store {self.config.name} connected successfully to {self.url}")
            else:
                logger.debug(f"Qdrant store {self.config.name} connected successfully to {self.host}:{init_kwargs['port']}")
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
                logger.debug(f"Creating Qdrant collection {collection_name} with dimension {dimension}")
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

            # Verify client is initialized
            if self._client is None:
                logger.error("Qdrant client is not initialized")
                return []

            # Check if collection exists before searching
            if not await self.collection_exists(collection_name):
                logger.warning(f"Collection {collection_name} does not exist in Qdrant. Returning empty results.")
                return []

            # Build filter if metadata filters provided
            search_filter = None
            filter_fields = []
            if filter_metadata:
                conditions = []
                for key, value in filter_metadata.items():
                    filter_fields.append(key)
                    conditions.append(
                        FieldCondition(
                            key=key,
                            match=MatchValue(value=value)
                        )
                    )
                search_filter = Filter(must=conditions) if conditions else None

            # Perform search with auto-retry on missing index
            # Note: API changed in qdrant-client v1.16+: search() -> query_points()
            #       and query_vector -> query
            search_results = await self._execute_search_with_index_retry(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                search_filter=search_filter,
                filter_fields=filter_fields
            )

            # Format results
            results = []
            for result in search_results:
                # Extract the original ID from payload
                original_id = result.payload.get('_original_id', str(result.id))

                # Extract document content (try multiple field names)
                document_text = (
                    result.payload.get('content') or
                    result.payload.get('document') or
                    result.payload.get('text') or
                    ''
                )

                # Remove internal fields and content fields from metadata
                # (content should be in separate field, not metadata)
                metadata = {
                    k: v for k, v in result.payload.items()
                    if not k.startswith('_') and k not in ['content', 'document', 'text']
                }

                results.append({
                    'id': original_id,
                    'score': result.score,
                    'metadata': metadata,
                    'text': document_text,  # Include document text
                    'content': document_text  # Also include as 'content' for compatibility
                })

            return results

        except AttributeError as e:
            logger.error(f"Qdrant client attribute error: {e}")
            logger.error(f"Client type: {type(self._client)}, Client is None: {self._client is None}")
            if self._client:
                all_methods = [m for m in dir(self._client) if not m.startswith('_')]
                logger.error(f"Available methods ({len(all_methods)} total): {all_methods}")
                # Check for common search-related methods
                search_methods = [m for m in all_methods if 'search' in m.lower() or 'query' in m.lower() or 'recommend' in m.lower()]
                logger.error(f"Search-related methods: {search_methods}")
            return []
        except Exception as e:
            logger.error(f"Error searching vectors in Qdrant: {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            logger.error(traceback.format_exc())
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

            # Create payload indexes for common filter fields
            # This is required for Qdrant Cloud to filter by these fields
            await self._create_payload_indexes(collection_name)

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

    async def _execute_search_with_index_retry(self,
                                               collection_name: str,
                                               query_vector: List[float],
                                               limit: int,
                                               search_filter: Any,
                                               filter_fields: List[str],
                                               retry_count: int = 0) -> List[Any]:
        """
        Execute search with automatic retry on missing index error.

        If Qdrant Cloud returns a "missing index" error, this method will
        automatically create the required index and retry the search.

        Args:
            collection_name: Name of the collection
            query_vector: Query vector
            limit: Maximum results
            search_filter: Qdrant filter object
            filter_fields: List of field names being filtered
            retry_count: Current retry attempt

        Returns:
            List of search results
        """
        try:
            # Try new API (qdrant-client v1.16+)
            search_results = self._client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=limit,
                query_filter=search_filter,
                with_payload=True
            )
            # Extract points from QueryResponse (v1.16+ returns QueryResponse object)
            if hasattr(search_results, 'points'):
                search_results = search_results.points
            return search_results

        except AttributeError:
            # Fall back to old API (qdrant-client < v1.16)
            logger.debug("Falling back to legacy search() method")
            search_params = {
                'collection_name': collection_name,
                'query_vector': query_vector,
                'limit': limit,
                'with_payload': True
            }
            if search_filter:
                search_params['query_filter'] = search_filter
            return self._client.search(**search_params)

        except Exception as e:
            error_str = str(e)
            # Check if this is a missing index error from Qdrant Cloud
            if 'Index required' in error_str and retry_count < 1:
                logger.info(f"Missing payload index detected, creating indexes for filter fields: {filter_fields}")

                # Create indexes for all filter fields
                for field_name in filter_fields:
                    await self.ensure_payload_index(collection_name, field_name)

                # Retry the search once
                return await self._execute_search_with_index_retry(
                    collection_name=collection_name,
                    query_vector=query_vector,
                    limit=limit,
                    search_filter=search_filter,
                    filter_fields=filter_fields,
                    retry_count=retry_count + 1
                )
            else:
                # Re-raise the exception if it's not an index error or we've already retried
                raise

    async def _create_payload_indexes(self, collection_name: str) -> None:
        """
        Create payload indexes for common filter fields.

        Qdrant Cloud requires payload indexes to filter by fields.
        This creates indexes for commonly used filter fields.

        Args:
            collection_name: Name of the collection
        """
        try:
            from qdrant_client.models import PayloadSchemaType

            # Common fields that are used for filtering
            index_fields = [
                ('file_id', PayloadSchemaType.KEYWORD),
                ('_original_id', PayloadSchemaType.KEYWORD),
                ('source', PayloadSchemaType.KEYWORD),
                ('type', PayloadSchemaType.KEYWORD),
                ('category', PayloadSchemaType.KEYWORD),
                ('adapter_name', PayloadSchemaType.KEYWORD),
            ]

            for field_name, field_type in index_fields:
                try:
                    self._client.create_payload_index(
                        collection_name=collection_name,
                        field_name=field_name,
                        field_schema=field_type
                    )
                    logger.debug(f"Created payload index for '{field_name}' on collection {collection_name}")
                except Exception as e:
                    # Index might already exist or field not present - that's OK
                    if "already exists" not in str(e).lower():
                        logger.debug(f"Could not create index for '{field_name}': {e}")

        except Exception as e:
            logger.warning(f"Error creating payload indexes: {e}")

    async def ensure_payload_index(self,
                                   collection_name: str,
                                   field_name: str,
                                   field_type: str = 'keyword') -> bool:
        """
        Ensure a payload index exists for a specific field.

        Call this method before filtering by a field that might not be indexed.

        Args:
            collection_name: Name of the collection
            field_name: Name of the payload field to index
            field_type: Type of index ('keyword', 'integer', 'float', 'bool', 'text')

        Returns:
            True if index exists or was created, False on error
        """
        await self.ensure_connected()

        try:
            from qdrant_client.models import PayloadSchemaType

            type_map = {
                'keyword': PayloadSchemaType.KEYWORD,
                'integer': PayloadSchemaType.INTEGER,
                'float': PayloadSchemaType.FLOAT,
                'bool': PayloadSchemaType.BOOL,
                'text': PayloadSchemaType.TEXT,
            }

            schema_type = type_map.get(field_type.lower(), PayloadSchemaType.KEYWORD)

            self._client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=schema_type
            )
            logger.debug(f"Created payload index for '{field_name}' on collection {collection_name}")
            return True

        except Exception as e:
            if "already exists" in str(e).lower():
                return True
            logger.warning(f"Error creating payload index for '{field_name}': {e}")
            return False
