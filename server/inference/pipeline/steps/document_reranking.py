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
        # Log when step is created
        config = container.get_or_none('config') or {}
        verbose = config.get('general', {}).get('verbose', False)
        if verbose:
            self.logger.info("DocumentRerankingStep initialized and added to pipeline")

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
        # Get verbose setting
        config = self.container.get_or_none('config') or {}
        verbose = config.get('general', {}).get('verbose', False)

        if verbose:
            self.logger.info("DocumentRerankingStep.should_execute() - Starting evaluation")

        if context.is_blocked:
            if verbose:
                self.logger.info("DocumentRerankingStep.should_execute() - Context is blocked, skipping")
            return False

        # Check if we have documents to rerank
        if not context.retrieved_docs or len(context.retrieved_docs) == 0:
            if verbose:
                self.logger.info("DocumentRerankingStep.should_execute() - No documents to rerank")
            else:
                self.logger.debug("No documents to rerank - skipping reranking step")
            return False

        if verbose:
            self.logger.info(f"DocumentRerankingStep.should_execute() - Found {len(context.retrieved_docs)} documents to potentially rerank")

        # Check if reranking is globally enabled
        reranker_config = config.get('reranker', {})
        global_reranker_enabled = reranker_config.get('enabled', False)

        if verbose:
            self.logger.info(f"DocumentRerankingStep.should_execute() - Global reranker enabled: {global_reranker_enabled}")

        # Check if adapter has reranker override
        adapter_has_reranker = False
        reranker_provider = None
        if context.adapter_name and self.container.has('adapter_manager'):
            adapter_manager = self.container.get('adapter_manager')
            adapter_config = adapter_manager.get_adapter_config(context.adapter_name) or {}
            reranker_provider = adapter_config.get('reranker_provider')
            adapter_has_reranker = bool(reranker_provider)

            if verbose:
                self.logger.info(f"DocumentRerankingStep.should_execute() - Adapter '{context.adapter_name}' reranker_provider: {reranker_provider or 'None'}")

        # Execute if global reranker is enabled OR adapter specifies a reranker
        should_rerank = global_reranker_enabled or adapter_has_reranker

        if verbose:
            self.logger.info(f"DocumentRerankingStep.should_execute() - Decision: {should_rerank} (global={global_reranker_enabled}, adapter={adapter_has_reranker})")

        if not should_rerank:
            if not verbose:
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
        # Get verbose setting
        config = self.container.get_or_none('config') or {}
        verbose = config.get('general', {}).get('verbose', False)

        if context.is_blocked:
            return context

        if verbose:
            self.logger.info(f"DocumentRerankingStep.process() - Starting reranking of {len(context.retrieved_docs)} documents")
        else:
            self.logger.debug(f"Reranking {len(context.retrieved_docs)} documents")

        try:
            # Get reranker service
            reranker_service = await self._get_reranker_service(context)

            if not reranker_service:
                if verbose:
                    self.logger.info("DocumentRerankingStep.process() - No reranker service available, skipping")
                else:
                    self.logger.warning("No reranker service available - skipping reranking")
                return context

            if verbose:
                provider = getattr(reranker_service, 'provider_name', 'unknown')
                model = getattr(reranker_service, 'model', 'unknown')
                self.logger.info(f"DocumentRerankingStep.process() - Using reranker: {provider}/{model}")

            # Extract document texts for reranking
            documents = self._extract_document_texts(context.retrieved_docs)

            if not documents:
                if verbose:
                    self.logger.info("DocumentRerankingStep.process() - No document texts extracted, skipping")
                else:
                    self.logger.warning("No document texts to rerank - skipping reranking")
                return context

            # Get top_n configuration
            top_n = self._get_top_n_config(context)

            if verbose:
                self.logger.info(f"DocumentRerankingStep.process() - Reranking {len(documents)} docs with top_n={top_n}")

            # Perform reranking
            reranked_results = await reranker_service.rerank(
                query=context.message,
                documents=documents,
                top_n=top_n
            )

            if not reranked_results:
                if verbose:
                    self.logger.info("DocumentRerankingStep.process() - Reranking returned no results, keeping original order")
                else:
                    self.logger.warning("Reranking returned no results - keeping original order")
                return context

            if verbose:
                top_scores = [r.get('score', 0.0) for r in reranked_results[:3]]
                self.logger.info(f"DocumentRerankingStep.process() - Reranked {len(documents)} → {len(reranked_results)} docs, top scores: {top_scores}")

            # Update context with reranked documents
            context.retrieved_docs = self._apply_reranking_results(
                context.retrieved_docs,
                reranked_results
            )

            # Update formatted context
            context.formatted_context = self._format_context(context.retrieved_docs)

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

            if verbose:
                self.logger.info(f"DocumentRerankingStep.process() - Successfully completed reranking")
            else:
                self.logger.debug(
                    f"Successfully reranked documents: {len(documents)} -> {len(reranked_results)}"
                )

        except Exception as e:
            # Log error but don't fail the pipeline - reranking is optional enhancement
            self.logger.error(f"Error during document reranking: {str(e)}")
            if verbose:
                import traceback
                self.logger.error(f"DocumentRerankingStep.process() - Traceback:\n{traceback.format_exc()}")
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

    def _format_context(self, documents: List[Dict[str, Any]]) -> str:
        """
        Format reranked documents into a context string.

        Args:
            documents: List of reranked documents

        Returns:
            Formatted context string
        """
        if not documents:
            return "No relevant information found."

        context = ""
        for i, doc in enumerate(documents):
            content = doc.get('content', '')
            metadata = doc.get('metadata', {})
            source = metadata.get('source', f"Document {i+1}")

            # Use reranked score if available, otherwise use original confidence
            relevance = doc.get('relevance', doc.get('confidence', 0.0))

            # Add document to context with relevance score
            context += f"[{i+1}] {source} (relevance: {relevance:.2f})\n{content}\n\n"

        return context
