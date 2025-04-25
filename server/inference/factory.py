"""
LLM Client Factory

This module provides a factory class for creating LLM clients based on the selected inference provider.
"""

import logging
from typing import Dict, Any, Optional

from .base_llm_client import BaseLLMClient
from .clients.ollama_client import OllamaClient
from .clients.vllm_client import QAVLLMClient
from .clients.llama_cpp_client import QALlamaCppClient

class LLMClientFactory:
    """Factory for creating LLM clients based on the selected inference provider."""
    
    @staticmethod
    def create_llm_client(
        config: Dict[str, Any], 
        retriever: Any, 
        guardrail_service: Any = None,
        reranker_service: Any = None,
        prompt_service: Any = None,
        no_results_message: str = ""
    ) -> BaseLLMClient:
        """
        Create an LLM client based on the selected inference provider.
        
        Args:
            config: Application configuration dictionary
            retriever: The retriever to use for document lookup
            guardrail_service: Optional service for content safety checks
            reranker_service: Optional service for reranking results
            prompt_service: Optional service for system prompts
            no_results_message: Message to show when no results are found
            
        Returns:
            An initialized LLM client instance
        """
        provider = config['general'].get('inference_provider', 'ollama')
        
        if provider == 'ollama':
            return OllamaClient(
                config, 
                retriever, 
                guardrail_service, 
                reranker_service, 
                prompt_service, 
                no_results_message
            )
        elif provider == 'vllm':
            return QAVLLMClient(
                config, 
                retriever, 
                guardrail_service, 
                reranker_service, 
                prompt_service, 
                no_results_message
            )
        elif provider == 'llama_cpp':
            return QALlamaCppClient(
                config, 
                retriever, 
                guardrail_service, 
                reranker_service, 
                prompt_service, 
                no_results_message
            )
        else:
            logging.warning(f"Unknown inference provider: {provider}, falling back to Ollama")
            return OllamaClient(
                config, 
                retriever, 
                guardrail_service, 
                reranker_service, 
                prompt_service, 
                no_results_message
            ) 