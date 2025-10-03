"""QA-specialized retriever implementations."""

import logging

from .qa_chroma_retriever import QAChromaRetriever
from .qa_sql_retriever import QASSQLRetriever

logger = logging.getLogger(__name__)

try:  # Optional dependency on qdrant_client
    from .qa_qdrant_retriever import QAQdrantRetriever
except ModuleNotFoundError:  # pragma: no cover - optional import guard
    QAQdrantRetriever = None
    logger.debug("qdrant_client not installed; QAQdrantRetriever unavailable")

try:  # Optional dependency on pinecone
    from .qa_pinecone_retriever import QAPineconeRetriever
except ModuleNotFoundError:  # pragma: no cover - optional import guard
    QAPineconeRetriever = None
    logger.debug("pinecone not installed; QAPineconeRetriever unavailable")

__all__ = [
    'QAChromaRetriever',
    'QASSQLRetriever',
]

if QAQdrantRetriever is not None:
    __all__.append('QAQdrantRetriever')

if QAPineconeRetriever is not None:
    __all__.append('QAPineconeRetriever')
