"""Passthrough conversational retriever implementation.

This retriever integrates with the existing pipeline infrastructure but
intentionally does not perform any retrieval. It exists so that
inference-only conversational adapters can reuse the same dynamic adapter
management flows as retrievers without triggering vector or SQL lookups.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from retrievers.base.base_retriever import BaseRetriever

logger = logging.getLogger(__name__)


class ConversationalImplementation(BaseRetriever):
    """Retriever-compatible adapter that short-circuits all retrieval logic."""

    def __init__(self, config: Dict[str, Any], domain_adapter: Optional[Any] = None, **kwargs: Any) -> None:
        super().__init__(config=config, domain_adapter=domain_adapter, **kwargs)
        logger.debug("Initialized conversational passthrough implementation")

    def _get_datasource_name(self) -> str:
        """Return the synthetic datasource identifier used for passthrough mode."""
        return "none"

    async def initialize(self) -> None:
        """Initialize shared services reused by BaseRetriever (API key service, etc.)."""
        if self.initialized:
            return
        await super().initialize()
        logger.info("Conversational passthrough implementation ready (no datasource involved)")

    async def close(self) -> None:
        """Close BaseRetriever resources (no additional cleanup required)."""
        await super().close()

    async def set_collection(self, collection_name: str) -> None:
        """Store the provided identifier for parity with retriever implementations."""
        self.collection = collection_name
        logger.debug("Passthrough adapter set_collection called with %s", collection_name)

    async def get_relevant_context(
        self,
        query: str,
        api_key: Optional[str] = None,
        collection_name: Optional[str] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Return an empty context list to indicate no retrieval was performed."""
        await super().get_relevant_context(query, api_key, collection_name, **kwargs)
        logger.debug("Passthrough adapter skipping retrieval for query: %s", query)
        return []
