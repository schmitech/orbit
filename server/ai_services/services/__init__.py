"""
Service-specific interfaces for AI services.

This package contains service-specific interfaces and implementations
for different AI service types (embeddings, inference, moderation, reranking, vision, audio, speech-to-speech).

Available Services:
    - EmbeddingService: Interface for embedding services
    - InferenceService: Interface for LLM inference services
    - ModerationService: Interface for content moderation services
    - RerankingService: Interface for document reranking services
    - VisionService: Interface for vision services
    - AudioService: Interface for audio services (TTS and STT)
    - SpeechToSpeechService: Interface for full-duplex speech-to-speech services (PersonaPlex)
"""

from .embedding_service import (
    EmbeddingService,
    EmbeddingResult,
    create_embedding_service
)

from .inference_service import (
    InferenceService,
    InferenceResult,
    create_inference_service
)

from .moderation_service import (
    ModerationService,
    ModerationResult,
    create_moderation_service
)

from .reranking_service import (
    RerankingService,
    RerankingResult,
    create_reranking_service
)

from .vision_service import (
    VisionService,
    VisionResult,
    create_vision_service
)

from .audio_service import (
    AudioService,
    AudioResult,
    create_audio_service
)

from .speech_to_speech_service import (
    SpeechToSpeechService,
    SpeechToSpeechResult,
    create_speech_to_speech_service
)

__all__ = [
    # Embedding
    'EmbeddingService',
    'EmbeddingResult',
    'create_embedding_service',

    # Inference
    'InferenceService',
    'InferenceResult',
    'create_inference_service',

    # Moderation
    'ModerationService',
    'ModerationResult',
    'create_moderation_service',

    # Reranking
    'RerankingService',
    'RerankingResult',
    'create_reranking_service',

    # Vision
    'VisionService',
    'VisionResult',
    'create_vision_service',

    # Audio
    'AudioService',
    'AudioResult',
    'create_audio_service',

    # Speech-to-Speech
    'SpeechToSpeechService',
    'SpeechToSpeechResult',
    'create_speech_to_speech_service',
]
