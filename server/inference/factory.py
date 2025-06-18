"""
LLM Client Factory

This module provides a factory class for creating LLM clients based on the selected inference provider.
"""

import logging
from typing import Dict, Any, Optional

from .base_llm_client import BaseLLMClient
from .clients import get_client_class

class LLMClientFactory:
    """Factory for creating LLM clients based on the selected inference provider."""
    
    @staticmethod
    def create_llm_client(
        config: Dict[str, Any], 
        retriever: Any, 
        reranker_service: Any = None,
        prompt_service: Any = None,
        no_results_message: str = ""
    ) -> BaseLLMClient:
        """
        Create an LLM client based on the selected inference provider.
        
        Args:
            config: Application configuration dictionary
            retriever: The retriever to use for document lookup
            reranker_service: Optional service for reranking results
            prompt_service: Optional service for system prompts
            no_results_message: Message to show when no results are found
            
        Returns:
            An initialized LLM client instance
        """
        provider = config['general'].get('inference_provider', 'ollama')
        
        try:
            # Get the appropriate client class dynamically
            client_class = get_client_class(provider)
            
            # Create and return the client instance
            return client_class(
                config, 
                retriever, 
                reranker_service, 
                prompt_service, 
                no_results_message
            )
        except (ImportError, ValueError) as e:
            logging.error(f"Failed to create LLM client for provider {provider}: {str(e)}")
            raise 