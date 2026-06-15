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


def _is_enabled(value) -> bool:
    """Helper to check if a value represents 'enabled'."""
    if value is True:
        return True
    if value is False:
        return False
    if isinstance(value, str):
        return value.lower() != 'false'
    return True  # Default to enabled


def _register_services(
    service_type: ServiceType,
    module_path: str,
    services: list,
    config: Dict[str, Any] = None,
    config_section: str = None,
    default_enabled: bool = True,
) -> None:
    """Import and register a list of (provider_key, class_name, display_name) tuples.

    If config_section is given and config is provided, providers whose
    enabled flag resolves to False are skipped before attempting the import.
    """
    cfg = config.get(config_section, {}) if config and config_section else {}
    for provider_key, class_name, display_name in services:
        if config and config_section:
            enabled = cfg.get(provider_key, {}).get('enabled', default_enabled)
            if not _is_enabled(enabled):
                logger.debug(f"Skipping {display_name} {service_type.value} service - disabled in config")
                continue
        try:
            module = __import__(module_path, fromlist=[class_name])
            AIServiceFactory.register_service(service_type, provider_key, getattr(module, class_name))
            logger.info(f"Registered {display_name} {service_type.value} service")
        except (ImportError, AttributeError) as e:
            logger.debug(f"Skipping {display_name} {service_type.value} service - missing dependencies: {e}")


def register_embedding_services() -> None:
    _register_services(ServiceType.EMBEDDING, 'ai_services.implementations.embedding', [
        ("openai", "OpenAIEmbeddingService", "OpenAI"),
        ("ollama", "OllamaEmbeddingService", "Ollama"),
        ("cohere", "CohereEmbeddingService", "Cohere"),
        ("mistral", "MistralEmbeddingService", "Mistral"),
        ("jina", "JinaEmbeddingService", "Jina"),
        ("llama_cpp", "LlamaCppEmbeddingService", "Llama.cpp"),
        ("openrouter", "OpenRouterEmbeddingService", "OpenRouter"),
        ("gemini", "GeminiEmbeddingService", "Gemini"),
        ("voyage", "VoyageEmbeddingService", "Voyage AI"),
    ])


def register_inference_services(config: Dict[str, Any] = None) -> None:
    """Register inference services. With config, only enabled providers are registered."""
    _register_services(ServiceType.INFERENCE, 'ai_services.implementations.inference', [
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
        ("ollama_remote", "OllamaRemoteInferenceService", "Ollama Remote"),
        ("bitnet", "BitNetInferenceService", "BitNet (1.58-bit)"),
        ("zai", "ZaiInferenceService", "Z.AI"),
        ("tensorrt", "TensorRTInferenceService", "TensorRT-LLM"),
        ("transformers", "TransformersInferenceService", "Transformers (Local)"),
        ("cerebras", "CerebrasInferenceService", "Cerebras"),
        ("deepinfra", "DeepInfraInferenceService", "DeepInfra"),
        ("lmstudio", "LMStudioInferenceService", "LM Studio"),
        ("moonshot", "MoonshotInferenceService", "Moonshot AI"),
        ("minimax", "MiniMaxInferenceService", "MiniMax"),
        ("nearai", "NearAIInferenceService", "NEAR AI Cloud"),
        ("nebius", "NebiusInferenceService", "Nebius AI Studio"),
        ("venice", "VeniceInferenceService", "Venice AI"),
        ("scaleway", "ScalewayInferenceService", "Scaleway"),
    ], config=config, config_section='inference', default_enabled=False)


def register_moderation_services() -> None:
    _register_services(ServiceType.MODERATION, 'ai_services.implementations.moderation', [
        ("openai", "OpenAIModerationService", "OpenAI"),
        ("anthropic", "AnthropicModerationService", "Anthropic"),
        ("ollama", "OllamaModerationService", "Ollama"),
    ])


def register_reranking_services(config: Dict[str, Any] = None) -> None:
    _register_services(ServiceType.RERANKING, 'ai_services.implementations.reranking', [
        ("ollama", "OllamaRerankingService", "Ollama"),
        ("cohere", "CohereRerankingService", "Cohere"),
        ("jina", "JinaRerankingService", "Jina AI"),
        ("openai", "OpenAIRerankingService", "OpenAI"),
        ("anthropic", "AnthropicRerankingService", "Anthropic"),
        ("voyage", "VoyageRerankingService", "Voyage AI"),
    ], config=config, config_section='rerankers', default_enabled=True)


def register_vision_services(config: Dict[str, Any] = None) -> None:
    # Default to False — if vision.yaml is not imported, no vision services should register
    _register_services(ServiceType.VISION, 'ai_services.implementations.vision', [
        ("openai", "OpenAIVisionService", "OpenAI"),
        ("gemini", "GeminiVisionService", "Gemini"),
        ("anthropic", "AnthropicVisionService", "Anthropic"),
        ("ollama", "OllamaVisionService", "Ollama"),
        ("ollama_cloud", "OllamaCloudVisionService", "Ollama Cloud"),
        ("vllm", "VLLMVisionService", "vLLM"),
        ("llama_cpp", "LlamaCppVisionService", "Llama.cpp"),
        ("cohere", "CohereVisionService", "Cohere"),
    ], config=config, config_section='visions', default_enabled=False)


def register_audio_services(config: Dict[str, Any] = None) -> None:
    """Register audio services. Both TTS and STT must be globally disabled to skip all."""
    if config:
        # Default to False — if tts.yaml/stt.yaml are not imported, no audio services should register
        tts_enabled = _is_enabled(config.get('tts', {}).get('enabled', False))
        stt_enabled = _is_enabled(config.get('stt', {}).get('enabled', False))
        if not tts_enabled and not stt_enabled:
            logger.info(
                "Both TTS and STT services are globally disabled - "
                "skipping all audio service registration."
            )
            return

    all_services = [
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
        ("xai", "XAIAudioService", "xAI (Grok)"),
    ]

    if config:
        tts_providers = config.get('tts_providers', {})
        stt_providers = config.get('stt_providers', {})
        # Provider is enabled if it appears in either TTS or STT config as enabled
        services = [
            (k, c, n) for k, c, n in all_services
            if _is_enabled(tts_providers.get(k, {}).get('enabled', True))
            or _is_enabled(stt_providers.get(k, {}).get('enabled', True))
        ]
    else:
        services = all_services

    _register_services(ServiceType.AUDIO, 'ai_services.implementations.audio', services)



def register_image_generation_services(config: Dict[str, Any] = None) -> None:
    if config and not _is_enabled(config.get('image', {}).get('enabled', False)):
        logger.info("Image generation is globally disabled - skipping registration.")
        return

    _register_services(ServiceType.IMAGE_GENERATION, 'ai_services.implementations.image', [
        ("openai", "OpenAIImageService", "OpenAI"),
        ("gemini", "GeminiImageService", "Gemini"),
        ("ollama", "OllamaImageService", "Ollama"),
        ("xai", "XAIImageService", "xAI (Grok)"),
    ], config=config, config_section='image_generation', default_enabled=False)


def register_video_generation_services(config: Dict[str, Any] = None) -> None:
    if config and not _is_enabled(config.get('video', {}).get('enabled', False)):
        logger.info("Video generation is globally disabled - skipping registration.")
        return

    _register_services(ServiceType.VIDEO_GENERATION, 'ai_services.implementations.video', [
        ("gemini", "GeminiVideoService", "Gemini"),
        ("xai", "XAIVideoService", "xAI (Grok)"),
    ], config=config, config_section='video_generation', default_enabled=False)


def register_all_services(config: Dict[str, Any] = None) -> None:
    """
    Register all available service implementations.

    Call this function at application startup to make all migrated
    services available via the AIServiceFactory.

    Args:
        config: Optional configuration dictionary. If provided, only enabled
                providers will be registered to save memory.
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
        register_image_generation_services(config)
        register_video_generation_services(config)
        register_audio_services(config)

        _services_registered = True

        # Log available services once registration completes
        available = AIServiceFactory.list_available_services()
        logger.info(f"Registered services: {available}")


def get_embedding_service_legacy(provider: str, config: Dict[str, Any]):
    """
    Legacy compatibility function for getting embedding services.

    Note:
        Prefer using AIServiceFactory.create_service() for new code.
    """
    from .services import create_embedding_service

    return create_embedding_service(provider, config)
