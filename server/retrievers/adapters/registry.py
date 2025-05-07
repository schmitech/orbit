"""
 Adapter Registry for managing adapters with multi-level hierarchy
"""

import logging
import importlib
from typing import Dict, Any, Callable, List, Optional, Type, Union

# Configure logging
logger = logging.getLogger(__name__)

class AdapterRegistry:
    """
     registry for managing adapter types, datasources, and implementations.
    Supports hierarchical structure with type -> datasource -> adapter name mapping.
    """
    
    def __init__(self):
        """Initialize the adapter registry."""
        # Dictionary mapping adapter types to datasources to implementations
        # Structure: {adapter_type: {datasource: {adapter_name: {implementation, factory_func, config}}}}
        self._registry = {}
        
    def register(self, 
                adapter_type: str, 
                datasource: str, 
                adapter_name: str, 
                implementation: str = None,
                factory_func: Callable = None,
                config: Dict[str, Any] = None):
        """
        Register an adapter implementation.
        
        Args:
            adapter_type: Type of adapter (e.g., 'retriever', 'parser')
            datasource: Datasource name (e.g., 'sqlite', 'chroma')
            adapter_name: Adapter name (e.g., 'qa', 'generic')
            implementation: Fully qualified implementation path (e.g., 'module.submodule.ClassName')
            factory_func: Optional factory function to create the adapter
            config: Optional configuration for the adapter
        """
        # Ensure the type exists in the registry
        if adapter_type not in self._registry:
            self._registry[adapter_type] = {}
            
        # Ensure the datasource exists for the type
        if datasource not in self._registry[adapter_type]:
            self._registry[adapter_type][datasource] = {}
            
        # Register the adapter
        self._registry[adapter_type][datasource][adapter_name] = {
            'implementation': implementation,
            'factory_func': factory_func,
            'config': config or {}
        }
        
        logger.info(f"Registered adapter: type={adapter_type}, datasource={datasource}, name={adapter_name}")
        
    def get(self, adapter_type: str, datasource: str, adapter_name: str) -> Optional[Dict[str, Any]]:
        """
        Get an adapter's registration info.
        
        Args:
            adapter_type: Type of adapter (e.g., 'retriever', 'parser')
            datasource: Datasource name (e.g., 'sqlite', 'chroma')
            adapter_name: Adapter name (e.g., 'qa', 'generic')
            
        Returns:
            Dictionary with implementation, factory_func, and config, or None if not found
        """
        try:
            return self._registry[adapter_type][datasource][adapter_name]
        except KeyError:
            return None
            
    def create(self, 
              adapter_type: str, 
              datasource: str, 
              adapter_name: str, 
              override_config: Dict[str, Any] = None, 
              **kwargs) -> Any:
        """
        Create an adapter instance.
        
        Args:
            adapter_type: Type of adapter (e.g., 'retriever', 'parser')
            datasource: Datasource name (e.g., 'sqlite', 'chroma')
            adapter_name: Adapter name (e.g., 'qa', 'generic')
            override_config: Optional configuration to override registered config
            **kwargs: Additional keyword arguments to pass to the factory
            
        Returns:
            An adapter instance
            
        Raises:
            ValueError: If the adapter cannot be found or created
        """
        # Log the attempt to create the adapter
        logger.info(f"Attempting to create adapter: type={adapter_type}, datasource={datasource}, name={adapter_name}")
        
        # Get adapter info
        adapter_info = self.get(adapter_type, datasource, adapter_name)
        
        if not adapter_info:
            # Try to import dynamically if the adapter is not registered
            logger.info(f"Adapter not found in registry, attempting dynamic import")
            if self._try_import_adapter(adapter_type, datasource, adapter_name):
                adapter_info = self.get(adapter_type, datasource, adapter_name)
            
            if not adapter_info:
                # Log detailed registry state for debugging
                logger.error(f"Adapter not found: type={adapter_type}, datasource={datasource}, name={adapter_name}")
                logger.error(f"Available types: {list(self._registry.keys())}")
                if adapter_type in self._registry:
                    logger.error(f"Available datasources for {adapter_type}: {list(self._registry[adapter_type].keys())}")
                    if datasource in self._registry[adapter_type]:
                        logger.error(f"Available adapters for {datasource}: {list(self._registry[adapter_type][datasource].keys())}")
                raise ValueError(f"Adapter not found: type={adapter_type}, datasource={datasource}, name={adapter_name}")
        
        try:
            # Merge configs, with override_config taking precedence
            config = {**adapter_info.get('config', {}), **(override_config or {})}
            
            # Log the attempt to create the adapter instance
            logger.info(f"Creating adapter instance with config: {config}")
            
            # Use factory function if available
            if adapter_info.get('factory_func'):
                factory = adapter_info['factory_func']
                return factory(config=config, **kwargs)
            
            # Otherwise, use implementation path to create instance
            implementation_path = adapter_info.get('implementation')
            if not implementation_path:
                raise ValueError(f"No implementation or factory function available for adapter: {adapter_type}.{datasource}.{adapter_name}")
                
            # Import module and get class
            module_path, class_name = implementation_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            adapter_class = getattr(module, class_name)
            
            # Create instance
            return adapter_class(config=config, **kwargs)
                
        except Exception as e:
            logger.error(f"Error creating adapter: {str(e)}")
            raise ValueError(f"Failed to create adapter: {str(e)}")
            
    def _try_import_adapter(self, adapter_type: str, datasource: str, adapter_name: str) -> bool:
        """
        Try to dynamically import an adapter module.
        
        Args:
            adapter_type: Type of adapter (e.g., 'retriever', 'parser')
            datasource: Datasource name (e.g., 'sqlite', 'chroma')
            adapter_name: Adapter name (e.g., 'qa', 'generic')
            
        Returns:
            True if the import was successful, False otherwise
        """
        try:
            # Try standard module path patterns
            potential_paths = [
                f"retrievers.adapters.{adapter_type}.{datasource}_{adapter_name}_adapter",
                f"retrievers.adapters.{adapter_name}.{datasource}_{adapter_name}_adapter",
                f"retrievers.adapters.{datasource}.{datasource}_{adapter_name}_adapter",
                f"retrievers.implementations.{datasource}.{datasource}_{adapter_name}_adapter"
            ]
            
            for path in potential_paths:
                try:
                    importlib.import_module(path)
                    # Check if registration occurred through import
                    if (adapter_type in self._registry and 
                        datasource in self._registry[adapter_type] and
                        adapter_name in self._registry[adapter_type][datasource]):
                        return True
                except ImportError:
                    pass
                    
            return False
        except Exception as e:
            logger.error(f"Error trying to import adapter: {str(e)}")
            return False
            
    def get_types(self) -> List[str]:
        """Get all registered adapter types."""
        return list(self._registry.keys())
        
    def get_datasources(self, adapter_type: str) -> List[str]:
        """Get all registered datasources for a given type."""
        if adapter_type in self._registry:
            return list(self._registry[adapter_type].keys())
        return []
        
    def get_adapters(self, adapter_type: str, datasource: str) -> List[str]:
        """Get all registered adapters for a given type and datasource."""
        if adapter_type in self._registry and datasource in self._registry[adapter_type]:
            return list(self._registry[adapter_type][datasource].keys())
        return []
        
    def load_from_config(self, config: Dict[str, Any]) -> None:
        """
        Load and register adapters from configuration.
        
        Args:
            config: Configuration dictionary containing adapter definitions
            
        Raises:
            ValueError: If the configuration is invalid
        """
        # Check if adapters section exists
        if 'adapters' not in config:
            logger.info("No adapters section found in configuration")
            return
            
        # Validate adapters section is a list
        if not isinstance(config['adapters'], list):
            logger.error("Invalid adapters configuration: 'adapters' must be a list")
            raise ValueError("Invalid adapters configuration: 'adapters' must be a list")
            
        # Iterate through adapter definitions
        for adapter_def in config['adapters']:
            try:
                # Validate required fields
                required_fields = ['type', 'datasource', 'adapter', 'implementation']
                missing_fields = [field for field in required_fields if field not in adapter_def]
                
                if missing_fields:
                    logger.error(f"Missing required fields in adapter definition: {missing_fields}")
                    logger.error(f"Adapter definition: {adapter_def}")
                    continue
                    
                adapter_type = adapter_def['type']
                datasource = adapter_def['datasource']
                adapter_name = adapter_def['adapter']
                implementation = adapter_def['implementation']
                adapter_config = adapter_def.get('config', {})
                
                # Register the adapter
                self.register(
                    adapter_type=adapter_type,
                    datasource=datasource,
                    adapter_name=adapter_name,
                    implementation=implementation,
                    config=adapter_config
                )
                logger.info(f"Registered adapter from config: {implementation}")
                    
            except Exception as e:
                logger.error(f"Error registering adapter from definition {adapter_def}: {e}")
                continue

# Create a singleton instance of the registry
ADAPTER_REGISTRY = AdapterRegistry()