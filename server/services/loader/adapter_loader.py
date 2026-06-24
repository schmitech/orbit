"""
Adapter Loader for handling adapter instantiation and initialization.

Coordinates adapter creation with dependency services.
"""

import asyncio
import copy
import logging
from typing import Any, Dict, Optional
from concurrent.futures import ThreadPoolExecutor

from config.config_manager import was_resolved_from_preset
from ai_services.factory import AIServiceFactory, ServiceType
from embeddings.base import EmbeddingServiceFactory
from services.adapter_capabilities import uses_retrieval_services

logger = logging.getLogger(__name__)


def _is_disabled(value: Any) -> bool:
    return value is False or (isinstance(value, str) and value.lower() == 'false')


class AdapterLoader:
    """
    Handles adapter instantiation and dependency coordination.

    Responsibilities:
    - Adapter instantiation
    - Manage adapter dependencies (providers, embeddings, rerankers)
    - Coordinate with cache managers
    - Handle initialization sequence
    """

    def __init__(
        self,
        config: Dict[str, Any],
        app_state: Any,
        provider_cache,
        embedding_cache,
        reranker_cache,
        vision_cache=None,
        audio_cache=None,
        thread_pool: Optional[ThreadPoolExecutor] = None,
        adapter_manager: Any = None
    ):
        """
        Initialize the adapter loader.

        Args:
            config: Application configuration
            app_state: FastAPI application state
            provider_cache: Provider cache manager
            embedding_cache: Embedding cache manager
            reranker_cache: Reranker cache manager
            vision_cache: Vision cache manager (optional for backward compatibility)
            audio_cache: Audio cache manager (optional for backward compatibility)
            thread_pool: Optional thread pool for async operations
            adapter_manager: Reference to DynamicAdapterManager for composite adapters
        """
        self.config = config
        self.app_state = app_state
        self.provider_cache = provider_cache
        self.embedding_cache = embedding_cache
        self.reranker_cache = reranker_cache
        self.vision_cache = vision_cache
        self.audio_cache = audio_cache
        self._thread_pool = thread_pool or ThreadPoolExecutor(max_workers=5)
        self.adapter_manager = adapter_manager

    async def load_adapter(
        self,
        adapter_name: str,
        adapter_config: Dict[str, Any]
    ) -> Any:
        """
        Load and initialize an adapter asynchronously.

        Args:
            adapter_name: Name of the adapter
            adapter_config: Configuration for the adapter

        Returns:
            The initialized adapter instance
        """
        # Preload inference provider if adapter has an override or uses global provider
        inference_provider = adapter_config.get('inference_provider')
        logger.debug(f"Adapter '{adapter_name}' inference_provider from config: {inference_provider}")
        if not inference_provider:
            # Use global default provider
            inference_provider = self.config.get('general', {}).get('inference_provider')
            logger.debug(f"Using global default inference_provider: {inference_provider}")

        if inference_provider:
            model_override = adapter_config.get('model')
            logger.debug(f"Preloading inference provider '{inference_provider}' for adapter '{adapter_name}' (model: {model_override or 'default'})")
            try:
                # Clear any stale cached instance for this provider BEFORE creating new one
                # This ensures we get a fresh instance with properly initialized client
                AIServiceFactory.clear_cache(service_type=ServiceType.INFERENCE, provider=inference_provider)
                logger.debug(f"Cleared AIServiceFactory inference cache for '{inference_provider}' before preload")

                await self.provider_cache.create_provider(inference_provider, model_override, adapter_name)
                log_msg = f"Preloaded inference provider '{inference_provider}' for adapter '{adapter_name}'"
                if model_override:
                    log_msg += f" with model override '{model_override}'"
                logger.debug(log_msg)
            except Exception as e:
                logger.error(f"Failed to preload inference provider '{inference_provider}' for adapter '{adapter_name}': {str(e)}", exc_info=True)
        else:
            logger.warning(f"No inference provider configured for adapter '{adapter_name}' (neither in adapter config nor global config)")

        uses_retrieval = uses_retrieval_services(adapter_config)

        # Preload retrieval services only when adapter capabilities require retrieval.
        embedding_provider = self._resolve_retrieval_provider(
            adapter_name,
            adapter_config,
            global_config_key='embedding',
            adapter_provider_key='embedding_provider',
            log_label='embedding',
            uses_retrieval_services=uses_retrieval,
        )
        await self._preload_service(
            provider=embedding_provider,
            cache_manager=self.embedding_cache,
            service_type=ServiceType.EMBEDDING,
            adapter_name=adapter_name,
            log_label='embedding',
            factory_clear=self._clear_embedding_factory_cache,
            warning_label='embedding service',
        )

        reranker_provider = self._resolve_retrieval_provider(
            adapter_name,
            adapter_config,
            global_config_key='reranker',
            adapter_provider_key='reranker_provider',
            log_label='reranker',
            uses_retrieval_services=uses_retrieval,
            provider_keys=('provider_override', 'provider'),
        )
        await self._preload_service(
            provider=reranker_provider,
            cache_manager=self.reranker_cache,
            service_type=ServiceType.RERANKING,
            adapter_name=adapter_name,
            log_label='reranker',
            warning_label='reranker service',
        )

        vision_provider = self._resolve_retrieval_provider(
            adapter_name,
            adapter_config,
            global_config_key='vision',
            adapter_provider_key='vision_provider',
            log_label='vision',
            uses_retrieval_services=uses_retrieval,
        )
        await self._preload_service(
            provider=vision_provider,
            cache_manager=self.vision_cache,
            service_type=ServiceType.VISION,
            adapter_name=adapter_name,
            log_label='vision',
            warning_label='vision service',
        )

        # Preload audio service ONLY if the adapter explicitly specifies an audio_provider
        # (Don't fall back to global default - most adapters don't need audio)
        audio_provider = adapter_config.get('audio_provider')
        if audio_provider:
            # Check if audio (sound) is globally enabled
            sound_global_config = self.config.get('sound', {})
            sound_globally_enabled = sound_global_config.get('enabled', True)
            if _is_disabled(sound_globally_enabled):
                logger.debug(f"Skipping audio preload for adapter '{adapter_name}' - audio is globally disabled")
                audio_provider = None

        await self._preload_service(
            provider=audio_provider,
            cache_manager=self.audio_cache,
            service_type=ServiceType.AUDIO,
            adapter_name=adapter_name,
            log_label='audio',
            cache_debug_label='audio',
            warning_label='audio service',
        )

        # Preload STT service ONLY if the adapter explicitly specifies an stt_provider
        # (Don't fall back to global default - most adapters don't need STT)
        stt_provider = adapter_config.get('stt_provider')
        if stt_provider:
            # Check if STT is globally enabled
            stt_global_config = self.config.get('stt', {})
            stt_globally_enabled = stt_global_config.get('enabled', True)
            if _is_disabled(stt_globally_enabled):
                logger.debug(f"Skipping STT preload for adapter '{adapter_name}' - STT is globally disabled")
                stt_provider = None
            else:
                # Check if the specific provider is enabled
                stt_providers_config = self.config.get('stt_providers', {})
                provider_config = stt_providers_config.get(stt_provider, {})
                provider_enabled = provider_config.get('enabled', True)
                if _is_disabled(provider_enabled):
                    logger.debug(f"Skipping STT preload for adapter '{adapter_name}' - provider '{stt_provider}' is disabled")
                    stt_provider = None

        await self._preload_service(
            provider=stt_provider,
            cache_manager=self.audio_cache,
            service_type=ServiceType.AUDIO,
            adapter_name=adapter_name,
            log_label='STT',
            cache_debug_label='audio/STT',
            warning_label='STT service',
        )

        # Preload image generation service ONLY if the adapter explicitly specifies an image_provider
        image_provider = adapter_config.get('image_provider')

        await self._preload_adapter_manager_service(
            provider=image_provider,
            adapter_name=adapter_name,
            manager_method='get_image_service',
            log_label='image generation',
            warning_label='image generation service',
        )

        # Preload video generation service ONLY if the adapter explicitly specifies a video_provider
        video_provider = adapter_config.get('video_provider')

        await self._preload_adapter_manager_service(
            provider=video_provider,
            adapter_name=adapter_name,
            manager_method='get_video_service',
            log_label='video generation',
            warning_label='video generation service',
        )

        # Preload TTS service ONLY if the adapter explicitly specifies a tts_provider
        # (Don't fall back to global default - most adapters don't need TTS)
        tts_provider = adapter_config.get('tts_provider')
        if tts_provider:
            # Check if TTS is globally enabled
            tts_global_config = self.config.get('tts', {})
            tts_globally_enabled = tts_global_config.get('enabled', True)
            if _is_disabled(tts_globally_enabled):
                logger.debug(f"Skipping TTS preload for adapter '{adapter_name}' - TTS is globally disabled")
                tts_provider = None
            else:
                # Check if the specific provider is enabled
                tts_providers_config = self.config.get('tts_providers', {})
                provider_config = tts_providers_config.get(tts_provider, {})
                provider_enabled = provider_config.get('enabled', True)
                if _is_disabled(provider_enabled):
                    logger.debug(f"Skipping TTS preload for adapter '{adapter_name}' - provider '{tts_provider}' is disabled")
                    tts_provider = None

        await self._preload_service(
            provider=tts_provider,
            cache_manager=self.audio_cache,
            service_type=ServiceType.AUDIO,
            adapter_name=adapter_name,
            log_label='TTS',
            cache_debug_label='audio/TTS',
            warning_label='TTS service',
        )

        # Run the import and initialization in a thread pool
        loop = asyncio.get_running_loop()

        def _sync_load():
            return self._create_adapter_sync(adapter_name, adapter_config)

        retriever = await loop.run_in_executor(self._thread_pool, _sync_load)

        # Initialize the retriever (if it's async)
        if hasattr(retriever, 'initialize'):
            if asyncio.iscoroutinefunction(retriever.initialize):
                await retriever.initialize()
            else:
                await loop.run_in_executor(self._thread_pool, retriever.initialize)

        # Initialize embeddings for intent adapters
        await self._initialize_intent_embeddings(retriever, adapter_name)

        return retriever

    def _resolve_retrieval_provider(
        self,
        adapter_name: str,
        adapter_config: Dict[str, Any],
        global_config_key: str,
        adapter_provider_key: str,
        log_label: str,
        uses_retrieval_services: bool,
        provider_keys: tuple[str, ...] = ('provider',),
    ) -> Optional[str]:
        global_config = self.config.get(global_config_key, {})
        if _is_disabled(global_config.get('enabled', True)):
            logger.debug(f"Skipping {log_label} preload for adapter '{adapter_name}' - {log_label} is globally disabled")
            return None

        provider = adapter_config.get(adapter_provider_key)
        if provider:
            return provider

        if not uses_retrieval_services:
            logger.debug(f"Skipping {log_label} preload for adapter '{adapter_name}' - adapter capabilities do not require retrieval")
            return None

        for provider_key in provider_keys:
            provider = global_config.get(provider_key)
            if provider:
                logger.debug(f"Using global default {adapter_provider_key}: {provider}")
                return provider

        return None

    async def _preload_service(
        self,
        provider: Optional[str],
        cache_manager: Any,
        service_type: ServiceType,
        adapter_name: str,
        log_label: str,
        warning_label: str,
        cache_debug_label: Optional[str] = None,
        factory_clear: Optional[Any] = None,
    ) -> None:
        if not provider or not cache_manager:
            return

        logger.info(f"Preloading {log_label} provider '{provider}' for adapter '{adapter_name}'")
        try:
            AIServiceFactory.clear_cache(service_type=service_type, provider=provider)
            logger.debug(f"Cleared AIServiceFactory {cache_debug_label or log_label} cache for '{provider}' before preload")

            if factory_clear:
                factory_clear(provider)

            await cache_manager.create_service(provider, adapter_name)
            logger.debug(f"Preloaded {log_label} provider '{provider}' for adapter '{adapter_name}'")
        except Exception as e:
            logger.warning(f"Failed to preload {warning_label} for adapter {adapter_name}: {str(e)}")

    def _clear_embedding_factory_cache(self, provider: str) -> None:
        factory_instances = EmbeddingServiceFactory.get_cached_instances()
        keys_to_remove = [k for k in factory_instances.keys() if k.startswith(f"{provider}:")]
        if not keys_to_remove:
            return

        with EmbeddingServiceFactory._get_lock():
            for key in keys_to_remove:
                if key in EmbeddingServiceFactory._instances:
                    del EmbeddingServiceFactory._instances[key]
        logger.debug(f"Cleared EmbeddingServiceFactory cache for '{provider}' before preload")

    async def _preload_adapter_manager_service(
        self,
        provider: Optional[str],
        adapter_name: str,
        manager_method: str,
        log_label: str,
        warning_label: str,
    ) -> None:
        if not provider or not self.adapter_manager or not hasattr(self.adapter_manager, manager_method):
            return

        logger.info(f"Preloading {log_label} provider '{provider}' for adapter '{adapter_name}'")
        try:
            method = getattr(self.adapter_manager, manager_method)
            await method(provider, adapter_name)
            logger.debug(f"Preloaded {log_label} provider '{provider}' for adapter '{adapter_name}'")
        except Exception as e:
            logger.warning(f"Failed to preload {warning_label} for adapter {adapter_name}: {str(e)}")

    def _create_adapter_sync(
        self,
        adapter_name: str,
        adapter_config: Dict[str, Any]
    ) -> Any:
        """
        Synchronously create an adapter instance.

        Args:
            adapter_name: Name of the adapter
            adapter_config: Configuration for the adapter

        Returns:
            The created adapter instance (not yet initialized)
        """
        implementation = adapter_config.get('implementation')
        datasource_name = adapter_config.get('datasource', 'none')
        domain_adapter_name = adapter_config.get('adapter')
        adapter_category = adapter_config.get('type', 'retriever')

        # Import the retriever class
        module_path, class_name = implementation.rsplit('.', 1)
        module = __import__(module_path, fromlist=[class_name])
        retriever_class = getattr(module, class_name)

        # Create domain adapter
        from adapters.registry import ADAPTER_REGISTRY
        adapter_config_params = adapter_config.get('config') or {}
        domain_adapter = None

        if domain_adapter_name:
            domain_adapter = ADAPTER_REGISTRY.create(
                adapter_type=adapter_category,
                datasource=datasource_name,
                adapter_name=domain_adapter_name,
                override_config=adapter_config_params
            )

        # Create a deep copy of config with the adapter config included
        config_with_adapter = copy.deepcopy(self.config)
        config_with_adapter['adapter_config'] = adapter_config_params

        # Include capabilities from the adapter configuration (deep copy to prevent mutation)
        if 'capabilities' in adapter_config:
            config_with_adapter['capabilities'] = copy.deepcopy(adapter_config['capabilities'])
            logger.debug("AdapterLoader: capabilities for %s: %s", adapter_name, config_with_adapter['capabilities'])

        # For intent adapters, include stores configuration
        if domain_adapter_name == 'intent' and 'stores' in self.config:
            config_with_adapter['stores'] = self.config['stores']

        # Include adapter-level inference provider override
        if 'inference_provider' in adapter_config:
            config_with_adapter['inference_provider'] = adapter_config['inference_provider']
            logger.debug(f"Setting inference provider override: {adapter_config['inference_provider']} for adapter: {adapter_name}")

        # Include adapter-level model override
        if adapter_config.get('model'):
            provider_for_model = adapter_config.get('inference_provider') or config_with_adapter.get('general', {}).get('inference_provider')
            if provider_for_model:
                inference_section = config_with_adapter.setdefault('inference', {}).setdefault(provider_for_model, {})
                model_value = adapter_config['model']
                
                # For Ollama: check if model value is actually a preset name
                # This allows adapters to specify `model: "lfm2-700m-cpu"` to use that preset
                if provider_for_model == 'ollama':
                    ollama_presets = config_with_adapter.get('ollama_presets', {})
                    if model_value in ollama_presets:
                        # Model value is a preset name - apply the full preset configuration
                        preset = ollama_presets[model_value]
                        original_preset = was_resolved_from_preset('ollama') or 'default'
                        
                        # Apply preset values to inference section (preserving enabled flag)
                        enabled = inference_section.get('enabled', True)
                        for key, value in preset.items():
                            inference_section[key] = value
                        inference_section['enabled'] = enabled
                        
                        logger.info(
                            "Preset override for adapter '%s': '%s' -> '%s' (model: %s)",
                            adapter_name,
                            original_preset,
                            model_value,
                            preset.get('model', 'unknown'),
                        )
                    else:
                        # Model value is a raw Ollama model name - apply as regular override
                        original_model = inference_section.get('model', 'default')
                        inference_section['model'] = model_value
                        logger.info(
                            "Model override for adapter '%s': '%s' -> '%s' (provider: %s)",
                            adapter_name,
                            original_model,
                            model_value,
                            provider_for_model,
                        )
                else:
                    # Non-Ollama provider - apply model override normally
                    original_model = inference_section.get('model', 'default')
                    inference_section['model'] = model_value
                    logger.info(
                        "Model override for adapter '%s': '%s' -> '%s' (provider: %s)",
                        adapter_name,
                        original_model,
                        model_value,
                        provider_for_model,
                    )

        # Include adapter-level embedding provider override
        if adapter_config.get('embedding_provider'):
            if 'embedding' not in config_with_adapter:
                config_with_adapter['embedding'] = {}
            config_with_adapter['embedding']['provider'] = adapter_config['embedding_provider']
            logger.debug(f"Setting embedding provider override: {adapter_config['embedding_provider']} for adapter: {adapter_name}")

        # Include adapter-level embedding model override
        # This allows adapters to use a different embedding model than the global default
        if adapter_config.get('embedding_model'):
            embedding_provider = adapter_config.get('embedding_provider') or config_with_adapter.get('embedding', {}).get('provider', 'ollama')
            if 'embeddings' not in config_with_adapter:
                config_with_adapter['embeddings'] = {}
            if embedding_provider not in config_with_adapter['embeddings']:
                config_with_adapter['embeddings'][embedding_provider] = {}
            original_model = config_with_adapter['embeddings'][embedding_provider].get('model', 'default')
            config_with_adapter['embeddings'][embedding_provider]['model'] = adapter_config['embedding_model']
            logger.debug(f"Setting embedding model override for adapter '{adapter_name}': '{original_model}' -> '{adapter_config['embedding_model']}' (provider: {embedding_provider})")

        # Include adapter-level database override
        if adapter_config.get('database'):
            if 'datasources' not in config_with_adapter:
                config_with_adapter['datasources'] = {}
            if datasource_name not in config_with_adapter['datasources']:
                config_with_adapter['datasources'][datasource_name] = {}

            original_database = config_with_adapter['datasources'][datasource_name].get('database', 'default')
            config_with_adapter['datasources'][datasource_name]['database'] = adapter_config['database']

            logger.debug(f"Database override for adapter '{adapter_name}': '{original_database}' -> '{adapter_config['database']}' (datasource: {datasource_name})")

        # Create datasource instance
        datasource_instance = None
        if datasource_name and datasource_name != 'none':
            try:
                from datasources.registry import get_registry as get_datasource_registry
                datasource_registry = get_datasource_registry()
                datasource_instance = datasource_registry.get_or_create_datasource(
                    datasource_name=datasource_name,
                    config=config_with_adapter,
                    logger_instance=logger
                )
                if datasource_instance:
                    logger.info(f"Got datasource instance '{datasource_name}' for retriever in adapter '{adapter_name}' (pooled)")
                else:
                    logger.warning(f"Failed to get datasource '{datasource_name}' for adapter '{adapter_name}'")
            except Exception as e:
                logger.warning(f"Error getting datasource '{datasource_name}' for adapter '{adapter_name}': {e}")
                datasource_instance = None

        # Build kwargs for retriever instantiation
        retriever_kwargs = {
            'config': config_with_adapter,
            'domain_adapter': domain_adapter,
            'datasource': datasource_instance
        }

        # For composite adapters, pass adapter_manager for child adapter resolution
        if domain_adapter_name == 'composite':
            retriever_kwargs['adapter_manager'] = self.adapter_manager
            logger.debug(f"Composite adapter '{adapter_name}': passing adapter_manager={self.adapter_manager is not None}")

        # Create retriever instance
        logger.debug("AdapterLoader: pre-constructor capabilities for %s: %s", adapter_name, config_with_adapter.get('capabilities', 'NOT SET'))
        retriever = retriever_class(**retriever_kwargs)

        # Store metadata for cleanup
        retriever._datasource_name = datasource_name
        retriever._datasource_config_for_release = config_with_adapter

        return retriever

    async def _initialize_intent_embeddings(self, retriever: Any, adapter_name: str) -> None:
        """
        Initialize embeddings for intent adapters.

        Args:
            retriever: The retriever instance
            adapter_name: Name of the adapter
        """
        if hasattr(retriever, 'domain_adapter') and retriever.domain_adapter:
            domain_adapter = retriever.domain_adapter
            if hasattr(domain_adapter, 'initialize_embeddings'):
                store_manager = None

                # Check app state for store manager
                if self.app_state:
                    store_manager = getattr(self.app_state, 'store_manager', None)
                    if not store_manager:
                        store_manager = getattr(self.app_state, 'vector_store_manager', None)

                # Create store manager if not found
                if not store_manager:
                    try:
                        from vector_stores.base.store_manager import StoreManager
                        store_manager = StoreManager()
                        logger.info(f"Created new StoreManager for adapter {adapter_name}")
                    except ImportError:
                        logger.warning("Vector store system not available")

                if store_manager:
                    logger.info(f"Initializing embeddings for adapter {adapter_name} with store manager")
                    await domain_adapter.initialize_embeddings(store_manager)
                else:
                    logger.info(f"Initializing embeddings for adapter {adapter_name} without store manager")
                    await domain_adapter.initialize_embeddings()

    def update_config(self, config: Dict[str, Any]) -> None:
        """
        Update the configuration reference.

        Args:
            config: New configuration dictionary
        """
        self.config = config
        # Also update cache managers' config references
        self.provider_cache.config = config
        self.embedding_cache.config = config
        self.reranker_cache.config = config
        if self.vision_cache:
            self.vision_cache.config = config
        if self.audio_cache:
            self.audio_cache.config = config
