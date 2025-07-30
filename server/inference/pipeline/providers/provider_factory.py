"""
Provider Factory for Pipeline Architecture

This module provides a factory for creating clean LLM providers
based on configuration with lazy loading to avoid import errors.
"""

import logging
import importlib
from typing import Dict, Any, Type, Optional
from .llm_provider import LLMProvider

class ProviderFactory:
    """
    Factory for creating clean LLM providers with lazy loading.
    
    This factory creates provider instances based on configuration
    without any legacy compatibility layers. Providers are loaded
    only when needed to avoid import errors for uninstalled packages.
    """
    
    # Provider mapping with module paths for lazy loading
    _provider_modules = {
        'openai': ('openai_provider', 'OpenAIProvider'),
        'anthropic': ('anthropic_provider', 'AnthropicProvider'),
        'ollama': ('ollama_provider', 'OllamaProvider'),
        'aws': ('aws_provider', 'AWSBedrockProvider'),
        'groq': ('groq_provider', 'GroqProvider'),
        'gemini': ('gemini_provider', 'GeminiProvider'),
        'mistral': ('mistral_provider', 'MistralProvider'),
        'cohere': ('cohere_provider', 'CohereProvider'),
        'deepseek': ('deepseek_provider', 'DeepSeekProvider'),
        'llama_cpp': ('llama_cpp_provider', 'LlamaCppProvider'),
        'together': ('together_provider', 'TogetherProvider'),
        'vllm': ('vllm_provider', 'VLLMProvider'),
        'openrouter': ('openrouter_provider', 'OpenRouterProvider'),
        'xai': ('xai_provider', 'XAIProvider'),
        'watson': ('watson_provider', 'WatsonProvider'),
        'vertex': ('vertex_ai_provider', 'VertexAIProvider'),
        'huggingface': ('huggingface_provider', 'HuggingFaceProvider'),
        'azure': ('azure_provider', 'AzureProvider'),
    }
    
    # Cache for loaded provider classes
    _provider_cache: Dict[str, Type[LLMProvider]] = {}
    
    @classmethod
    def _load_provider_class(cls, provider_name: str) -> Optional[Type[LLMProvider]]:
        """
        Lazily load a provider class by name.
        
        Args:
            provider_name: Name of the provider to load
            
        Returns:
            Provider class if successfully loaded, None if import fails
        """
        if provider_name not in cls._provider_modules:
            return None
            
        # Check cache first
        if provider_name in cls._provider_cache:
            return cls._provider_cache[provider_name]
        
        module_name, class_name = cls._provider_modules[provider_name]
        
        try:
            # Import the module dynamically
            # Try different import strategies
            try:
                # First try relative import
                module = importlib.import_module(f'.{module_name}', package='inference.pipeline.providers')
            except ImportError:
                try:
                    # Try absolute import without 'server' prefix
                    module = importlib.import_module(f'inference.pipeline.providers.{module_name}')
                except ImportError:
                    # Fallback to absolute import with 'server' prefix
                    module = importlib.import_module(f'server.inference.pipeline.providers.{module_name}')
            
            provider_class = getattr(module, class_name)
            
            # Cache the loaded class
            cls._provider_cache[provider_name] = provider_class
            
            logging.getLogger(__name__).debug(f"Successfully loaded provider: {provider_name}")
            return provider_class
            
        except ImportError as e:
            logging.getLogger(__name__).warning(
                f"Failed to import provider '{provider_name}': {e}. "
                f"This provider may not be installed. Install the required dependencies "
                f"or use a different provider."
            )
            return None
        except AttributeError as e:
            logging.getLogger(__name__).error(
                f"Provider class '{class_name}' not found in module '{module_name}': {e}"
            )
            return None
        except Exception as e:
            logging.getLogger(__name__).error(
                f"Unexpected error loading provider '{provider_name}': {e}"
            )
            return None
    
    @classmethod
    def create_provider(cls, config: Dict[str, Any]) -> LLMProvider:
        """
        Create an LLM provider based on configuration.
        
        Args:
            config: Application configuration dictionary
            
        Returns:
            An initialized LLM provider instance
            
        Raises:
            ValueError: If the provider is not supported or cannot be loaded
        """
        provider_name = config['general'].get('inference_provider', 'openai')
        
        if provider_name not in cls._provider_modules:
            supported = ', '.join(cls._provider_modules.keys())
            raise ValueError(f"Unsupported provider '{provider_name}'. Supported providers: {supported}")
        
        provider_class = cls._load_provider_class(provider_name)
        
        if provider_class is None:
            supported = ', '.join(cls._provider_modules.keys())
            raise ValueError(
                f"Provider '{provider_name}' could not be loaded. "
                f"This may be due to missing dependencies. "
                f"Supported providers: {supported}"
            )
        
        provider = provider_class(config)
        
        logging.getLogger(__name__).info(f"Created {provider_name} provider")
        return provider
    
    @classmethod
    def register_provider(cls, name: str, module_name: str, class_name: str) -> None:
        """
        Register a new provider for lazy loading.
        
        Args:
            name: Provider name
            module_name: Module name (without package prefix)
            class_name: Provider class name
        """
        cls._provider_modules[name] = (module_name, class_name)
        # Clear cache entry if it exists
        cls._provider_cache.pop(name, None)
        logging.getLogger(__name__).info(f"Registered provider: {name}")
    
    @classmethod
    def list_providers(cls) -> list:
        """
        List all available providers.
        
        Returns:
            List of provider names
        """
        return list(cls._provider_modules.keys())
    
    @classmethod
    def list_available_providers(cls) -> list:
        """
        List providers that can be successfully loaded.
        
        Returns:
            List of provider names that can be imported
        """
        available = []
        for provider_name in cls._provider_modules:
            if cls._load_provider_class(provider_name) is not None:
                available.append(provider_name)
        return available 