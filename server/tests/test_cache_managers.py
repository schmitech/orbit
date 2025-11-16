"""
Unit tests for cache manager components.

Tests the specialized cache managers:
- AdapterCacheManager
- ProviderCacheManager
- EmbeddingCacheManager
- RerankerCacheManager
"""

import pytest
import asyncio
import sys
import os
from unittest.mock import Mock, MagicMock, AsyncMock, patch, PropertyMock
from concurrent.futures import ThreadPoolExecutor

# Add the server directory to the Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.cache.adapter_cache_manager import AdapterCacheManager
from services.cache.provider_cache_manager import ProviderCacheManager
from services.cache.embedding_cache_manager import EmbeddingCacheManager
from services.cache.reranker_cache_manager import RerankerCacheManager
from services.cache.vision_cache_manager import VisionCacheManager
from services.cache.audio_cache_manager import AudioCacheManager


class TestAdapterCacheManager:
    """Test AdapterCacheManager class"""

    def setup_method(self):
        """Setup test fixtures"""
        self.cache_manager = AdapterCacheManager()

    def test_init(self):
        """Test initialization"""
        assert self.cache_manager._cache == {}
        assert self.cache_manager._locks == {}
        assert self.cache_manager._initializing == set()

    def test_get_returns_none_when_not_cached(self):
        """Test get returns None when adapter not cached"""
        result = self.cache_manager.get("nonexistent")
        assert result is None

    def test_put_and_get(self):
        """Test putting and getting an adapter"""
        adapter = Mock()
        self.cache_manager.put("test_adapter", adapter)

        result = self.cache_manager.get("test_adapter")
        assert result is adapter

    def test_contains_false_when_not_cached(self):
        """Test contains returns False when not cached"""
        assert self.cache_manager.contains("nonexistent") is False

    def test_contains_true_when_cached(self):
        """Test contains returns True when cached"""
        self.cache_manager.put("test_adapter", Mock())
        assert self.cache_manager.contains("test_adapter") is True

    def test_get_cached_names_empty(self):
        """Test get_cached_names returns empty list when no adapters cached"""
        assert self.cache_manager.get_cached_names() == []

    def test_get_cached_names_with_adapters(self):
        """Test get_cached_names returns list of cached adapters"""
        self.cache_manager.put("adapter1", Mock())
        self.cache_manager.put("adapter2", Mock())

        names = self.cache_manager.get_cached_names()
        assert set(names) == {"adapter1", "adapter2"}

    def test_get_cache_size(self):
        """Test get_cache_size returns correct count"""
        assert self.cache_manager.get_cache_size() == 0

        self.cache_manager.put("adapter1", Mock())
        assert self.cache_manager.get_cache_size() == 1

        self.cache_manager.put("adapter2", Mock())
        assert self.cache_manager.get_cache_size() == 2

    def test_claim_initialization_success(self):
        """Test claiming initialization ownership"""
        result = self.cache_manager.claim_initialization("test_adapter")
        assert result is True
        assert "test_adapter" in self.cache_manager._initializing

    def test_claim_initialization_fails_when_already_initializing(self):
        """Test claiming initialization fails when already initializing"""
        self.cache_manager._initializing.add("test_adapter")
        result = self.cache_manager.claim_initialization("test_adapter")
        assert result is False

    def test_claim_initialization_fails_when_already_cached(self):
        """Test claiming initialization fails when already cached"""
        self.cache_manager.put("test_adapter", Mock())
        result = self.cache_manager.claim_initialization("test_adapter")
        assert result is False

    def test_release_initialization(self):
        """Test releasing initialization ownership"""
        self.cache_manager._initializing.add("test_adapter")
        self.cache_manager.release_initialization("test_adapter")
        assert "test_adapter" not in self.cache_manager._initializing

    def test_is_initializing(self):
        """Test checking if adapter is initializing"""
        assert self.cache_manager.is_initializing("test_adapter") is False

        self.cache_manager._initializing.add("test_adapter")
        assert self.cache_manager.is_initializing("test_adapter") is True

    def test_get_initializing_count(self):
        """Test getting count of initializing adapters"""
        assert self.cache_manager.get_initializing_count() == 0

        self.cache_manager._initializing.add("adapter1")
        assert self.cache_manager.get_initializing_count() == 1

        self.cache_manager._initializing.add("adapter2")
        assert self.cache_manager.get_initializing_count() == 2

    @pytest.mark.asyncio
    async def test_remove_returns_none_when_not_cached(self):
        """Test remove returns None when adapter not cached"""
        result = await self.cache_manager.remove("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_remove_returns_adapter_and_clears_cache(self):
        """Test remove returns adapter and clears from cache"""
        adapter = Mock(spec=[])  # No close method
        self.cache_manager.put("test_adapter", adapter)

        result = await self.cache_manager.remove("test_adapter")
        assert result is adapter
        assert self.cache_manager.contains("test_adapter") is False

    @pytest.mark.asyncio
    async def test_remove_calls_close_if_sync(self):
        """Test remove calls sync close method"""
        adapter = Mock()
        adapter.close = Mock()
        self.cache_manager.put("test_adapter", adapter)

        await self.cache_manager.remove("test_adapter")
        adapter.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_calls_close_if_async(self):
        """Test remove calls async close method"""
        adapter = Mock()
        adapter.close = AsyncMock()
        self.cache_manager.put("test_adapter", adapter)

        await self.cache_manager.remove("test_adapter")
        adapter.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clear_removes_all_adapters(self):
        """Test clear removes all adapters"""
        self.cache_manager.put("adapter1", Mock(spec=[]))
        self.cache_manager.put("adapter2", Mock(spec=[]))

        await self.cache_manager.clear()
        assert self.cache_manager.get_cache_size() == 0


class TestProviderCacheManager:
    """Test ProviderCacheManager class"""

    def setup_method(self):
        """Setup test fixtures"""
        self.config = {
            'general': {'verbose': False},
            'inference': {
                'openai': {'model': 'gpt-4'}
            }
        }
        self.thread_pool = ThreadPoolExecutor(max_workers=2)
        self.cache_manager = ProviderCacheManager(self.config, self.thread_pool)

    def teardown_method(self):
        """Cleanup"""
        self.thread_pool.shutdown(wait=False)

    def test_build_cache_key_without_model(self):
        """Test building cache key without model override"""
        key = self.cache_manager.build_cache_key("openai")
        assert key == "openai"

    def test_build_cache_key_with_model(self):
        """Test building cache key with model override"""
        key = self.cache_manager.build_cache_key("openai", "gpt-4-turbo")
        assert key == "openai:gpt-4-turbo"

    def test_get_returns_none_when_not_cached(self):
        """Test get returns None when provider not cached"""
        result = self.cache_manager.get("nonexistent")
        assert result is None

    def test_put_and_get(self):
        """Test putting and getting a provider"""
        provider = Mock()
        self.cache_manager.put("openai:gpt-4", provider)

        result = self.cache_manager.get("openai:gpt-4")
        assert result is provider

    def test_contains(self):
        """Test contains method"""
        assert self.cache_manager.contains("openai:gpt-4") is False

        self.cache_manager.put("openai:gpt-4", Mock())
        assert self.cache_manager.contains("openai:gpt-4") is True

    def test_get_cached_keys(self):
        """Test getting cached keys"""
        self.cache_manager.put("openai:gpt-4", Mock())
        self.cache_manager.put("anthropic:claude", Mock())

        keys = self.cache_manager.get_cached_keys()
        assert set(keys) == {"openai:gpt-4", "anthropic:claude"}

    def test_get_cache_size(self):
        """Test getting cache size"""
        assert self.cache_manager.get_cache_size() == 0

        self.cache_manager.put("openai:gpt-4", Mock())
        assert self.cache_manager.get_cache_size() == 1

    @pytest.mark.asyncio
    async def test_remove_returns_none_when_not_cached(self):
        """Test remove returns None when provider not cached"""
        result = await self.cache_manager.remove("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_remove_returns_provider_and_clears_cache(self):
        """Test remove returns provider and clears from cache"""
        provider = Mock(spec=[])
        self.cache_manager.put("openai:gpt-4", provider)

        result = await self.cache_manager.remove("openai:gpt-4")
        assert result is provider
        assert self.cache_manager.contains("openai:gpt-4") is False

    @pytest.mark.asyncio
    async def test_remove_by_prefix_exact_match(self):
        """Test remove_by_prefix with exact match"""
        self.cache_manager.put("openai", Mock(spec=[]))

        removed = await self.cache_manager.remove_by_prefix("openai")
        assert "openai" in removed
        assert self.cache_manager.contains("openai") is False

    @pytest.mark.asyncio
    async def test_remove_by_prefix_with_variants(self):
        """Test remove_by_prefix removes all variants"""
        self.cache_manager.put("openai", Mock(spec=[]))
        self.cache_manager.put("openai:gpt-4", Mock(spec=[]))
        self.cache_manager.put("openai:gpt-4-turbo", Mock(spec=[]))
        self.cache_manager.put("anthropic:claude", Mock(spec=[]))  # Should not be removed

        removed = await self.cache_manager.remove_by_prefix("openai")
        assert len(removed) == 3
        assert "openai" in removed
        assert "openai:gpt-4" in removed
        assert "openai:gpt-4-turbo" in removed
        assert self.cache_manager.contains("anthropic:claude") is True

    @pytest.mark.asyncio
    async def test_clear_removes_all_providers(self):
        """Test clear removes all providers"""
        self.cache_manager.put("openai:gpt-4", Mock(spec=[]))
        self.cache_manager.put("anthropic:claude", Mock(spec=[]))

        await self.cache_manager.clear()
        assert self.cache_manager.get_cache_size() == 0


class TestEmbeddingCacheManager:
    """Test EmbeddingCacheManager class"""

    def setup_method(self):
        """Setup test fixtures"""
        self.config = {
            'general': {'verbose': False},
            'embeddings': {
                'openai': {'model': 'text-embedding-3-small'},
                'ollama': {'model': 'nomic-embed-text'}
            }
        }
        self.thread_pool = ThreadPoolExecutor(max_workers=2)
        self.cache_manager = EmbeddingCacheManager(self.config, self.thread_pool)

    def teardown_method(self):
        """Cleanup"""
        self.thread_pool.shutdown(wait=False)

    def test_build_cache_key_with_model(self):
        """Test building cache key with model from config"""
        key = self.cache_manager.build_cache_key("openai")
        assert key == "openai:text-embedding-3-small"

    def test_build_cache_key_without_model(self):
        """Test building cache key when model not in config"""
        key = self.cache_manager.build_cache_key("nonexistent")
        assert key == "nonexistent"

    def test_get_and_put(self):
        """Test put and get operations"""
        service = Mock()
        self.cache_manager.put("openai:text-embedding-3-small", service)

        result = self.cache_manager.get("openai:text-embedding-3-small")
        assert result is service

    def test_contains(self):
        """Test contains method"""
        assert self.cache_manager.contains("key") is False

        self.cache_manager.put("key", Mock())
        assert self.cache_manager.contains("key") is True

    def test_get_cached_keys(self):
        """Test getting cached keys"""
        self.cache_manager.put("openai:model", Mock())
        self.cache_manager.put("ollama:model", Mock())

        keys = self.cache_manager.get_cached_keys()
        assert set(keys) == {"openai:model", "ollama:model"}

    @pytest.mark.asyncio
    async def test_remove(self):
        """Test remove operation"""
        service = Mock(spec=[])
        self.cache_manager.put("key", service)

        result = await self.cache_manager.remove("key")
        assert result is service
        assert self.cache_manager.contains("key") is False

    @pytest.mark.asyncio
    async def test_clear(self):
        """Test clear operation"""
        self.cache_manager.put("key1", Mock(spec=[]))
        self.cache_manager.put("key2", Mock(spec=[]))

        await self.cache_manager.clear()
        assert self.cache_manager.get_cache_size() == 0


class TestRerankerCacheManager:
    """Test RerankerCacheManager class"""

    def setup_method(self):
        """Setup test fixtures"""
        self.config = {
            'general': {'verbose': False},
            'rerankers': {
                'cohere': {'model': 'rerank-english-v3.0'},
                'flashrank': {'model': 'ms-marco-MiniLM-L-12-v2'}
            }
        }
        self.thread_pool = ThreadPoolExecutor(max_workers=2)
        self.cache_manager = RerankerCacheManager(self.config, self.thread_pool)

    def teardown_method(self):
        """Cleanup"""
        self.thread_pool.shutdown(wait=False)

    def test_build_cache_key_with_model(self):
        """Test building cache key with model from config"""
        key = self.cache_manager.build_cache_key("cohere")
        assert key == "cohere:rerank-english-v3.0"

    def test_build_cache_key_without_model(self):
        """Test building cache key when model not in config"""
        key = self.cache_manager.build_cache_key("nonexistent")
        assert key == "nonexistent"

    def test_get_and_put(self):
        """Test put and get operations"""
        service = Mock()
        self.cache_manager.put("cohere:rerank-english-v3.0", service)

        result = self.cache_manager.get("cohere:rerank-english-v3.0")
        assert result is service

    def test_contains(self):
        """Test contains method"""
        assert self.cache_manager.contains("key") is False

        self.cache_manager.put("key", Mock())
        assert self.cache_manager.contains("key") is True

    def test_get_cached_keys(self):
        """Test getting cached keys"""
        self.cache_manager.put("cohere:model", Mock())
        self.cache_manager.put("flashrank:model", Mock())

        keys = self.cache_manager.get_cached_keys()
        assert set(keys) == {"cohere:model", "flashrank:model"}

    @pytest.mark.asyncio
    async def test_remove(self):
        """Test remove operation"""
        service = Mock(spec=[])
        self.cache_manager.put("key", service)

        result = await self.cache_manager.remove("key")
        assert result is service
        assert self.cache_manager.contains("key") is False

    @pytest.mark.asyncio
    async def test_clear(self):
        """Test clear operation"""
        self.cache_manager.put("key1", Mock(spec=[]))
        self.cache_manager.put("key2", Mock(spec=[]))

        await self.cache_manager.clear()
        assert self.cache_manager.get_cache_size() == 0


class TestVisionCacheManager:
    """Test VisionCacheManager class"""

    def setup_method(self):
        """Setup test fixtures"""
        self.config = {
            'general': {'verbose': False},
            'vision': {
                'openai': {'model': 'gpt-4-vision-preview'},
                'gemini': {'model': 'gemini-pro-vision'}
            }
        }
        self.thread_pool = ThreadPoolExecutor(max_workers=2)
        self.cache_manager = VisionCacheManager(self.config, self.thread_pool)

    def teardown_method(self):
        """Cleanup"""
        self.thread_pool.shutdown(wait=False)

    def test_build_cache_key_with_model(self):
        """Test building cache key with model from config"""
        key = self.cache_manager.build_cache_key("openai")
        assert key == "openai:gpt-4-vision-preview"

    def test_build_cache_key_without_model(self):
        """Test building cache key when model not in config"""
        key = self.cache_manager.build_cache_key("nonexistent")
        assert key == "nonexistent"

    def test_get_and_put(self):
        """Test put and get operations"""
        service = Mock()
        self.cache_manager.put("openai:gpt-4-vision-preview", service)

        result = self.cache_manager.get("openai:gpt-4-vision-preview")
        assert result is service

    def test_contains(self):
        """Test contains method"""
        assert self.cache_manager.contains("key") is False

        self.cache_manager.put("key", Mock())
        assert self.cache_manager.contains("key") is True

    def test_get_cached_keys(self):
        """Test getting cached keys"""
        self.cache_manager.put("openai:model", Mock())
        self.cache_manager.put("gemini:model", Mock())

        keys = self.cache_manager.get_cached_keys()
        assert set(keys) == {"openai:model", "gemini:model"}

    def test_get_cache_size(self):
        """Test getting cache size"""
        assert self.cache_manager.get_cache_size() == 0

        self.cache_manager.put("key", Mock())
        assert self.cache_manager.get_cache_size() == 1

    @pytest.mark.asyncio
    async def test_remove(self):
        """Test remove operation"""
        service = Mock(spec=[])
        self.cache_manager.put("key", service)

        result = await self.cache_manager.remove("key")
        assert result is service
        assert self.cache_manager.contains("key") is False

    @pytest.mark.asyncio
    async def test_clear(self):
        """Test clear operation"""
        self.cache_manager.put("key1", Mock(spec=[]))
        self.cache_manager.put("key2", Mock(spec=[]))

        await self.cache_manager.clear()
        assert self.cache_manager.get_cache_size() == 0


class TestAudioCacheManager:
    """Test AudioCacheManager class"""

    def setup_method(self):
        """Setup test fixtures"""
        self.config = {
            'general': {'verbose': False},
            'sound': {
                'openai': {'tts_model': 'tts-1', 'stt_model': 'whisper-1'},
                'elevenlabs': {'tts_model': 'eleven_monolingual_v1'},
                'whisper': {'stt_model': 'base'}
            }
        }
        self.thread_pool = ThreadPoolExecutor(max_workers=2)
        self.cache_manager = AudioCacheManager(self.config, self.thread_pool)

    def teardown_method(self):
        """Cleanup"""
        self.thread_pool.shutdown(wait=False)

    def test_build_cache_key_with_tts_model(self):
        """Test building cache key with TTS model from config"""
        key = self.cache_manager.build_cache_key("openai")
        assert key == "openai:tts-1"

    def test_build_cache_key_with_stt_model_only(self):
        """Test building cache key with only STT model"""
        key = self.cache_manager.build_cache_key("whisper")
        assert key == "whisper:base"

    def test_build_cache_key_without_model(self):
        """Test building cache key when model not in config"""
        key = self.cache_manager.build_cache_key("nonexistent")
        assert key == "nonexistent"

    def test_get_and_put(self):
        """Test put and get operations"""
        service = Mock()
        self.cache_manager.put("openai:tts-1", service)

        result = self.cache_manager.get("openai:tts-1")
        assert result is service

    def test_contains(self):
        """Test contains method"""
        assert self.cache_manager.contains("key") is False

        self.cache_manager.put("key", Mock())
        assert self.cache_manager.contains("key") is True

    def test_get_cached_keys(self):
        """Test getting cached keys"""
        self.cache_manager.put("openai:model", Mock())
        self.cache_manager.put("elevenlabs:model", Mock())

        keys = self.cache_manager.get_cached_keys()
        assert set(keys) == {"openai:model", "elevenlabs:model"}

    def test_get_cache_size(self):
        """Test getting cache size"""
        assert self.cache_manager.get_cache_size() == 0

        self.cache_manager.put("key", Mock())
        assert self.cache_manager.get_cache_size() == 1

    @pytest.mark.asyncio
    async def test_remove(self):
        """Test remove operation"""
        service = Mock(spec=[])
        self.cache_manager.put("key", service)

        result = await self.cache_manager.remove("key")
        assert result is service
        assert self.cache_manager.contains("key") is False

    @pytest.mark.asyncio
    async def test_clear(self):
        """Test clear operation"""
        self.cache_manager.put("key1", Mock(spec=[]))
        self.cache_manager.put("key2", Mock(spec=[]))

        await self.cache_manager.clear()
        assert self.cache_manager.get_cache_size() == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
