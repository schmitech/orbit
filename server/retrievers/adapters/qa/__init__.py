"""
QA-specific retrievers for different datasources.
"""

from ...implementations.chroma.chroma_retriever import ChromaRetriever
from .qa_sqlite_retriever import QASqliteRetriever

# Export a factory function as QARetriever
def QARetriever(datasource_type, *args, **kwargs):
    """
    Factory function to create the appropriate QA retriever based on datasource type.
    
    Args:
        datasource_type: Type of datasource ('chroma', 'sqlite', etc.)
        *args, **kwargs: Arguments to pass to the retriever constructor
        
    Returns:
        An instance of the appropriate QA retriever
    """
    if datasource_type.lower() == 'chroma':
        return ChromaRetriever(*args, **kwargs)
    elif datasource_type.lower() == 'sqlite':
        return QASqliteRetriever(*args, **kwargs)
    else:
        raise ValueError(f"Unsupported datasource type for QA retrieval: {datasource_type}")

__all__ = ['QARetriever', 'ChromaRetriever', 'QASqliteRetriever']

"""
QA adapter package initialization.
This ensures adapters are properly loaded and registered.
"""

import logging
logger = logging.getLogger(__name__)

# Explicitly import all adapter modules to ensure they register with the factory
try:
    from .chroma_qa_adapter import ChromaQAAdapter
    logger.warning("Successfully imported and registered ChromaQAAdapter")
except ImportError as e:
    logger.error(f"Failed to import ChromaQAAdapter: {str(e)}")
