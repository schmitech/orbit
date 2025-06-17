"""
Client implementations for various LLM providers.

This package contains client implementations for different LLM providers.
"""

def get_client_class(provider: str):
    """
    Dynamically import and return the appropriate client class for the given provider.
    
    Args:
        provider: The name of the provider (e.g., 'ollama', 'openai', etc.)
        
    Returns:
        The client class for the specified provider
        
    Raises:
        ImportError: If the provider's module cannot be imported
        ValueError: If the provider is not supported
    """
    try:
        if provider == 'ollama':
            from .ollama import OllamaClient
            return OllamaClient
        elif provider == 'vllm':
            from .vllm import QAVLLMClient
            return QAVLLMClient
        elif provider == 'llama_cpp':
            from .llama_cpp import QALlamaCppClient
            return QALlamaCppClient
        elif provider == 'openai':
            from .openai import OpenAIClient
            return OpenAIClient
        elif provider == 'gemini':
            from .gemini import GeminiClient
            return GeminiClient
        elif provider == 'groq':
            from .groq import GroqClient
            return GroqClient
        elif provider == 'deepseek':
            from .deepseek import DeepSeekClient
            return DeepSeekClient
        elif provider == 'vertex':
            from .vertex_ai import VertexAIClient
            return VertexAIClient
        elif provider == 'mistral':
            from .mistral import MistralClient
            return MistralClient
        elif provider == 'anthropic':
            from .anthropic import AnthropicClient
            return AnthropicClient
        elif provider == 'together':
            from .together import TogetherAIClient
            return TogetherAIClient
        elif provider == 'xai':
            from .xai import XAIClient
            return XAIClient
        elif provider == 'aws':
            from .aws import AWSBedrockClient
            return AWSBedrockClient
        elif provider == 'azure':
            from .azure import AzureOpenAIClient
            return AzureOpenAIClient
        elif provider == 'openrouter':
            from .openrouter import OpenRouterClient
            return OpenRouterClient
        elif provider == 'huggingface':
            from .hf import HuggingFaceClient
            return HuggingFaceClient
        elif provider == 'cohere':
            from .cohere import CohereClient
            return CohereClient
        else:
            raise ValueError(f"Unsupported provider: {provider}")
    except ImportError as e:
        raise ImportError(f"Failed to import {provider} client: {str(e)}")

__all__ = ["get_client_class"] 