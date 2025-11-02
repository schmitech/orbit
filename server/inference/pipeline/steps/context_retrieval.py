"""
Context Retrieval Step

This step retrieves relevant context documents for RAG processing.
"""

import logging
from typing import Dict, Any
from ..base import PipelineStep, ProcessingContext

class ContextRetrievalStep(PipelineStep):
    """
    Retrieve relevant context documents.
    
    This step performs RAG (Retrieval-Augmented Generation) by
    searching for relevant documents based on the user's query.
    """
    
    def should_execute(self, context: ProcessingContext) -> bool:
        """
        Determine if this step should execute.
        
        Returns:
            True if adapter manager is available, not in inference-only mode, and not blocked
        """
        config = self.container.get_or_none('config') or {}
        inference_only = config.get('general', {}).get('inference_only', False)
        
        if context.is_blocked:
            return False

        if inference_only:
            return False

        if not (self.container.has('adapter_manager') or self.container.has('retriever')):
            return False

        if not context.adapter_name:
            return False

        # Skip retrieval for passthrough adapters that explicitly opt out of context fetching
        if self.container.has('adapter_manager'):
            adapter_manager = self.container.get('adapter_manager')
            adapter_config = adapter_manager.get_adapter_config(context.adapter_name) or {}
            if adapter_config.get('type') == 'passthrough':
                return False

        return True
    
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
        
        try:
            # Try to get adapter from adapter manager first (dynamic loading)
            if self.container.has('adapter_manager'):
                adapter_manager = self.container.get('adapter_manager')
                retriever = await adapter_manager.get_adapter(context.adapter_name)
                self.logger.debug(f"Using dynamic adapter: {context.adapter_name}")
            else:
                # Fall back to static retriever
                retriever = self.container.get('retriever')
                self.logger.debug(f"Using static retriever with adapter_name: {context.adapter_name}")
            
            # Get relevant documents
            # Pass file_ids if present (for file adapter filtering)
            retriever_kwargs = {}
            if context.file_ids:
                # For file adapter, pass file_ids to filter by specific files
                if context.adapter_name == 'file-document-qa' or hasattr(retriever, 'get_relevant_context'):
                    # FileVectorRetriever accepts file_id parameter
                    # If multiple file_ids, we'll pass all of them and let retriever handle it
                    retriever_kwargs['file_ids'] = context.file_ids
                    # Also pass api_key for file ownership validation
                    if context.api_key:
                        retriever_kwargs['api_key'] = context.api_key
            
            docs = await retriever.get_relevant_context(
                query=context.message,
                adapter_name=context.adapter_name,
                **retriever_kwargs
            )
            
            context.retrieved_docs = docs

            # Check if results were truncated
            truncation_info = None
            if docs and len(docs) > 0:
                # Check first document for truncation metadata
                first_doc_metadata = docs[0].get('metadata', {})
                if first_doc_metadata.get('truncated', False):
                    truncation_info = {
                        'shown': first_doc_metadata.get('result_count', len(docs)),
                        'total': first_doc_metadata.get('total_available', len(docs))
                    }
                    self.logger.info(f"Retrieved {len(docs)} documents (truncated from {truncation_info['total']} total)")
                else:
                    self.logger.debug(f"Retrieved {len(docs)} documents")
            else:
                self.logger.debug(f"Retrieved {len(docs)} documents")

            # Format context for LLM (pass adapter_name and truncation info for formatting decision)
            context.formatted_context = self._format_context(docs, context.adapter_name, truncation_info)
            
        except Exception as e:
            self.logger.error(f"Error during context retrieval: {str(e)}")
            context.set_error(f"Failed to retrieve context: {str(e)}")
        
        return context
    
    def _format_context(self, documents: list, adapter_name: str = None, truncation_info: dict = None) -> str:
        """
        Format retrieved documents into a context string.

        Args:
            documents: List of retrieved documents
            adapter_name: Name of the adapter (used to determine formatting style)
            truncation_info: Dict with 'shown' and 'total' keys if results were truncated

        Returns:
            Formatted context string
        """
        if not documents:
            return "No relevant information found."

        # For file adapter, use clean formatting without citations to prevent
        # LLMs (especially Gemini) from adding citation markers like 【Document 1】
        is_file_adapter = adapter_name and 'file' in adapter_name.lower()

        context = ""

        # Add truncation notice at the beginning if applicable
        if truncation_info:
            shown = truncation_info.get('shown', len(documents))
            total = truncation_info.get('total', len(documents))
            if shown < total:
                context += f"NOTE: Showing {shown} of {total} total results from database. Results have been truncated.\n\n"

        for i, doc in enumerate(documents):
            content = doc.get('content', '')

            if is_file_adapter:
                # Clean format without source labels or confidence scores
                context += f"{content}\n\n"
            else:
                # Standard format with document references for other adapters
                metadata = doc.get('metadata', {})
                source = metadata.get('source', f"Document {i+1}")
                confidence = doc.get('confidence', doc.get('relevance', 0.0))
                context += f"[{i+1}] {source} (confidence: {confidence:.2f})\n{content}\n\n"

        return context.strip() 
