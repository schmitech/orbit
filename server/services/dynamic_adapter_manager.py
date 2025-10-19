"""
Dynamic Adapter Manager Service for handling on-demand adapter loading.

This service replaces the static single adapter initialization with a dynamic
system that loads adapters based on API key configurations.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Set
from concurrent.futures import ThreadPoolExecutor
import threading

logger = logging.getLogger(__name__)


class DynamicAdapterManager:
    """
    Manages dynamic loading and caching of adapters based on API key configurations.
    
    This service:
    - Loads adapters on-demand based on adapter names
    - Caches initialized adapters for performance
    - Handles adapter lifecycle and cleanup
    - Provides thread-safe access to adapters
    """
    
    def __init__(self, config: Dict[str, Any], app_state=None):
        """
        Initialize the Dynamic Adapter Manager.
        
        Args:
            config: Application configuration
            app_state: FastAPI application state for accessing services
        """
        self.config = config
        self.app_state = app_state
        self.logger = logger
        self.verbose = config.get('general', {}).get('verbose', False)
        
        # Cache for initialized adapters
        self._adapter_cache: Dict[str, Any] = {}
        self._adapter_locks: Dict[str, threading.Lock] = {}
        self._cache_lock = threading.Lock()
        
        # Cache for initialized inference providers
        self._provider_cache: Dict[str, Any] = {}
        self._provider_cache_lock = threading.Lock()
        self._provider_initializing: Set[str] = set()

        # Cache for initialized embedding services
        self._embedding_cache: Dict[str, Any] = {}
        self._embedding_cache_lock = threading.Lock()
        self._embedding_initializing: Set[str] = set()
        
        # Thread pool for adapter initialization
        self._thread_pool = ThreadPoolExecutor(max_workers=5)
        
        # Track loaded adapter configurations
        self._adapter_configs: Dict[str, Dict[str, Any]] = {}
        self._load_adapter_configs()
        
        # Set to track which adapters are currently being initialized
        self._initializing_adapters: Set[str] = set()
        
        self.logger.info("Dynamic Adapter Manager initialized")
        
    def _load_adapter_configs(self):
        """Load adapter configurations from config."""
        inference_only = self.config.get('general', {}).get('inference_only', False)

        adapter_configs = self.config.get('adapters', [])
        
        enabled_count = 0
        disabled_count = 0
        
        for adapter_config in adapter_configs:
            adapter_name = adapter_config.get('name')
            if adapter_name:
                # Check if adapter is enabled (default to True if not specified)
                is_enabled = adapter_config.get('enabled', True)
                
                if is_enabled:
                    self._adapter_configs[adapter_name] = adapter_config
                    enabled_count += 1
                    if self.verbose:
                        inference_provider = adapter_config.get('inference_provider')
                        log_message = f"Loaded adapter config: {adapter_name} (enabled)"
                        if inference_provider:
                            log_message += f" with inference provider override: {inference_provider}"
                        self.logger.info(log_message)
                else:
                    disabled_count += 1
                    if self.verbose:
                        self.logger.info(f"Skipping disabled adapter: {adapter_name}")

        if inference_only:
            self.logger.info(f"Loaded {enabled_count} adapter configurations for inference/model overrides (inference-only mode)")
        else:
            self.logger.info(f"Loaded {enabled_count} enabled adapter configurations ({disabled_count} disabled)")
    
    async def get_adapter(self, adapter_name: str) -> Any:
        """
        Get an adapter instance by name, loading it if necessary.
        
        Args:
            adapter_name: Name of the adapter to retrieve
            
        Returns:
            The initialized adapter instance
            
        Raises:
            ValueError: If adapter configuration is not found
            Exception: If adapter initialization fails
        """
        if not adapter_name:
            raise ValueError("Adapter name cannot be empty")
        
        # Check if adapter is already cached
        if adapter_name in self._adapter_cache:
            if self.verbose:
                self.logger.debug(f"Using cached adapter: {adapter_name}")
            return self._adapter_cache[adapter_name]
        
        # Try to claim initialization ownership
        should_initialize = False
        with self._cache_lock:
            if adapter_name in self._adapter_cache:
                return self._adapter_cache[adapter_name]
            if adapter_name not in self._initializing_adapters:
                self._initializing_adapters.add(adapter_name)
                should_initialize = True

        # If someone else is initializing, wait for them
        if not should_initialize:
            while True:
                await asyncio.sleep(0.1)
                with self._cache_lock:
                    if adapter_name in self._adapter_cache:
                        return self._adapter_cache[adapter_name]
                    if adapter_name not in self._initializing_adapters:
                        # Initializer failed, we should try
                        self._initializing_adapters.add(adapter_name)
                        should_initialize = True
                        break
        
        try:
            # Load the adapter
            adapter = await self._load_adapter(adapter_name)

            # Cache the adapter
            with self._cache_lock:
                self._adapter_cache[adapter_name] = adapter
                # Create a lock for this adapter for future thread-safe operations
                self._adapter_locks[adapter_name] = threading.Lock()

            # Log adapter configuration details
            adapter_config = self._adapter_configs.get(adapter_name, {})
            inference_provider = adapter_config.get('inference_provider') or self.config.get('general', {}).get('inference_provider', 'default')
            model_override = adapter_config.get('model')

            # Get embedding configuration
            embedding_provider = adapter_config.get('embedding_provider') or self.config.get('embedding', {}).get('provider', 'ollama')
            embedding_model = None
            if embedding_provider in self.config.get('embeddings', {}):
                embedding_model = self.config.get('embeddings', {}).get(embedding_provider, {}).get('model')

            # Check if this is an intent adapter and get store info
            adapter_type = adapter_config.get('adapter')
            store_info = ""
            if adapter_type == 'intent':
                store_name = adapter_config.get('config', {}).get('store_name')
                if store_name:
                    store_info = f", store: {store_name}"

            # Build log message with all details
            log_parts = [f"Successfully loaded adapter '{adapter_name}'"]

            # Inference provider and model
            if model_override:
                log_parts.append(f"inference: {inference_provider}/{model_override}")
            else:
                log_parts.append(f"inference: {inference_provider}")

            # Embedding provider and model
            if embedding_model:
                log_parts.append(f"embedding: {embedding_provider}/{embedding_model}")
            else:
                log_parts.append(f"embedding: {embedding_provider}")

            # Store info for intent adapters
            if store_info:
                log_parts.append(store_info.lstrip(", "))

            # Database info if overridden
            if adapter_config.get('database'):
                log_parts.append(f"database: {adapter_config['database']}")

            self.logger.info(f"{log_parts[0]} ({', '.join(log_parts[1:])})")
            return adapter

        except ValueError as e:
            # Check if this is a "No service registered" error for a disabled provider
            if "No service registered for inference with provider" in str(e):
                adapter_config = self._adapter_configs.get(adapter_name, {})
                inference_provider = adapter_config.get('inference_provider') or self.config.get('general', {}).get('inference_provider', 'unknown')

                self.logger.warning("=" * 80)
                self.logger.warning(f"SKIPPING ADAPTER '{adapter_name}': Inference provider not available")
                self.logger.warning("=" * 80)
                self.logger.warning(f"The adapter '{adapter_name}' specifies inference provider '{inference_provider}'")
                self.logger.warning(f"which is not registered (likely disabled in config/inference.yaml).")
                self.logger.warning("")
                self.logger.warning("To fix this:")
                self.logger.warning(f"  1. Enable '{inference_provider}' in config/inference.yaml, OR")
                self.logger.warning(f"  2. Change the adapter's inference_provider in config/adapters.yaml, OR")
                self.logger.warning(f"  3. Disable this adapter by setting 'enabled: false' in config/adapters.yaml")
                self.logger.warning("")
                self.logger.warning(f"The adapter '{adapter_name}' will NOT be available.")
                self.logger.warning("=" * 80)

                # Don't cache this adapter but don't crash the server
                # The adapter simply won't be available for use
                # Re-raise so caller knows this adapter is not available, but they can handle it
                raise ValueError(f"Adapter '{adapter_name}' cannot be loaded: provider '{inference_provider}' is disabled") from e

            else:
                # Re-raise other ValueError exceptions
                self.logger.error(f"Failed to load adapter {adapter_name}: {str(e)}")
                raise

        except Exception as e:
            self.logger.error(f"Failed to load adapter {adapter_name}: {str(e)}")
            raise
        finally:
            # Remove from initializing set
            with self._cache_lock:
                self._initializing_adapters.discard(adapter_name)

    async def get_overridden_provider(self, provider_name: str, adapter_name: str = None) -> Any:
        """
        Get an inference provider instance by name, loading and caching it if necessary.
        This is for providers specified as overrides in adapter configs.

        Args:
            provider_name: The name of the provider to create
            adapter_name: Optional adapter name to get model override from
        """
        if not provider_name:
            raise ValueError("Provider name cannot be empty")

        # Create cache key that includes adapter-specific model if present
        cache_key = provider_name
        model_override = None

        if adapter_name and adapter_name in self._adapter_configs:
            adapter_config = self._adapter_configs[adapter_name]
            if adapter_config.get('model'):
                model_override = adapter_config['model']
                cache_key = f"{provider_name}:{model_override}"
                if self.verbose:
                    self.logger.info(f"Found model override '{model_override}' for adapter '{adapter_name}'")

        # Check cache with the specific key
        if cache_key in self._provider_cache:
            if self.verbose:
                self.logger.debug(f"Using cached provider: {cache_key}")
            return self._provider_cache[cache_key]

        # Try to claim initialization ownership
        should_initialize = False
        with self._provider_cache_lock:
            if cache_key in self._provider_cache:
                return self._provider_cache[cache_key]
            if cache_key not in self._provider_initializing:
                self._provider_initializing.add(cache_key)
                should_initialize = True

        # If someone else is initializing, wait for them
        if not should_initialize:
            while True:
                await asyncio.sleep(0.1)
                with self._provider_cache_lock:
                    if cache_key in self._provider_cache:
                        return self._provider_cache[cache_key]
                    if cache_key not in self._provider_initializing:
                        # Initializer failed, we should try
                        self._provider_initializing.add(cache_key)
                        should_initialize = True
                        break

        try:
            # Prepare config with model override if specified
            import copy
            config_for_provider = copy.deepcopy(self.config)

            if model_override:
                # Ensure the inference section exists
                if 'inference' not in config_for_provider:
                    config_for_provider['inference'] = {}
                if provider_name not in config_for_provider['inference']:
                    config_for_provider['inference'][provider_name] = {}

                # Set the model override
                config_for_provider['inference'][provider_name]['model'] = model_override
                self.logger.info(f"Loading inference provider '{provider_name}' with model override: {model_override}")
            else:
                self.logger.info(f"Loading inference provider '{provider_name}' with default model")

            try:
                from server.inference.pipeline.providers import UnifiedProviderFactory as ProviderFactory
            except ImportError:
                # Fallback for test environment
                from inference.pipeline.providers import UnifiedProviderFactory as ProviderFactory

            # Create and initialize the provider
            provider = ProviderFactory.create_provider_by_name(provider_name, config_for_provider)
            if hasattr(provider, 'initialize'):
                if asyncio.iscoroutinefunction(provider.initialize):
                    await provider.initialize()
                else:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(self._thread_pool, provider.initialize)

            # Cache the initialized provider with the specific key
            with self._provider_cache_lock:
                self._provider_cache[cache_key] = provider

            self.logger.info(f"Successfully cached inference provider: {cache_key}")
            return provider
        except Exception as e:
            self.logger.error(f"Failed to load overridden provider {provider_name}: {str(e)}")
            raise
        finally:
            with self._provider_cache_lock:
                self._provider_initializing.discard(cache_key)

    async def get_overridden_embedding(self, provider_name: str, adapter_name: str = None) -> Any:
        """
        Get an embedding service instance by name, loading and caching it if necessary.
        This is for embedding providers specified as overrides in adapter configs.

        Args:
            provider_name: The name of the embedding provider to create
            adapter_name: Optional adapter name for logging context
        """
        if not provider_name:
            raise ValueError("Embedding provider name cannot be empty")

        # Create cache key for the embedding service
        # Get the model from embeddings config
        embedding_config = self.config.get('embeddings', {}).get(provider_name, {})
        model = embedding_config.get('model', '')
        cache_key = f"{provider_name}:{model}" if model else provider_name

        # Check cache with the specific key
        if cache_key in self._embedding_cache:
            if self.verbose:
                self.logger.debug(f"Using cached embedding service: {cache_key}")
            return self._embedding_cache[cache_key]

        # Try to claim initialization ownership
        should_initialize = False
        with self._embedding_cache_lock:
            if cache_key in self._embedding_cache:
                return self._embedding_cache[cache_key]
            if cache_key not in self._embedding_initializing:
                self._embedding_initializing.add(cache_key)
                should_initialize = True

        # If someone else is initializing, wait for them
        if not should_initialize:
            while True:
                await asyncio.sleep(0.1)
                with self._embedding_cache_lock:
                    if cache_key in self._embedding_cache:
                        return self._embedding_cache[cache_key]
                    if cache_key not in self._embedding_initializing:
                        # Initializer failed, we should try
                        self._embedding_initializing.add(cache_key)
                        should_initialize = True
                        break

        try:
            adapter_context = f" for adapter '{adapter_name}'" if adapter_name else ""
            if model:
                self.logger.info(f"Loading embedding service '{provider_name}/{model}'{adapter_context}")
            else:
                self.logger.info(f"Loading embedding service '{provider_name}'{adapter_context}")

            # Import the embedding service factory
            try:
                from server.embeddings.base import EmbeddingServiceFactory
            except ImportError:
                from embeddings.base import EmbeddingServiceFactory

            # Create the embedding service
            embedding_service = EmbeddingServiceFactory.create_embedding_service(
                self.config,
                provider_name
            )

            # Initialize if needed
            if hasattr(embedding_service, 'initialize'):
                if asyncio.iscoroutinefunction(embedding_service.initialize):
                    await embedding_service.initialize()
                else:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(self._thread_pool, embedding_service.initialize)

            # Cache the initialized embedding service
            with self._embedding_cache_lock:
                self._embedding_cache[cache_key] = embedding_service

            self.logger.info(f"Successfully cached embedding service: {cache_key}{adapter_context}")
            return embedding_service
        except Exception as e:
            self.logger.error(f"Failed to load embedding service {provider_name}: {str(e)}")
            raise
        finally:
            with self._embedding_cache_lock:
                self._embedding_initializing.discard(cache_key)

    async def _load_adapter(self, adapter_name: str) -> Any:
        """Load and initialize an adapter asynchronously"""
        # Get adapter configuration
        adapter_config = self._adapter_configs.get(adapter_name)
        if not adapter_config:
            raise ValueError(f"No adapter configuration found for: {adapter_name}")

        # Preload embedding service if adapter has an override (and it's not null)
        if adapter_config.get('embedding_provider'):
            embedding_provider = adapter_config['embedding_provider']
            try:
                await self.get_overridden_embedding(embedding_provider, adapter_name)
            except Exception as e:
                self.logger.warning(f"Failed to preload embedding service for adapter {adapter_name}: {str(e)}")

        # Run the import and initialization in a thread pool to prevent blocking
        loop = asyncio.get_event_loop()
        
        def _sync_load():
            # This runs in a thread, so it won't block the event loop
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
            import copy
            config_with_adapter = copy.deepcopy(self.config)
            # Pass adapter config in the standardized key for all retrievers
            config_with_adapter['adapter_config'] = adapter_config_params

            # For intent adapters, include stores configuration
            if domain_adapter_name == 'intent' and 'stores' in self.config:
                config_with_adapter['stores'] = self.config['stores']

            # Include adapter-level inference provider override if specified
            if 'inference_provider' in adapter_config:
                config_with_adapter['inference_provider'] = adapter_config['inference_provider']
                if self.verbose:
                    logger.info(f"Setting inference provider override: {adapter_config['inference_provider']} for adapter: {adapter_name}")

            # Include adapter-level model override if specified
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

            # Include adapter-level embedding provider override if specified (and it's not null)
            if adapter_config.get('embedding_provider'):
                # Ensure the 'embedding' key exists
                if 'embedding' not in config_with_adapter:
                    config_with_adapter['embedding'] = {}

                config_with_adapter['embedding']['provider'] = adapter_config['embedding_provider']
                if self.verbose:
                    logger.info(f"Setting embedding provider override: {adapter_config['embedding_provider']} for adapter: {adapter_name}")

            # Include adapter-level database override if specified
            if adapter_config.get('database'):
                # Ensure the datasources section exists
                if 'datasources' not in config_with_adapter:
                    config_with_adapter['datasources'] = {}
                if datasource_name not in config_with_adapter['datasources']:
                    config_with_adapter['datasources'][datasource_name] = {}
                
                # Set the database override
                original_database = config_with_adapter['datasources'][datasource_name].get('database', 'default')
                config_with_adapter['datasources'][datasource_name]['database'] = adapter_config['database']
                
                if self.verbose:
                    logger.info(
                        f"Database override for adapter '{adapter_name}': '{original_database}' -> '{adapter_config['database']}' (datasource: {datasource_name})"
                    )

            # Create datasource instance for the retriever using the datasource registry with pooling
            datasource_instance = None
            if datasource_name and datasource_name != 'none':
                try:
                    from datasources.registry import get_registry as get_datasource_registry
                    datasource_registry = get_datasource_registry()
                    # Use get_or_create_datasource for pooling instead of create_datasource
                    datasource_instance = datasource_registry.get_or_create_datasource(
                        datasource_name=datasource_name,
                        config=config_with_adapter,
                        logger_instance=logger
                    )
                    if datasource_instance:
                        logger.info(f"Got datasource instance '{datasource_name}' for retriever in adapter '{adapter_name}' (pooled)")
                    else:
                        logger.warning(f"Failed to get datasource '{datasource_name}' for adapter '{adapter_name}', retriever will not have access to datasource")
                except Exception as e:
                    logger.warning(f"Error getting datasource '{datasource_name}' for adapter '{adapter_name}': {e}. Retriever will proceed without datasource.")
                    datasource_instance = None

            # Create retriever instance with datasource
            retriever = retriever_class(
                config=config_with_adapter,
                domain_adapter=domain_adapter,
                datasource=datasource_instance
            )

            # Store metadata for cleanup: datasource name and config
            retriever._datasource_name = datasource_name
            retriever._datasource_config_for_release = config_with_adapter
            
            return retriever
        
        # Load adapter in thread pool
        retriever = await loop.run_in_executor(self._thread_pool, _sync_load)
        
        # Initialize the retriever (if it's async)
        if hasattr(retriever, 'initialize'):
            if asyncio.iscoroutinefunction(retriever.initialize):
                await retriever.initialize()
            else:
                await loop.run_in_executor(self._thread_pool, retriever.initialize)
        
        # Initialize embeddings for intent adapters that support it
        if hasattr(retriever, 'domain_adapter') and retriever.domain_adapter:
            domain_adapter = retriever.domain_adapter
            if hasattr(domain_adapter, 'initialize_embeddings'):
                # Try to get store manager from multiple sources
                store_manager = None
                
                # First, check app state for store manager
                if self.app_state:
                    store_manager = getattr(self.app_state, 'store_manager', None)
                    if not store_manager:
                        # Check for vector_store_manager (legacy name)
                        store_manager = getattr(self.app_state, 'vector_store_manager', None)
                
                # If no store manager in app state, create one if vector stores are configured
                if not store_manager:
                    try:
                        from vector_stores.base.store_manager import StoreManager
                        store_manager = StoreManager()
                        self.logger.info(f"Created new StoreManager for adapter {adapter_name}")
                    except ImportError:
                        self.logger.warning("Vector store system not available")
                
                if store_manager:
                    self.logger.info(f"Initializing embeddings for adapter {adapter_name} with store manager")
                    await domain_adapter.initialize_embeddings(store_manager)
                else:
                    self.logger.info(f"Initializing embeddings for adapter {adapter_name} without store manager")
                    await domain_adapter.initialize_embeddings()
        
        return retriever
    
    def get_adapter_config(self, adapter_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the configuration for a specific adapter.
        
        Args:
            adapter_name: The name of the adapter
            
        Returns:
            The adapter configuration dictionary or None if not found
        """
        return self._adapter_configs.get(adapter_name)
    
    def get_available_adapters(self) -> list[str]:
        """
        Get list of available adapter names.
        
        Returns:
            List of adapter names that can be loaded
        """
        return list(self._adapter_configs.keys())
    
    def get_cached_adapters(self) -> list[str]:
        """
        Get list of currently cached adapter names.
        
        Returns:
            List of adapter names that are currently cached
        """
        return list(self._adapter_cache.keys())
    
    async def preload_adapter(self, adapter_name: str) -> None:
        """
        Preload an adapter into cache.
        
        Args:
            adapter_name: Name of the adapter to preload
        """
        try:
            await self.get_adapter(adapter_name)
            self.logger.info(f"Preloaded adapter: {adapter_name}")
        except Exception as e:
            self.logger.error(f"Failed to preload adapter {adapter_name}: {str(e)}")
    
    async def preload_all_adapters(self, timeout_per_adapter: float = 30.0) -> Dict[str, Any]:
        """
        Preload all adapters in parallel with timeout protection.
        
        Args:
            timeout_per_adapter: Maximum time to wait for each adapter to load
            
        Returns:
            Dict with preload results for each adapter
        """
        available_adapters = self.get_available_adapters()
        if not available_adapters:
            return {}
        
        self.logger.info(f"Preloading {len(available_adapters)} adapters in parallel...")
        
        # Create tasks for parallel loading
        async def load_adapter_with_timeout(adapter_name: str):
            try:
                # Load adapter with timeout
                await asyncio.wait_for(
                    self.get_adapter(adapter_name),
                    timeout=timeout_per_adapter
                )

                # Determine the inference provider and model for logging
                adapter_config = self.get_adapter_config(adapter_name) or {}
                inference_provider = adapter_config.get('inference_provider') or self.config.get('general', {}).get('inference_provider', 'default')
                model_override = adapter_config.get('model')

                # Also preload the inference provider to catch disabled provider errors early
                try:
                    await self.get_overridden_provider(inference_provider, adapter_name)
                    self.logger.debug(f"Successfully preloaded inference provider '{inference_provider}' for adapter '{adapter_name}'")
                except ValueError as provider_error:
                    if "No service registered for inference with provider" in str(provider_error):
                        # This is a disabled provider error
                        raise ValueError(f"Adapter '{adapter_name}' uses disabled inference provider '{inference_provider}'") from provider_error
                    else:
                        raise

                # Get embedding configuration
                embedding_provider = adapter_config.get('embedding_provider') or self.config.get('embedding', {}).get('provider', 'ollama')
                embedding_model = None
                if embedding_provider in self.config.get('embeddings', {}):
                    embedding_model = self.config.get('embeddings', {}).get(embedding_provider, {}).get('model')

                # Check if this is an intent adapter and get store info
                adapter_type = adapter_config.get('adapter')
                store_info = ""
                if adapter_type == 'intent':
                    store_name = adapter_config.get('config', {}).get('store_name')
                    if store_name:
                        store_info = f", store: {store_name}"

                # Build message parts
                msg_parts = []

                # Inference provider and model
                if model_override:
                    msg_parts.append(f"inference: {inference_provider}/{model_override}")
                else:
                    msg_parts.append(f"inference: {inference_provider}")

                # Embedding provider and model
                if embedding_model:
                    msg_parts.append(f"embedding: {embedding_provider}/{embedding_model}")
                else:
                    msg_parts.append(f"embedding: {embedding_provider}")

                # Store info for intent adapters
                if store_info:
                    msg_parts.append(store_info.lstrip(", "))

                message = f"Preloaded successfully ({', '.join(msg_parts)})"

                return {
                    "adapter_name": adapter_name,
                    "success": True,
                    "message": message
                }
            except asyncio.TimeoutError:
                return {
                    "adapter_name": adapter_name,
                    "success": False,
                    "error": f"Timeout after {timeout_per_adapter}s"
                }
            except ValueError as e:
                # Check if this is a disabled provider error
                if "No service registered for inference with provider" in str(e):
                    adapter_config = self.get_adapter_config(adapter_name) or {}
                    inference_provider = adapter_config.get('inference_provider') or self.config.get('general', {}).get('inference_provider', 'unknown')
                    return {
                        "adapter_name": adapter_name,
                        "success": False,
                        "error": f"Inference provider '{inference_provider}' is disabled (enable in config/inference.yaml)"
                    }
                else:
                    return {
                        "adapter_name": adapter_name,
                        "success": False,
                        "error": str(e)
                    }
            except Exception as e:
                return {
                    "adapter_name": adapter_name,
                    "success": False,
                    "error": str(e)
                }
        
        # Run all adapter loading tasks in parallel
        tasks = [load_adapter_with_timeout(name) for name in available_adapters]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        preload_results = {}
        successful_count = 0
        
        for result in results:
            if isinstance(result, Exception):
                # This shouldn't happen due to exception handling in load_adapter_with_timeout
                self.logger.error(f"Unexpected exception in adapter preloading: {result}")
                continue
                
            adapter_name = result["adapter_name"]
            preload_results[adapter_name] = result
            
            if result["success"]:
                successful_count += 1
                self.logger.info(f"✅ {adapter_name}: {result['message']}")
            else:
                self.logger.warning(f"❌ {adapter_name}: {result['error']}")
        
        self.logger.info(f"Adapter preloading completed: {successful_count}/{len(available_adapters)} successful")
        
        return preload_results
    
    async def remove_adapter(self, adapter_name: str) -> bool:
        """
        Remove an adapter from cache and clean up resources.
        
        Args:
            adapter_name: Name of the adapter to remove
            
        Returns:
            True if adapter was removed, False if not found
        """
        with self._cache_lock:
            if adapter_name not in self._adapter_cache:
                return False
            
            adapter = self._adapter_cache.pop(adapter_name)
            self._adapter_locks.pop(adapter_name, None)
        
        # Try to close the adapter if it has a close method
        try:
            if hasattr(adapter, 'close'):
                if asyncio.iscoroutinefunction(adapter.close):
                    await adapter.close()
                else:
                    adapter.close()
        except Exception as e:
            self.logger.warning(f"Error closing adapter {adapter_name}: {str(e)}")

        # Release the datasource reference (uses reference counting)
        try:
            if (hasattr(adapter, '_datasource') and adapter._datasource is not None and
                hasattr(adapter, '_datasource_name') and hasattr(adapter, '_datasource_config_for_release')):
                from datasources.registry import get_registry as get_datasource_registry
                datasource_registry = get_datasource_registry()
                datasource_registry.release_datasource(
                    datasource_name=adapter._datasource_name,
                    config=adapter._datasource_config_for_release,
                    logger_instance=self.logger
                )
        except Exception as e:
            self.logger.warning(f"Error releasing datasource for adapter {adapter_name}: {str(e)}")

        self.logger.info(f"Removed adapter from cache: {adapter_name}")
        return True
    
    async def clear_cache(self) -> None:
        """Clear all cached adapters and clean up resources."""
        adapter_names = list(self._adapter_cache.keys())
        
        for adapter_name in adapter_names:
            await self.remove_adapter(adapter_name)
        
        self.logger.info("Cleared all adapters from cache")
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on the adapter manager.

        Returns:
            Health status information
        """
        # Get datasource pool stats
        try:
            from datasources.registry import get_registry as get_datasource_registry
            datasource_registry = get_datasource_registry()
            datasource_stats = datasource_registry.get_pool_stats()
        except Exception:
            datasource_stats = {}

        return {
            "status": "healthy",
            "available_adapters": len(self._adapter_configs),
            "cached_adapters": len(self._adapter_cache),
            "cached_inference_providers": len(self._provider_cache),
            "cached_embedding_services": len(self._embedding_cache),
            "initializing_adapters": len(self._initializing_adapters),
            "adapter_configs": list(self._adapter_configs.keys()),
            "cached_adapter_names": list(self._adapter_cache.keys()),
            "cached_inference_provider_keys": list(self._provider_cache.keys()),
            "cached_embedding_service_keys": list(self._embedding_cache.keys()),
            "datasource_pool": datasource_stats
        }
    
    async def close(self) -> None:
        """Clean up all resources."""
        # Close all cached providers
        for provider_name, provider in self._provider_cache.items():
            try:
                if hasattr(provider, 'close'):
                    if asyncio.iscoroutinefunction(provider.close):
                        await provider.close()
                    else:
                        provider.close()
                self.logger.info(f"Closed cached provider: {provider_name}")
            except Exception as e:
                self.logger.warning(f"Error closing cached provider {provider_name}: {str(e)}")

        self._provider_cache.clear()

        # Close all cached embedding services
        for embedding_name, embedding_service in self._embedding_cache.items():
            try:
                if hasattr(embedding_service, 'close'):
                    if asyncio.iscoroutinefunction(embedding_service.close):
                        await embedding_service.close()
                    else:
                        embedding_service.close()
                self.logger.info(f"Closed cached embedding service: {embedding_name}")
            except Exception as e:
                self.logger.warning(f"Error closing cached embedding service {embedding_name}: {str(e)}")

        self._embedding_cache.clear()

        # Clear all cached adapters
        await self.clear_cache()

        # Shutdown datasource pool
        try:
            from datasources.registry import get_registry as get_datasource_registry
            datasource_registry = get_datasource_registry()
            await datasource_registry.shutdown_pool(self.logger)
        except Exception as e:
            self.logger.error(f"Error shutting down datasource pool: {e}")

        # Shutdown thread pool
        self._thread_pool.shutdown(wait=True)

        self.logger.info("Dynamic Adapter Manager closed")


class AdapterProxy:
    """
    Proxy object that provides a retriever-like interface for the dynamic adapter manager.
    
    This allows LLM clients to use the adapter manager as if it were a single retriever,
    while actually routing to the appropriate adapter based on the adapter name.
    """
    
    def __init__(self, adapter_manager: DynamicAdapterManager):
        """
        Initialize the adapter proxy.
        
        Args:
            adapter_manager: The dynamic adapter manager instance
        """
        self.adapter_manager = adapter_manager
        self.logger = logger
    
    async def get_relevant_context(self, 
                                   query: str, 
                                   adapter_name: str,
                                   api_key: Optional[str] = None,
                                   **kwargs) -> list[Dict[str, Any]]:
        """
        Get relevant context using the specified adapter.
        
        Args:
            query: The user's query
            adapter_name: Name of the adapter to use
            api_key: Optional API key (for backward compatibility)
            **kwargs: Additional parameters
            
        Returns:
            List of relevant context items
        """
        if not adapter_name:
            raise ValueError("Adapter name is required")
        
        try:
            # Get the appropriate adapter
            adapter = await self.adapter_manager.get_adapter(adapter_name)
            
            # Call the adapter's get_relevant_context method
            # Pass api_key for compatibility but prioritize adapter_name routing
            return await adapter.get_relevant_context(
                query=query,
                api_key=api_key,
                **kwargs
            )
        except Exception as e:
            self.logger.error(f"Error getting context from adapter {adapter_name}: {str(e)}")
            return []
    
    async def initialize(self) -> None:
        """Initialize method for compatibility."""
        # The adapter manager handles initialization of individual adapters
        pass
    
    async def close(self) -> None:
        """Close method for compatibility."""
        await self.adapter_manager.close() 
