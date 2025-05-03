"""
QA-specific retrievers and adapters for different datasources.
"""

from ...implementations.chroma.chroma_retriever import ChromaRetriever
from ...implementations.sqlite.sqlite_retriever import SqliteRetriever
from .chroma_qa_adapter import ChromaQAAdapter
from .qa_sqlite_adapter import QASqliteAdapter

# Export a factory function as QARetriever
def QARetriever(datasource_type, *args, **kwargs):
    """
    Factory function to create the appropriate QA retriever based on datasource type.
    
    Args:
        datasource_type: Type of datasource ('chroma', 'sqlite', etc.)
        *args, **kwargs: Arguments to pass to the retriever constructor
        
    Returns:
        An instance of the appropriate QA retriever with domain adapter
    """
    # Extract confidence threshold from config if available
    config = kwargs.get('config', {})
    confidence_threshold = config.get('confidence_threshold', 0.5)
    
    if datasource_type.lower() == 'chroma':
        retriever = ChromaRetriever(*args, **kwargs)
        retriever.domain_adapter = ChromaQAAdapter(confidence_threshold=confidence_threshold)
        return retriever
    elif datasource_type.lower() == 'sqlite':
        retriever = SqliteRetriever(*args, **kwargs)
        retriever.domain_adapter = QASqliteAdapter(confidence_threshold=confidence_threshold)
        return retriever
    else:
        raise ValueError(f"Unsupported datasource type for QA retrieval: {datasource_type}")

__all__ = ['QARetriever', 'ChromaRetriever', 'SqliteRetriever', 'ChromaQAAdapter', 'QASqliteAdapter']

"""
QA adapter package initialization.
This ensures adapters are properly loaded and registered.
"""

import logging
from retrievers.adapters.domain_adapters import DocumentAdapterFactory

logger = logging.getLogger(__name__)

# Explicitly import all adapter modules to ensure they register with the factory
try:
    from .chroma_qa_adapter import ChromaQAAdapter
    # Note: Registration is now handled in the ChromaQAAdapter module itself
    logger.info("Successfully imported ChromaQAAdapter")
except ImportError as e:
    logger.error(f"Failed to import ChromaQAAdapter: {str(e)}")

try:
    from .qa_sqlite_adapter import QASqliteAdapter
    # Note: Registration is now handled in the QASqliteAdapter module itself
    logger.info("Successfully imported QASqliteAdapter")
except ImportError as e:
    logger.error(f"Failed to import QASqliteAdapter: {str(e)}")
