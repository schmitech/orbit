"""
Context Retrieval Step

This step retrieves relevant context documents for RAG processing.
Refactored to use capability-based architecture instead of hardcoded adapter checks.
"""

import logging
from typing import Dict, Any, Optional
from ..base import PipelineStep, ProcessingContext
from adapters.capabilities import (
    AdapterCapabilities,
    get_capability_registry,
    FormattingStyle,
    RetrievalBehavior
)

class ContextRetrievalStep(PipelineStep):
    """
    Retrieve relevant context documents.

    This step performs RAG (Retrieval-Augmented Generation) by
    searching for relevant documents based on the user's query.

    Uses capability-based architecture to determine adapter behavior
    without hardcoded type checks.
    """

    def __init__(self, container: 'ServiceContainer'):
        """Initialize the step and load adapter capabilities."""
        super().__init__(container)
        self._capability_registry = get_capability_registry()

        # Get verbose setting from config if available
        config = container.get('config') if container.has('config') else {}
        self.verbose = config.get('general', {}).get('verbose', False) if isinstance(config, dict) else False

        self._initialize_capabilities()

    def _initialize_capabilities(self) -> None:
        """
        Initialize adapter capabilities from configuration.

        This runs once at startup to register all adapter capabilities
        from the configuration, avoiding repeated config parsing.
        """
        if not self.container.has('adapter_manager'):
            self.logger.debug(
                "Adapter manager not available, skipping capability initialization. "
                "Capabilities will be inferred on-demand."
            )
            return

        adapter_manager = self.container.get('adapter_manager')

        # Get all adapter configurations
        adapter_configs = adapter_manager._adapter_configs if hasattr(
            adapter_manager, '_adapter_configs'
        ) else {}

        for adapter_name, adapter_config in adapter_configs.items():
            # Check if capabilities are explicitly defined in config
            if 'capabilities' in adapter_config:
                # Load from config
                self._capability_registry.register_from_config(
                    adapter_name, adapter_config
                )
            else:
                # Infer capabilities from adapter type and config
                capabilities = self._infer_capabilities(adapter_config)
                self._capability_registry.register(adapter_name, capabilities)

        self.logger.info(
            f"Initialized capabilities for {len(adapter_configs)} adapters"
        )

    def _infer_capabilities(self, adapter_config: Dict[str, Any], adapter_name: Optional[str] = None) -> AdapterCapabilities:
        """
        Infer adapter capabilities from configuration.

        This provides backward compatibility for adapters that don't
        explicitly declare capabilities in their config.

        Args:
            adapter_config: Adapter configuration dictionary
            adapter_name: Optional adapter name for threading detection

        Returns:
            Inferred AdapterCapabilities
        """
        adapter_type = adapter_config.get('type', 'retriever')
        adapter_impl = adapter_config.get('adapter', '')
        
        # Use provided adapter_name or get from config
        if not adapter_name:
            adapter_name = adapter_config.get('name', '')

        # Passthrough adapters
        if adapter_type == 'passthrough':
            if adapter_impl == 'multimodal':
                return AdapterCapabilities.for_passthrough(supports_file_retrieval=True)
            else:
                return AdapterCapabilities.for_passthrough(supports_file_retrieval=False)

        # File adapters
        if adapter_impl == 'file' or 'file' in adapter_name.lower():
            return AdapterCapabilities.for_file_adapter()

        # Standard retriever adapters (QA, Intent, etc.)
        return AdapterCapabilities.for_standard_retriever(adapter_name=adapter_name)

    def _get_capabilities(self, adapter_name: str) -> Optional[AdapterCapabilities]:
        """
        Get capabilities for an adapter.

        Args:
            adapter_name: Name of the adapter

        Returns:
            AdapterCapabilities or None if not found
        """
        capabilities = self._capability_registry.get(adapter_name)

        if not capabilities:
            # Try to get from adapter manager if not in registry
            if self.container.has('adapter_manager'):
                adapter_manager = self.container.get('adapter_manager')
                adapter_config = adapter_manager.get_adapter_config(adapter_name)

                if adapter_config:
                    try:
                        capabilities = self._infer_capabilities(adapter_config, adapter_name)
                        self._capability_registry.register(adapter_name, capabilities)
                        self.logger.debug(
                            f"Inferred and registered capabilities for adapter: {adapter_name}"
                        )
                    except Exception as e:
                        self.logger.warning(
                            f"Failed to infer capabilities for adapter '{adapter_name}': {e}. "
                            "Using default behavior."
                        )
                else:
                    self.logger.warning(
                        f"Adapter configuration not found for '{adapter_name}'. "
                        "Capabilities cannot be inferred."
                    )

        return capabilities

    def should_execute(self, context: ProcessingContext) -> bool:
        """
        Determine if this step should execute.

        Uses capability-based decision making instead of hardcoded checks.

        Returns:
            True if adapter manager is available and retrieval should occur
        """
        if context.is_blocked:
            return False

        if not (self.container.has('adapter_manager') or self.container.has('retriever')):
            return False

        if not context.adapter_name:
            return False

        # Get adapter capabilities
        capabilities = self._get_capabilities(context.adapter_name)

        if not capabilities:
            # No capabilities found - assume standard retrieval for backward compatibility
            self.logger.warning(
                f"No capabilities found for adapter '{context.adapter_name}'. "
                "This may indicate: "
                "1) Adapter not registered in capability registry, "
                "2) Adapter configuration missing, or "
                "3) Capability inference failed. "
                "Assuming standard retrieval behavior (ALWAYS, STANDARD formatting)."
            )
            return True

        # Use capabilities to determine if retrieval should execute
        return capabilities.should_retrieve(context)

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        """
        Process the context and retrieve relevant documents.

        Args:
            context: The processing context

        Returns:
            The modified context with retrieved documents
        """
        if context.is_blocked:
            return context

        self.logger.debug(f"Retrieving context for adapter: {context.adapter_name}")

        # Check if this is a thread follow-up (use stored dataset instead of retrieval)
        if context.thread_id:
            try:
                # Get thread service from container
                if self.container.has('thread_service'):
                    thread_service = self.container.get('thread_service')
                else:
                    # Create thread service if not in container
                    from services.thread_service import ThreadService
                    config = self.container.get('config')
                    thread_service = ThreadService(config)
                    await thread_service.initialize()
                
                # Get stored dataset from thread
                dataset = await thread_service.get_thread_dataset(context.thread_id)
                
                if dataset:
                    query_context, raw_results = dataset
                    # Convert raw results to retrieved_docs format
                    docs = raw_results if isinstance(raw_results, list) else []
                    
                    # Update session_id to thread session_id for conversation history
                    thread_info = await thread_service.get_thread(context.thread_id)
                    if thread_info:
                        context.session_id = thread_info.get('thread_session_id', context.session_id)
                    
                    context.retrieved_docs = docs
                    
                    if self.verbose:
                        self.logger.info(f"Loaded {len(docs)} documents from thread {context.thread_id}")
                    
                    # Format context for LLM
                    capabilities = self._get_capabilities(context.adapter_name)
                    truncation_info = self._get_truncation_info(docs)
                    context.formatted_context = self._format_context(
                        docs,
                        capabilities,
                        truncation_info
                    )
                    
                    return context
                else:
                    self.logger.warning(f"Thread {context.thread_id} dataset not found or expired, falling back to normal retrieval")
            except Exception as e:
                self.logger.error(f"Error loading thread dataset: {e}, falling back to normal retrieval")

        # Get adapter capabilities
        capabilities = self._get_capabilities(context.adapter_name)

        try:
            # Get retriever instance
            retriever = await self._get_retriever(context)

            if not retriever:
                context.set_error("Retriever not available")
                return context

            # Build retriever kwargs based on capabilities
            retriever_kwargs = self._build_retriever_kwargs(context, capabilities)

            # Get relevant documents
            docs = await retriever.get_relevant_context(
                query=context.message,
                collection_name=None,
                **retriever_kwargs
            )

            context.retrieved_docs = docs

            # Check if results were truncated
            truncation_info = self._get_truncation_info(docs)

            if truncation_info:
                shown = truncation_info['shown']
                total = truncation_info['total']
                self.logger.info(
                    f"Retrieved {len(docs)} documents "
                    f"(truncated from {total} total)"
                )
            else:
                self.logger.debug(f"Retrieved {len(docs)} documents")

            # Format context for LLM using capabilities
            context.formatted_context = self._format_context(
                docs,
                capabilities,
                truncation_info
            )

        except Exception as e:
            self.logger.error(f"Error during context retrieval: {str(e)}")
            context.set_error(f"Failed to retrieve context: {str(e)}")

        return context

    async def _get_retriever(self, context: ProcessingContext) -> Any:
        """
        Get retriever instance for the adapter.

        Args:
            context: Processing context

        Returns:
            Retriever instance or None
        """
        # Try to get adapter from adapter manager first (dynamic loading)
        if self.container.has('adapter_manager'):
            adapter_manager = self.container.get('adapter_manager')
            retriever = await adapter_manager.get_adapter(context.adapter_name)
            self.logger.debug(f"Using dynamic adapter: {context.adapter_name}")
            return retriever
        else:
            # Fall back to static retriever
            retriever = self.container.get('retriever')
            self.logger.debug(
                f"Using static retriever with adapter_name: {context.adapter_name}"
            )
            return retriever

    def _build_retriever_kwargs(
        self,
        context: ProcessingContext,
        capabilities: Optional[AdapterCapabilities]
    ) -> Dict[str, Any]:
        """
        Build kwargs for get_relevant_context() based on capabilities.

        Args:
            context: Processing context
            capabilities: Adapter capabilities

        Returns:
            Dictionary of kwargs
        """
        if capabilities:
            # Use capabilities to build kwargs
            return capabilities.build_retriever_kwargs(context)

        # Fallback: build kwargs manually for backward compatibility
        kwargs = {}

        # Always include api_key if present
        if context.api_key:
            kwargs['api_key'] = context.api_key

        # Include file_ids if present (for backward compatibility)
        if context.file_ids:
            kwargs['file_ids'] = context.file_ids

        # Include session_id if present
        if context.session_id:
            kwargs['session_id'] = context.session_id

        return kwargs

    def _get_truncation_info(self, docs: list) -> Optional[Dict[str, int]]:
        """
        Extract truncation information from retrieved documents.

        Args:
            docs: List of retrieved documents

        Returns:
            Dictionary with 'shown' and 'total' keys, or None
        """
        if not docs or len(docs) == 0:
            return None

        # Check first document for truncation metadata
        first_doc_metadata = docs[0].get('metadata', {})

        if first_doc_metadata.get('truncated', False):
            return {
                'shown': first_doc_metadata.get('result_count', len(docs)),
                'total': first_doc_metadata.get('total_available', len(docs))
            }

        return None

    def _format_context(
        self,
        documents: list,
        capabilities: Optional[AdapterCapabilities],
        truncation_info: Optional[Dict[str, int]] = None
    ) -> str:
        """
        Format retrieved documents into a context string.

        Uses capabilities to determine formatting style instead of
        hardcoded adapter name checks.

        Args:
            documents: List of retrieved documents
            capabilities: Adapter capabilities
            truncation_info: Dict with 'shown' and 'total' keys if results were truncated

        Returns:
            Formatted context string
        """
        if not documents:
            return "No relevant information found."

        # Determine formatting style from capabilities
        if capabilities and capabilities.custom_format_context:
            # Use custom formatting if provided
            return capabilities.custom_format_context(
                documents, truncation_info
            )

        formatting_style = (
            capabilities.formatting_style
            if capabilities
            else FormattingStyle.STANDARD
        )

        if formatting_style == FormattingStyle.CLEAN:
            return self._format_clean(documents, truncation_info)
        else:
            return self._format_standard(documents, truncation_info)

    def _format_clean(
        self,
        documents: list,
        truncation_info: Optional[Dict[str, int]] = None
    ) -> str:
        """
        Format documents in clean style (no citations).

        Used for file and multimodal adapters to prevent LLMs from
        adding citation markers like 【Document 1】.

        Args:
            documents: List of documents
            truncation_info: Truncation information

        Returns:
            Formatted context string
        """
        context = ""

        # Add truncation notice at the beginning if applicable
        if truncation_info:
            shown = truncation_info.get('shown', len(documents))
            total = truncation_info.get('total', len(documents))
            if shown < total:
                context += (
                    f"NOTE: Showing {shown} of {total} total results from database. "
                    "Results have been truncated.\n\n"
                )

        for i, doc in enumerate(documents):
            content = doc.get('content', '')

            # Add context label for first chunk to help LLM understand this is document content
            if i == 0:
                context += "## Content extracted from uploaded file(s):\n\n"

            context += f"{content}\n\n"

        return context.strip()

    def _format_standard(
        self,
        documents: list,
        truncation_info: Optional[Dict[str, int]] = None
    ) -> str:
        """
        Format documents in standard style (with citations).

        Used for standard retriever adapters (QA, Intent, etc.).

        Args:
            documents: List of documents
            truncation_info: Truncation information

        Returns:
            Formatted context string
        """
        context = ""

        # Add truncation notice at the beginning if applicable
        if truncation_info:
            shown = truncation_info.get('shown', len(documents))
            total = truncation_info.get('total', len(documents))
            if shown < total:
                context += (
                    f"NOTE: Showing {shown} of {total} total results from database. "
                    "Results have been truncated.\n\n"
                )

        for i, doc in enumerate(documents):
            content = doc.get('content', '')
            metadata = doc.get('metadata', {})
            source = metadata.get('source', f"Document {i+1}")
            confidence = doc.get('confidence', doc.get('relevance', 0.0))

            context += (
                f"[{i+1}] {source} (confidence: {confidence:.2f})\n"
                f"{content}\n\n"
            )

        return context.strip()
