"""
Cache management components for the Dynamic Adapter Manager.

This package provides specialized cache managers for different service types:
- AdapterCacheManager: Manages adapter instances
- ProviderCacheManager: Manages inference provider instances
- EmbeddingCacheManager: Manages embedding service instances
- RerankerCacheManager: Manages reranker service instances
- VisionCacheManager: Manages vision service instances
- AudioCacheManager: Manages audio service instances (TTS/STT)
"""

from .adapter_cache_manager import AdapterCacheManager
from .provider_cache_manager import ProviderCacheManager
from .embedding_cache_manager import EmbeddingCacheManager
from .reranker_cache_manager import RerankerCacheManager
from .vision_cache_manager import VisionCacheManager
from .audio_cache_manager import AudioCacheManager

__all__ = [
    "AdapterCacheManager",
    "ProviderCacheManager",
    "EmbeddingCacheManager",
    "RerankerCacheManager",
    "VisionCacheManager",
    "AudioCacheManager",
]
