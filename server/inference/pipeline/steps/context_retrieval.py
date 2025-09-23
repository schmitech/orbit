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
            docs = await retriever.get_relevant_context(
                query=context.message,
                adapter_name=context.adapter_name
            )
            
            context.retrieved_docs = docs
            self.logger.debug(f"Retrieved {len(docs)} documents")
            
            # Format context for LLM
            context.formatted_context = self._format_context(docs)
            
        except Exception as e:
            self.logger.error(f"Error during context retrieval: {str(e)}")
            context.set_error(f"Failed to retrieve context: {str(e)}")
        
        return context
    
    def _format_context(self, documents: list) -> str:
        """
        Format retrieved documents into a context string.
        
        Args:
            documents: List of retrieved documents
            
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
            
            # Try different field names based on what's available
            confidence = doc.get('confidence', doc.get('relevance', 0.0))
            
            # Add document to context with confidence score if available
            context += f"[{i+1}] {source} (confidence: {confidence:.2f})\n{content}\n\n"
        
        return context 
