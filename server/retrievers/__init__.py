"""
Retriever package for handling different types of data retrieval implementations.
"""

import logging

# Configure logging
logger = logging.getLogger(__name__)
logger.info("Initializing retrievers package")

from .base.base_retriever import BaseRetriever, RetrieverFactory
from .base.vector_retriever import VectorDBRetriever
from .base.sql_retriever import SQLRetriever
from .adapters.domain_adapters import DocumentAdapterFactory

# Expose main interfaces
__all__ = [
    'BaseRetriever',
    'RetrieverFactory',
    'VectorDBRetriever',
    'SQLRetriever',
    'DocumentAdapterFactory'
]

# Import implementations to register them
# from .implementations import QAChromaRetriever
# from .implementations import QASqliteRetriever
# from .adapters.qa import QARetriever

# # Force import our specialized adapters to ensure registration
# try:
#     from .adapters.qa.chroma_qa_adapter import ChromaQAAdapter
#     logger.info("Successfully imported ChromaQAAdapter through retrievers/__init__.py")
# except ImportError as e:
#     logger.error(f"Error importing ChromaQAAdapter: {str(e)}")