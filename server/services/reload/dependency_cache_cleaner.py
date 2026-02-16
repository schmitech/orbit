"""
Dependency Cache Cleaner for clearing provider/embedding/reranker caches.

Manages resource cleanup when adapter configurations change.
"""

import logging
from typing import Any, Dict, List, Optional

from ai_services.factory import AIServiceFactory, ServiceType
from embeddings.base import EmbeddingServiceFactory

logger = logging.getLogger(__name__)


class DependencyCacheCleaner:
    """
    Clears provider/embedding/reranker/vision/audio/store/datasource caches when adapters change.

    Responsibilities:
    - Clear provider/embedding/reranker/vision/audio caches
    - Clear STT/TTS caches (via audio_cache)
    - Clear vector store caches when store_name changes
    - Clear datasource caches when database/datasource config changes
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
        audio_cache=None,
        app_state=None
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
            app_state: FastAPI app state for accessing store_manager and datasource_registry
        """
        self.config = config
        self.provider_cache = provider_cache
        self.embedding_cache = embedding_cache
        self.reranker_cache = reranker_cache
        self.vision_cache = vision_cache
        self.audio_cache = audio_cache
        self.app_state = app_state

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

        # Clear STT cache (uses audio_cache)
        stt_caches = await self._clear_stt_cache(adapter_config)
        cleared_caches.extend(stt_caches)

        # Clear TTS cache (uses audio_cache)
        tts_caches = await self._clear_tts_cache(adapter_config)
        cleared_caches.extend(tts_caches)

        # Clear store cache if store_name changed
        store_caches = await self._clear_store_cache(adapter_name, adapter_config)
        cleared_caches.extend(store_caches)

        # Clear datasource cache if datasource/database changed
        datasource_caches = await self._clear_datasource_cache(adapter_name, adapter_config)
        cleared_caches.extend(datasource_caches)

        if cleared_caches:
            logger.info(f"Cleared dependency caches for adapter '{adapter_name}': {', '.join(cleared_caches)}")
            provider_count = sum(1 for c in cleared_caches if c.startswith("provider:"))
            embedding_count = sum(1 for c in cleared_caches if c.startswith("embedding:"))
            reranker_count = sum(1 for c in cleared_caches if c.startswith("reranker:"))
            vision_count = sum(1 for c in cleared_caches if c.startswith("vision:"))
            audio_count = sum(1 for c in cleared_caches if c.startswith("audio:"))
            stt_count = sum(1 for c in cleared_caches if c.startswith("stt:"))
            tts_count = sum(1 for c in cleared_caches if c.startswith("tts:"))
            store_count = sum(1 for c in cleared_caches if c.startswith("store:"))
            datasource_count = sum(1 for c in cleared_caches if c.startswith("datasource:"))
            logger.debug(
                "Cache clearing summary for '%s': %s provider(s), %s embedding(s), "
                "%s reranker(s), %s vision, %s audio, %s stt, %s tts, %s store(s), %s datasource(s)",
                adapter_name,
                provider_count,
                embedding_count,
                reranker_count,
                vision_count,
                audio_count,
                stt_count,
                tts_count,
                store_count,
                datasource_count,
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

        # If no adapter-specific provider, use global default
        if not old_provider:
            old_provider = self.config.get('general', {}).get('inference_provider')
            if old_provider:
                logger.debug(f"Using global default inference provider for cache clearing: {old_provider}")

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

        # Also clear the AIServiceFactory cache for this provider
        # This is critical - the factory has its own instance cache separate from provider_cache
        AIServiceFactory.clear_cache(service_type=ServiceType.INFERENCE, provider=old_provider)
        logger.debug(f"Cleared AIServiceFactory inference cache for provider '{old_provider}'")

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

        # If no adapter-specific provider, use global default
        if not old_embedding_provider:
            old_embedding_provider = self.config.get('embedding', {}).get('provider')
            if old_embedding_provider:
                logger.debug(f"Using global default embedding provider for cache clearing: {old_embedding_provider}")

        if not old_embedding_provider:
            return cleared

        # Build cache key the same way as in embedding cache manager
        cache_key = self.embedding_cache.build_cache_key(old_embedding_provider)

        if self.embedding_cache.contains(cache_key):
            await self.embedding_cache.remove(cache_key)
            cleared.append(f"embedding:{cache_key}")

        # Also clear the AIServiceFactory cache for this provider
        AIServiceFactory.clear_cache(service_type=ServiceType.EMBEDDING, provider=old_embedding_provider)
        logger.debug(f"Cleared AIServiceFactory embedding cache for provider '{old_embedding_provider}'")

        # Also clear the EmbeddingServiceFactory cache for this provider
        # This is a third cache layer used by the legacy embedding system
        try:
            factory_instances = EmbeddingServiceFactory.get_cached_instances()
            keys_to_remove = [k for k in factory_instances.keys() if k.startswith(f"{old_embedding_provider}:")]
            if keys_to_remove:
                with EmbeddingServiceFactory._get_lock():
                    for key in keys_to_remove:
                        if key in EmbeddingServiceFactory._instances:
                            del EmbeddingServiceFactory._instances[key]
                            cleared.append(f"embedding_factory:{key}")
                logger.debug(f"Cleared EmbeddingServiceFactory cache for provider '{old_embedding_provider}': {keys_to_remove}")
        except Exception as e:
            logger.warning(f"Error clearing EmbeddingServiceFactory cache: {e}")

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

        # If no adapter-specific provider, use global default
        if not old_reranker_provider:
            # Check for reranker provider_override, or fallback to inference provider
            reranker_config = self.config.get('reranker', {})
            old_reranker_provider = reranker_config.get('provider_override') or reranker_config.get('provider')
            if old_reranker_provider:
                logger.debug(f"Using global default reranker provider for cache clearing: {old_reranker_provider}")

        if not old_reranker_provider:
            return cleared

        # Build cache key the same way as in reranker cache manager
        cache_key = self.reranker_cache.build_cache_key(old_reranker_provider)

        if self.reranker_cache.contains(cache_key):
            await self.reranker_cache.remove(cache_key)
            cleared.append(f"reranker:{cache_key}")

        # Also clear the AIServiceFactory cache for this provider
        AIServiceFactory.clear_cache(service_type=ServiceType.RERANKING, provider=old_reranker_provider)
        logger.debug(f"Cleared AIServiceFactory reranking cache for provider '{old_reranker_provider}'")

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

        # If no adapter-specific provider, use global default
        if not old_vision_provider:
            vision_config = self.config.get('vision', {})
            old_vision_provider = vision_config.get('provider')
            if old_vision_provider:
                logger.debug(f"Using global default vision provider for cache clearing: {old_vision_provider}")

        if not old_vision_provider or not self.vision_cache:
            return cleared

        # Build cache key the same way as in vision cache manager
        cache_key = self.vision_cache.build_cache_key(old_vision_provider)

        if self.vision_cache.contains(cache_key):
            await self.vision_cache.remove(cache_key)
            cleared.append(f"vision:{cache_key}")

        # Also clear the AIServiceFactory cache for this provider
        AIServiceFactory.clear_cache(service_type=ServiceType.VISION, provider=old_vision_provider)
        logger.debug(f"Cleared AIServiceFactory vision cache for provider '{old_vision_provider}'")

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

        # If no adapter-specific provider, use global default from sound config
        if not old_audio_provider:
            sound_config = self.config.get('sound', {})
            old_audio_provider = sound_config.get('provider')
            if old_audio_provider:
                logger.debug(f"Using global default audio provider for cache clearing: {old_audio_provider}")

        if not old_audio_provider or not self.audio_cache:
            return cleared

        # Build cache key the same way as in audio cache manager
        cache_key = self.audio_cache.build_cache_key(old_audio_provider)

        if self.audio_cache.contains(cache_key):
            await self.audio_cache.remove(cache_key)
            cleared.append(f"audio:{cache_key}")

        # Also clear the AIServiceFactory cache for this provider
        AIServiceFactory.clear_cache(service_type=ServiceType.AUDIO, provider=old_audio_provider)
        logger.debug(f"Cleared AIServiceFactory audio cache for provider '{old_audio_provider}'")

        return cleared

    async def _clear_stt_cache(self, adapter_config: Dict[str, Any]) -> List[str]:
        """
        Clear STT (Speech-to-Text) cache entries for an adapter configuration.

        Args:
            adapter_config: Adapter configuration

        Returns:
            List of cleared cache descriptions
        """
        cleared = []
        old_stt_provider = adapter_config.get('stt_provider')

        # If no adapter-specific provider, use global default from stt config
        if not old_stt_provider:
            stt_config = self.config.get('stt', {})
            old_stt_provider = stt_config.get('provider')
            if old_stt_provider:
                logger.debug(f"Using global default STT provider for cache clearing: {old_stt_provider}")

        if not old_stt_provider or not self.audio_cache:
            return cleared

        # STT uses audio_cache
        cache_key = self.audio_cache.build_cache_key(old_stt_provider)

        if self.audio_cache.contains(cache_key):
            await self.audio_cache.remove(cache_key)
            cleared.append(f"stt:{cache_key}")

        # Also clear the AIServiceFactory cache for this provider (STT uses AUDIO service type)
        AIServiceFactory.clear_cache(service_type=ServiceType.AUDIO, provider=old_stt_provider)
        logger.debug(f"Cleared AIServiceFactory audio/STT cache for provider '{old_stt_provider}'")

        return cleared

    async def _clear_tts_cache(self, adapter_config: Dict[str, Any]) -> List[str]:
        """
        Clear TTS (Text-to-Speech) cache entries for an adapter configuration.

        Args:
            adapter_config: Adapter configuration

        Returns:
            List of cleared cache descriptions
        """
        cleared = []
        old_tts_provider = adapter_config.get('tts_provider')

        # If no adapter-specific provider, use global default from tts config
        if not old_tts_provider:
            tts_config = self.config.get('tts', {})
            old_tts_provider = tts_config.get('provider')
            if old_tts_provider:
                logger.debug(f"Using global default TTS provider for cache clearing: {old_tts_provider}")

        if not old_tts_provider or not self.audio_cache:
            return cleared

        # TTS uses audio_cache
        cache_key = self.audio_cache.build_cache_key(old_tts_provider)

        if self.audio_cache.contains(cache_key):
            await self.audio_cache.remove(cache_key)
            cleared.append(f"tts:{cache_key}")

        # Also clear the AIServiceFactory cache for this provider (TTS uses AUDIO service type)
        AIServiceFactory.clear_cache(service_type=ServiceType.AUDIO, provider=old_tts_provider)
        logger.debug(f"Cleared AIServiceFactory audio/TTS cache for provider '{old_tts_provider}'")

        return cleared

    async def _clear_store_cache(self, adapter_name: str, adapter_config: Dict[str, Any]) -> List[str]:
        """
        Clear vector store cache entries when store_name or vector_store changes.

        Args:
            adapter_name: Name of the adapter
            adapter_config: Adapter configuration

        Returns:
            List of cleared cache descriptions
        """
        cleared = []

        if not self.app_state:
            return cleared

        # Get store manager from app_state
        store_manager = getattr(self.app_state, 'store_manager', None)
        if not store_manager:
            store_manager = getattr(self.app_state, 'vector_store_manager', None)

        if not store_manager:
            return cleared

        # Check for store_name in config section (intent adapters)
        config_section = adapter_config.get('config', {})
        store_name = config_section.get('store_name')

        # Check for vector_store in config section (multimodal/file adapters)
        vector_store = config_section.get('vector_store')

        # Get template collection name for intent adapters
        config_section.get('template_collection_name')

        stores_to_check = []
        if store_name:
            stores_to_check.append(store_name)
        if vector_store:
            stores_to_check.append(vector_store)

        for store in stores_to_check:
            try:
                # Check if store exists in cache
                if hasattr(store_manager, '_stores') and store in store_manager._stores:
                    # Remove from store manager cache
                    cached_store = store_manager._stores.pop(store, None)
                    if cached_store:
                        # Try to close the store connection
                        if hasattr(cached_store, 'disconnect'):
                            try:
                                await cached_store.disconnect()
                            except Exception as e:
                                logger.debug(f"Error disconnecting store {store}: {e}")
                        cleared.append(f"store:{store}")
                        logger.info(f"Cleared store cache for '{store}' (adapter: {adapter_name})")
            except Exception as e:
                logger.warning(f"Error clearing store cache for {store}: {e}")

        return cleared

    async def _clear_datasource_cache(self, adapter_name: str, adapter_config: Dict[str, Any]) -> List[str]:
        """
        Clear datasource cache entries when datasource or database config changes.

        Args:
            adapter_name: Name of the adapter
            adapter_config: Adapter configuration

        Returns:
            List of cleared cache descriptions
        """
        cleared = []

        # Get datasource name from adapter config
        datasource_name = adapter_config.get('datasource')
        if not datasource_name or datasource_name == 'none':
            return cleared

        # Get database override from adapter config
        database_override = adapter_config.get('database')

        try:
            from datasources.registry import get_registry as get_datasource_registry
            datasource_registry = get_datasource_registry()

            # Build cache key similar to how datasource registry does it
            # This uses the adapter-level database override if present
            datasource_config = self.config.get('datasources', {}).get(datasource_name, {})

            # If adapter has database override, build custom cache key
            if database_override:
                if datasource_name in ['sqlite']:
                    cache_key = f"{datasource_name}:{database_override}"
                elif datasource_name in ['duckdb']:
                    cache_key = f"{datasource_name}:{database_override}"
                elif datasource_name in ['postgres', 'postgresql', 'mysql', 'mssql']:
                    host = datasource_config.get('host', 'localhost')
                    port = datasource_config.get('port', 5432)
                    username = datasource_config.get('username', '')
                    cache_key = f"{datasource_name}:{host}:{port}:{database_override}:{username}"
                elif datasource_name in ['mongodb', 'mongo']:
                    host = datasource_config.get('host', 'localhost')
                    port = datasource_config.get('port', 27017)
                    cache_key = f"{datasource_name}:{host}:{port}:{database_override}"
                else:
                    cache_key = datasource_name
            else:
                # Use standard cache key generation
                cache_key = datasource_registry._generate_cache_key(datasource_name, self.config)

            # Check if datasource is cached and release it
            if hasattr(datasource_registry, '_datasource_pool'):
                if cache_key in datasource_registry._datasource_pool:
                    try:
                        # Release the datasource (decrements reference count)
                        await datasource_registry.release_datasource(datasource_name, self.config)
                        cleared.append(f"datasource:{cache_key}")
                        logger.info(f"Released datasource cache for '{cache_key}' (adapter: {adapter_name})")
                    except Exception as e:
                        logger.debug(f"Error releasing datasource {cache_key}: {e}")

        except ImportError:
            logger.debug("Datasource registry not available for cache clearing")
        except Exception as e:
            logger.warning(f"Error clearing datasource cache for {datasource_name}: {e}")

        return cleared

    def update_config(self, config: Dict[str, Any]) -> None:
        """
        Update the configuration reference.

        Args:
            config: New configuration dictionary
        """
        self.config = config

    def set_app_state(self, app_state) -> None:
        """
        Set the app_state reference for accessing store_manager and datasource_registry.

        Args:
            app_state: FastAPI app state
        """
        self.app_state = app_state
