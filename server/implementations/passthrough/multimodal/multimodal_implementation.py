"""
Multimodal conversational retriever implementation.

This retriever combines conversation history with file retrieval capabilities.
It maintains conversation context (like conversational-passthrough) while
also supporting file chunk retrieval from vector stores when files are
provided in the request.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from retrievers.base.base_retriever import BaseRetriever

logger = logging.getLogger(__name__)


class MultimodalImplementation(BaseRetriever):
    """
    Retriever-compatible adapter that combines conversation with file retrieval.

    When file_ids are provided in the request, it retrieves relevant chunks
    from those files. When no files are present, it behaves like a passthrough
    adapter (empty context, conversation-only).

    Note: File tracking is managed by the frontend (localStorage). The backend
    is stateless - it only processes file_ids sent with each request.
    """

    def __init__(self, config: Dict[str, Any], domain_adapter: Optional[Any] = None, **kwargs: Any) -> None:
        super().__init__(config=config, domain_adapter=domain_adapter, **kwargs)

        # Initialize file retriever (will be initialized lazily)
        self._file_retriever = None

        self.logger.debug("Initialized multimodal conversational implementation")
    
    def _get_datasource_name(self) -> str:
        """Return the synthetic datasource identifier used for passthrough mode."""
        return "none"
    
    async def initialize(self) -> None:
        """Initialize shared services and file retriever."""
        if self.initialized:
            return

        await super().initialize()

        # Initialize file retriever for file chunk retrieval
        if self._file_retriever is None:
            try:
                from retrievers.implementations.file.file_retriever import FileVectorRetriever
                # Use the same config structure as file-document-qa adapter
                # Get adapter config first, then fallback to global files config
                adapter_config = self.config.get('adapter_config', {})
                files_config = self.config.get('files', {})

                # Create config for file retriever
                file_retriever_config = {
                    **self.config,  # Include all config
                    'adapter_config': adapter_config,  # Preserve adapter-specific config
                    'files': files_config  # Include files config
                }

                self._file_retriever = FileVectorRetriever(
                    config=file_retriever_config,
                    domain_adapter=self.domain_adapter
                )
                await self._file_retriever.initialize()

                if self.verbose:
                    self.logger.info("FileVectorRetriever initialized for multimodal adapter")
            except Exception as e:
                self.logger.warning(f"Failed to initialize FileVectorRetriever: {e}. "
                                 f"Multimodal adapter will operate without file retrieval.")
                self._file_retriever = None

        if self.verbose:
            self.logger.info("Multimodal conversational implementation ready")
    
    async def close(self) -> None:
        """Close BaseRetriever resources and file retriever."""
        if self._file_retriever:
            try:
                await self._file_retriever.close()
            except Exception as e:
                self.logger.warning(f"Error closing file retriever: {e}")
        
        await super().close()
    
    async def set_collection(self, collection_name: str) -> None:
        """Store the provided identifier for parity with retriever implementations."""
        self.collection = collection_name
        if self.verbose:
            self.logger.debug("Multimodal adapter set_collection called with %s", collection_name)
    
    async def get_relevant_context(
        self,
        query: str,
        api_key: Optional[str] = None,
        collection_name: Optional[str] = None,
        session_id: Optional[str] = None,
        file_ids: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant context from files provided in the request.

        The frontend manages file associations (in localStorage). This method
        simply processes whatever file_ids are sent with each request.

        Args:
            query: User query
            api_key: API key for authentication
            collection_name: Collection name (not used for multimodal)
            session_id: Session identifier (for logging only)
            file_ids: List of file IDs to query (from frontend)
            **kwargs: Additional parameters

        Returns:
            List of file chunks if file_ids provided, empty list otherwise
        """
        await super().get_relevant_context(query, api_key, collection_name, **kwargs)

        # Ensure initialized
        await self.initialize()

        # If no file retriever available, return empty (conversation-only)
        if not self._file_retriever:
            if self.verbose:
                self.logger.debug("Multimodal adapter: No file retriever available, returning empty context")
            return []

        # If no file_ids provided, return empty context (pure conversation mode)
        if not file_ids:
            if self.verbose:
                self.logger.info("Multimodal adapter: No file_ids provided, returning empty context (conversation-only mode)")
            return []

        # Retrieve chunks from the provided files
        try:
            if self.verbose:
                self.logger.info(f"Multimodal adapter: Retrieving chunks from {len(file_ids)} files: {file_ids}")
                self.logger.info(f"Query: {query[:100]}...")

            # Use FileVectorRetriever to get relevant chunks
            chunks = await self._file_retriever.get_relevant_context(
                query=query,
                api_key=api_key,
                file_ids=file_ids,  # Use file_ids from request
                collection_name=None  # Let retriever find collections by file_id
            )

            if self.verbose:
                self.logger.info(f"Multimodal adapter: Retrieved {len(chunks)} chunks from {len(file_ids)} files")
            if chunks:
                self.logger.debug(f"First chunk preview: {chunks[0].get('content', '')[:200]}...")

            return chunks

        except Exception as e:
            self.logger.error(f"Error retrieving file chunks: {e}")
            # Return empty context on error (don't break conversation)
            return []

