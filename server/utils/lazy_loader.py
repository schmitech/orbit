"""
Lazy Loader Utility
==================

A utility class for lazy loading of resources.
"""

from typing import Any, Callable, Dict
import logging

logger = logging.getLogger(__name__)

class LazyLoader:
    """
    A utility class that provides lazy loading functionality.
    Resources are only initialized when first accessed.
    """
    
    def __init__(self, factory_func: Callable[[], Any], name: str = None):
        """
        Initialize a lazy loader with a factory function.
        
        Args:
            factory_func: Function that will be called to create the resource when needed
            name: Optional name for logging purposes
        """
        self._factory_func = factory_func
        self._instance = None
        self._initialized = False
        self._name = name or "resource"
    
    def get_instance(self) -> Any:
        """
        Get the resource instance, initializing it if needed.
        
        Returns:
            The initialized resource
        """
        if not self._initialized:
            logger.info(f"Lazy loading {self._name}...")
            try:
                self._instance = self._factory_func()
                self._initialized = True
                logger.info(f"{self._name} loaded successfully")
            except Exception as e:
                logger.error(f"Error lazy loading {self._name}: {str(e)}")
                raise
        return self._instance

class AdapterRegistry:
    """
    A registry for lazy-loaded adapters.
    Provides a central place to register and retrieve adapters.
    """
    
    def __init__(self):
        """Initialize an empty adapter registry."""
        self._adapters: Dict[str, LazyLoader] = {}
        
    def register(self, adapter_type: str, factory_func: Callable[[], Any]) -> None:
        """
        Register a new adapter factory function.
        
        Args:
            adapter_type: The type identifier for this adapter
            factory_func: Function that will be called to create the adapter when needed
        """
        self._adapters[adapter_type] = LazyLoader(factory_func, f"{adapter_type} adapter")
        
    def get(self, adapter_type: str) -> Any:
        """
        Get an adapter instance, initializing it if needed.
        
        Args:
            adapter_type: The type identifier for the adapter
            
        Returns:
            The initialized adapter instance
            
        Raises:
            KeyError: If the requested adapter type is not registered
        """
        if adapter_type not in self._adapters:
            raise KeyError(f"Adapter type '{adapter_type}' not registered")
        
        return self._adapters[adapter_type].get_instance()
    
    def is_registered(self, adapter_type: str) -> bool:
        """
        Check if an adapter type is registered.
        
        Args:
            adapter_type: The adapter type to check
            
        Returns:
            True if the adapter is registered, False otherwise
        """
        return adapter_type in self._adapters 