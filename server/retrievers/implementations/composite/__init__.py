"""Composite retriever implementations for multi-source query routing."""

import logging

logger = logging.getLogger(__name__)

try:
    from .composite_intent_retriever import CompositeIntentRetriever
    _composite_available = True
except ImportError as e:
    CompositeIntentRetriever = None
    _composite_available = False
    logger.debug(f"CompositeIntentRetriever not available: {e}")

__all__ = []

if _composite_available and CompositeIntentRetriever is not None:
    __all__.append('CompositeIntentRetriever')

