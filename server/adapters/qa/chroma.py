"""
ChromaDB-specific QA adapter
"""

from typing import Dict, Any, List, Optional
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
                                        context_items: List[Dict[str, Any]],
                                        query: str) -> List[Dict[str, Any]]:
        return context_items

    def apply_domain_filtering(self, context_items: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        return self.apply_domain_specific_filtering(context_items, query)
