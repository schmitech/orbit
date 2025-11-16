"""
Unit tests for reload components.

Tests:
- DependencyCacheCleaner
- AdapterReloader
"""

import pytest
import asyncio
import sys
import os
from unittest.mock import Mock, MagicMock, AsyncMock, patch

# Add the server directory to the Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.reload.dependency_cache_cleaner import DependencyCacheCleaner
from services.reload.adapter_reloader import AdapterReloader


class TestDependencyCacheCleaner:
    """Test DependencyCacheCleaner class"""

    def setup_method(self):
        """Setup test fixtures"""
        self.config = {
            'general': {'verbose': False},
            'embeddings': {
                'openai': {'model': 'text-embedding-3-small'},
                'ollama': {'model': 'nomic-embed-text'}
            },
            'rerankers': {
                'cohere': {'model': 'rerank-english-v3.0'},
                'flashrank': {'model': 'ms-marco-MiniLM-L-12-v2'}
            }
        }

        # Create mock cache managers
        self.provider_cache = Mock()
        self.embedding_cache = Mock()
        self.reranker_cache = Mock()

        # Setup async methods
        self.provider_cache.remove = AsyncMock(return_value=Mock())
        self.provider_cache.remove_by_prefix = AsyncMock(return_value=[])
        self.provider_cache.contains = Mock(return_value=False)
        self.provider_cache.build_cache_key = Mock(side_effect=lambda p, m=None: f"{p}:{m}" if m else p)

        self.embedding_cache.remove = AsyncMock(return_value=Mock())
        self.embedding_cache.contains = Mock(return_value=False)
        self.embedding_cache.build_cache_key = Mock(
            side_effect=lambda p: f"{p}:{self.config['embeddings'].get(p, {}).get('model', '')}"
            if self.config['embeddings'].get(p, {}).get('model') else p
        )

        self.reranker_cache.remove = AsyncMock(return_value=Mock())
        self.reranker_cache.contains = Mock(return_value=False)
        self.reranker_cache.build_cache_key = Mock(
            side_effect=lambda p: f"{p}:{self.config['rerankers'].get(p, {}).get('model', '')}"
            if self.config['rerankers'].get(p, {}).get('model') else p
        )

        self.cleaner = DependencyCacheCleaner(
            self.config,
            self.provider_cache,
            self.embedding_cache,
            self.reranker_cache,
            verbose=False
        )

    @pytest.mark.asyncio
    async def test_clear_adapter_dependencies_empty_config(self):
        """Test clearing dependencies with no config returns empty list"""
        result = await self.cleaner.clear_adapter_dependencies("test_adapter", None)
        assert result == []

    @pytest.mark.asyncio
    async def test_clear_adapter_dependencies_no_overrides(self):
        """Test clearing dependencies when adapter has no overrides"""
        adapter_config = {
            'name': 'test_adapter',
            'enabled': True
        }

        result = await self.cleaner.clear_adapter_dependencies("test_adapter", adapter_config)
        assert result == []

    @pytest.mark.asyncio
    async def test_clear_provider_cache_exact_match(self):
        """Test clearing provider cache with exact match"""
        adapter_config = {
            'inference_provider': 'openai',
            'model': 'gpt-4'
        }

        self.provider_cache.contains = Mock(return_value=True)

        result = await self.cleaner.clear_adapter_dependencies("test_adapter", adapter_config)

        self.provider_cache.build_cache_key.assert_called_with('openai', 'gpt-4')
        self.provider_cache.remove.assert_called_once_with('openai:gpt-4')
        assert 'provider:openai:gpt-4' in result

    @pytest.mark.asyncio
    async def test_clear_provider_cache_fallback_to_prefix(self):
        """Test clearing provider cache falls back to prefix when exact match not found"""
        adapter_config = {
            'inference_provider': 'openai',
            'model': 'gpt-4'
        }

        self.provider_cache.contains = Mock(return_value=False)
        self.provider_cache.remove_by_prefix = AsyncMock(return_value=['openai', 'openai:gpt-3.5'])

        result = await self.cleaner.clear_adapter_dependencies("test_adapter", adapter_config)

        self.provider_cache.remove_by_prefix.assert_called_once_with('openai')
        assert 'provider:openai' in result
        assert 'provider:openai:gpt-3.5' in result

    @pytest.mark.asyncio
    async def test_clear_provider_cache_without_model(self):
        """Test clearing provider cache when no model override"""
        adapter_config = {
            'inference_provider': 'openai'
        }

        self.provider_cache.contains = Mock(return_value=True)

        result = await self.cleaner.clear_adapter_dependencies("test_adapter", adapter_config)

        self.provider_cache.build_cache_key.assert_called_with('openai', None)
        assert 'provider:openai' in result

    @pytest.mark.asyncio
    async def test_clear_embedding_cache(self):
        """Test clearing embedding cache"""
        adapter_config = {
            'embedding_provider': 'openai'
        }

        self.embedding_cache.contains = Mock(return_value=True)

        result = await self.cleaner.clear_adapter_dependencies("test_adapter", adapter_config)

        self.embedding_cache.build_cache_key.assert_called_once_with('openai')
        self.embedding_cache.remove.assert_called_once()
        assert 'embedding:openai:text-embedding-3-small' in result

    @pytest.mark.asyncio
    async def test_clear_reranker_cache(self):
        """Test clearing reranker cache"""
        adapter_config = {
            'reranker_provider': 'cohere'
        }

        self.reranker_cache.contains = Mock(return_value=True)

        result = await self.cleaner.clear_adapter_dependencies("test_adapter", adapter_config)

        self.reranker_cache.build_cache_key.assert_called_once_with('cohere')
        self.reranker_cache.remove.assert_called_once()
        assert 'reranker:cohere:rerank-english-v3.0' in result

    @pytest.mark.asyncio
    async def test_clear_all_dependencies(self):
        """Test clearing all types of dependencies"""
        adapter_config = {
            'inference_provider': 'openai',
            'model': 'gpt-4',
            'embedding_provider': 'ollama',
            'reranker_provider': 'flashrank'
        }

        self.provider_cache.contains = Mock(return_value=True)
        self.embedding_cache.contains = Mock(return_value=True)
        self.reranker_cache.contains = Mock(return_value=True)

        result = await self.cleaner.clear_adapter_dependencies("test_adapter", adapter_config)

        assert len(result) == 3
        assert any('provider:' in r for r in result)
        assert any('embedding:' in r for r in result)
        assert any('reranker:' in r for r in result)

    def test_update_config(self):
        """Test updating config reference"""
        new_config = {'general': {'verbose': True}}
        self.cleaner.update_config(new_config)
        assert self.cleaner.config == new_config


class TestAdapterReloader:
    """Test AdapterReloader class"""

    def setup_method(self):
        """Setup test fixtures"""
        # Create mock components
        self.config_manager = Mock()
        self.adapter_cache = Mock()
        self.adapter_loader = Mock()
        self.dependency_cleaner = Mock()

        # Setup common async mocks
        self.adapter_cache.remove = AsyncMock(return_value=Mock())
        self.adapter_cache.contains = Mock(return_value=False)
        self.adapter_loader.load_adapter = AsyncMock(return_value=Mock())
        self.dependency_cleaner.clear_adapter_dependencies = AsyncMock(return_value=[])

        self.reloader = AdapterReloader(
            self.config_manager,
            self.adapter_cache,
            self.adapter_loader,
            self.dependency_cleaner,
            verbose=False
        )

    @pytest.mark.asyncio
    async def test_reload_single_adapter_not_found(self):
        """Test reloading adapter that doesn't exist in config"""
        new_config = {'adapters': []}

        with pytest.raises(ValueError, match="not found in configuration"):
            await self.reloader.reload_single_adapter("nonexistent", new_config)

    @pytest.mark.asyncio
    async def test_reload_single_adapter_added(self):
        """Test reloading a newly added adapter"""
        new_config = {
            'adapters': [
                {'name': 'new_adapter', 'enabled': True, 'model': 'gpt-4'}
            ]
        }

        self.config_manager.get = Mock(return_value=None)
        self.config_manager.contains = Mock(return_value=False)
        self.config_manager.put = Mock()
        self.adapter_cache.contains = Mock(return_value=False)
        self.adapter_cache.put = Mock()

        result = await self.reloader.reload_single_adapter("new_adapter", new_config)

        assert result['action'] == 'added'
        assert result['adapter_name'] == 'new_adapter'
        self.config_manager.put.assert_called_once()
        self.adapter_loader.load_adapter.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reload_single_adapter_updated(self):
        """Test reloading an updated adapter"""
        old_config = {'name': 'test_adapter', 'enabled': True, 'model': 'gpt-4'}
        new_adapter_config = {'name': 'test_adapter', 'enabled': True, 'model': 'gpt-4-turbo'}
        new_config = {'adapters': [new_adapter_config]}

        self.config_manager.get = Mock(return_value=old_config)
        self.config_manager.contains = Mock(return_value=True)
        self.config_manager.put = Mock()
        self.adapter_cache.contains = Mock(return_value=True)
        self.adapter_cache.get = Mock(return_value=Mock())
        self.adapter_cache.put = Mock()

        result = await self.reloader.reload_single_adapter("test_adapter", new_config)

        assert result['action'] == 'updated'
        assert result['previous_config'] == old_config
        assert result['new_config'] == new_adapter_config
        self.dependency_cleaner.clear_adapter_dependencies.assert_awaited_once()
        self.adapter_cache.remove.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reload_single_adapter_disabled(self):
        """Test reloading adapter that becomes disabled"""
        old_config = {'name': 'test_adapter', 'enabled': True}
        new_config = {
            'adapters': [
                {'name': 'test_adapter', 'enabled': False}
            ]
        }

        self.config_manager.get = Mock(return_value=old_config)
        self.config_manager.remove = Mock()
        self.adapter_cache.contains = Mock(return_value=True)

        result = await self.reloader.reload_single_adapter("test_adapter", new_config)

        assert result['action'] == 'disabled'
        self.config_manager.remove.assert_called_once_with('test_adapter')

    @pytest.mark.asyncio
    async def test_reload_single_adapter_enabled(self):
        """Test reloading adapter that becomes enabled"""
        new_config = {
            'adapters': [
                {'name': 'test_adapter', 'enabled': True, 'model': 'gpt-4'}
            ]
        }

        # Old config shows it was disabled
        old_config = {'name': 'test_adapter', 'enabled': False}
        self.config_manager.get = Mock(return_value=old_config)
        self.config_manager.contains = Mock(return_value=True)
        self.config_manager.put = Mock()
        self.adapter_cache.contains = Mock(return_value=False)
        self.adapter_cache.put = Mock()

        result = await self.reloader.reload_single_adapter("test_adapter", new_config)

        assert result['action'] == 'enabled'

    @pytest.mark.asyncio
    async def test_reload_all_adapters_added(self):
        """Test reload_all_adapters detects added adapters"""
        new_config = {
            'adapters': [
                {'name': 'existing', 'enabled': True, 'model': 'gpt-4'},
                {'name': 'new_adapter', 'enabled': True, 'model': 'gpt-4'}
            ]
        }

        self.config_manager.get = Mock(side_effect=lambda n:
            {'name': 'existing', 'enabled': True, 'model': 'gpt-4'} if n == 'existing' else None
        )
        self.config_manager.get_available_adapters = Mock(return_value=['existing'])
        self.config_manager.put = Mock()
        self.adapter_cache.put = Mock()
        self.adapter_cache.contains = Mock(return_value=False)

        result = await self.reloader.reload_all_adapters(new_config)

        assert 'new_adapter' in result['added_names']
        assert result['added'] == 1

    @pytest.mark.asyncio
    async def test_reload_all_adapters_removed(self):
        """Test reload_all_adapters detects removed adapters"""
        new_config = {
            'adapters': [
                {'name': 'remaining', 'enabled': True, 'model': 'gpt-4'}
            ]
        }

        old_config = {'name': 'removed', 'enabled': True, 'model': 'gpt-4'}
        remaining_config = {'name': 'remaining', 'enabled': True, 'model': 'gpt-4'}

        def get_side_effect(name):
            if name == 'removed':
                return old_config
            elif name == 'remaining':
                return remaining_config
            return None

        self.config_manager.get = Mock(side_effect=get_side_effect)
        self.config_manager.get_available_adapters = Mock(return_value=['remaining', 'removed'])
        self.config_manager.remove = Mock()
        self.config_manager.get_adapter_count = Mock(return_value=1)
        self.adapter_cache.contains = Mock(return_value=True)

        result = await self.reloader.reload_all_adapters(new_config)

        assert 'removed' in result['removed_names']
        assert result['removed'] == 1

    @pytest.mark.asyncio
    async def test_reload_all_adapters_updated(self):
        """Test reload_all_adapters detects updated adapters"""
        old_config = {'name': 'test', 'enabled': True, 'model': 'gpt-4'}
        new_adapter_config = {'name': 'test', 'enabled': True, 'model': 'gpt-4-turbo'}
        new_config = {'adapters': [new_adapter_config]}

        self.config_manager.get = Mock(return_value=old_config)
        self.config_manager.get_available_adapters = Mock(return_value=['test'])
        self.config_manager.put = Mock()
        self.config_manager.get_adapter_count = Mock(return_value=1)
        self.adapter_cache.contains = Mock(return_value=True)
        self.adapter_cache.put = Mock()

        result = await self.reloader.reload_all_adapters(new_config)

        assert 'test' in result['updated_names']
        assert result['updated'] == 1

    @pytest.mark.asyncio
    async def test_reload_all_adapters_unchanged(self):
        """Test reload_all_adapters detects unchanged adapters"""
        config = {'name': 'test', 'enabled': True, 'model': 'gpt-4'}
        new_config = {'adapters': [config]}

        self.config_manager.get = Mock(return_value=config)
        self.config_manager.get_available_adapters = Mock(return_value=['test'])
        self.config_manager.get_adapter_count = Mock(return_value=1)

        result = await self.reloader.reload_all_adapters(new_config)

        assert result['unchanged'] == 1
        assert result['added'] == 0
        assert result['removed'] == 0
        assert result['updated'] == 0

    @pytest.mark.asyncio
    async def test_preload_adapter_safe_handles_value_error(self):
        """Test _preload_adapter_safe handles ValueError gracefully"""
        adapter_config = {'name': 'test', 'enabled': True}
        self.adapter_loader.load_adapter = AsyncMock(
            side_effect=ValueError("Provider not available")
        )

        # Should not raise, just log error
        await self.reloader._preload_adapter_safe("test", adapter_config, "updated")

        self.adapter_cache.put.assert_not_called()

    @pytest.mark.asyncio
    async def test_preload_adapter_safe_handles_exception(self):
        """Test _preload_adapter_safe handles generic exceptions gracefully"""
        adapter_config = {'name': 'test', 'enabled': True}
        self.adapter_loader.load_adapter = AsyncMock(
            side_effect=Exception("Something went wrong")
        )

        # Should not raise, just log warning
        await self.reloader._preload_adapter_safe("test", adapter_config, "newly added")

        self.adapter_cache.put.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
