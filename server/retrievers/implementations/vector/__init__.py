"""
Vector database retriever implementations
"""

from .chroma_retriever import ChromaRetriever
from .milvus_retriever import MilvusRetriever
from .pinecone_retriever import PineconeRetriever
from .elasticsearch_retriever import ElasticsearchRetriever
from .redis_retriever import RedisRetriever
try:  # Optional dependency
    from .qdrant_retriever import QdrantRetriever
except ModuleNotFoundError:  # pragma: no cover - optional import guard
    QdrantRetriever = None

    import logging

    logger = logging.getLogger(__name__)
    logger.debug("qdrant_client not installed; QdrantRetriever unavailable")

__all__ = [
    'ChromaRetriever',
    'MilvusRetriever',
    'PineconeRetriever',
    'ElasticsearchRetriever',
    'RedisRetriever',
]

if QdrantRetriever is not None:
    __all__.append('QdrantRetriever')
