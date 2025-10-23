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

    Features datasource pooling to share connections between adapters.
    """

    def __init__(self):
        """Initialize the datasource registry."""
        self._registry: Dict[str, Type[BaseDatasource]] = {}
        self._discovered = False

        # Datasource pooling: cache instances to share between adapters
        self._datasource_pool: Dict[str, BaseDatasource] = {}
        self._datasource_references: Dict[str, int] = {}  # Reference counting

        import threading
        self._pool_lock = threading.Lock()
        
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

    def _generate_cache_key(self, datasource_name: str, config: Dict[str, Any]) -> str:
        """
        Generate a cache key for datasource pooling based on connection parameters.

        Args:
            datasource_name: Name of the datasource
            config: Configuration dictionary

        Returns:
            Cache key string
        """
        datasource_config = config.get('datasources', {}).get(datasource_name, {})

        # Extract connection-identifying parameters based on datasource type
        if datasource_name in ['sqlite']:
            # SQLite: cache key is database file path
            database = datasource_config.get('database', 'sqlite_db.db')
            return f"{datasource_name}:{database}"

        elif datasource_name in ['postgres', 'postgresql', 'mysql', 'mssql']:
            # Relational DBs: cache key includes host, port, database
            host = datasource_config.get('host', 'localhost')
            port = datasource_config.get('port', 5432)
            database = datasource_config.get('database', 'default')
            username = datasource_config.get('username', '')
            return f"{datasource_name}:{host}:{port}:{database}:{username}"

        elif datasource_name in ['chroma', 'chromadb']:
            # ChromaDB: cache key includes host and port (or path for persistent)
            host = datasource_config.get('host', 'localhost')
            port = datasource_config.get('port', 8000)
            path = datasource_config.get('path', '')
            if path:
                return f"{datasource_name}:path:{path}"
            return f"{datasource_name}:{host}:{port}"

        elif datasource_name in ['qdrant']:
            # Qdrant: cache key includes host and port
            host = datasource_config.get('host', 'localhost')
            port = datasource_config.get('port', 6333)
            return f"{datasource_name}:{host}:{port}"

        elif datasource_name in ['pinecone']:
            # Pinecone: cache key includes environment and index
            environment = datasource_config.get('environment', 'default')
            index = datasource_config.get('index', 'default')
            return f"{datasource_name}:{environment}:{index}"

        elif datasource_name in ['mongodb', 'mongo']:
            # MongoDB: cache key includes host, port, database
            host = datasource_config.get('host', 'localhost')
            port = datasource_config.get('port', 27017)
            database = datasource_config.get('database', 'default')
            return f"{datasource_name}:{host}:{port}:{database}"

        elif datasource_name in ['elasticsearch']:
            # Elasticsearch: cache key includes node URL and username
            node = datasource_config.get('node', 'http://localhost:9200')
            auth_config = datasource_config.get('auth', {})
            username = auth_config.get('username', 'anonymous')
            return f"{datasource_name}:{node}:{username}"

        else:
            # Generic: use datasource name as cache key (no pooling)
            logger.warning(f"No specific cache key generation for {datasource_name}, using datasource name only")
            return datasource_name

    def get_or_create_datasource(self,
                                 datasource_name: str,
                                 config: Dict[str, Any],
                                 logger_instance: Optional[logging.Logger] = None) -> Optional[BaseDatasource]:
        """
        Get a cached datasource or create a new one with reference counting.

        Args:
            datasource_name: Name of the datasource to create
            config: Configuration dictionary
            logger_instance: Logger instance

        Returns:
            Datasource instance or None if not found
        """
        # Generate cache key based on connection parameters
        cache_key = self._generate_cache_key(datasource_name, config)

        with self._pool_lock:
            # Check if we have a cached datasource
            if cache_key in self._datasource_pool:
                datasource = self._datasource_pool[cache_key]
                # Increment reference count
                self._datasource_references[cache_key] = self._datasource_references.get(cache_key, 0) + 1

                if logger_instance:
                    logger_instance.info(
                        f"Reusing cached datasource '{datasource_name}' (key: {cache_key}, "
                        f"refs: {self._datasource_references[cache_key]})"
                    )

                return datasource

            # Create new datasource
            implementation = self.get_implementation(datasource_name)
            if not implementation:
                if logger_instance:
                    logger_instance.error(f"Datasource implementation not found: {datasource_name}")
                return None

            try:
                datasource = implementation(config, logger_instance)

                # Cache the new datasource
                self._datasource_pool[cache_key] = datasource
                self._datasource_references[cache_key] = 1

                if logger_instance:
                    logger_instance.info(
                        f"Created new datasource '{datasource_name}' (key: {cache_key}, refs: 1)"
                    )

                return datasource

            except Exception as e:
                if logger_instance:
                    logger_instance.error(f"Failed to create datasource {datasource_name}: {e}")
                return None

    def release_datasource(self,
                          datasource_name: str,
                          config: Dict[str, Any],
                          logger_instance: Optional[logging.Logger] = None) -> None:
        """
        Release a datasource reference. Closes the datasource when reference count reaches 0.

        Args:
            datasource_name: Name of the datasource
            config: Configuration dictionary (used to generate cache key)
            logger_instance: Logger instance
        """
        cache_key = self._generate_cache_key(datasource_name, config)

        with self._pool_lock:
            if cache_key not in self._datasource_pool:
                if logger_instance:
                    logger_instance.warning(f"Attempted to release non-existent datasource: {cache_key}")
                return

            # Decrement reference count
            self._datasource_references[cache_key] = self._datasource_references.get(cache_key, 1) - 1

            if self._datasource_references[cache_key] <= 0:
                # No more references, close and remove from pool
                datasource = self._datasource_pool.pop(cache_key)
                self._datasource_references.pop(cache_key, None)

                try:
                    # Close the datasource
                    import asyncio
                    if asyncio.iscoroutinefunction(datasource.close):
                        # Schedule async close
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.create_task(datasource.close())
                        else:
                            asyncio.run(datasource.close())
                    else:
                        datasource.close()

                    if logger_instance:
                        logger_instance.info(f"Closed datasource '{datasource_name}' (key: {cache_key}, refs: 0)")
                except Exception as e:
                    if logger_instance:
                        logger_instance.error(f"Error closing datasource {cache_key}: {e}")
            else:
                if logger_instance:
                    logger_instance.info(
                        f"Released datasource '{datasource_name}' (key: {cache_key}, "
                        f"refs: {self._datasource_references[cache_key]})"
                    )

    def get_pool_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the datasource pool.

        Returns:
            Dictionary with pool statistics
        """
        with self._pool_lock:
            return {
                "total_cached_datasources": len(self._datasource_pool),
                "datasource_keys": list(self._datasource_pool.keys()),
                "reference_counts": dict(self._datasource_references),
                "total_references": sum(self._datasource_references.values())
            }

    async def shutdown_pool(self, logger_instance: Optional[logging.Logger] = None) -> None:
        """
        Force close all datasources in the pool during shutdown.
        This is a cleanup method for graceful server shutdown.

        Args:
            logger_instance: Logger instance for logging
        """
        with self._pool_lock:
            datasources_to_close = list(self._datasource_pool.items())
            self._datasource_pool.clear()
            self._datasource_references.clear()

        if logger_instance:
            logger_instance.info(f"Shutting down datasource pool: closing {len(datasources_to_close)} datasources")

        for cache_key, datasource in datasources_to_close:
            try:
                import asyncio
                if asyncio.iscoroutinefunction(datasource.close):
                    await datasource.close()
                else:
                    datasource.close()

                if logger_instance:
                    logger_instance.info(f"Closed datasource: {cache_key}")
            except Exception as e:
                if logger_instance:
                    logger_instance.error(f"Error closing datasource {cache_key} during shutdown: {e}")


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
