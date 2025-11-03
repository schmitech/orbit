"""
Store manager for managing vector store instances and their lifecycle.
"""

import logging
import os
import warnings
from typing import Dict, Any, Optional, List, Type
import asyncio
from datetime import datetime, UTC
import yaml
from pathlib import Path

from .base_store import BaseStore, StoreConfig, StoreStatus

logger = logging.getLogger(__name__)


class StoreManager:
    """
    Manages vector store instances, handles their lifecycle,
    and provides a unified interface for store operations.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the store manager.

        Args:
            config_path: Path to the stores configuration file
        """
        self._stores: Dict[str, BaseStore] = {}
        self._store_classes: Dict[str, Type[BaseStore]] = {}
        self._lock = asyncio.Lock()
        self._config = {}

        # Get verbose setting from global config
        try:
            from config.config_manager import load_config
            global_config = load_config()
            self.verbose = global_config.get('general', {}).get('verbose', False)
        except Exception:
            self.verbose = False

        if config_path is None:
            config_path = "config/stores.yaml"

        # Load configuration if provided
        if config_path:
            self._load_config(config_path)

        # Register available store classes
        self._register_store_classes()

        if self.verbose:
            logger.info("StoreManager initialized")
    
    def _load_config(self, config_path: str):
        """Load configuration from YAML file."""
        try:
            path = Path(config_path)
            if path.exists():
                with open(path, 'r') as f:
                    self._config = yaml.safe_load(f)
                if self.verbose:
                    logger.info(f"Loaded configuration from {config_path}")
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
    
    def _register_store_classes(self):
        """Register available vector store implementations."""
        vector_stores_config = self._config.get('vector_stores', {})

        if vector_stores_config.get('chroma', {}).get('enabled', False):
            try:
                from ..implementations.chroma_store import ChromaStore
                self._store_classes['chroma'] = ChromaStore
                if self.verbose:
                    logger.info("Registered ChromaStore")
            except ImportError:
                logger.warning("ChromaStore not available")

        if vector_stores_config.get('pinecone', {}).get('enabled', False):
            try:
                from ..implementations.pinecone_store import PineconeStore
                self._store_classes['pinecone'] = PineconeStore
                logger.info("Registered PineconeStore")
            except ImportError:
                logger.warning("PineconeStore not available")

        if vector_stores_config.get('qdrant', {}).get('enabled', False):
            try:
                from ..implementations.qdrant_store import QdrantStore
                self._store_classes['qdrant'] = QdrantStore
                logger.info("Registered QdrantStore")
            except ImportError:
                logger.warning("QdrantStore not available")

        if vector_stores_config.get('faiss', {}).get('enabled', False):
            try:
                from ..implementations.faiss_store import FaissStore
                self._store_classes['faiss'] = FaissStore
                logger.info("Registered FaissStore")
            except ImportError:
                logger.warning("FaissStore not available")

        if vector_stores_config.get('weaviate', {}).get('enabled', False):
            try:
                from ..implementations.weaviate_store import WeaviateStore
                self._store_classes['weaviate'] = WeaviateStore
                logger.info("Registered WeaviateStore")
            except ImportError:
                logger.warning("WeaviateStore not available")

        if vector_stores_config.get('milvus', {}).get('enabled', False):
            try:
                from ..implementations.milvus_store import MilvusStore
                self._store_classes['milvus'] = MilvusStore
                logger.info("Registered MilvusStore")
            except ImportError:
                logger.warning("MilvusStore not available")

        if vector_stores_config.get('marqo', {}).get('enabled', False):
            try:
                # Suppress Pydantic deprecation warnings from Marqo
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=DeprecationWarning, module="marqo.*")
                    from ..implementations.marqo_store import MarqoStore
                self._store_classes['marqo'] = MarqoStore
                logger.info("Registered MarqoStore")
            except ImportError:
                logger.warning("MarqoStore not available")

        if vector_stores_config.get('pgvector', {}).get('enabled', False):
            try:
                from ..implementations.pgvector_store import PgvectorStore
                self._store_classes['pgvector'] = PgvectorStore
                logger.info("Registered PgvectorStore")
            except ImportError:
                logger.warning("PgvectorStore not available")

        if vector_stores_config.get('duckdb', {}).get('enabled', False):
            try:
                from ..implementations.duckdb_store import DuckDBStore
                self._store_classes['duckdb'] = DuckDBStore
                logger.info("Registered DuckDBStore")
            except ImportError:
                logger.warning("DuckDBStore not available")

    @staticmethod
    def _resolve_env_variable(value: Any) -> Any:
        """
        Resolve environment variable placeholders like ${VAR_NAME}.

        Args:
            value: Value that may contain env var placeholder

        Returns:
            Resolved value
        """
        if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
            env_var = value[2:-1]  # Remove ${ and }
            resolved = os.getenv(env_var)
            if resolved is None:
                logger.warning(f"Environment variable {env_var} not found, using placeholder value")
                return value
            return resolved
        elif isinstance(value, dict):
            # Recursively resolve dict values
            return {k: StoreManager._resolve_env_variable(v) for k, v in value.items()}
        elif isinstance(value, list):
            # Recursively resolve list values
            return [StoreManager._resolve_env_variable(item) for item in value]
        return value
    
    async def create_store(self, 
                          name: str,
                          store_type: str = 'chroma',
                          config: Optional[Dict[str, Any]] = None) -> BaseStore:
        """
        Create and initialize a new store instance.
        
        Args:
            name: Unique name for the store instance
            store_type: Type of store to create (e.g., 'chroma')
            config: Optional configuration override
            
        Returns:
            Initialized store instance
        """
        async with self._lock:
            # Check if store already exists
            if name in self._stores:
                logger.warning(f"Store {name} already exists")
                return self._stores[name]
            
            # Get store class
            if store_type not in self._store_classes:
                raise ValueError(f"Unknown store type: {store_type}")
            
            store_class = self._store_classes[store_type]
            
            # Create store configuration
            store_config = self._create_store_config(name, store_type, config)
            
            # Create store instance
            store = store_class(store_config)
            
            # Initialize connection
            if await store.connect():
                self._stores[name] = store
                if self.verbose:
                    logger.info(f"Store {name} created and connected successfully")
                return store
            else:
                raise ConnectionError(f"Failed to connect to store {name}")
    
    def _create_store_config(self,
                           name: str,
                           store_type: str,
                           override_config: Optional[Dict[str, Any]] = None) -> StoreConfig:
        """
        Create store configuration from loaded config and overrides.

        Args:
            name: Store name
            store_type: Type of store
            override_config: Optional configuration override

        Returns:
            StoreConfig instance
        """
        # Get configuration for store type from vector_stores
        default_config = {}
        if self._config and 'vector_stores' in self._config:
            store_configs = self._config['vector_stores']
            if store_type in store_configs:
                # Store config is now directly under the store type (no default_config wrapper)
                store_config = store_configs[store_type]
                # Extract everything except 'enabled'
                default_config = {k: v for k, v in store_config.items() if k != 'enabled'}

        # Merge with override config
        final_config = {**default_config}
        if override_config:
            final_config['connection_params'] = {
                **default_config.get('connection_params', {}),
                **override_config.get('connection_params', {})
            }
            for key in ['pool_size', 'timeout', 'ephemeral', 'auto_cleanup']:
                if key in override_config:
                    final_config[key] = override_config[key]

        # Resolve environment variables in connection params
        if 'connection_params' in final_config:
            final_config['connection_params'] = self._resolve_env_variable(
                final_config['connection_params']
            )

        # Add verbose setting to connection_params
        connection_params = final_config.get('connection_params', {})
        connection_params['verbose'] = self.verbose

        return StoreConfig(
            name=name,
            connection_params=connection_params,
            pool_size=final_config.get('pool_size', 5),
            timeout=final_config.get('timeout', 30),
            ephemeral=final_config.get('ephemeral', False),
            auto_cleanup=final_config.get('auto_cleanup', True)
        )
    
    async def get_store(self, name: str) -> Optional[BaseStore]:
        """
        Get a store instance by name.
        
        Args:
            name: Store name
            
        Returns:
            Store instance or None if not found
        """
        return self._stores.get(name)
    
    async def get_or_create_store(self, 
                                 name: str,
                                 store_type: str = 'chroma',
                                 config: Optional[Dict[str, Any]] = None) -> BaseStore:
        """
        Get existing store or create new one if it doesn't exist.
        
        Args:
            name: Store name
            store_type: Type of store to create if needed
            config: Optional configuration for new store
            
        Returns:
            Store instance
        """
        store = await self.get_store(name)
        if store is None:
            store = await self.create_store(name, store_type, config)
        return store
    
    async def remove_store(self, name: str) -> bool:
        """
        Remove and disconnect a store.
        
        Args:
            name: Store name
            
        Returns:
            True if removed, False if not found
        """
        async with self._lock:
            if name in self._stores:
                store = self._stores[name]
                await store.disconnect()
                del self._stores[name]
                logger.info(f"Store {name} removed")
                return True
            return False
    
    async def list_stores(self) -> List[Dict[str, Any]]:
        """
        List all managed stores with their status.
        
        Returns:
            List of store information dictionaries
        """
        stores_info = []
        for name, store in self._stores.items():
            stats = await store.get_stats()
            stores_info.append({
                'name': name,
                'type': store.__class__.__name__,
                'status': stats.get('status'),
                'ephemeral': stats.get('ephemeral'),
                'operation_count': stats.get('operation_count'),
                'created_at': stats.get('created_at'),
                'last_accessed': stats.get('last_accessed')
            })
        return stores_info
    
    async def health_check_all(self) -> Dict[str, bool]:
        """
        Perform health check on all stores.
        
        Returns:
            Dictionary of store name to health status
        """
        results = {}
        for name, store in self._stores.items():
            try:
                results[name] = await store.health_check()
            except Exception as e:
                logger.error(f"Health check failed for {name}: {e}")
                results[name] = False
        return results
    
    async def cleanup_ephemeral_stores(self, max_age_seconds: int = 3600):
        """
        Clean up ephemeral stores that haven't been accessed recently.
        
        Args:
            max_age_seconds: Maximum age in seconds before cleanup
        """
        current_time = datetime.now(UTC)
        stores_to_remove = []
        
        for name, store in self._stores.items():
            if store.config.ephemeral:
                age = (current_time - store._last_accessed).total_seconds()
                if age > max_age_seconds:
                    stores_to_remove.append(name)
        
        for name in stores_to_remove:
            logger.info(f"Cleaning up ephemeral store {name}")
            await self.remove_store(name)
    
    async def shutdown(self):
        """Shutdown all stores and cleanup resources."""
        logger.info("Shutting down StoreManager")
        
        # Disconnect all stores
        for name in list(self._stores.keys()):
            await self.remove_store(name)
        
        logger.info("StoreManager shutdown complete")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about managed stores.
        
        Returns:
            Dictionary of statistics
        """
        stats = {
            'total_stores': len(self._stores),
            'stores_by_type': {},
            'available_store_types': list(self._store_classes.keys())
        }
        
        for store in self._stores.values():
            store_type = store.__class__.__name__
            stats['stores_by_type'][store_type] = stats['stores_by_type'].get(store_type, 0) + 1
        
        return stats
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.shutdown()


# Global store manager instance
_global_store_manager: Optional[StoreManager] = None


def get_store_manager(config_path: Optional[str] = None) -> StoreManager:
    """
    Get or create the global store manager instance.
    
    Args:
        config_path: Optional path to configuration file
        
    Returns:
        StoreManager instance
    """
    global _global_store_manager
    if _global_store_manager is None:
        _global_store_manager = StoreManager(config_path)
    return _global_store_manager