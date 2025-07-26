"""
Service Container for Dependency Injection

This module provides a service container that manages dependencies and enables
loose coupling between components in the pipeline architecture.
"""

from typing import Dict, Any, Type, Optional, Callable
import logging

class ServiceContainer:
    """
    Dependency injection container for managing services.
    
    This container supports both singleton instances and factory functions,
    allowing for flexible service registration and retrieval.
    """
    
    def __init__(self):
        """Initialize the service container."""
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Callable] = {}
        self._singletons: Dict[str, Any] = {}
        self.logger = logging.getLogger(__name__)
    
    def register_singleton(self, name: str, instance: Any) -> None:
        """
        Register a singleton service instance.
        
        Args:
            name: The service name
            instance: The service instance
        """
        self._singletons[name] = instance
        self.logger.debug(f"Registered singleton service: {name}")
    
    def register_factory(self, name: str, factory: Callable) -> None:
        """
        Register a factory function for service creation.
        
        Args:
            name: The service name
            factory: A callable that creates service instances
        """
        self._factories[name] = factory
        self.logger.debug(f"Registered factory for service: {name}")
    
    def get(self, name: str) -> Any:
        """
        Get a service by name.
        
        Args:
            name: The service name
            
        Returns:
            The service instance
            
        Raises:
            KeyError: If the service is not found
        """
        # Check singletons first
        if name in self._singletons:
            return self._singletons[name]
        
        # Create from factory
        if name in self._factories:
            service = self._factories[name]()
            self.logger.debug(f"Created service from factory: {name}")
            return service
        
        raise KeyError(f"Service '{name}' not found in container")
    
    def has(self, name: str) -> bool:
        """
        Check if a service is registered.
        
        Args:
            name: The service name
            
        Returns:
            True if the service is registered, False otherwise
        """
        return name in self._singletons or name in self._factories
    
    def get_or_none(self, name: str) -> Optional[Any]:
        """
        Get a service by name or return None if not found.
        
        Args:
            name: The service name
            
        Returns:
            The service instance or None
        """
        try:
            return self.get(name)
        except KeyError:
            return None
    
    def clear(self) -> None:
        """Clear all registered services."""
        self._services.clear()
        self._factories.clear()
        self._singletons.clear()
        self.logger.debug("Cleared all services from container")
    
    def list_services(self) -> Dict[str, str]:
        """
        List all registered services and their types.
        
        Returns:
            Dictionary mapping service names to their types (singleton/factory)
        """
        services = {}
        for name in self._singletons:
            services[name] = "singleton"
        for name in self._factories:
            services[name] = "factory"
        return services 