"""
Service registration module for AI services.

This module handles the registration of all migrated service implementations
with the AIServiceFactory, enabling them to be created via the factory pattern.

Call register_all_services() at application startup to register all available services.
"""

import logging
import threading
import sys
from typing import Dict, Any

from .factory import AIServiceFactory
from .base import ServiceType

logger = logging.getLogger(__name__)


_registry_lock = threading.Lock()
_services_registered = False

# Ensure module has consistent identity regardless of import path
sys.modules.setdefault('ai_services.registry', sys.modules[__name__])
sys.modules.setdefault('server.ai_services.registry', sys.modules[__name__])


def register_embedding_services() -> None:
    """
    Register all embedding service implementations with the factory.

    This makes them available for creation via AIServiceFactory.create_service()
    Services with missing dependencies are skipped with a warning.
    """
    # Define services to register with their import paths
    services = [
        ("openai", "OpenAIEmbeddingService", "OpenAI"),
        ("ollama", "OllamaEmbeddingService", "Ollama"),
        ("cohere", "CohereEmbeddingService", "Cohere"),
        ("mistral", "MistralEmbeddingService", "Mistral"),
        ("jina", "JinaEmbeddingService", "Jina"),
        ("llama_cpp", "LlamaCppEmbeddingService", "Llama.cpp"),
    ]

    for provider_key, class_name, display_name in services:
        try:
            # Lazy import - only import what we can
            module = __import__('ai_services.implementations', fromlist=[class_name])
            service_class = getattr(module, class_name)

            AIServiceFactory.register_service(
                ServiceType.EMBEDDING,
                provider_key,
                service_class
            )
            logger.info(f"Registered {display_name} embedding service")
        except (ImportError, AttributeError) as e:
            logger.debug(
                f"Skipping {display_name} embedding service - missing dependencies: {e}"
            )


def register_inference_services() -> None:
    """
    Register all inference service implementations with the factory.

    This makes them available for creation via AIServiceFactory.create_service()
    Services with missing dependencies are skipped with a warning.

    Currently includes:
    - OpenAI, Anthropic, Ollama (Phase 3 Week 1)
    - Groq, Mistral, DeepSeek, Fireworks, Perplexity,
      Together, OpenRouter, xAI (Phase 3 Extended - OpenAI-compatible)
    - AWS Bedrock, Azure OpenAI, Vertex AI, Gemini (Phase 3 Extended - Cloud)
    - Cohere, NVIDIA, Replicate, Watson, vLLM, Llama.cpp, Hugging Face,
      Ollama Cloud (Phase 3 Extended - Custom/Local)
    """
    # Define all services to register with their import paths
    services = [
        # Core inference services (Phase 3 Week 1)
        ("openai", "OpenAIInferenceService", "OpenAI"),
        ("anthropic", "AnthropicInferenceService", "Anthropic"),
        ("ollama", "OllamaInferenceService", "Ollama"),

        # OpenAI-compatible inference services (Phase 3 Extended)
        ("groq", "GroqInferenceService", "Groq"),
        ("mistral", "MistralInferenceService", "Mistral"),
        ("deepseek", "DeepSeekInferenceService", "DeepSeek"),
        ("fireworks", "FireworksInferenceService", "Fireworks"),
        ("perplexity", "PerplexityInferenceService", "Perplexity"),
        ("together", "TogetherInferenceService", "Together"),
        ("openrouter", "OpenRouterInferenceService", "OpenRouter"),
        ("xai", "XAIInferenceService", "xAI (Grok)"),

        # Cloud provider inference services (Phase 3 Extended - Cloud Providers)
        ("aws", "AWSBedrockInferenceService", "AWS Bedrock"),
        ("azure", "AzureOpenAIInferenceService", "Azure OpenAI"),
        ("vertexai", "VertexAIInferenceService", "Vertex AI"),
        ("gemini", "GeminiInferenceService", "Gemini"),

        # Custom/Local inference services (Phase 3 Extended - Final 8 providers)
        ("cohere", "CohereInferenceService", "Cohere"),
        ("nvidia", "NVIDIAInferenceService", "NVIDIA NIM"),
        ("replicate", "ReplicateInferenceService", "Replicate"),
        ("watson", "WatsonInferenceService", "IBM Watson"),
        ("vllm", "VLLMInferenceService", "vLLM"),
        ("llama_cpp", "LlamaCppInferenceService", "Llama.cpp"),
        ("huggingface", "HuggingFaceInferenceService", "Hugging Face"),
        ("ollama_cloud", "OllamaCloudInferenceService", "Ollama Cloud"),
        ("bitnet", "BitNetInferenceService", "BitNet (1.58-bit)"),
    ]

    for provider_key, class_name, display_name in services:
        try:
            # Lazy import - only import what we can
            module = __import__('ai_services.implementations', fromlist=[class_name])
            service_class = getattr(module, class_name)

            AIServiceFactory.register_service(
                ServiceType.INFERENCE,
                provider_key,
                service_class
            )
            logger.info(f"Registered {display_name} inference service")
        except (ImportError, AttributeError) as e:
            logger.debug(
                f"Skipping {display_name} inference service - missing dependencies: {e}"
            )


def register_moderation_services() -> None:
    """
    Register all moderation service implementations with the factory.

    This makes them available for creation via AIServiceFactory.create_service()
    Services with missing dependencies are skipped with a warning.
    """
    # Define services to register with their import paths
    services = [
        ("openai", "OpenAIModerationService", "OpenAI"),
        ("anthropic", "AnthropicModerationService", "Anthropic"),
        ("ollama", "OllamaModerationService", "Ollama"),
    ]

    for provider_key, class_name, display_name in services:
        try:
            # Lazy import - only import what we can
            module = __import__('ai_services.implementations', fromlist=[class_name])
            service_class = getattr(module, class_name)

            AIServiceFactory.register_service(
                ServiceType.MODERATION,
                provider_key,
                service_class
            )
            logger.info(f"Registered {display_name} moderation service")
        except (ImportError, AttributeError) as e:
            logger.debug(
                f"Skipping {display_name} moderation service - missing dependencies: {e}"
            )


def register_reranking_services() -> None:
    """
    Register all reranking service implementations with the factory.

    This makes them available for creation via AIServiceFactory.create_service()
    Services with missing dependencies are skipped with a warning.
    """
    # Define services to register with their import paths
    services = [
        ("ollama", "OllamaRerankingService", "Ollama"),
    ]

    for provider_key, class_name, display_name in services:
        try:
            # Lazy import - only import what we can
            module = __import__('ai_services.implementations', fromlist=[class_name])
            service_class = getattr(module, class_name)

            AIServiceFactory.register_service(
                ServiceType.RERANKING,
                provider_key,
                service_class
            )
            logger.info(f"Registered {display_name} reranking service")
        except (ImportError, AttributeError) as e:
            logger.debug(
                f"Skipping {display_name} reranking service - missing dependencies: {e}"
            )


def register_all_services() -> None:
    """
    Register all available service implementations.

    Call this function at application startup to make all migrated
    services available via the AIServiceFactory.

    Example:
        >>> from ai_services.registry import register_all_services
        >>> register_all_services()
        >>> # Now services can be created via factory
        >>> service = AIServiceFactory.create_service(
        ...     ServiceType.EMBEDDING,
        ...     "openai",
        ...     config
        ... )
    """
    global _services_registered

    # Fast path without locking for already-registered case
    if _services_registered:
        return

    with _registry_lock:
        if _services_registered:
            return

        logger.info("Registering all AI services...")

        register_embedding_services()
        register_inference_services()
        register_moderation_services()
        register_reranking_services()

        _services_registered = True

        # Log available services once registration completes
        available = AIServiceFactory.list_available_services()
        logger.info(f"Registered services: {available}")


def get_embedding_service_legacy(provider: str, config: Dict[str, Any]):
    """
    Legacy compatibility function for getting embedding services.

    This function provides backward compatibility with the old factory pattern.
    It uses the new unified architecture under the hood.

    Args:
        provider: Provider name (e.g., 'openai', 'ollama')
        config: Configuration dictionary

    Returns:
        Embedding service instance

    Example:
        >>> # Old way (still works)
        >>> service = get_embedding_service_legacy('openai', config)
        >>> await service.initialize()

    Note:
        Prefer using AIServiceFactory.create_service() for new code.
    """
    from .services import create_embedding_service

    return create_embedding_service(provider, config)
