"""
Retriever Cache Manager

Provides singleton caching for retriever instances to avoid repeated initialization.
Caches retrievers based on configuration to ensure proper reuse across requests.
"""

import logging
import hashlib
import json
from typing import Dict, Any
from retrievers.implementations.file.file_retriever import FileVectorRetriever

logger = logging.getLogger(__name__)


class RetrieverCache:
    """
    Singleton cache manager for FileVectorRetriever instances.

    Caches retrievers based on configuration to prevent repeated initialization
    while ensuring different adapters/configurations get separate instances.
    """

    _instance = None
    _cache: Dict[str, FileVectorRetriever] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RetrieverCache, cls).__new__(cls)
            cls._cache = {}
        return cls._instance

    def _get_cache_key(self, config: Dict[str, Any]) -> str:
        """
        Generate a cache key based on relevant configuration parameters.

        Args:
            config: Configuration dictionary

        Returns:
            Cache key string
        """
        # Extract relevant config params that affect retriever behavior
        cache_params = {
            'embedding_provider': config.get('embedding', {}).get('provider', 'ollama'),
            'embedding_model': config.get('embedding', {}).get('model', ''),
            'vector_store': config.get('files', {}).get('default_vector_store', 'chroma'),
            'collection_prefix': config.get('files', {}).get('default_collection_prefix', 'files_'),
            # Include adapter config if present (for adapter-specific settings)
            'adapter_config': config.get('adapter_config', {})
        }

        # Create deterministic hash of config params
        config_str = json.dumps(cache_params, sort_keys=True)
        cache_key = hashlib.md5(config_str.encode()).hexdigest()

        return cache_key

    async def get_retriever(self, config: Dict[str, Any]) -> FileVectorRetriever:
        """
        Get or create a FileVectorRetriever instance.

        Args:
            config: Configuration dictionary

        Returns:
            Cached or new FileVectorRetriever instance
        """
        cache_key = self._get_cache_key(config)

        # Check if retriever already exists in cache
        if cache_key in self._cache:
            retriever = self._cache[cache_key]
            # Ensure it's initialized (should already be, but check just in case)
            if not retriever.initialized:
                await retriever.initialize()
            logger.debug(f"Reusing cached FileVectorRetriever (cache_key: {cache_key[:8]}...)")
            return retriever

        # Create new retriever instance
        logger.info(f"Creating new FileVectorRetriever (cache_key: {cache_key[:8]}...)")
        retriever = FileVectorRetriever(config=config)
        await retriever.initialize()

        # Cache for future use
        self._cache[cache_key] = retriever
        logger.debug(f"Cached FileVectorRetriever (total cached: {len(self._cache)})")

        return retriever

    def clear_cache(self) -> None:
        """Clear all cached retrievers."""
        logger.info(f"Clearing retriever cache ({len(self._cache)} instances)")
        self._cache.clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        return {
            'cached_retrievers': len(self._cache),
            'cache_keys': [key[:8] + '...' for key in self._cache.keys()]
        }


# Global singleton instance
_retriever_cache = RetrieverCache()


def get_retriever_cache() -> RetrieverCache:
    """Get the global RetrieverCache singleton instance."""
    return _retriever_cache
