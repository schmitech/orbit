"""
Datasource Registry for managing datasource implementations with automatic discovery
"""

import logging
import importlib
import pkgutil
from typing import Dict, Any, Optional, Type, List
from .base.base_datasource import BaseDatasource

# Configure logging
logger = logging.getLogger(__name__)


class DatasourceRegistry:
    """
    Registry for managing datasource implementations with automatic discovery.
    
    This registry automatically discovers and registers datasource implementations
    from the implementations package, providing a unified interface for creating
    datasource instances.
    """
    
    def __init__(self):
        """Initialize the datasource registry."""
        self._registry: Dict[str, Type[BaseDatasource]] = {}
        self._discovered = False
        
    def _discover_implementations(self) -> None:
        """Auto-discover datasource implementations from the implementations package."""
        if self._discovered:
            return
            
        logger.info("Starting auto-discovery of datasource implementations...")
        
        try:
            # Import the implementations package
            from . import implementations
            
            # Walk through all modules in the implementations package
            for importer, modname, ispkg in pkgutil.walk_packages(
                implementations.__path__, 
                implementations.__name__ + "."
            ):
                try:
                    # Import the module
                    module = importlib.import_module(modname)
                    
                    # Look for classes that inherit from BaseDatasource
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and 
                            issubclass(attr, BaseDatasource) and 
                            attr != BaseDatasource):
                            
                            # Get the datasource name by creating a temporary instance
                            try:
                                # Create a minimal instance to access the property
                                temp_instance = attr({}, None)
                                datasource_name_value = temp_instance.datasource_name
                                
                                if datasource_name_value:
                                    self._registry[datasource_name_value] = attr
                                    logger.info(f"Discovered datasource implementation: {datasource_name_value} -> {attr.__name__}")
                                else:
                                    logger.warning(f"Class {attr.__name__} has empty datasource_name")
                            except Exception as e:
                                logger.warning(f"Class {attr.__name__} couldn't be instantiated to get datasource_name: {e}")
                                
                except Exception as e:
                    logger.warning(f"Failed to import module {modname}: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to discover datasource implementations: {e}")
            
        self._discovered = True
        logger.info(f"Datasource discovery completed. Found {len(self._registry)} implementations: {list(self._registry.keys())}")
    
    def register(self, datasource_name: str, implementation: Type[BaseDatasource]) -> None:
        """
        Manually register a datasource implementation.
        
        Args:
            datasource_name: Name of the datasource (e.g., 'mysql', 'mongodb')
            implementation: Class that implements BaseDatasource
        """
        if not issubclass(implementation, BaseDatasource):
            raise ValueError(f"Implementation must inherit from BaseDatasource")
            
        self._registry[datasource_name] = implementation
        logger.info(f"Manually registered datasource: {datasource_name} -> {implementation.__name__}")
    
    def get_implementation(self, datasource_name: str) -> Optional[Type[BaseDatasource]]:
        """
        Get a datasource implementation by name.
        
        Args:
            datasource_name: Name of the datasource
            
        Returns:
            The implementation class or None if not found
        """
        if not self._discovered:
            self._discover_implementations()
            
        return self._registry.get(datasource_name)
    
    def list_available(self) -> List[str]:
        """
        List all available datasource implementations.
        
        Returns:
            List of datasource names
        """
        if not self._discovered:
            self._discover_implementations()
            
        return list(self._registry.keys())
    
    def create_datasource(self, 
                         datasource_name: str, 
                         config: Dict[str, Any], 
                         logger: Optional[logging.Logger] = None) -> Optional[BaseDatasource]:
        """
        Create a datasource instance.
        
        Args:
            datasource_name: Name of the datasource to create
            config: Configuration dictionary
            logger: Logger instance
            
        Returns:
            Datasource instance or None if not found
        """
        implementation = self.get_implementation(datasource_name)
        if not implementation:
            logger.error(f"Datasource implementation not found: {datasource_name}")
            return None
            
        try:
            return implementation(config, logger)
        except Exception as e:
            logger.error(f"Failed to create datasource {datasource_name}: {e}")
            return None
    
    def is_available(self, datasource_name: str) -> bool:
        """
        Check if a datasource implementation is available.
        
        Args:
            datasource_name: Name of the datasource
            
        Returns:
            True if available, False otherwise
        """
        return self.get_implementation(datasource_name) is not None


# Global registry instance
_registry = DatasourceRegistry()


def get_registry() -> DatasourceRegistry:
    """Get the global datasource registry instance."""
    return _registry


def create_datasource(datasource_name: str, 
                     config: Dict[str, Any], 
                     logger: Optional[logging.Logger] = None) -> Optional[BaseDatasource]:
    """
    Create a datasource instance using the global registry.
    
    Args:
        datasource_name: Name of the datasource to create
        config: Configuration dictionary
        logger: Logger instance
        
    Returns:
        Datasource instance or None if not found
    """
    return _registry.create_datasource(datasource_name, config, logger)
