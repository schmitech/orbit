"""
Dynamic Adapter Manager Service for handling on-demand adapter loading.

This service replaces the static single adapter initialization with a dynamic
system that loads adapters based on API key configurations.

Refactored to use specialized components for better maintainability:
- Cache managers for different service types
- Configuration management
- Adapter loading
- Reload orchestration
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

from .cache import (
    AdapterCacheManager,
    ProviderCacheManager,
    EmbeddingCacheManager,
    RerankerCacheManager,
    VisionCacheManager,
    AudioCacheManager,
)
from .config import AdapterConfigManager, ConfigChangeDetector
from .loader import AdapterLoader
from .reload import DependencyCacheCleaner, AdapterReloader

logger = logging.getLogger(__name__)


class DynamicAdapterManager:
    """
    Manages dynamic loading and caching of adapters based on API key configurations.

    This service acts as a facade coordinating specialized components:
    - Cache managers for adapters, providers, embeddings, and rerankers
    - Configuration management for adapter configs
    - Adapter loading and initialization
    - Reload orchestration for hot-swapping

    This class maintains backward-compatible public API while delegating
    to specialized components for better maintainability.
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

        # Thread pool for adapter initialization
        self._thread_pool = ThreadPoolExecutor(max_workers=5)

        # Initialize specialized components
        self._init_cache_managers()
        self._init_config_manager()
        self._init_loader()
        self._init_reloader()

        self.logger.info("Dynamic Adapter Manager initialized")

    def _init_cache_managers(self) -> None:
        """Initialize cache manager components."""
        self.adapter_cache = AdapterCacheManager()
        self.provider_cache = ProviderCacheManager(self.config, self._thread_pool)
        self.embedding_cache = EmbeddingCacheManager(self.config, self._thread_pool)
        self.reranker_cache = RerankerCacheManager(self.config, self._thread_pool)
        self.vision_cache = VisionCacheManager(self.config, self._thread_pool)
        self.audio_cache = AudioCacheManager(self.config, self._thread_pool)

    def _init_config_manager(self) -> None:
        """Initialize configuration manager."""
        self.config_manager = AdapterConfigManager(self.config)

    def _init_loader(self) -> None:
        """Initialize adapter loader."""
        self.adapter_loader = AdapterLoader(
            self.config,
            self.app_state,
            self.provider_cache,
            self.embedding_cache,
            self.reranker_cache,
            self.vision_cache,
            self.audio_cache,
            self._thread_pool
        )

    def _init_reloader(self) -> None:
        """Initialize reload components."""
        self.dependency_cleaner = DependencyCacheCleaner(
            self.config,
            self.provider_cache,
            self.embedding_cache,
            self.reranker_cache,
            self.vision_cache,
            self.audio_cache
        )
        self.reloader = AdapterReloader(
            self.config_manager,
            self.adapter_cache,
            self.adapter_loader,
            self.dependency_cleaner
        )

    async def get_adapter(self, adapter_name: str) -> Any:
        """
        Get an adapter instance by name, loading it if necessary.

        Args:
            adapter_name: Name of the adapter to retrieve

        Returns:
            The initialized adapter instance

        Raises:
            ValueError: If adapter configuration is not found or disabled
            Exception: If adapter initialization fails
        """
        if not adapter_name:
            raise ValueError("Adapter name cannot be empty")

        # Check if adapter is in active configs (prevents disabled adapters from being used)
        if not self.config_manager.contains(adapter_name):
            self.logger.warning(f"Attempted to access disabled or removed adapter: {adapter_name}")
            raise ValueError(f"Adapter '{adapter_name}' is not available (may be disabled or removed)")

        # Check if adapter is already cached
        cached_adapter = self.adapter_cache.get(adapter_name)
        if cached_adapter:
            logger.debug(f"Using cached adapter: {adapter_name}")
            return cached_adapter

        # Try to claim initialization ownership
        if not self.adapter_cache.claim_initialization(adapter_name):
            # Someone else is initializing, wait for them
            return await self._wait_for_adapter_initialization(adapter_name)

        try:
            # Load the adapter
            adapter_config = self.config_manager.get(adapter_name)
            adapter = await self.adapter_loader.load_adapter(adapter_name, adapter_config)

            # Cache the adapter
            self.adapter_cache.put(adapter_name, adapter)

            # Log adapter configuration details
            self._log_adapter_loaded(adapter_name, adapter_config)

            return adapter

        except ValueError as e:
            self._handle_adapter_load_error(adapter_name, e)
            raise
        except Exception as e:
            self.logger.error(f"Failed to load adapter {adapter_name}: {str(e)}")
            raise
        finally:
            self.adapter_cache.release_initialization(adapter_name)

    async def _wait_for_adapter_initialization(self, adapter_name: str) -> Any:
        """
        Wait for another process to finish initializing an adapter.

        Args:
            adapter_name: Name of the adapter being initialized

        Returns:
            The initialized adapter instance
        """
        while True:
            await asyncio.sleep(0.1)
            cached_adapter = self.adapter_cache.get(adapter_name)
            if cached_adapter:
                return cached_adapter
            if not self.adapter_cache.is_initializing(adapter_name):
                # Initializer failed, we should try
                if self.adapter_cache.claim_initialization(adapter_name):
                    break
        # Recursively call get_adapter to load it ourselves
        self.adapter_cache.release_initialization(adapter_name)
        return await self.get_adapter(adapter_name)

    def _log_adapter_loaded(self, adapter_name: str, adapter_config: Dict[str, Any]) -> None:
        """Log detailed information about a loaded adapter."""
        inference_provider = adapter_config.get('inference_provider') or self.config.get('general', {}).get('inference_provider', 'default')
        model_override = adapter_config.get('model')

        # Get embedding configuration
        embedding_provider = adapter_config.get('embedding_provider') or self.config.get('embedding', {}).get('provider', 'ollama')
        embedding_model = None
        if embedding_provider in self.config.get('embeddings', {}):
            embedding_model = self.config.get('embeddings', {}).get(embedding_provider, {}).get('model')

        # Get reranker configuration
        reranker_provider = adapter_config.get('reranker_provider')
        reranker_model = None
        if reranker_provider and reranker_provider in self.config.get('rerankers', {}):
            reranker_model = self.config.get('rerankers', {}).get(reranker_provider, {}).get('model')

        # Check if this is an intent adapter
        adapter_type = adapter_config.get('adapter')
        store_info = ""
        if adapter_type == 'intent':
            store_name = adapter_config.get('config', {}).get('store_name')
            if store_name:
                store_info = f", store: {store_name}"

        # Build log message
        log_parts = [f"Successfully loaded adapter '{adapter_name}'"]

        if model_override:
            log_parts.append(f"inference: {inference_provider}/{model_override}")
        else:
            log_parts.append(f"inference: {inference_provider}")

        if embedding_model:
            log_parts.append(f"embedding: {embedding_provider}/{embedding_model}")
        else:
            log_parts.append(f"embedding: {embedding_provider}")

        if reranker_provider:
            if reranker_model:
                log_parts.append(f"reranker: {reranker_provider}/{reranker_model}")
            else:
                log_parts.append(f"reranker: {reranker_provider}")

        if store_info:
            log_parts.append(store_info.lstrip(", "))

        if adapter_config.get('database'):
            log_parts.append(f"database: {adapter_config['database']}")

        self.logger.info(f"{log_parts[0]} ({', '.join(log_parts[1:])})")

    def _handle_adapter_load_error(self, adapter_name: str, error: ValueError) -> None:
        """Handle adapter loading errors with helpful messages."""
        if "No service registered for inference with provider" in str(error):
            adapter_config = self.config_manager.get(adapter_name) or {}
            inference_provider = adapter_config.get('inference_provider') or self.config.get('general', {}).get('inference_provider', 'unknown')

            self.logger.warning("=" * 80)
            self.logger.warning(f"SKIPPING ADAPTER '{adapter_name}': Inference provider not available")
            self.logger.warning("=" * 80)
            self.logger.warning(f"The adapter '{adapter_name}' specifies inference provider '{inference_provider}'")
            self.logger.warning("which is not registered (likely disabled in config/inference.yaml).")
            self.logger.warning("")
            self.logger.warning("To fix this:")
            self.logger.warning(f"  1. Enable '{inference_provider}' in config/inference.yaml, OR")
            self.logger.warning(f"  2. Change the adapter's inference_provider in config/adapters.yaml, OR")
            self.logger.warning(f"  3. Disable this adapter by setting 'enabled: false' in config/adapters.yaml")
            self.logger.warning("")
            self.logger.warning(f"The adapter '{adapter_name}' will NOT be available.")
            self.logger.warning("=" * 80)

            raise ValueError(f"Adapter '{adapter_name}' cannot be loaded: provider '{inference_provider}' is disabled") from error
        else:
            self.logger.error(f"Failed to load adapter {adapter_name}: {str(error)}")

    async def get_overridden_provider(self, provider_name: str, adapter_name: str = None) -> Any:
        """
        Get an inference provider instance by name, loading and caching it if necessary.

        Args:
            provider_name: The name of the provider to create
            adapter_name: Optional adapter name to get model override from
        """
        if not provider_name:
            raise ValueError("Provider name cannot be empty")

        model_override = None
        if adapter_name:
            adapter_config = self.config_manager.get(adapter_name)
            if adapter_config and adapter_config.get('model'):
                model_override = adapter_config['model']
                logger.debug(f"Found model override '{model_override}' for adapter '{adapter_name}'")

        return await self.provider_cache.create_provider(provider_name, model_override, adapter_name)

    async def get_overridden_embedding(self, provider_name: str, adapter_name: str = None) -> Any:
        """
        Get an embedding service instance by name, loading and caching it if necessary.

        Args:
            provider_name: The name of the embedding provider to create
            adapter_name: Optional adapter name for logging context
        """
        if not provider_name:
            raise ValueError("Embedding provider name cannot be empty")

        return await self.embedding_cache.create_service(provider_name, adapter_name)

    async def get_overridden_reranker(self, provider_name: str, adapter_name: str = None) -> Any:
        """
        Get a reranker service instance by name, loading and caching it if necessary.

        Args:
            provider_name: The name of the reranker provider to create
            adapter_name: Optional adapter name for logging context
        """
        if not provider_name:
            raise ValueError("Reranker provider name cannot be empty")

        return await self.reranker_cache.create_service(provider_name, adapter_name)

    async def get_overridden_vision(self, provider_name: str, adapter_name: str = None) -> Any:
        """
        Get a vision service instance by name, loading and caching it if necessary.

        Args:
            provider_name: The name of the vision provider to create
            adapter_name: Optional adapter name for logging context
        """
        if not provider_name:
            raise ValueError("Vision provider name cannot be empty")

        return await self.vision_cache.create_service(provider_name, adapter_name)

    async def get_overridden_audio(self, provider_name: str, adapter_name: str = None) -> Any:
        """
        Get an audio service instance by name, loading and caching it if necessary.

        Args:
            provider_name: The name of the audio provider to create
            adapter_name: Optional adapter name for logging context
        """
        if not provider_name:
            raise ValueError("Audio provider name cannot be empty")

        return await self.audio_cache.create_service(provider_name, adapter_name)

    def get_adapter_config(self, adapter_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the configuration for a specific adapter.

        Args:
            adapter_name: The name of the adapter

        Returns:
            The adapter configuration dictionary or None if not found
        """
        return self.config_manager.get(adapter_name)

    def get_available_adapters(self) -> list[str]:
        """
        Get list of available adapter names.

        Returns:
            List of adapter names that can be loaded
        """
        return self.config_manager.get_available_adapters()

    def get_cached_adapters(self) -> list[str]:
        """
        Get list of currently cached adapter names.

        Returns:
            List of adapter names that are currently cached
        """
        return self.adapter_cache.get_cached_names()

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

        async def load_adapter_with_timeout(adapter_name: str):
            try:
                await asyncio.wait_for(
                    self.get_adapter(adapter_name),
                    timeout=timeout_per_adapter
                )

                # Also preload the inference provider
                adapter_config = self.get_adapter_config(adapter_name) or {}
                inference_provider = adapter_config.get('inference_provider') or self.config.get('general', {}).get('inference_provider', 'default')

                try:
                    await self.get_overridden_provider(inference_provider, adapter_name)
                except ValueError as provider_error:
                    if "No service registered for inference with provider" in str(provider_error):
                        raise ValueError(f"Adapter '{adapter_name}' uses disabled inference provider '{inference_provider}'") from provider_error
                    else:
                        raise

                # Build success message
                message = self._build_preload_success_message(adapter_name, adapter_config)

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
                return self._build_preload_error_result(adapter_name, e)
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

    def _build_preload_success_message(self, adapter_name: str, adapter_config: Dict[str, Any]) -> str:
        """Build success message for adapter preloading."""
        model_override = adapter_config.get('model')
        inference_provider = adapter_config.get('inference_provider') or self.config.get('general', {}).get('inference_provider', 'default')

        embedding_provider = adapter_config.get('embedding_provider') or self.config.get('embedding', {}).get('provider', 'ollama')
        embedding_model = None
        if embedding_provider in self.config.get('embeddings', {}):
            embedding_model = self.config.get('embeddings', {}).get(embedding_provider, {}).get('model')

        reranker_provider = adapter_config.get('reranker_provider')
        reranker_model = None
        if reranker_provider and reranker_provider in self.config.get('rerankers', {}):
            reranker_model = self.config.get('rerankers', {}).get(reranker_provider, {}).get('model')

        adapter_type = adapter_config.get('adapter')
        store_info = ""
        if adapter_type == 'intent':
            store_name = adapter_config.get('config', {}).get('store_name')
            if store_name:
                store_info = f", store: {store_name}"

        msg_parts = []

        if model_override:
            msg_parts.append(f"inference: {inference_provider}/{model_override}")
        else:
            msg_parts.append(f"inference: {inference_provider}")

        if embedding_model:
            msg_parts.append(f"embedding: {embedding_provider}/{embedding_model}")
        else:
            msg_parts.append(f"embedding: {embedding_provider}")

        if reranker_provider:
            if reranker_model:
                msg_parts.append(f"reranker: {reranker_provider}/{reranker_model}")
            else:
                msg_parts.append(f"reranker: {reranker_provider}")

        if store_info:
            msg_parts.append(store_info.lstrip(", "))

        return f"Preloaded successfully ({', '.join(msg_parts)})"

    def _build_preload_error_result(self, adapter_name: str, error: ValueError) -> Dict[str, Any]:
        """Build error result for adapter preloading."""
        if "No service registered for inference with provider" in str(error):
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
                "error": str(error)
            }

    async def remove_adapter(self, adapter_name: str, clear_dependencies: bool = False) -> bool:
        """
        Remove an adapter from cache and clean up resources.

        Args:
            adapter_name: Name of the adapter to remove
            clear_dependencies: If True, clear provider/embedding/reranker caches before removal

        Returns:
            True if adapter was removed, False if not found
        """
        if clear_dependencies:
            old_config = self.config_manager.get(adapter_name)
            if old_config:
                await self.dependency_cleaner.clear_adapter_dependencies(adapter_name, old_config)

        removed = await self.adapter_cache.remove(adapter_name)
        return removed is not None

    async def clear_cache(self) -> None:
        """Clear all cached adapters and clean up resources."""
        await self.adapter_cache.clear()
        self.logger.info("Cleared all adapters from cache")

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on the adapter manager.

        Returns:
            Health status information
        """
        try:
            from datasources.registry import get_registry as get_datasource_registry
            datasource_registry = get_datasource_registry()
            datasource_stats = datasource_registry.get_pool_stats()
        except Exception:
            datasource_stats = {}

        return {
            "status": "healthy",
            "available_adapters": self.config_manager.get_adapter_count(),
            "cached_adapters": self.adapter_cache.get_cache_size(),
            "cached_inference_providers": self.provider_cache.get_cache_size(),
            "cached_embedding_services": self.embedding_cache.get_cache_size(),
            "cached_reranker_services": self.reranker_cache.get_cache_size(),
            "cached_vision_services": self.vision_cache.get_cache_size(),
            "cached_audio_services": self.audio_cache.get_cache_size(),
            "initializing_adapters": self.adapter_cache.get_initializing_count(),
            "adapter_configs": self.config_manager.get_available_adapters(),
            "cached_adapter_names": self.adapter_cache.get_cached_names(),
            "cached_inference_provider_keys": self.provider_cache.get_cached_keys(),
            "cached_embedding_service_keys": self.embedding_cache.get_cached_keys(),
            "cached_reranker_service_keys": self.reranker_cache.get_cached_keys(),
            "cached_vision_service_keys": self.vision_cache.get_cached_keys(),
            "cached_audio_service_keys": self.audio_cache.get_cached_keys(),
            "datasource_pool": datasource_stats
        }

    async def reload_adapter_configs(self, config: Dict[str, Any], adapter_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Reload adapter configurations from new config and perform hot-swap.

        Args:
            config: The new configuration dictionary containing adapter configs
            adapter_name: Optional name of specific adapter to reload. If None, reloads all adapters.

        Returns:
            Summary dict with counts of added/removed/updated adapters
        """
        # Update global config
        self.config = config
        logger.debug("Updated global config for adapter reload")

        # Update config references in all components
        self.adapter_loader.update_config(config)
        self.dependency_cleaner.update_config(config)
        self.config_manager.config = config

        if adapter_name:
            return await self.reloader.reload_single_adapter(adapter_name, config)
        else:
            return await self.reloader.reload_all_adapters(config)

    async def close(self) -> None:
        """Clean up all resources."""
        # Close all cached providers
        await self.provider_cache.close()

        # Close all cached embedding services
        await self.embedding_cache.close()

        # Close all cached reranker services
        await self.reranker_cache.close()

        # Close all cached vision services
        await self.vision_cache.close()

        # Close all cached audio services
        await self.audio_cache.close()

        # Clear all cached adapters
        await self.adapter_cache.clear()

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

    # Backward compatibility properties for internal state access
    @property
    def _adapter_cache(self) -> Dict[str, Any]:
        """Backward compatibility: Direct access to adapter cache dict."""
        return self.adapter_cache._cache

    @property
    def _adapter_configs(self) -> Dict[str, Dict[str, Any]]:
        """Backward compatibility: Direct access to adapter configs dict."""
        return self.config_manager._adapter_configs

    @property
    def _provider_cache(self) -> Dict[str, Any]:
        """Backward compatibility: Direct access to provider cache dict."""
        return self.provider_cache._cache

    @property
    def _embedding_cache(self) -> Dict[str, Any]:
        """Backward compatibility: Direct access to embedding cache dict."""
        return self.embedding_cache._cache

    @property
    def _reranker_cache(self) -> Dict[str, Any]:
        """Backward compatibility: Direct access to reranker cache dict."""
        return self.reranker_cache._cache

    @property
    def _vision_cache(self) -> Dict[str, Any]:
        """Backward compatibility: Direct access to vision cache dict."""
        return self.vision_cache._cache

    @property
    def _audio_cache(self) -> Dict[str, Any]:
        """Backward compatibility: Direct access to audio cache dict."""
        return self.audio_cache._cache

    @property
    def _initializing_adapters(self):
        """Backward compatibility: Direct access to initializing set."""
        return self.adapter_cache._initializing


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
            adapter = await self.adapter_manager.get_adapter(adapter_name)
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
        pass

    async def close(self) -> None:
        """Close method for compatibility."""
        await self.adapter_manager.close()
