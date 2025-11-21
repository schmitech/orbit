"""
Adapter Loader for handling adapter instantiation and initialization.

Coordinates adapter creation with dependency services.
"""

import asyncio
import copy
import logging
from typing import Any, Dict, Optional
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


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
        thread_pool: Optional[ThreadPoolExecutor] = None
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
        """
        self.config = config
        self.app_state = app_state
        self.provider_cache = provider_cache
        self.embedding_cache = embedding_cache
        self.reranker_cache = reranker_cache
        self.vision_cache = vision_cache
        self.audio_cache = audio_cache
        self._thread_pool = thread_pool or ThreadPoolExecutor(max_workers=5)

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
        # Preload embedding service if adapter has an override
        if adapter_config.get('embedding_provider'):
            embedding_provider = adapter_config['embedding_provider']
            try:
                await self.embedding_cache.create_service(embedding_provider, adapter_name)
            except Exception as e:
                logger.warning(f"Failed to preload embedding service for adapter {adapter_name}: {str(e)}")

        # Preload reranker service if adapter has an override
        if adapter_config.get('reranker_provider'):
            reranker_provider = adapter_config['reranker_provider']
            try:
                await self.reranker_cache.create_service(reranker_provider, adapter_name)
            except Exception as e:
                logger.warning(f"Failed to preload reranker service for adapter {adapter_name}: {str(e)}")

        # Preload vision service if adapter has an override
        if adapter_config.get('vision_provider') and self.vision_cache:
            vision_provider = adapter_config['vision_provider']
            try:
                await self.vision_cache.create_service(vision_provider, adapter_name)
            except Exception as e:
                logger.warning(f"Failed to preload vision service for adapter {adapter_name}: {str(e)}")

        # Preload audio service if adapter has an override
        if adapter_config.get('audio_provider') and self.audio_cache:
            audio_provider = adapter_config['audio_provider']
            try:
                await self.audio_cache.create_service(audio_provider, adapter_name)
            except ValueError as e:
                # Check if audio is globally disabled
                sound_config = self.config.get('sound', {})
                is_audio_disabled = sound_config.get('enabled', True) is False or \
                                   (isinstance(sound_config.get('enabled'), str) and
                                    sound_config.get('enabled').lower() == 'false')

                if is_audio_disabled:
                    # This is expected - audio is globally disabled
                    logger.debug(
                        f"Skipping audio service preload for adapter '{adapter_name}' "
                        f"(provider: {audio_provider}) - audio is globally disabled"
                    )
                else:
                    # Provider not registered for another reason
                    logger.warning(
                        f"Failed to preload audio service for adapter '{adapter_name}' "
                        f"(provider: {audio_provider}): {str(e)}"
                    )
            except Exception as e:
                logger.warning(f"Failed to preload audio service for adapter {adapter_name}: {str(e)}")

        # Run the import and initialization in a thread pool
        loop = asyncio.get_event_loop()

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
                original_model = inference_section.get('model', 'default')
                inference_section['model'] = adapter_config['model']
                logger.info(
                    "Model override for adapter '%s': '%s' -> '%s' (provider: %s)",
                    adapter_name,
                    original_model,
                    adapter_config['model'],
                    provider_for_model,
                )

        # Include adapter-level embedding provider override
        if adapter_config.get('embedding_provider'):
            if 'embedding' not in config_with_adapter:
                config_with_adapter['embedding'] = {}
            config_with_adapter['embedding']['provider'] = adapter_config['embedding_provider']
            logger.debug(f"Setting embedding provider override: {adapter_config['embedding_provider']} for adapter: {adapter_name}")

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

        # Create retriever instance
        retriever = retriever_class(
            config=config_with_adapter,
            domain_adapter=domain_adapter,
            datasource=datasource_instance
        )

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
