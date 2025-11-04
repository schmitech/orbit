"""
Tests for Retriever Cache

Tests the RetrieverCache singleton for caching FileVectorRetriever instances.
"""

import pytest
import pytest_asyncio
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# Add server directory to Python path
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.retriever_cache import RetrieverCache, get_retriever_cache


@pytest.fixture
def cache():
    """Fixture to provide a fresh RetrieverCache instance"""
    # Clear the cache before each test
    cache_instance = get_retriever_cache()
    cache_instance.clear_cache()
    return cache_instance


def test_retriever_cache_singleton():
    """Test that RetrieverCache is a singleton"""
    cache1 = get_retriever_cache()
    cache2 = get_retriever_cache()

    assert cache1 is cache2
    assert id(cache1) == id(cache2)


def test_cache_key_generation_same_config(cache):
    """Test that identical configs produce the same cache key"""
    config1 = {
        'embedding': {'provider': 'ollama', 'model': 'nomic-embed-text'},
        'files': {'default_vector_store': 'chroma', 'default_collection_prefix': 'files_'}
    }

    config2 = {
        'embedding': {'provider': 'ollama', 'model': 'nomic-embed-text'},
        'files': {'default_vector_store': 'chroma', 'default_collection_prefix': 'files_'}
    }

    key1 = cache._get_cache_key(config1)
    key2 = cache._get_cache_key(config2)

    assert key1 == key2


def test_cache_key_generation_different_provider(cache):
    """Test that different embedding providers produce different cache keys"""
    config_ollama = {
        'embedding': {'provider': 'ollama', 'model': 'nomic-embed-text'},
        'files': {'default_vector_store': 'chroma'}
    }

    config_openai = {
        'embedding': {'provider': 'openai', 'model': 'text-embedding-3-small'},
        'files': {'default_vector_store': 'chroma'}
    }

    key_ollama = cache._get_cache_key(config_ollama)
    key_openai = cache._get_cache_key(config_openai)

    assert key_ollama != key_openai


def test_cache_key_generation_different_model(cache):
    """Test that different embedding models produce different cache keys"""
    config1 = {
        'embedding': {'provider': 'ollama', 'model': 'nomic-embed-text'},
        'files': {'default_vector_store': 'chroma'}
    }

    config2 = {
        'embedding': {'provider': 'ollama', 'model': 'mxbai-embed-large'},
        'files': {'default_vector_store': 'chroma'}
    }

    key1 = cache._get_cache_key(config1)
    key2 = cache._get_cache_key(config2)

    assert key1 != key2


def test_cache_key_generation_different_vector_store(cache):
    """Test that different vector stores produce different cache keys"""
    config_chroma = {
        'embedding': {'provider': 'ollama'},
        'files': {'default_vector_store': 'chroma'}
    }

    config_pinecone = {
        'embedding': {'provider': 'ollama'},
        'files': {'default_vector_store': 'pinecone'}
    }

    key_chroma = cache._get_cache_key(config_chroma)
    key_pinecone = cache._get_cache_key(config_pinecone)

    assert key_chroma != key_pinecone


def test_cache_key_generation_different_adapter_config(cache):
    """Test that different adapter configs produce different cache keys"""
    config1 = {
        'embedding': {'provider': 'ollama'},
        'files': {'default_vector_store': 'chroma'},
        'adapter_config': {'collection_prefix': 'adapter1_'}
    }

    config2 = {
        'embedding': {'provider': 'ollama'},
        'files': {'default_vector_store': 'chroma'},
        'adapter_config': {'collection_prefix': 'adapter2_'}
    }

    key1 = cache._get_cache_key(config1)
    key2 = cache._get_cache_key(config2)

    assert key1 != key2


def test_cache_key_deterministic(cache):
    """Test that cache key generation is deterministic"""
    config = {
        'embedding': {'provider': 'ollama', 'model': 'test'},
        'files': {'default_vector_store': 'chroma'},
        'adapter_config': {'some_setting': 'value'}
    }

    # Generate key multiple times
    keys = [cache._get_cache_key(config) for _ in range(5)]

    # All keys should be identical
    assert len(set(keys)) == 1


@pytest.mark.asyncio
async def test_get_retriever_creates_and_caches(cache):
    """Test that get_retriever creates a retriever and caches it"""
    config = {
        'embedding': {'provider': 'ollama', 'model': 'nomic-embed-text'},
        'files': {'default_vector_store': 'chroma'}
    }

    # Mock the FileVectorRetriever initialization
    with patch('services.retriever_cache.FileVectorRetriever') as mock_retriever_class:
        mock_retriever_instance = Mock()
        mock_retriever_instance.initialized = False
        mock_retriever_instance.initialize = AsyncMock()
        mock_retriever_class.return_value = mock_retriever_instance

        # First call should create new retriever
        retriever1 = await cache.get_retriever(config)

        assert mock_retriever_class.called
        assert mock_retriever_instance.initialize.called
        assert retriever1 is mock_retriever_instance

        # Reset mocks
        mock_retriever_class.reset_mock()
        mock_retriever_instance.initialize.reset_mock()
        mock_retriever_instance.initialized = True

        # Second call should return cached retriever
        retriever2 = await cache.get_retriever(config)

        assert not mock_retriever_class.called  # Should not create new instance
        assert not mock_retriever_instance.initialize.called  # Should not re-initialize
        assert retriever2 is mock_retriever_instance  # Should be same instance


@pytest.mark.asyncio
async def test_get_retriever_different_configs_create_separate_instances(cache):
    """Test that different configs create separate cached retrievers"""
    config1 = {
        'embedding': {'provider': 'ollama', 'model': 'model1'},
        'files': {'default_vector_store': 'chroma'}
    }

    config2 = {
        'embedding': {'provider': 'openai', 'model': 'model2'},
        'files': {'default_vector_store': 'chroma'}
    }

    with patch('services.retriever_cache.FileVectorRetriever') as mock_retriever_class:
        # Create two different mock instances
        mock_retriever1 = Mock()
        mock_retriever1.initialized = False
        mock_retriever1.initialize = AsyncMock()

        mock_retriever2 = Mock()
        mock_retriever2.initialized = False
        mock_retriever2.initialize = AsyncMock()

        mock_retriever_class.side_effect = [mock_retriever1, mock_retriever2]

        # Get retriever for config1
        retriever1 = await cache.get_retriever(config1)

        # Get retriever for config2
        retriever2 = await cache.get_retriever(config2)

        # Should have created two instances
        assert mock_retriever_class.call_count == 2
        assert retriever1 is not retriever2


@pytest.mark.asyncio
async def test_get_retriever_reinitializes_if_not_initialized(cache):
    """Test that get_retriever reinitializes if retriever is not initialized"""
    config = {
        'embedding': {'provider': 'ollama'},
        'files': {'default_vector_store': 'chroma'}
    }

    with patch('services.retriever_cache.FileVectorRetriever') as mock_retriever_class:
        mock_retriever = Mock()
        mock_retriever.initialized = False
        mock_retriever.initialize = AsyncMock()
        mock_retriever_class.return_value = mock_retriever

        # First call
        await cache.get_retriever(config)

        # Manually set to uninitialized (simulating some edge case)
        mock_retriever.initialized = False
        mock_retriever.initialize.reset_mock()

        # Second call should reinitialize
        await cache.get_retriever(config)

        assert mock_retriever.initialize.called


def test_clear_cache(cache):
    """Test that clear_cache removes all cached retrievers"""
    # Manually add some items to cache
    cache._cache['key1'] = Mock()
    cache._cache['key2'] = Mock()
    cache._cache['key3'] = Mock()

    assert len(cache._cache) == 3

    # Clear cache
    cache.clear_cache()

    assert len(cache._cache) == 0


def test_get_cache_stats(cache):
    """Test that get_cache_stats returns correct information"""
    # Initially empty
    stats = cache.get_cache_stats()
    assert stats['cached_retrievers'] == 0
    assert stats['cache_keys'] == []

    # Add some mock entries
    cache._cache['abc123'] = Mock()
    cache._cache['def456'] = Mock()

    stats = cache.get_cache_stats()
    assert stats['cached_retrievers'] == 2
    assert len(stats['cache_keys']) == 2
    assert 'abc123...' in stats['cache_keys']
    assert 'def456...' in stats['cache_keys']


@pytest.mark.asyncio
async def test_cache_persists_across_multiple_calls(cache):
    """Test that cache persists across multiple sequential calls"""
    config = {
        'embedding': {'provider': 'ollama'},
        'files': {'default_vector_store': 'chroma'}
    }

    with patch('services.retriever_cache.FileVectorRetriever') as mock_retriever_class:
        mock_retriever = Mock()
        mock_retriever.initialized = False
        mock_retriever.initialize = AsyncMock()
        mock_retriever_class.return_value = mock_retriever

        # Make multiple calls
        retrievers = []
        for _ in range(5):
            mock_retriever.initialized = True  # After first init
            retriever = await cache.get_retriever(config)
            retrievers.append(retriever)

        # Should have created only one instance
        assert mock_retriever_class.call_count == 1

        # All retrieved instances should be the same
        assert all(r is mock_retriever for r in retrievers)


def test_cache_key_handles_missing_config_params(cache):
    """Test that cache key generation handles missing config parameters gracefully"""
    # Minimal config with missing params
    config = {}

    # Should not raise an error
    key = cache._get_cache_key(config)

    assert isinstance(key, str)
    assert len(key) > 0


def test_cache_key_handles_nested_config(cache):
    """Test that cache key generation handles complex nested config"""
    config = {
        'embedding': {
            'provider': 'openai',
            'model': 'text-embedding-3-small',
            'extra': 'ignored'
        },
        'files': {
            'default_vector_store': 'pinecone',
            'default_collection_prefix': 'custom_',
            'other_setting': 'ignored'
        },
        'adapter_config': {
            'setting1': 'value1',
            'setting2': {'nested': 'value2'}
        },
        'other_config': 'ignored'
    }

    key = cache._get_cache_key(config)

    assert isinstance(key, str)
    assert len(key) == 32  # MD5 hash is 32 characters
