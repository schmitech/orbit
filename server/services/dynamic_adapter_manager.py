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
        adapter_configs = self.config.get('adapters', [])
        
        for adapter_config in adapter_configs:
            adapter_name = adapter_config.get('name')
            if adapter_name:
                self._adapter_configs[adapter_name] = adapter_config
                if self.verbose:
                    self.logger.info(f"Loaded adapter config: {adapter_name}")
        
        self.logger.info(f"Loaded {len(self._adapter_configs)} adapter configurations")
    
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
        
        # Check if adapter is currently being initialized
        with self._cache_lock:
            if adapter_name in self._initializing_adapters:
                # Wait for initialization to complete
                while adapter_name in self._initializing_adapters:
                    await asyncio.sleep(0.1)
                
                # Check cache again after waiting
                if adapter_name in self._adapter_cache:
                    return self._adapter_cache[adapter_name]
            
            # Mark adapter as being initialized
            self._initializing_adapters.add(adapter_name)
        
        try:
            # Load the adapter
            adapter = await self._load_adapter(adapter_name)
            
            # Cache the adapter
            with self._cache_lock:
                self._adapter_cache[adapter_name] = adapter
                # Create a lock for this adapter for future thread-safe operations
                self._adapter_locks[adapter_name] = threading.Lock()
            
            self.logger.info(f"Successfully loaded and cached adapter: {adapter_name}")
            return adapter
            
        except Exception as e:
            self.logger.error(f"Failed to load adapter {adapter_name}: {str(e)}")
            raise
        finally:
            # Remove from initializing set
            with self._cache_lock:
                self._initializing_adapters.discard(adapter_name)
    
    async def _load_adapter(self, adapter_name: str) -> Any:
        """
        Load and initialize an adapter.
        
        Args:
            adapter_name: Name of the adapter to load
            
        Returns:
            The initialized adapter instance
        """
        # Get adapter configuration
        adapter_config = self._adapter_configs.get(adapter_name)
        if not adapter_config:
            raise ValueError(f"No adapter configuration found for: {adapter_name}")
        
        # Extract adapter details
        implementation = adapter_config.get('implementation')
        datasource = adapter_config.get('datasource')
        adapter_type = adapter_config.get('adapter')
        
        if not implementation or not datasource or not adapter_type:
            raise ValueError(f"Missing required adapter fields for {adapter_name}")
        
        self.logger.info(f"Loading adapter {adapter_name}: {datasource} retriever with {adapter_type} adapter")
        
        try:
            # Import the specific retriever class
            module_path, class_name = implementation.rsplit('.', 1)
            module = __import__(module_path, fromlist=[class_name])
            retriever_class = getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            self.logger.error(f"Could not load retriever class from {implementation}: {str(e)}")
            raise ValueError(f"Failed to load retriever implementation: {str(e)}")
        
        # Create the domain adapter using the registry
        try:
            from retrievers.adapters.registry import ADAPTER_REGISTRY
            adapter_config_params = adapter_config.get('config', {})
            domain_adapter = ADAPTER_REGISTRY.create(
                adapter_type='retriever',
                datasource=datasource,
                adapter_name=adapter_type,
                **adapter_config_params
            )
            self.logger.info(f"Successfully created {adapter_type} domain adapter for {adapter_name}")
        except Exception as adapter_error:
            self.logger.error(f"Error creating domain adapter for {adapter_name}: {str(adapter_error)}")
            raise ValueError(f"Failed to create domain adapter: {str(adapter_error)}")
        
        # Prepare appropriate arguments based on the provider type
        retriever_kwargs = {
            'config': self.config,
            'domain_adapter': domain_adapter
        }
        
        # Add adapter-specific config to the retriever kwargs
        # This allows the retriever to access its specific configuration (like table name, collection name)
        adapter_specific_config = adapter_config.get('config', {})
        
        # Create a modified config that includes the adapter-specific settings
        # at the top level for easier access by the retriever
        modified_config = self.config.copy()
        
        # Add adapter-specific config including collection name
        full_adapter_config = adapter_specific_config.copy()
        
        # Add collection name from adapter config if present
        if 'collection' in adapter_config:
            full_adapter_config['collection'] = adapter_config['collection']
            
        if full_adapter_config:
            modified_config['adapter_config'] = full_adapter_config
            # Also add the adapter config in the expected location for backward compatibility
            modified_config['adapters'] = [adapter_config]
            
        retriever_kwargs['config'] = modified_config
        
        # Add appropriate client/connection based on the provider type
        if self.app_state:
            if datasource == 'chroma':
                if hasattr(self.app_state, 'embedding_service'):
                    retriever_kwargs['embeddings'] = self.app_state.embedding_service
                if hasattr(self.app_state, 'chroma_client'):
                    retriever_kwargs['collection'] = self.app_state.chroma_client
            elif datasource == 'sqlite':
                if hasattr(self.app_state, 'datasource_client'):
                    retriever_kwargs['connection'] = self.app_state.datasource_client
        
        # Create and initialize the retriever instance
        self.logger.info(f"Creating {datasource} retriever instance for {adapter_name}")
        retriever = retriever_class(**retriever_kwargs)
        
        # Initialize the retriever
        await retriever.initialize()
        
        self.logger.info(f"Successfully initialized adapter: {adapter_name}")
        return retriever
    
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
        return {
            "status": "healthy",
            "available_adapters": len(self._adapter_configs),
            "cached_adapters": len(self._adapter_cache),
            "initializing_adapters": len(self._initializing_adapters),
            "adapter_configs": list(self._adapter_configs.keys()),
            "cached_adapter_names": list(self._adapter_cache.keys())
        }
    
    async def close(self) -> None:
        """Clean up all resources."""
        # Clear all cached adapters
        await self.clear_cache()
        
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
                collection_name=None,  # Not used in adapter-based routing
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