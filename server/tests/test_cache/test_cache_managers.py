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
from unittest.mock import Mock, AsyncMock
from concurrent.futures import ThreadPoolExecutor

# Add the server directory to the Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from services.cache.adapter_cache_manager import AdapterCacheManager
from services.cache.provider_cache_manager import ProviderCacheManager
from services.cache.embedding_cache_manager import EmbeddingCacheManager
from services.cache.reranker_cache_manager import RerankerCacheManager
from services.cache.vision_cache_manager import VisionCacheManager
from services.cache.audio_cache_manager import AudioCacheManager
from services.cache.image_cache_manager import ImageGenerationCacheManager
from services.cache.video_cache_manager import VideoGenerationCacheManager
from services.cache.service_cache_manager import ServiceCacheManager


class TestAdapterCacheManager:
    """Test AdapterCacheManager class"""

    def setup_method(self):
        """Setup test fixtures"""
        self.cache_manager = AdapterCacheManager()

    def test_init(self):
        """Test initialization"""
        assert self.cache_manager._cache == {}
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
            'general': {},
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
            'general': {},
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
    async def test_remove_without_closing_service(self):
        """Test remove can evict a shared service without closing it."""
        service = AsyncMock()
        self.cache_manager.put("key", service)

        result = await self.cache_manager.remove("key", close_service=False)

        assert result is service
        assert self.cache_manager.contains("key") is False
        service.close.assert_not_called()

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
            'general': {},
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
            'general': {},
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
            'general': {},
            'tts_providers': {
                'openai': {'tts_model': 'tts-1'},
                'elevenlabs': {'tts_model': 'eleven_monolingual_v1'}
            },
            'stt_providers': {
                'openai': {'stt_model': 'whisper-1'},
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

    def test_is_disabled_handles_boolean_and_string_false(self):
        """Test enabled-flag parsing for disabled audio sections."""
        assert AudioCacheManager._is_disabled({'enabled': False}) is True
        assert AudioCacheManager._is_disabled({'enabled': 'false'}) is True
        assert AudioCacheManager._is_disabled({'enabled': 'FALSE'}) is True
        assert AudioCacheManager._is_disabled({'enabled': True}) is False
        assert AudioCacheManager._is_disabled({'enabled': 'true'}) is False


class TestImageGenerationCacheManager:
    """Test ImageGenerationCacheManager class"""

    def setup_method(self):
        self.config = {
            'general': {},
            'image_generation': {
                'openai': {'model': 'gpt-image-2'},
                'gemini': {'model': 'imagen-4.0-generate-001'},
            }
        }
        self.thread_pool = ThreadPoolExecutor(max_workers=2)
        self.cache_manager = ImageGenerationCacheManager(self.config, self.thread_pool)

    def teardown_method(self):
        self.thread_pool.shutdown(wait=False)

    def test_build_cache_key_with_model(self):
        assert self.cache_manager.build_cache_key("openai") == "openai:gpt-image-2"

    def test_build_cache_key_without_model(self):
        assert self.cache_manager.build_cache_key("nonexistent") == "nonexistent"

    def test_get_and_put(self):
        service = Mock()
        self.cache_manager.put("openai:gpt-image-2", service)
        assert self.cache_manager.get("openai:gpt-image-2") is service

    def test_contains(self):
        assert self.cache_manager.contains("key") is False
        self.cache_manager.put("key", Mock())
        assert self.cache_manager.contains("key") is True

    def test_get_cached_keys(self):
        self.cache_manager.put("openai:model", Mock())
        self.cache_manager.put("gemini:model", Mock())
        assert set(self.cache_manager.get_cached_keys()) == {"openai:model", "gemini:model"}

    def test_get_cache_size(self):
        assert self.cache_manager.get_cache_size() == 0
        self.cache_manager.put("key", Mock())
        assert self.cache_manager.get_cache_size() == 1

    @pytest.mark.asyncio
    async def test_remove(self):
        service = Mock(spec=[])
        self.cache_manager.put("key", service)
        result = await self.cache_manager.remove("key")
        assert result is service
        assert self.cache_manager.contains("key") is False

    @pytest.mark.asyncio
    async def test_clear(self):
        self.cache_manager.put("key1", Mock(spec=[]))
        self.cache_manager.put("key2", Mock(spec=[]))
        await self.cache_manager.clear()
        assert self.cache_manager.get_cache_size() == 0


class TestVideoGenerationCacheManager:
    """Test VideoGenerationCacheManager class"""

    def setup_method(self):
        self.config = {
            'general': {},
            'video_generation': {
                'gemini': {'model': 'veo-2.0-generate-001'},
                'xai': {'model': 'grok-imagine-video'},
            }
        }
        self.thread_pool = ThreadPoolExecutor(max_workers=2)
        self.cache_manager = VideoGenerationCacheManager(self.config, self.thread_pool)

    def teardown_method(self):
        self.thread_pool.shutdown(wait=False)

    def test_build_cache_key_with_model(self):
        assert self.cache_manager.build_cache_key("gemini") == "gemini:veo-2.0-generate-001"

    def test_build_cache_key_without_model(self):
        assert self.cache_manager.build_cache_key("nonexistent") == "nonexistent"

    def test_get_and_put(self):
        service = Mock()
        self.cache_manager.put("gemini:veo-2.0-generate-001", service)
        assert self.cache_manager.get("gemini:veo-2.0-generate-001") is service

    def test_contains(self):
        assert self.cache_manager.contains("key") is False
        self.cache_manager.put("key", Mock())
        assert self.cache_manager.contains("key") is True

    def test_get_cached_keys(self):
        self.cache_manager.put("gemini:model", Mock())
        self.cache_manager.put("xai:model", Mock())
        assert set(self.cache_manager.get_cached_keys()) == {"gemini:model", "xai:model"}

    def test_get_cache_size(self):
        assert self.cache_manager.get_cache_size() == 0
        self.cache_manager.put("key", Mock())
        assert self.cache_manager.get_cache_size() == 1

    @pytest.mark.asyncio
    async def test_remove(self):
        service = Mock(spec=[])
        self.cache_manager.put("key", service)
        result = await self.cache_manager.remove("key")
        assert result is service
        assert self.cache_manager.contains("key") is False

    @pytest.mark.asyncio
    async def test_clear(self):
        self.cache_manager.put("key1", Mock(spec=[]))
        self.cache_manager.put("key2", Mock(spec=[]))
        await self.cache_manager.clear()
        assert self.cache_manager.get_cache_size() == 0


class TestServiceCacheManager:
    """Test shared service-cache behavior."""

    @pytest.mark.asyncio
    async def test_concurrent_create_shares_in_flight_initialization(self):
        """Concurrent creates for a key wait on one initializer."""
        created = []
        started = asyncio.Event()
        release = asyncio.Event()

        class TestCacheManager(ServiceCacheManager):
            service_label = "test service"

            async def _create_instance(self, provider_name, adapter_name=None, **kwargs):
                created.append(provider_name)
                started.set()
                await release.wait()
                return Mock(spec=[])

        cache_manager = TestCacheManager({})
        first = asyncio.create_task(cache_manager._create_cached_service("key", "provider"))
        await started.wait()
        second = asyncio.create_task(cache_manager._create_cached_service("key", "provider"))

        release.set()
        first_result, second_result = await asyncio.gather(first, second)

        assert first_result is second_result
        assert created == ["provider"]

    @pytest.mark.asyncio
    async def test_failed_create_releases_waiters_for_retry(self):
        """Waiters do not busy-wait or hang after a failed initialization."""
        attempts = 0

        class TestCacheManager(ServiceCacheManager):
            service_label = "test service"

            async def _create_instance(self, provider_name, adapter_name=None, **kwargs):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise RuntimeError("boom")
                return Mock(spec=[])

        cache_manager = TestCacheManager({})

        with pytest.raises(RuntimeError):
            await cache_manager._create_cached_service("key", "provider")

        service = await cache_manager._create_cached_service("key", "provider")

        assert service is cache_manager.get("key")
        assert attempts == 2

    @pytest.mark.asyncio
    async def test_remove_matching_closes_matching_services(self):
        """Prefix removal uses the shared atomic matching removal path."""
        cache_manager = ProviderCacheManager({'general': {}})
        openai = AsyncMock()
        openai_variant = AsyncMock()
        anthropic = AsyncMock()
        cache_manager.put("openai", openai)
        cache_manager.put("openai:gpt-4", openai_variant)
        cache_manager.put("anthropic", anthropic)

        removed = await cache_manager.remove_by_prefix("openai")

        assert set(removed) == {"openai", "openai:gpt-4"}
        assert cache_manager.contains("openai") is False
        assert cache_manager.contains("openai:gpt-4") is False
        assert cache_manager.contains("anthropic") is True
        openai.close.assert_awaited_once()
        openai_variant.close.assert_awaited_once()
        anthropic.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_remove_cancels_in_flight_create_without_popping_new_owner(self):
        """A stale initializer cannot cache after remove or clear a newer owner."""
        first_started = asyncio.Event()
        second_started = asyncio.Event()
        release_first = asyncio.Event()
        release_second = asyncio.Event()
        services = []

        class TestCacheManager(ServiceCacheManager):
            service_label = "test service"

            async def _create_instance(self, provider_name, adapter_name=None, **kwargs):
                service = AsyncMock()
                services.append(service)
                if len(services) == 1:
                    first_started.set()
                    await release_first.wait()
                else:
                    second_started.set()
                    await release_second.wait()
                return service

        cache_manager = TestCacheManager({})
        first = asyncio.create_task(cache_manager._create_cached_service("key", "provider"))
        await first_started.wait()

        assert await cache_manager.remove("key") is None

        second = asyncio.create_task(cache_manager._create_cached_service("key", "provider"))
        await second_started.wait()

        release_first.set()
        with pytest.raises(RuntimeError, match="initialization for key was cancelled"):
            await first

        release_second.set()
        second_result = await second

        assert second_result is services[1]
        assert cache_manager.get("key") is services[1]
        services[0].close.assert_awaited_once()
        services[1].close.assert_not_called()


SERVICE_MANAGER_CASES = [
    (
        ProviderCacheManager,
        {
            'general': {},
            'inference': {
                'openai': {'model': 'gpt-4'}
            }
        },
    ),
    (
        EmbeddingCacheManager,
        {
            'general': {},
            'embeddings': {
                'openai': {'model': 'text-embedding-3-small'}
            }
        },
    ),
    (
        RerankerCacheManager,
        {
            'general': {},
            'rerankers': {
                'cohere': {'model': 'rerank-english-v3.0'}
            }
        },
    ),
    (
        VisionCacheManager,
        {
            'general': {},
            'vision': {
                'openai': {'model': 'gpt-4-vision-preview'}
            }
        },
    ),
    (
        AudioCacheManager,
        {
            'general': {},
            'tts_providers': {
                'openai': {'tts_model': 'tts-1'}
            },
            'stt_providers': {}
        },
    ),
    (
        ImageGenerationCacheManager,
        {
            'general': {},
            'image_generation': {
                'openai': {'model': 'gpt-image-2'}
            }
        },
    ),
    (
        VideoGenerationCacheManager,
        {
            'general': {},
            'video_generation': {
                'gemini': {'model': 'veo-2.0-generate-001'}
            }
        },
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("manager_cls,config", SERVICE_MANAGER_CASES)
async def test_close_shuts_down_self_owned_thread_pool(manager_cls, config):
    """Managers shut down executors they create themselves."""
    cache_manager = manager_cls(config)
    thread_pool = cache_manager._thread_pool

    await cache_manager.close()

    with pytest.raises(RuntimeError):
        thread_pool.submit(lambda: None)


@pytest.mark.asyncio
@pytest.mark.parametrize("manager_cls,config", SERVICE_MANAGER_CASES)
async def test_close_leaves_injected_thread_pool_running(manager_cls, config):
    """Managers do not shut down shared executors injected by callers."""
    thread_pool = ThreadPoolExecutor(max_workers=1)
    cache_manager = manager_cls(config, thread_pool)

    try:
        await cache_manager.close()
        future = thread_pool.submit(lambda: "running")
        assert future.result(timeout=1) == "running"
    finally:
        thread_pool.shutdown(wait=False)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
