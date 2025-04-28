"""
Client modules for external services
"""

from .base_retriever import BaseRetriever, RetrieverFactory
from .qa_chroma_retriever import QAChromaRetriever
from .qa_sqlite_retriever import QASqliteRetriever

# Register retrievers with the factory
RetrieverFactory.register_retriever("qa_chroma", QAChromaRetriever)
RetrieverFactory.register_retriever("qa_sqlite", QASqliteRetriever)

__all__ = ['BaseRetriever', 'QAChromaRetriever', 'QASqliteRetriever', 'RetrieverFactory']

