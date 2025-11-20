"""
Document Reranking Step

This step reranks retrieved documents using a reranking service to improve relevance.
Runs after context retrieval and before LLM inference.
"""

import logging
from typing import Dict, Any, List, Optional
from ..base import PipelineStep, ProcessingContext


class DocumentRerankingStep(PipelineStep):
    """
    Rerank retrieved documents using a reranking service.

    This step:
    - Runs after context retrieval and before LLM inference
    - Uses adapter-level or global reranker configuration
    - Improves relevance of retrieved documents
    - Handles errors gracefully without breaking the pipeline
    - Preserves document metadata after reranking
    """

    def __init__(self, container):
        """Initialize the reranking step."""
        super().__init__(container)
        self.logger.debug("DocumentRerankingStep initialized and added to pipeline")

    def should_execute(self, context: ProcessingContext) -> bool:
        """
        Determine if this step should execute.

        Returns:
            True if:
            1. Retrieval happened (context.retrieved_docs exists and not empty)
            2. Reranker service is available in container OR adapter specifies reranker_provider
            3. Not blocked
            4. Not in inference-only mode (or adapter has retrieval)
        """
        config = self.container.get_or_none('config') or {}
        debug_enabled = self.logger.isEnabledFor(logging.DEBUG)

        if debug_enabled:
            self.logger.debug("DocumentRerankingStep.should_execute() - Starting evaluation")

        if context.is_blocked:
            if debug_enabled:
                self.logger.debug("DocumentRerankingStep.should_execute() - Context is blocked, skipping")
            return False

        # Check if we have documents to rerank
        if not context.retrieved_docs or len(context.retrieved_docs) == 0:
            self.logger.debug("DocumentRerankingStep.should_execute() - No documents to rerank")
            return False

        if debug_enabled:
            self.logger.debug(
                "DocumentRerankingStep.should_execute() - Found %s documents to potentially rerank",
                len(context.retrieved_docs),
            )

        # Check if reranking is globally enabled
        reranker_config = config.get('reranker', {})
        global_reranker_enabled = reranker_config.get('enabled', False)

        if debug_enabled:
            self.logger.debug(
                "DocumentRerankingStep.should_execute() - Global reranker enabled: %s",
                global_reranker_enabled,
            )

        # Check if adapter has reranker override
        adapter_has_reranker = False
        reranker_provider = None
        if context.adapter_name and self.container.has('adapter_manager'):
            adapter_manager = self.container.get('adapter_manager')
            adapter_config = adapter_manager.get_adapter_config(context.adapter_name) or {}
            reranker_provider = adapter_config.get('reranker_provider')
            adapter_has_reranker = bool(reranker_provider)

            if debug_enabled:
                self.logger.debug(
                    "DocumentRerankingStep.should_execute() - Adapter '%s' reranker_provider: %s",
                    context.adapter_name,
                    reranker_provider or 'None',
                )

        # Execute if global reranker is enabled OR adapter specifies a reranker
        should_rerank = global_reranker_enabled or adapter_has_reranker

        if debug_enabled:
            self.logger.debug(
                "DocumentRerankingStep.should_execute() - Decision: %s (global=%s, adapter=%s)",
                should_rerank,
                global_reranker_enabled,
                adapter_has_reranker,
            )

        if not should_rerank:
            self.logger.debug("Reranking disabled - skipping reranking step")
            return False

        return True

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        """
        Process the context and rerank retrieved documents.

        Args:
            context: The processing context with retrieved documents

        Returns:
            The modified context with reranked documents
        """
        if context.is_blocked:
            return context

        self.logger.debug(
            "DocumentRerankingStep.process() - Starting reranking of %s documents",
            len(context.retrieved_docs),
        )

        try:
            # Get reranker service
            reranker_service = await self._get_reranker_service(context)

            if not reranker_service:
                self.logger.warning("No reranker service available - skipping reranking")
                return context

            provider = getattr(reranker_service, 'provider_name', 'unknown')
            model = getattr(reranker_service, 'model', 'unknown')
            self.logger.debug(
                "DocumentRerankingStep.process() - Using reranker: %s/%s",
                provider,
                model,
            )

            # Extract document texts for reranking
            documents = self._extract_document_texts(context.retrieved_docs)

            if not documents:
                self.logger.warning("No document texts to rerank - skipping reranking")
                return context

            # Get top_n configuration
            top_n = self._get_top_n_config(context)

            self.logger.debug(
                "DocumentRerankingStep.process() - Reranking %s docs with top_n=%s",
                len(documents),
                top_n,
            )

            # Perform reranking
            reranked_results = await reranker_service.rerank(
                query=context.message,
                documents=documents,
                top_n=top_n
            )

            if not reranked_results:
                self.logger.warning("Reranking returned no results - keeping original order")
                return context

            top_scores = [r.get('score', 0.0) for r in reranked_results[:3]]
            self.logger.debug(
                "DocumentRerankingStep.process() - Reranked %s → %s docs, top scores: %s",
                len(documents),
                len(reranked_results),
                top_scores,
            )

            # Update context with reranked documents
            context.retrieved_docs = self._apply_reranking_results(
                context.retrieved_docs,
                reranked_results
            )

            # Update formatted context (pass adapter_name for formatting decision)
            context.formatted_context = self._format_context(context.retrieved_docs, context.adapter_name)

            # Store reranking metadata
            if not hasattr(context, 'metadata'):
                context.metadata = {}

            context.metadata['reranking'] = {
                'provider': getattr(reranker_service, 'provider_name', 'unknown'),
                'model': getattr(reranker_service, 'model', 'unknown'),
                'original_count': len(documents),
                'reranked_count': len(reranked_results),
                'top_scores': [r.get('score', 0.0) for r in reranked_results[:3]]
            }

            self.logger.debug(
                "Successfully reranked documents: %s -> %s",
                len(documents),
                len(reranked_results),
            )

        except Exception as e:
            # Log error but don't fail the pipeline - reranking is optional enhancement
            self.logger.error(
                "Error during document reranking: %s",
                str(e),
                exc_info=self.logger.isEnabledFor(logging.DEBUG),
            )
            self.logger.warning("Continuing with original document order")

        return context

    async def _get_reranker_service(self, context: ProcessingContext) -> Optional[Any]:
        """
        Get the appropriate reranker service for this context.

        First checks for adapter-level override, then falls back to global service.

        Args:
            context: Processing context

        Returns:
            Reranker service instance or None
        """
        # Check for adapter-level reranker override
        if context.adapter_name and self.container.has('adapter_manager'):
            adapter_manager = self.container.get('adapter_manager')
            adapter_config = adapter_manager.get_adapter_config(context.adapter_name) or {}

            reranker_provider = adapter_config.get('reranker_provider')

            if reranker_provider:
                # Try to get adapter-specific reranker
                try:
                    if hasattr(adapter_manager, 'get_overridden_reranker'):
                        reranker = await adapter_manager.get_overridden_reranker(
                            reranker_provider,
                            context.adapter_name
                        )
                        self.logger.debug(
                            f"Using adapter-specific reranker: {reranker_provider}"
                        )
                        return reranker
                except Exception as e:
                    self.logger.warning(
                        f"Failed to get adapter-specific reranker: {str(e)}"
                    )

        # Fall back to global reranker service
        if self.container.has('reranker_service'):
            return self.container.get('reranker_service')

        return None

    def _extract_document_texts(self, documents: List[Dict[str, Any]]) -> List[str]:
        """
        Extract text content from document dictionaries.

        Args:
            documents: List of document dictionaries

        Returns:
            List of document text strings
        """
        texts = []
        for doc in documents:
            # Try different field names for content
            text = doc.get('content') or doc.get('text') or doc.get('page_content') or ''
            if text:
                texts.append(str(text))

        return texts

    def _get_top_n_config(self, context: ProcessingContext) -> Optional[int]:
        """
        Get top_n configuration from adapter or global config.

        Args:
            context: Processing context

        Returns:
            top_n value or None
        """
        # Check adapter config first
        if context.adapter_name and self.container.has('adapter_manager'):
            adapter_manager = self.container.get('adapter_manager')
            adapter_config = adapter_manager.get_adapter_config(context.adapter_name) or {}

            adapter_top_n = adapter_config.get('config', {}).get('reranker_top_n')
            if adapter_top_n is not None:
                return adapter_top_n

        # Fall back to global config
        config = self.container.get_or_none('config') or {}
        reranker_config = config.get('reranker', {})
        provider_name = reranker_config.get('provider', 'ollama')

        provider_config = config.get('rerankers', {}).get(provider_name, {})
        return provider_config.get('top_n')

    def _apply_reranking_results(
        self,
        original_docs: List[Dict[str, Any]],
        reranked_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Apply reranking results to original documents, preserving metadata.

        Args:
            original_docs: Original document list
            reranked_results: Reranking results with scores and indices

        Returns:
            Reranked documents with metadata preserved
        """
        reranked_docs = []

        for result in reranked_results:
            # Get the original document by index
            idx = result.get('index', 0)

            if 0 <= idx < len(original_docs):
                # Copy the original document
                doc = original_docs[idx].copy()

                # Update or add relevance score from reranking
                doc['relevance'] = result.get('score', 0.0)
                doc['reranked'] = True

                reranked_docs.append(doc)

        return reranked_docs

    def _format_context(self, documents: List[Dict[str, Any]], adapter_name: str = None) -> str:
        """
        Format reranked documents into a context string.

        Args:
            documents: List of reranked documents
            adapter_name: Name of the adapter (used to determine formatting style)

        Returns:
            Formatted context string
        """
        if not documents:
            return "No relevant information found."

        # For file adapter, use clean formatting without citations to prevent
        # LLMs (especially Gemini) from adding citation markers like 【Document 1】
        is_file_adapter = adapter_name and 'file' in adapter_name.lower()

        context = ""
        for i, doc in enumerate(documents):
            content = doc.get('content', '')

            if is_file_adapter:
                # Clean format without source labels or relevance scores
                context += f"{content}\n\n"
            else:
                # Standard format with document references for other adapters
                metadata = doc.get('metadata', {})
                source = metadata.get('source', f"Document {i+1}")
                relevance = doc.get('relevance', doc.get('confidence', 0.0))
                context += f"[{i+1}] {source} (relevance: {relevance:.2f})\n{content}\n\n"

        return context.strip()
