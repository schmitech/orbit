"""
Thread Dataset Service
======================

This service handles storage and retrieval of datasets for conversation threads.
Supports the configured cache service (Redis, Memcached, ...) with TTL as primary
storage, with fallback to SQLite/MongoDB.

Datasets are stored separately from query context for efficient retrieval.
"""

import logging
import json
import gzip
import threading
import hashlib
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, UTC

from services.cache_backends import CacheProvider, create_cache_service
from services.database_service import create_database_service

logger = logging.getLogger(__name__)


class ThreadDatasetService:
    """Service for storing and retrieving thread datasets with singleton pattern"""
    
    # Singleton pattern implementation
    _instances: Dict[str, 'ThreadDatasetService'] = {}
    _lock = threading.Lock()
    
    def __new__(cls, config: Dict[str, Any], cache_service: Optional['CacheProvider'] = None):
        """Create or return existing ThreadDatasetService instance based on configuration"""
        cache_key = cls._create_cache_key(config)
        
        with cls._lock:
            if cache_key not in cls._instances:
                instance = super().__new__(cls)
                cls._instances[cache_key] = instance
                logger.debug(f"Created new ThreadDatasetService instance for: {cache_key}")
            else:
                logger.debug(f"Reusing existing ThreadDatasetService instance for: {cache_key}")
            return cls._instances[cache_key]
    
    @staticmethod
    def _uses_cache_backend(threading_config: Dict[str, Any]) -> bool:
        return threading_config.get('storage_backend', 'cache') == 'cache'

    @classmethod
    def _create_cache_key(cls, config: Dict[str, Any]) -> str:
        """Create a cache key based on threading configuration"""
        threading_config = config.get('conversation_threading', {})

        # Create key from configuration parameters
        key_parts = [
            str(threading_config.get('enabled', True)),
            str(threading_config.get('dataset_ttl_hours', 24)),
            threading_config.get('storage_backend', 'cache'),
            threading_config.get('cache_key_prefix', 'thread_dataset:'),
        ]

        # Include cache provider connection details if using the cache backend
        if cls._uses_cache_backend(threading_config):
            from services.cache_backends import get_provider_config
            _, provider_config = get_provider_config(config)
            key_parts.extend([
                provider_config.get('host', provider_config.get('database_path', 'localhost')),
                str(provider_config.get('port', '')),
                str(provider_config.get('db', 0)),
            ])
        
        # Create hash of the key parts for consistency
        key_string = '|'.join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    @classmethod
    def get_cache_stats(cls) -> Dict[str, Any]:
        """Get statistics about cached ThreadDatasetService instances"""
        with cls._lock:
            return {
                'total_cached_instances': len(cls._instances),
                'cached_configurations': list(cls._instances.keys()),
                'memory_info': f"{len(cls._instances)} ThreadDatasetService instances cached"
            }
    
    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached instances (useful for testing)"""
        with cls._lock:
            cls._instances.clear()
            logger.debug("Cleared all ThreadDatasetService cached instances")

    def __init__(self, config: Dict[str, Any], cache_service: Optional['CacheProvider'] = None):
        """
        Initialize the thread dataset service.

        Args:
            config: Application configuration
            cache_service: Optional pre-initialized cache provider (avoids creating duplicates)
        """
        # Guard against re-initialization (singleton pattern - __init__ is called even when __new__ returns existing instance)
        if hasattr(self, '_singleton_initialized') and self._singleton_initialized:
            logger.debug("ThreadDatasetService already initialized (singleton), skipping re-initialization")
            return

        self.config = config

        # Threading configuration
        threading_config = config.get('conversation_threading', {})
        self.enabled = threading_config.get('enabled', True)
        self.dataset_ttl_hours = threading_config.get('dataset_ttl_hours', 24)
        self.storage_backend = threading_config.get('storage_backend', 'cache')
        self.uses_cache = self._uses_cache_backend(threading_config)
        self.cache_key_prefix = threading_config.get('cache_key_prefix', 'thread_dataset:')

        # Initialize services - set to None first to avoid AttributeError
        self.cache_service = None
        self.database_service = None

        # Initialize the cache service (if threading is enabled and storage backend is the cache)
        if self.enabled and self.uses_cache:
            try:
                # Use provided cache_service or create new one (singleton pattern ensures reuse)
                self.cache_service = cache_service if cache_service is not None else create_cache_service(config)
                if self.cache_service.enabled:
                    logger.debug(f"✓ ThreadDatasetService: cache storage enabled (key prefix: {self.cache_key_prefix})")
                else:
                    logger.warning(
                        "Cache is disabled - please enable caching (internal_services.cache.enabled) to use "
                        "cache-backed conversation threading. Will fall back to database storage."
                    )
            except Exception as e:
                logger.warning(f"Failed to initialize cache service: {e}. Will fall back to database storage if the cache doesn't become available.")

        # Always initialize database service as fallback (even when using the cache service)
        # This ensures we can fall back if the cache becomes unavailable
        try:
            self.database_service = create_database_service(config)
        except Exception as e:
            logger.error(f"Failed to initialize database service: {e}")
            self.database_service = None

        # Always log initialization status for verification
        db_fallback_status = f", database_fallback={'available' if self.database_service else 'unavailable'}"
        if self.uses_cache:
            cache_status = 'enabled' if (self.cache_service and self.cache_service.enabled) else 'not yet enabled'
            logger.info(f"ThreadDatasetService initialized: storage_backend=cache ({cache_status}), ttl={self.dataset_ttl_hours}h{db_fallback_status}")
        else:
            logger.info(f"ThreadDatasetService initialized: storage_backend={self.storage_backend}, ttl={self.dataset_ttl_hours}h{db_fallback_status}")

        # Mark as initialized to prevent re-initialization
        self._singleton_initialized = True

    async def initialize(self) -> None:
        """Initialize the service and its dependencies."""
        if not self.enabled:
            return

        # Prevent re-initialization of singleton instances
        if hasattr(self, '_singleton_initialized') and self._singleton_initialized:
            # Check if async initialization has been done
            if hasattr(self, '_async_initialized'):
                return
            # Otherwise continue to async initialization

        # Initialize the cache service if using it
        if self.cache_service:
            await self.cache_service.initialize()

        # Initialize database if using it
        if self.database_service:
            await self.database_service.initialize()

        # Mark async initialization as complete
        self._async_initialized = True

    def _generate_dataset_key(self, thread_id: str) -> str:
        """Generate a unique dataset key for a thread."""
        if self.uses_cache:
            return f"{self.cache_key_prefix}{thread_id}"
        else:
            return f"thread_dataset_{thread_id}"

    def _compress_data(self, data: Dict[str, Any]) -> bytes:
        """Compress data using gzip for efficient storage."""
        json_str = json.dumps(data, default=str)
        return gzip.compress(json_str.encode('utf-8'))

    def _decompress_data(self, compressed_data: bytes) -> Dict[str, Any]:
        """Decompress data from gzip."""
        json_str = gzip.decompress(compressed_data).decode('utf-8')
        return json.loads(json_str)

    async def store_dataset(
        self,
        thread_id: str,
        query_context: Dict[str, Any],
        raw_results: list
    ) -> str:
        """
        Store a dataset for a thread.

        Args:
            thread_id: Unique thread identifier
            query_context: Query context (original query, parameters, template_id)
            raw_results: Raw results from the retriever

        Returns:
            Dataset key for retrieval
        """
        if not self.enabled:
            raise RuntimeError("Thread dataset service is not enabled")

        dataset_key = self._generate_dataset_key(thread_id)
        
        # Prepare dataset structure
        dataset = {
            'thread_id': thread_id,
            'query_context': query_context,
            'raw_results': raw_results,
            'stored_at': datetime.now(UTC).isoformat()
        }

        # Calculate expiration time
        expires_at = datetime.now(UTC) + timedelta(hours=self.dataset_ttl_hours)
        ttl_seconds = int(self.dataset_ttl_hours * 3600)

        try:
            if self.uses_cache and self.cache_service and self.cache_service.enabled:
                # Store in the cache service with TTL
                compressed = self._compress_data(dataset)
                # Binary payloads need base64 encoding for string-based cache backends
                import base64
                encoded = base64.b64encode(compressed).decode('utf-8')
                await self.cache_service.set(dataset_key, encoded, ttl=ttl_seconds)
                
                # Always log cache storage for verification
                logger.debug(f"✓ Stored dataset for thread {thread_id} in cache (key: {dataset_key}, TTL: {ttl_seconds}s, results: {len(raw_results)} items)")
                
                logger.debug(f"Dataset structure: query_context keys={list(query_context.keys())}, raw_results count={len(raw_results)}")
            else:
                # Store in database
                if not self.database_service:
                    raise RuntimeError("Database service not available for dataset storage")
                
                # Store as JSON in a special collection/table
                collection_name = 'thread_datasets'
                document = {
                    'id': dataset_key,
                    'thread_id': str(thread_id),  # Convert to string for SQLite compatibility
                    'dataset_json': json.dumps(dataset, default=str),
                    'expires_at': expires_at.isoformat(),
                    'created_at': datetime.now(UTC).isoformat()
                }

                # Upsert: a dataset_key can be re-stored (e.g. per-turn generation
                # memory overwriting the prior turn), so update in place if a row
                # already exists rather than blindly inserting and hitting the
                # unique constraint on 'id'. Two concurrent stores for the same key
                # can both miss the update and race to insert; the loser's insert
                # fails (raises on sqlite/postgres, returns None on Mongo), so on
                # either failure mode retry as an update now that the winner's row
                # exists — this is what makes the last writer's data win instead of
                # silently dropping the loser's turn.
                updated = await self.database_service.update_one(
                    collection_name, {'id': dataset_key}, {'$set': document}
                )
                if not updated:
                    insert_error = None
                    try:
                        inserted_id = await self.database_service.insert_one(collection_name, document)
                        insert_failed = inserted_id is None
                    except Exception as e:
                        insert_failed = True
                        insert_error = e
                    if insert_failed and not await self.database_service.update_one(
                        collection_name, {'id': dataset_key}, {'$set': document}
                    ):
                        raise insert_error or RuntimeError(f"Failed to store dataset {dataset_key}: insert returned no id")
                
                logger.debug(f"Stored dataset for thread {thread_id} in database (expires: {expires_at})")
            
            return dataset_key

        except Exception as e:
            logger.error(f"Failed to store dataset for thread {thread_id}: {e}")
            raise

    async def get_dataset(self, dataset_key: str) -> Optional[Tuple[Dict[str, Any], list]]:
        """
        Retrieve a dataset by key.

        Args:
            dataset_key: Dataset key from store_dataset()

        Returns:
            Tuple of (query_context, raw_results) or None if not found/expired
        """
        if not self.enabled:
            return None

        try:
            if self.uses_cache and self.cache_service and self.cache_service.enabled:
                # Retrieve from the cache service
                encoded = await self.cache_service.get(dataset_key)
                if not encoded:
                    logger.debug(f"Dataset {dataset_key} not found in cache (may have expired)")
                    return None
                
                # Decode and decompress
                import base64
                compressed = base64.b64decode(encoded.encode('utf-8'))
                dataset = self._decompress_data(compressed)
                
                # Log successful retrieval for verification
                logger.debug(f"✓ Retrieved dataset {dataset_key} from cache (results: {len(dataset.get('raw_results', []))} items)")
                
            else:
                # Retrieve from database
                if not self.database_service:
                    return None
                
                collection_name = 'thread_datasets'
                document = await self.database_service.find_one(
                    collection_name,
                    {'id': dataset_key}
                )
                
                if not document:
                    logger.debug(f"Dataset {dataset_key} not found in database")
                    return None
                
                # Check expiration
                expires_at_str = document.get('expires_at')
                if expires_at_str:
                    expires_at = datetime.fromisoformat(expires_at_str)
                    if datetime.now(UTC) > expires_at:
                        logger.debug(f"Dataset {dataset_key} has expired")
                        # Delete expired dataset
                        await self.delete_dataset(dataset_key)
                        return None
                
                # Parse dataset JSON
                dataset_json = document.get('dataset_json')
                if not dataset_json:
                    return None
                dataset = json.loads(dataset_json)
            
            # Extract query context and raw results
            query_context = dataset.get('query_context', {})
            raw_results = dataset.get('raw_results', [])
            
            logger.debug(f"Retrieved dataset {dataset_key} with {len(raw_results)} results")
            
            return (query_context, raw_results)

        except Exception as e:
            logger.error(f"Failed to retrieve dataset {dataset_key}: {e}")
            return None

    async def delete_dataset(self, dataset_key: str) -> bool:
        """
        Delete a dataset by key.

        Args:
            dataset_key: Dataset key to delete

        Returns:
            True if deleted, False otherwise
        """
        if not self.enabled:
            return False

        try:
            # Debug logging to identify why the cache path is not being used (INFO level for troubleshooting)
            logger.debug(f"delete_dataset: storage_backend={self.storage_backend}, cache_service={'exists' if self.cache_service else 'None'}, cache_enabled={self.cache_service.enabled if self.cache_service else 'N/A'}")

            # Match the storage logic: try the cache service first if configured and enabled, otherwise use database
            if self.uses_cache and self.cache_service and self.cache_service.enabled:
                # Delete from the cache service
                deleted_count = await self.cache_service.delete(dataset_key)
                deleted = deleted_count > 0

                # Always log deletion result for verification
                if deleted:
                    logger.debug(f"✓ Deleted dataset {dataset_key} from cache (deleted_count: {deleted_count})")
                else:
                    logger.warning(f"Dataset {dataset_key} not found in cache (deleted_count: {deleted_count})")

                return deleted
            else:
                # Fallback to database (matches store_dataset behavior)
                if not self.database_service:
                    logger.warning(f"Cannot delete dataset {dataset_key}: database service not available")
                    return False

                collection_name = 'thread_datasets'
                result = await self.database_service.delete_one(
                    collection_name,
                    {'id': dataset_key}
                )

                if result:
                    logger.debug(f"Deleted dataset {dataset_key} from database")

                return result

        except Exception as e:
            logger.error(f"Failed to delete dataset {dataset_key}: {e}")
            return False

    async def cleanup_expired_datasets(self) -> int:
        """
        Clean up expired datasets from database storage.
        The cache service handles expiration automatically, so this only affects database storage.

        Returns:
            Number of datasets deleted
        """
        if not self.enabled or not self.database_service:
            return 0

        try:
            collection_name = 'thread_datasets'
            now = datetime.now(UTC).isoformat()

            # Find expired datasets
            expired = await self.database_service.find_many(
                collection_name,
                {'expires_at': {'$lt': now}},
                limit=1000
            )
            
            if not expired:
                return 0
            
            # Delete expired datasets
            deleted_count = 0
            for doc in expired:
                result = await self.database_service.delete_one(
                    collection_name,
                    {'id': doc.get('id')}
                )
                if result:
                    deleted_count += 1
            
            if deleted_count > 0:
                logger.debug(f"Cleaned up {deleted_count} expired thread datasets")
            
            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup expired datasets: {e}")
            return 0

    async def close(self) -> None:
        """Close the service and its dependencies."""
        if self.cache_service:
            await self.cache_service.close()
        
        # Database service cleanup is handled by the service itself
