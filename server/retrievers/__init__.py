"""
Client modules for external services
"""

# Import enhanced base classes
from .base_retriever import BaseRetriever, VectorDBRetriever, SQLRetriever
from .base_retriever import RetrieverFactory

# Import enhanced retrievers
from .chroma_retriever import ChromaRetriever
from .sqlite_retriever import SqliteRetriever

# Register retrievers with the factory
RetrieverFactory.register_retriever("chroma", ChromaRetriever)
RetrieverFactory.register_retriever("sqlite", SqliteRetriever)

# Export public API
__all__ = [
    # Base classes
    'BaseRetriever', 
    'VectorDBRetriever', 
    'SQLRetriever',
    'RetrieverFactory',
    
    # Enhanced retrievers
    'ChromaRetriever',
    'SqliteRetriever',
]