"""
File Retriever

Retriever implementations for querying uploaded files.
Supports both vector store (chunked documents) and DuckDB (structured data) approaches.
"""

from .file_retriever import FileVectorRetriever

__all__ = [
    'FileVectorRetriever',
]
