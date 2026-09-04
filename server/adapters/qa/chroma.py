"""
ChromaDB-specific QA adapter
"""

from typing import Any
import logging
from adapters.qa.base import QADocumentAdapter
from adapters.factory import DocumentAdapterFactory

logger = logging.getLogger(__name__)

DocumentAdapterFactory.register_adapter("chroma_qa", lambda **kwargs: ChromaQAAdapter(**kwargs))


class ChromaQAAdapter(QADocumentAdapter):
    """Adapter for question-answer pairs in ChromaDB.

    Inherits QA formatting and answer extraction from QADocumentAdapter.
    Overrides filtering to skip confidence-based pruning (Chroma's similarity
    search already handles relevance ordering).
    """

    def apply_domain_specific_filtering(self,
                                        context_items: list[dict[str, Any]],
                                        query: str) -> list[dict[str, Any]]:
        return context_items
