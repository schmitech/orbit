"""
Retriever package for handling different types of document retrieval systems.
"""

from .base.base_retriever import BaseRetriever
from .base.vector_retriever import VectorDBRetriever
from .base.sql_retriever import SQLRetriever
from .adapters.domain_adapters import DocumentAdapterFactory

# Expose main interfaces
__all__ = [
    'BaseRetriever',
    'VectorDBRetriever',
    'SQLRetriever',
    'DocumentAdapterFactory'
]

# Import implementations to register them
from .implementations.chroma import ChromaRetriever
from .implementations.sqlite import SQLiteRetriever
from .adapters.qa import QARetriever