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
    """
    from .implementations import (
        OpenAIEmbeddingService,
        OllamaEmbeddingService,
        CohereEmbeddingService,
        MistralEmbeddingService,
        JinaEmbeddingService,
        LlamaCppEmbeddingService
    )

    # Register embedding services
    AIServiceFactory.register_service(
        ServiceType.EMBEDDING,
        "openai",
        OpenAIEmbeddingService
    )
    logger.info("Registered OpenAI embedding service")

    AIServiceFactory.register_service(
        ServiceType.EMBEDDING,
        "ollama",
        OllamaEmbeddingService
    )
    logger.info("Registered Ollama embedding service")

    AIServiceFactory.register_service(
        ServiceType.EMBEDDING,
        "cohere",
        CohereEmbeddingService
    )
    logger.info("Registered Cohere embedding service")

    AIServiceFactory.register_service(
        ServiceType.EMBEDDING,
        "mistral",
        MistralEmbeddingService
    )
    logger.info("Registered Mistral embedding service")

    AIServiceFactory.register_service(
        ServiceType.EMBEDDING,
        "jina",
        JinaEmbeddingService
    )
    logger.info("Registered Jina embedding service")

    AIServiceFactory.register_service(
        ServiceType.EMBEDDING,
        "llama_cpp",
        LlamaCppEmbeddingService
    )
    logger.info("Registered Llama.cpp embedding service")


def register_inference_services() -> None:
    """
    Register all inference service implementations with the factory.

    This makes them available for creation via AIServiceFactory.create_service()

    Currently includes:
    - OpenAI, Anthropic, Ollama (Phase 3 Week 1)
    - Groq, Mistral, DeepSeek, Fireworks, Perplexity,
      Together, OpenRouter, xAI (Phase 3 Extended - OpenAI-compatible)
    - AWS Bedrock, Azure OpenAI, Vertex AI, Gemini (Phase 3 Extended - Cloud)
    - Cohere, NVIDIA, Replicate, Watson, vLLM, Llama.cpp, Hugging Face,
      Ollama Cloud (Phase 3 Extended - Custom/Local)
    """
    from .implementations import (
        OpenAIInferenceService,
        AnthropicInferenceService,
        OllamaInferenceService,
        GroqInferenceService,
        MistralInferenceService,
        DeepSeekInferenceService,
        FireworksInferenceService,
        PerplexityInferenceService,
        TogetherInferenceService,
        OpenRouterInferenceService,
        XAIInferenceService,
        AWSBedrockInferenceService,
        AzureOpenAIInferenceService,
        VertexAIInferenceService,
        GeminiInferenceService,
        CohereInferenceService,
        NVIDIAInferenceService,
        ReplicateInferenceService,
        WatsonInferenceService,
        VLLMInferenceService,
        LlamaCppInferenceService,
        HuggingFaceInferenceService,
        OllamaCloudInferenceService,
    )

    # Core inference services (Phase 3 Week 1)
    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "openai",
        OpenAIInferenceService
    )
    logger.info("Registered OpenAI inference service")

    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "anthropic",
        AnthropicInferenceService
    )
    logger.info("Registered Anthropic inference service")

    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "ollama",
        OllamaInferenceService
    )
    logger.info("Registered Ollama inference service")

    # OpenAI-compatible inference services (Phase 3 Extended)
    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "groq",
        GroqInferenceService
    )
    logger.info("Registered Groq inference service")

    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "mistral",
        MistralInferenceService
    )
    logger.info("Registered Mistral inference service")

    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "deepseek",
        DeepSeekInferenceService
    )
    logger.info("Registered DeepSeek inference service")


    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "fireworks",
        FireworksInferenceService
    )
    logger.info("Registered Fireworks inference service")

    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "perplexity",
        PerplexityInferenceService
    )
    logger.info("Registered Perplexity inference service")

    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "together",
        TogetherInferenceService
    )
    logger.info("Registered Together inference service")

    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "openrouter",
        OpenRouterInferenceService
    )
    logger.info("Registered OpenRouter inference service")

    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "xai",
        XAIInferenceService
    )
    logger.info("Registered xAI (Grok) inference service")

    # Cloud provider inference services (Phase 3 Extended - Cloud Providers)
    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "aws",
        AWSBedrockInferenceService
    )
    logger.info("Registered AWS Bedrock inference service")

    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "azure",
        AzureOpenAIInferenceService
    )
    logger.info("Registered Azure OpenAI inference service")

    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "vertexai",
        VertexAIInferenceService
    )
    logger.info("Registered Vertex AI inference service")

    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "gemini",
        GeminiInferenceService
    )
    logger.info("Registered Gemini inference service")

    # Custom/Local inference services (Phase 3 Extended - Final 8 providers)
    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "cohere",
        CohereInferenceService
    )
    logger.info("Registered Cohere inference service")

    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "nvidia",
        NVIDIAInferenceService
    )
    logger.info("Registered NVIDIA NIM inference service")

    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "replicate",
        ReplicateInferenceService
    )
    logger.info("Registered Replicate inference service")

    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "watson",
        WatsonInferenceService
    )
    logger.info("Registered IBM Watson inference service")

    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "vllm",
        VLLMInferenceService
    )
    logger.info("Registered vLLM inference service")

    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "llama_cpp",
        LlamaCppInferenceService
    )
    logger.info("Registered Llama.cpp inference service")

    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "huggingface",
        HuggingFaceInferenceService
    )
    logger.info("Registered Hugging Face inference service")

    AIServiceFactory.register_service(
        ServiceType.INFERENCE,
        "ollama_cloud",
        OllamaCloudInferenceService
    )
    logger.info("Registered Ollama Cloud inference service")


def register_moderation_services() -> None:
    """
    Register all moderation service implementations with the factory.

    This makes them available for creation via AIServiceFactory.create_service()
    """
    from .implementations import (
        OpenAIModerationService,
        AnthropicModerationService,
        OllamaModerationService
    )

    # Register moderation services
    AIServiceFactory.register_service(
        ServiceType.MODERATION,
        "openai",
        OpenAIModerationService
    )
    logger.info("Registered OpenAI moderation service")

    AIServiceFactory.register_service(
        ServiceType.MODERATION,
        "anthropic",
        AnthropicModerationService
    )
    logger.info("Registered Anthropic moderation service")

    AIServiceFactory.register_service(
        ServiceType.MODERATION,
        "ollama",
        OllamaModerationService
    )
    logger.info("Registered Ollama moderation service")


def register_reranking_services() -> None:
    """
    Register all reranking service implementations with the factory.

    This makes them available for creation via AIServiceFactory.create_service()
    """
    from .implementations import (
        OllamaRerankingService,
    )

    # Register reranking services
    AIServiceFactory.register_service(
        ServiceType.RERANKING,
        "ollama",
        OllamaRerankingService
    )
    logger.info("Registered Ollama reranking service")


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
