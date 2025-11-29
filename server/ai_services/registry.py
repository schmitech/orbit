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


def register_inference_services(config: Dict[str, Any] = None) -> None:
    """
    Register all inference service implementations with the factory.

    This makes them available for creation via AIServiceFactory.create_service()
    Services with missing dependencies are skipped with a warning.

    If config is provided, only services marked as enabled in the inference config
    will be registered, reducing memory usage.

    Args:
        config: Optional configuration dictionary. If provided, only enabled providers
                will be registered based on config['inference'][provider]['enabled']
    """
    # Define all services to register with their import paths
    services = [
        ("openai", "OpenAIInferenceService", "OpenAI"),
        ("anthropic", "AnthropicInferenceService", "Anthropic"),
        ("ollama", "OllamaInferenceService", "Ollama"),
        ("groq", "GroqInferenceService", "Groq"),
        ("mistral", "MistralInferenceService", "Mistral"),
        ("deepseek", "DeepSeekInferenceService", "DeepSeek"),
        ("fireworks", "FireworksInferenceService", "Fireworks"),
        ("perplexity", "PerplexityInferenceService", "Perplexity"),
        ("together", "TogetherInferenceService", "Together"),
        ("openrouter", "OpenRouterInferenceService", "OpenRouter"),
        ("xai", "XAIInferenceService", "xAI (Grok)"),
        ("aws", "AWSBedrockInferenceService", "AWS Bedrock"),
        ("azure", "AzureOpenAIInferenceService", "Azure OpenAI"),
        ("vertexai", "VertexAIInferenceService", "Vertex AI"),
        ("gemini", "GeminiInferenceService", "Gemini"),
        ("cohere", "CohereInferenceService", "Cohere"),
        ("nvidia", "NVIDIAInferenceService", "NVIDIA NIM"),
        ("replicate", "ReplicateInferenceService", "Replicate"),
        ("watson", "WatsonInferenceService", "IBM Watson"),
        ("vllm", "VLLMInferenceService", "vLLM"),
        ("llama_cpp", "LlamaCppInferenceService", "Llama.cpp"),
        ("shimmy", "ShimmyInferenceService", "Shimmy"),
        ("huggingface", "HuggingFaceInferenceService", "Hugging Face"),
        ("ollama_cloud", "OllamaCloudInferenceService", "Ollama Cloud"),
        ("bitnet", "BitNetInferenceService", "BitNet (1.58-bit)"),
        ("zai", "ZaiInferenceService", "Z.AI"),
    ]

    # Get inference config if available
    inference_config = config.get('inference', {}) if config else {}

    for provider_key, class_name, display_name in services:
        # Check if provider is enabled in config (if config is provided)
        if config:
            provider_config = inference_config.get(provider_key, {})
            is_enabled = provider_config.get('enabled', False)

            if not is_enabled:
                logger.debug(f"Skipping {display_name} inference service - disabled in config")
                continue

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


def register_reranking_services(config: Dict[str, Any] = None) -> None:
    """
    Register all reranking service implementations with the factory.

    This makes them available for creation via AIServiceFactory.create_service()
    Services with missing dependencies are skipped with a warning.
    Services that are disabled in config are not registered.
    """
    # Define services to register with their import paths
    services = [
        ("ollama", "OllamaRerankingService", "Ollama"),
        ("cohere", "CohereRerankingService", "Cohere"),
        ("jina", "JinaRerankingService", "Jina AI"),
        ("openai", "OpenAIRerankingService", "OpenAI"),
        ("anthropic", "AnthropicRerankingService", "Anthropic"),
        ("voyage", "VoyageRerankingService", "Voyage AI"),
    ]

    for provider_key, class_name, display_name in services:
        # Check if provider is enabled in config
        if config:
            rerankers_config = config.get('rerankers', {})
            provider_config = rerankers_config.get(provider_key, {})
            enabled = provider_config.get('enabled', True)
            # Check for explicit False (boolean False or string 'false')
            if enabled is False or (isinstance(enabled, str) and enabled.lower() == 'false'):
                logger.info(
                    f"Skipping {display_name} reranking service - disabled in config"
                )
                continue
        
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


def register_vision_services(config: Dict[str, Any] = None) -> None:
    """
    Register all vision service implementations with the factory.

    This makes them available for creation via AIServiceFactory.create_service()
    Services with missing dependencies are skipped with a warning.
    Services that are disabled in config are not registered.

    Args:
        config: Optional configuration dictionary. If provided, only enabled providers
                will be registered based on config['vision'][provider]['enabled']
    """
    # Define services to register with their import paths
    services = [
        ("openai", "OpenAIVisionService", "OpenAI"),
        ("gemini", "GeminiVisionService", "Gemini"),
        ("anthropic", "AnthropicVisionService", "Anthropic"),
        ("ollama", "OllamaVisionService", "Ollama"),
        ("vllm", "VLLMVisionService", "vLLM"),
        ("llama_cpp", "LlamaCppVisionService", "Llama.cpp"),
        ("cohere", "CohereVisionService", "Cohere"),
    ]

    # Get vision config if available
    vision_config = config.get('vision', {}) if config else {}

    for provider_key, class_name, display_name in services:
        # Check if provider is enabled in config
        if config:
            provider_config = vision_config.get(provider_key, {})
            enabled = provider_config.get('enabled', True)
            if enabled is False or (isinstance(enabled, str) and enabled.lower() == 'false'):
                logger.debug(f"Skipping {display_name} vision service - disabled in config")
                continue
        
        try:
            # Lazy import - only import what we can
            module = __import__('ai_services.implementations', fromlist=[class_name])
            service_class = getattr(module, class_name)

            AIServiceFactory.register_service(
                ServiceType.VISION,
                provider_key,
                service_class
            )
            logger.info(f"Registered {display_name} vision service")
        except (ImportError, AttributeError) as e:
            logger.debug(
                f"Skipping {display_name} vision service - missing dependencies: {e}"
            )


def register_audio_services(config: Dict[str, Any] = None) -> None:
    """
    Register all audio service implementations with the factory.

    This makes them available for creation via AIServiceFactory.create_service()
    Services with missing dependencies are skipped with a warning.
    Services that are disabled in config are not registered.

    Args:
        config: Optional configuration dictionary. If provided, only enabled providers
                will be registered based on config['sound']['enabled'] and config['sounds'][provider]['enabled']
    """
    # Check global sound.enabled flag first
    if config:
        sound_config = config.get('sound', {})
        sound_enabled = sound_config.get('enabled', True)

        # If sound is globally disabled, skip all audio service registration
        if sound_enabled is False or (isinstance(sound_enabled, str) and sound_enabled.lower() == 'false'):
            logger.info(
                "Sound services are globally disabled (sound.enabled: false) - "
                "skipping all audio service registration. "
                "TTS and STT functionality will not be available. "
                "Adapters with audio_provider configured will load but audio features will be inactive."
            )
            return

    # Define services to register with their import paths
    services = [
        ("openai", "OpenAIAudioService", "OpenAI"),
        ("google", "GoogleAudioService", "Google"),
        ("gemini", "GeminiAudioService", "Gemini"),
        ("anthropic", "AnthropicAudioService", "Anthropic"),
        ("ollama", "OllamaAudioService", "Ollama"),
        ("cohere", "CohereAudioService", "Cohere"),
        ("elevenlabs", "ElevenLabsAudioService", "ElevenLabs"),
        ("whisper", "WhisperAudioService", "Whisper (Local)"),
        ("vllm", "VLLMAudioService", "vLLM"),
        ("coqui", "CoquiAudioService", "Coqui TTS (Local)"),
    ]

    # Get sounds config if available (plural form, like 'visions')
    sounds_config = config.get('sounds', {}) if config else {}

    for provider_key, class_name, display_name in services:
        # Check if provider is enabled in config
        if config:
            provider_config = sounds_config.get(provider_key, {})
            enabled = provider_config.get('enabled', True)
            if enabled is False or (isinstance(enabled, str) and enabled.lower() == 'false'):
                logger.debug(f"Skipping {display_name} audio service - disabled in config")
                continue
        
        try:
            # Lazy import - only import what we can
            module = __import__('ai_services.implementations', fromlist=[class_name])
            service_class = getattr(module, class_name)

            AIServiceFactory.register_service(
                ServiceType.AUDIO,
                provider_key,
                service_class
            )
            logger.info(f"Registered {display_name} audio service")
        except (ImportError, AttributeError) as e:
            logger.debug(
                f"Skipping {display_name} audio service - missing dependencies: {e}"
            )


def register_all_services(config: Dict[str, Any] = None) -> None:
    """
    Register all available service implementations.

    Call this function at application startup to make all migrated
    services available via the AIServiceFactory.

    Args:
        config: Optional configuration dictionary. If provided, only enabled
                inference providers will be registered to save memory.

    Example:
        >>> from ai_services.registry import register_all_services
        >>> register_all_services(config)
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
        register_inference_services(config)
        register_moderation_services()
        register_reranking_services(config)
        register_vision_services(config)
        register_audio_services(config)

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
