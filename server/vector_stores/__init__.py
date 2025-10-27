"""
Vector database stores for ORBIT system.

This package provides a clean, modular architecture for vector storage:

Structure:
- base/: Core abstractions and management
  - base_store.py: Abstract base for all stores
  - base_vector_store.py: Base class for vector stores
  - store_manager.py: Lifecycle management for stores
  
- implementations/: Concrete vector store implementations
  - chroma_store.py: ChromaDB implementation
  
- services/: High-level services using vector stores
  - template_embedding_store.py: SQL template embedding management
  
- store_factory.py: Factory functions for creating stores
"""

# Base classes - always available (no external dependencies)
from .base.base_store import BaseStore, StoreConfig, StoreStatus, StoreType

# Optional imports with lazy loading for dependencies
def _lazy_import():
    """Lazy import of components that require additional dependencies."""
    try:
        from .base.store_manager import StoreManager, get_store_manager
        from .implementations.chroma_store import ChromaStore
        from .implementations.faiss_store import FaissStore
        from .implementations.weaviate_store import WeaviateStore
        from .implementations.milvus_store import MilvusStore
        from .implementations.marqo_store import MarqoStore
        from .implementations.pgvector_store import PgvectorStore
        from .services.template_embedding_store import TemplateEmbeddingStore
        from .store_factory import create_store_manager, get_configured_store_manager
        return {
            'StoreManager': StoreManager,
            'get_store_manager': get_store_manager,
            'ChromaStore': ChromaStore,
            'FaissStore': FaissStore,
            'WeaviateStore': WeaviateStore,
            'MilvusStore': MilvusStore,
            'MarqoStore': MarqoStore,
            'PgvectorStore': PgvectorStore,
            'TemplateEmbeddingStore': TemplateEmbeddingStore,
            'create_store_manager': create_store_manager,
            'get_configured_store_manager': get_configured_store_manager
        }
    except ImportError:
        return {}

# Try to import optional components
_OPTIONAL_COMPONENTS = _lazy_import()

# Make optional components available at module level
for name, component in _OPTIONAL_COMPONENTS.items():
    globals()[name] = component

__all__ = [
    # Base classes - always available
    'BaseStore',
    'BaseVectorStore', 
    'StoreConfig',
    'StoreStatus',
    'StoreType',
] + list(_OPTIONAL_COMPONENTS.keys())