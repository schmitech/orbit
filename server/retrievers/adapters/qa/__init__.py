"""
QA-specific retrievers and adapters for different datasources.
"""

from ...implementations.qa_chroma_retriever import QAChromaRetriever
from ...implementations.qa_sql_retriever import QASSQLRetriever
from .chroma_qa_adapter import ChromaQAAdapter
from .qa_sql_adapter import QASQLAdapter

# Export a factory function as QARetriever
def QARetriever(datasource_type, *args, **kwargs):
    """
    Factory function to create the appropriate QA retriever based on datasource type.
    
    Args:
        datasource_type: Type of datasource ('chroma', 'sql', etc.)
        *args, **kwargs: Arguments to pass to the retriever constructor
        
    Returns:
        An instance of the appropriate QA retriever with domain adapter
    """
    # Extract confidence threshold from config if available
    config = kwargs.get('config', {})
    confidence_threshold = config.get('confidence_threshold', 0.5)
    
    if datasource_type.lower() == 'chroma':
        retriever = QAChromaRetriever(*args, **kwargs)
        retriever.domain_adapter = ChromaQAAdapter(confidence_threshold=confidence_threshold)
        return retriever
    elif datasource_type.lower() == 'sql':
        retriever = QASSQLRetriever(*args, **kwargs)
        retriever.domain_adapter = QASQLAdapter(confidence_threshold=confidence_threshold)
        return retriever
    else:
        raise ValueError(f"Unsupported datasource type for QA retrieval: {datasource_type}")

__all__ = ['QARetriever', 'QAChromaRetriever', 'QASSQLRetriever', 'ChromaQAAdapter', 'QASQLAdapter']

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
    from .qa_sql_adapter import QASQLAdapter
    # Note: Registration is now handled in the QASQLAdapter module itself
    logger.info("Successfully imported QASQLAdapter")
except ImportError as e:
    logger.error(f"Failed to import QASQLAdapter: {str(e)}")
