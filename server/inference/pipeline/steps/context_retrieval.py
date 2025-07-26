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
            True if retriever is available, not in inference-only mode, and not blocked
        """
        config = self.container.get_or_none('config') or {}
        inference_only = config.get('general', {}).get('inference_only', False)
        
        return (not inference_only and 
                self.container.has('retriever') and 
                context.adapter_name and
                not context.is_blocked)
    
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
            retriever = self.container.get('retriever')
            
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