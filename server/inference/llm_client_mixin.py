"""
LLM Client Mixin

This module provides common functionality shared across different LLM client implementations.
"""

import json
import time
import logging
from typing import Dict, List, Any, Optional, AsyncGenerator

class LLMClientMixin:
    """
    Mixin class providing common functionality for LLM clients.
    
    This mixin implements common patterns found across different LLM client implementations,
    reducing code duplication and making clients more maintainable.
    """
    
    async def _check_message_safety(self, message: str) -> bool:
        """
        Check if a message passes safety checks.
        
        Args:
            message: The user's message
            
        Returns:
            True if message is safe, False otherwise
        """
        if not self.guardrail_service:
            return True
            
        is_safe = await self.guardrail_service.is_safe(message)
        if not is_safe and getattr(self, 'verbose', False):
            self.logger.warning("Message failed safety check")
            
        return is_safe
    
    async def _get_system_prompt(self, system_prompt_id: Optional[str] = None) -> str:
        """
        Get the system prompt from the prompt service or return default.
        
        Args:
            system_prompt_id: Optional ID of a system prompt to use
            
        Returns:
            System prompt string
        """
        system_prompt = "You are a helpful assistant that provides accurate information."
        
        if not system_prompt_id or not self.prompt_service:
            return system_prompt
            
        # Log if verbose mode is enabled
        if getattr(self, 'verbose', False):
            self.logger.info(f"Fetching system prompt with ID: {system_prompt_id}")
            
        # Get prompt from service
        prompt_doc = await self.prompt_service.get_prompt_by_id(system_prompt_id)
        if prompt_doc and 'prompt' in prompt_doc:
            system_prompt = prompt_doc['prompt']
            if getattr(self, 'verbose', False):
                self.logger.debug(f"Using custom system prompt: {system_prompt[:100]}...")
                
        return system_prompt
    
    async def _retrieve_and_rerank_docs(self, message: str, collection_name: str) -> List[Dict[str, Any]]:
        """
        Retrieve documents and rerank them if a reranker is available.
        
        Args:
            message: The user's message
            collection_name: Name of the collection to query for context
            
        Returns:
            List of retrieved and optionally reranked documents
        """
        # Log if verbose mode is enabled
        if getattr(self, 'verbose', False):
            self.logger.info(f"Retrieving context from collection: {collection_name}")
            
        # Query for relevant documents
        retrieved_docs = await self.retriever.get_relevant_context(
            query=message,
            collection_name=collection_name
        )
        
        if getattr(self, 'verbose', False):
            self.logger.info(f"Retrieved {len(retrieved_docs)} relevant documents")
        
        # Rerank if reranker is available
        if self.reranker_service and retrieved_docs:
            if getattr(self, 'verbose', False):
                self.logger.info("Reranking retrieved documents")
            retrieved_docs = await self.reranker_service.rerank(message, retrieved_docs)
            
        return retrieved_docs
    
    async def _handle_unsafe_message(self) -> Dict[str, Any]:
        """
        Generate a standard response for unsafe messages.
        
        Returns:
            Dictionary with safety response
        """
        return {
            "response": "I'm sorry, but I cannot respond to that message as it may violate content safety guidelines.",
            "sources": [],
            "tokens": 0,
            "processing_time": 0
        }
    
    async def _handle_unsafe_message_stream(self) -> str:
        """
        Generate a standard streaming response for unsafe messages.
        
        Returns:
            JSON string with safety response
        """
        return json.dumps({
            "response": "I'm sorry, but I cannot respond to that message as it may violate content safety guidelines.",
            "sources": [],
            "done": True
        })
    
    async def _prepare_prompt_with_context(self, message: str, system_prompt: str, context: str) -> str:
        """
        Prepare the full prompt with system prompt, context and user message.
        
        Args:
            message: The user's message
            system_prompt: The system prompt to use
            context: The context from retrieved documents
            
        Returns:
            Formatted prompt string
        """
        prompt = f"{system_prompt}\n\nContext information:\n{context}\n\nUser: {message}\nAssistant:"
        
        if getattr(self, 'verbose', False):
            self.logger.debug(f"Prepared prompt length: {len(prompt)} characters")
            
        return prompt
    
    def _measure_execution_time(self, start_time: float) -> float:
        """
        Calculate execution time from start time to now.
        
        Args:
            start_time: The start time from time.time()
            
        Returns:
            Processing time in seconds
        """
        end_time = time.time()
        processing_time = end_time - start_time
        
        if getattr(self, 'verbose', False):
            self.logger.info(f"Received response in {processing_time:.2f} seconds")
            
        return processing_time
    
    def _estimate_tokens(self, prompt: str, response_text: str) -> int:
        """
        Estimate token count for models that don't provide direct token counts.
        
        Args:
            prompt: The input prompt
            response_text: The generated response
            
        Returns:
            Estimated token count
        """
        # Rough estimate: ~4 chars per token
        estimated_tokens = len(prompt) // 4 + len(response_text) // 4
        
        if getattr(self, 'verbose', False):
            self.logger.info(f"Estimated token usage: {estimated_tokens}")
            
        return estimated_tokens 