"""
Provider Factory for Pipeline Architecture

This module provides a factory for creating clean LLM providers
based on configuration.
"""

import logging
from typing import Dict, Any
from .llm_provider import LLMProvider
from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider
from .ollama_provider import OllamaProvider
from .aws_provider import AWSBedrockProvider
from .groq_provider import GroqProvider
from .gemini_provider import GeminiProvider
from .mistral_provider import MistralProvider
from .cohere_provider import CohereProvider
from .deepseek_provider import DeepSeekProvider
from .llama_cpp_provider import LlamaCppProvider
from .together_provider import TogetherProvider
from .vllm_provider import VLLMProvider
from .openrouter_provider import OpenRouterProvider
from .xai_provider import XAIProvider
from .watson_provider import WatsonProvider
from .vertex_ai_provider import VertexAIProvider
from .huggingface_provider import HuggingFaceProvider
from .azure_provider import AzureProvider

class ProviderFactory:
    """
    Factory for creating clean LLM providers.
    
    This factory creates provider instances based on configuration
    without any legacy compatibility layers.
    """
    
    _providers = {
        'openai': OpenAIProvider,
        'anthropic': AnthropicProvider,
        'ollama': OllamaProvider,
        'aws': AWSBedrockProvider,
        'groq': GroqProvider,
        'gemini': GeminiProvider,
        'mistral': MistralProvider,
        'cohere': CohereProvider,
        'deepseek': DeepSeekProvider,
        'llama_cpp': LlamaCppProvider,
        'together': TogetherProvider,
        'vllm': VLLMProvider,
        'openrouter': OpenRouterProvider,
        'xai': XAIProvider,
        'watson': WatsonProvider,
        'vertex': VertexAIProvider,
        'huggingface': HuggingFaceProvider,
        'azure': AzureProvider,
    }
    
    @classmethod
    def create_provider(cls, config: Dict[str, Any]) -> LLMProvider:
        """
        Create an LLM provider based on configuration.
        
        Args:
            config: Application configuration dictionary
            
        Returns:
            An initialized LLM provider instance
            
        Raises:
            ValueError: If the provider is not supported
        """
        provider_name = config['general'].get('inference_provider', 'openai')
        
        if provider_name not in cls._providers:
            supported = ', '.join(cls._providers.keys())
            raise ValueError(f"Unsupported provider '{provider_name}'. Supported providers: {supported}")
        
        provider_class = cls._providers[provider_name]
        provider = provider_class(config)
        
        logging.getLogger(__name__).info(f"Created {provider_name} provider")
        return provider
    
    @classmethod
    def register_provider(cls, name: str, provider_class: type) -> None:
        """
        Register a new provider class.
        
        Args:
            name: Provider name
            provider_class: Provider class that implements LLMProvider
        """
        cls._providers[name] = provider_class
        logging.getLogger(__name__).info(f"Registered provider: {name}")
    
    @classmethod
    def list_providers(cls) -> list:
        """
        List all available providers.
        
        Returns:
            List of provider names
        """
        return list(cls._providers.keys()) 