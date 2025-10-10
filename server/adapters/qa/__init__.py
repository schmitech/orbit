"""
QA (Question-Answer) adapter package.

This package provides adapters for question-answer document retrieval,
including datasource-specific implementations for ChromaDB, SQL databases, etc.
"""

from adapters.qa.base import QADocumentAdapter
from adapters.qa.chroma import ChromaQAAdapter
from adapters.qa.sql import QASQLAdapter

__all__ = ['QADocumentAdapter', 'ChromaQAAdapter', 'QASQLAdapter']
