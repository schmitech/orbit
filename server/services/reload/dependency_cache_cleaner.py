"""
Dependency Cache Cleaner for clearing provider/embedding/reranker caches.

Manages resource cleanup when adapter configurations change.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DependencyCacheCleaner:
    """
    Clears provider/embedding/reranker caches when adapters change.

    Responsibilities:
    - Clear provider/embedding/reranker caches
    - Handle cache key construction consistently
    - Manage resource cleanup
    """

    def __init__(
        self,
        config: Dict[str, Any],
        provider_cache,
        embedding_cache,
        reranker_cache,
        vision_cache=None,
        audio_cache=None
    ):
        """
        Initialize the dependency cache cleaner.

        Args:
            config: Application configuration
            provider_cache: Provider cache manager
            embedding_cache: Embedding cache manager
            reranker_cache: Reranker cache manager
            vision_cache: Vision cache manager (optional for backward compatibility)
            audio_cache: Audio cache manager (optional for backward compatibility)
        """
        self.config = config
        self.provider_cache = provider_cache
        self.embedding_cache = embedding_cache
        self.reranker_cache = reranker_cache
        self.vision_cache = vision_cache
        self.audio_cache = audio_cache

    async def clear_adapter_dependencies(
        self,
        adapter_name: str,
        adapter_config: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """
        Clear all provider/embedding/reranker caches for an adapter.

        Args:
            adapter_name: Name of the adapter
            adapter_config: Configuration of the adapter

        Returns:
            List of cleared cache descriptions
        """
        if not adapter_config:
            logger.debug(f"No config found for adapter '{adapter_name}', skipping dependency cache clearing")
            return []

        cleared_caches = []

        # Clear inference provider cache
        provider_caches = await self._clear_provider_cache(adapter_config)
        cleared_caches.extend(provider_caches)

        # Clear embedding cache
        embedding_caches = await self._clear_embedding_cache(adapter_config)
        cleared_caches.extend(embedding_caches)

        # Clear reranker cache
        reranker_caches = await self._clear_reranker_cache(adapter_config)
        cleared_caches.extend(reranker_caches)

        # Clear vision cache
        vision_caches = await self._clear_vision_cache(adapter_config)
        cleared_caches.extend(vision_caches)

        # Clear audio cache
        audio_caches = await self._clear_audio_cache(adapter_config)
        cleared_caches.extend(audio_caches)

        if cleared_caches:
            logger.info(f"Cleared dependency caches for adapter '{adapter_name}': {', '.join(cleared_caches)}")
            provider_count = sum(1 for c in cleared_caches if c.startswith("provider:"))
            embedding_count = sum(1 for c in cleared_caches if c.startswith("embedding:"))
            reranker_count = sum(1 for c in cleared_caches if c.startswith("reranker:"))
            vision_count = sum(1 for c in cleared_caches if c.startswith("vision:"))
            audio_count = sum(1 for c in cleared_caches if c.startswith("audio:"))
            logger.debug(
                "Cache clearing summary for '%s': %s provider(s), %s embedding(s), "
                "%s reranker(s), %s vision, %s audio",
                adapter_name,
                provider_count,
                embedding_count,
                reranker_count,
                vision_count,
                audio_count,
            )
        else:
            logger.debug(f"No dependency caches to clear for adapter '{adapter_name}'")

        return cleared_caches

    async def _clear_provider_cache(self, adapter_config: Dict[str, Any]) -> List[str]:
        """
        Clear provider cache entries for an adapter configuration.

        Args:
            adapter_config: Adapter configuration

        Returns:
            List of cleared cache descriptions
        """
        cleared = []
        old_provider = adapter_config.get('inference_provider')
        old_model = adapter_config.get('model')

        if not old_provider:
            return cleared

        # Build cache key using the cache manager's method for consistency
        cache_key = self.provider_cache.build_cache_key(old_provider, old_model)

        # Try exact match first
        if self.provider_cache.contains(cache_key):
            await self.provider_cache.remove(cache_key)
            cleared.append(f"provider:{cache_key}")
        else:
            # Fallback: clear all variants of this provider
            removed_keys = await self.provider_cache.remove_by_prefix(old_provider)
            for key in removed_keys:
                cleared.append(f"provider:{key}")

            if removed_keys:
                logger.debug(f"Cleared provider cache variants for '{old_provider}': {removed_keys}")

        return cleared

    async def _clear_embedding_cache(self, adapter_config: Dict[str, Any]) -> List[str]:
        """
        Clear embedding cache entries for an adapter configuration.

        Args:
            adapter_config: Adapter configuration

        Returns:
            List of cleared cache descriptions
        """
        cleared = []
        old_embedding_provider = adapter_config.get('embedding_provider')

        if not old_embedding_provider:
            return cleared

        # Build cache key the same way as in embedding cache manager
        cache_key = self.embedding_cache.build_cache_key(old_embedding_provider)

        if self.embedding_cache.contains(cache_key):
            await self.embedding_cache.remove(cache_key)
            cleared.append(f"embedding:{cache_key}")

        return cleared

    async def _clear_reranker_cache(self, adapter_config: Dict[str, Any]) -> List[str]:
        """
        Clear reranker cache entries for an adapter configuration.

        Args:
            adapter_config: Adapter configuration

        Returns:
            List of cleared cache descriptions
        """
        cleared = []
        old_reranker_provider = adapter_config.get('reranker_provider')

        if not old_reranker_provider:
            return cleared

        # Build cache key the same way as in reranker cache manager
        cache_key = self.reranker_cache.build_cache_key(old_reranker_provider)

        if self.reranker_cache.contains(cache_key):
            await self.reranker_cache.remove(cache_key)
            cleared.append(f"reranker:{cache_key}")

        return cleared

    async def _clear_vision_cache(self, adapter_config: Dict[str, Any]) -> List[str]:
        """
        Clear vision cache entries for an adapter configuration.

        Args:
            adapter_config: Adapter configuration

        Returns:
            List of cleared cache descriptions
        """
        cleared = []
        old_vision_provider = adapter_config.get('vision_provider')

        if not old_vision_provider or not self.vision_cache:
            return cleared

        # Build cache key the same way as in vision cache manager
        cache_key = self.vision_cache.build_cache_key(old_vision_provider)

        if self.vision_cache.contains(cache_key):
            await self.vision_cache.remove(cache_key)
            cleared.append(f"vision:{cache_key}")

        return cleared

    async def _clear_audio_cache(self, adapter_config: Dict[str, Any]) -> List[str]:
        """
        Clear audio cache entries for an adapter configuration.

        Args:
            adapter_config: Adapter configuration

        Returns:
            List of cleared cache descriptions
        """
        cleared = []
        old_audio_provider = adapter_config.get('audio_provider')

        if not old_audio_provider or not self.audio_cache:
            return cleared

        # Build cache key the same way as in audio cache manager
        cache_key = self.audio_cache.build_cache_key(old_audio_provider)

        if self.audio_cache.contains(cache_key):
            await self.audio_cache.remove(cache_key)
            cleared.append(f"audio:{cache_key}")

        return cleared

    def update_config(self, config: Dict[str, Any]) -> None:
        """
        Update the configuration reference.

        Args:
            config: New configuration dictionary
        """
        self.config = config
