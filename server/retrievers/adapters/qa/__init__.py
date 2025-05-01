"""
QA-specific retrievers for different datasources.
"""

from .qa_chroma_retriever import QAChromaRetriever
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
        return QAChromaRetriever(*args, **kwargs)
    elif datasource_type.lower() == 'sqlite':
        return QASqliteRetriever(*args, **kwargs)
    else:
        raise ValueError(f"Unsupported datasource type for QA retrieval: {datasource_type}")

__all__ = ['QARetriever', 'QAChromaRetriever', 'QASqliteRetriever']
