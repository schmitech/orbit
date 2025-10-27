"""
Service-specific interfaces for AI services.

This package contains service-specific interfaces and implementations
for different AI service types (embeddings, inference, moderation, reranking).

Available Services:
    - EmbeddingService: Interface for embedding services
    - InferenceService: Interface for LLM inference services
    - ModerationService: Interface for content moderation services
    - RerankingService: Interface for document reranking services

Future Services:
    - VisionService: Vision service interface (Phase 5)
    - AudioService: Audio service interface (Phase 5)
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
    ModerationCategory,
    create_moderation_service
)

from .reranking_service import (
    RerankingService,
    RerankingResult,
    create_reranking_service
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
    'ModerationCategory',
    'create_moderation_service',

    # Reranking
    'RerankingService',
    'RerankingResult',
    'create_reranking_service',
]
