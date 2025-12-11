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
            'general': {},
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
        new_config = {'general': {}}
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


class TestAdapterLoaderInferencePreload:
    """Test AdapterLoader inference provider preload functionality"""

    def setup_method(self):
        """Setup test fixtures"""
        self.config = {
            'general': {
                'inference_provider': 'default_provider'
            },
            'inference': {
                'openai': {'model': 'gpt-4'},
                'ollama': {'model': 'llama2'},
                'default_provider': {'model': 'default-model'}
            },
            'adapters': []
        }

        # Create mock cache managers
        self.provider_cache = Mock()
        self.embedding_cache = Mock()
        self.reranker_cache = Mock()
        self.vision_cache = Mock()
        self.audio_cache = Mock()
        self.app_state = Mock()

        # Setup async methods on caches
        self.provider_cache.create_provider = AsyncMock(return_value=Mock())
        self.embedding_cache.create_service = AsyncMock(return_value=Mock())
        self.reranker_cache.create_service = AsyncMock(return_value=Mock())
        self.vision_cache.create_service = AsyncMock(return_value=Mock())
        self.audio_cache.create_service = AsyncMock(return_value=Mock())

    def _create_loader(self):
        """Create AdapterLoader with mocks"""
        from services.loader.adapter_loader import AdapterLoader
        return AdapterLoader(
            self.config,
            self.app_state,
            self.provider_cache,
            self.embedding_cache,
            self.reranker_cache,
            self.vision_cache,
            self.audio_cache
        )

    @pytest.mark.asyncio
    async def test_inference_provider_preload_during_adapter_load(self):
        """Test that inference provider is preloaded when loading an adapter"""
        adapter_config = {
            'name': 'test_adapter',
            'enabled': True,
            'inference_provider': 'openai',
            'implementation': 'retrievers.passthrough.PassthroughRetriever'
        }

        loader = self._create_loader()

        # Mock the _create_adapter_sync method to avoid import chain issues
        mock_retriever = Mock()
        mock_retriever.domain_adapter = None
        with patch.object(loader, '_create_adapter_sync', return_value=mock_retriever):
            await loader.load_adapter('test_adapter', adapter_config)

            # Verify inference provider was preloaded
            self.provider_cache.create_provider.assert_called()
            call_args = self.provider_cache.create_provider.call_args
            assert call_args[0][0] == 'openai'  # provider_name
            assert call_args[0][2] == 'test_adapter'  # adapter_name

    @pytest.mark.asyncio
    async def test_inference_provider_preload_with_model_override(self):
        """Test that inference provider is preloaded with model override"""
        adapter_config = {
            'name': 'test_adapter',
            'enabled': True,
            'inference_provider': 'openai',
            'model': 'gpt-4-turbo',
            'implementation': 'retrievers.passthrough.PassthroughRetriever'
        }

        loader = self._create_loader()

        # Mock the _create_adapter_sync method to avoid import chain issues
        mock_retriever = Mock()
        mock_retriever.domain_adapter = None
        with patch.object(loader, '_create_adapter_sync', return_value=mock_retriever):
            await loader.load_adapter('test_adapter', adapter_config)

            # Verify inference provider was preloaded with model override
            self.provider_cache.create_provider.assert_called()
            call_args = self.provider_cache.create_provider.call_args
            assert call_args[0][0] == 'openai'  # provider_name
            assert call_args[0][1] == 'gpt-4-turbo'  # model_override
            assert call_args[0][2] == 'test_adapter'  # adapter_name

    @pytest.mark.asyncio
    async def test_inference_provider_preload_uses_global_default(self):
        """Test that global default provider is used when adapter doesn't specify one"""
        adapter_config = {
            'name': 'test_adapter',
            'enabled': True,
            # No inference_provider specified - should use global default
            'implementation': 'retrievers.passthrough.PassthroughRetriever'
        }

        loader = self._create_loader()

        # Mock the _create_adapter_sync method to avoid import chain issues
        mock_retriever = Mock()
        mock_retriever.domain_adapter = None
        with patch.object(loader, '_create_adapter_sync', return_value=mock_retriever):
            await loader.load_adapter('test_adapter', adapter_config)

            # Verify inference provider was preloaded with global default
            self.provider_cache.create_provider.assert_called()
            call_args = self.provider_cache.create_provider.call_args
            assert call_args[0][0] == 'default_provider'  # global default

    @pytest.mark.asyncio
    async def test_inference_provider_preload_failure_continues(self):
        """Test that adapter loading continues even if inference provider preload fails"""
        adapter_config = {
            'name': 'test_adapter',
            'enabled': True,
            'inference_provider': 'failing_provider',
            'implementation': 'retrievers.passthrough.PassthroughRetriever'
        }

        # Make provider preload fail
        self.provider_cache.create_provider = AsyncMock(
            side_effect=Exception("Provider initialization failed")
        )

        loader = self._create_loader()

        # Mock the _create_adapter_sync method to avoid import chain issues
        mock_retriever = Mock()
        mock_retriever.domain_adapter = None
        with patch.object(loader, '_create_adapter_sync', return_value=mock_retriever):
            # Should not raise even though provider preload failed
            # The adapter loading should continue and return the retriever
            result = await loader.load_adapter('test_adapter', adapter_config)
            assert result is mock_retriever

    @pytest.mark.asyncio
    async def test_no_inference_provider_preload_when_none_configured(self):
        """Test that no preload happens when no provider is configured anywhere"""
        # Remove global default
        self.config['general'] = {}

        adapter_config = {
            'name': 'test_adapter',
            'enabled': True,
            # No inference_provider specified and no global default
            'implementation': 'retrievers.passthrough.PassthroughRetriever'
        }

        loader = self._create_loader()

        # Mock the _create_adapter_sync method to avoid import chain issues
        mock_retriever = Mock()
        mock_retriever.domain_adapter = None
        with patch.object(loader, '_create_adapter_sync', return_value=mock_retriever):
            await loader.load_adapter('test_adapter', adapter_config)

            # Should NOT have called create_provider since no provider is configured
            self.provider_cache.create_provider.assert_not_called()


class TestAdapterLoaderSTTTTSPreload:
    """Tests for STT and TTS provider preloading in AdapterLoader"""

    def setup_method(self):
        """Set up test fixtures"""
        self.config = {
            'general': {'inference_provider': 'default_provider'},
            'stt': {'enabled': True},
            'tts': {'enabled': True}
        }
        self.app_state = Mock()
        self.provider_cache = Mock()
        self.provider_cache.create_provider = AsyncMock()
        self.embedding_cache = Mock()
        self.embedding_cache.create_service = AsyncMock()
        self.reranker_cache = Mock()
        self.reranker_cache.create_service = AsyncMock()
        self.vision_cache = Mock()
        self.vision_cache.create_service = AsyncMock()
        self.audio_cache = Mock()
        self.audio_cache.create_service = AsyncMock()

    def _create_loader(self):
        from services.loader.adapter_loader import AdapterLoader
        return AdapterLoader(
            self.config,
            self.app_state,
            self.provider_cache,
            self.embedding_cache,
            self.reranker_cache,
            self.vision_cache,
            self.audio_cache
        )

    @pytest.mark.asyncio
    async def test_stt_provider_preload(self):
        """Test that STT provider is preloaded when specified"""
        adapter_config = {
            'name': 'test_adapter',
            'enabled': True,
            'stt_provider': 'whisper',
            'implementation': 'retrievers.passthrough.PassthroughRetriever'
        }

        loader = self._create_loader()

        mock_retriever = Mock()
        mock_retriever.domain_adapter = None
        with patch.object(loader, '_create_adapter_sync', return_value=mock_retriever):
            await loader.load_adapter('test_adapter', adapter_config)

            # Verify STT provider was preloaded via audio_cache
            self.audio_cache.create_service.assert_called()
            call_args = self.audio_cache.create_service.call_args
            assert call_args[0][0] == 'whisper'

    @pytest.mark.asyncio
    async def test_tts_provider_preload(self):
        """Test that TTS provider is preloaded when specified"""
        adapter_config = {
            'name': 'test_adapter',
            'enabled': True,
            'tts_provider': 'openai',
            'implementation': 'retrievers.passthrough.PassthroughRetriever'
        }

        loader = self._create_loader()

        mock_retriever = Mock()
        mock_retriever.domain_adapter = None
        with patch.object(loader, '_create_adapter_sync', return_value=mock_retriever):
            await loader.load_adapter('test_adapter', adapter_config)

            # Verify TTS provider was preloaded via audio_cache
            self.audio_cache.create_service.assert_called()
            call_args = self.audio_cache.create_service.call_args
            assert call_args[0][0] == 'openai'

    @pytest.mark.asyncio
    async def test_both_stt_and_tts_preload(self):
        """Test that both STT and TTS providers are preloaded when specified"""
        adapter_config = {
            'name': 'test_adapter',
            'enabled': True,
            'stt_provider': 'whisper',
            'tts_provider': 'coqui',
            'implementation': 'retrievers.passthrough.PassthroughRetriever'
        }

        loader = self._create_loader()

        mock_retriever = Mock()
        mock_retriever.domain_adapter = None
        with patch.object(loader, '_create_adapter_sync', return_value=mock_retriever):
            await loader.load_adapter('test_adapter', adapter_config)

            # Verify both were called
            assert self.audio_cache.create_service.call_count >= 2


class TestDependencyCacheCleanerExtended:
    """Tests for extended DependencyCacheCleaner functionality"""

    def setup_method(self):
        """Set up test fixtures"""
        self.config = {
            'general': {'inference_provider': 'default'},
            'datasources': {
                'sqlite': {'database': '/path/to/db.sqlite'}
            }
        }
        self.provider_cache = Mock()
        self.provider_cache.build_cache_key = Mock(return_value='provider:test')
        self.provider_cache.contains = Mock(return_value=True)
        self.provider_cache.remove = AsyncMock()

        self.embedding_cache = Mock()
        self.embedding_cache.build_cache_key = Mock(return_value='embedding:test')
        self.embedding_cache.contains = Mock(return_value=False)

        self.reranker_cache = Mock()
        self.reranker_cache.build_cache_key = Mock(return_value='reranker:test')
        self.reranker_cache.contains = Mock(return_value=False)

        self.vision_cache = Mock()
        self.vision_cache.build_cache_key = Mock(return_value='vision:test')
        self.vision_cache.contains = Mock(return_value=False)

        self.audio_cache = Mock()
        self.audio_cache.build_cache_key = Mock(return_value='audio:test')
        self.audio_cache.contains = Mock(return_value=True)
        self.audio_cache.remove = AsyncMock()

        self.app_state = Mock()
        self.store_manager = Mock()
        self.store_manager._stores = {}
        self.app_state.store_manager = self.store_manager

    def _create_cleaner(self):
        from services.reload.dependency_cache_cleaner import DependencyCacheCleaner
        return DependencyCacheCleaner(
            self.config,
            self.provider_cache,
            self.embedding_cache,
            self.reranker_cache,
            self.vision_cache,
            self.audio_cache,
            self.app_state
        )

    @pytest.mark.asyncio
    async def test_clear_stt_cache(self):
        """Test clearing STT provider cache"""
        adapter_config = {
            'name': 'test_adapter',
            'stt_provider': 'whisper'
        }

        cleaner = self._create_cleaner()
        cleared = await cleaner._clear_stt_cache(adapter_config)

        self.audio_cache.remove.assert_awaited_once()
        assert len(cleared) == 1
        assert cleared[0].startswith('stt:')

    @pytest.mark.asyncio
    async def test_clear_tts_cache(self):
        """Test clearing TTS provider cache"""
        adapter_config = {
            'name': 'test_adapter',
            'tts_provider': 'openai'
        }

        cleaner = self._create_cleaner()
        cleared = await cleaner._clear_tts_cache(adapter_config)

        self.audio_cache.remove.assert_awaited_once()
        assert len(cleared) == 1
        assert cleared[0].startswith('tts:')

    @pytest.mark.asyncio
    async def test_clear_store_cache(self):
        """Test clearing store cache when store_name is configured"""
        # Set up store in cache
        mock_store = Mock()
        mock_store.disconnect = AsyncMock()
        self.store_manager._stores = {'qdrant': mock_store}

        adapter_config = {
            'name': 'test_adapter',
            'config': {
                'store_name': 'qdrant'
            }
        }

        cleaner = self._create_cleaner()
        cleared = await cleaner._clear_store_cache('test_adapter', adapter_config)

        assert len(cleared) == 1
        assert 'store:qdrant' in cleared
        mock_store.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clear_store_cache_no_store_manager(self):
        """Test that store cache clearing is skipped when no store_manager"""
        self.app_state.store_manager = None
        self.app_state.vector_store_manager = None

        adapter_config = {
            'name': 'test_adapter',
            'config': {
                'store_name': 'qdrant'
            }
        }

        cleaner = self._create_cleaner()
        cleared = await cleaner._clear_store_cache('test_adapter', adapter_config)

        assert len(cleared) == 0

    @pytest.mark.asyncio
    async def test_clear_all_dependencies_includes_new_caches(self):
        """Test that clear_adapter_dependencies includes STT, TTS, store, and datasource"""
        adapter_config = {
            'name': 'test_adapter',
            'inference_provider': 'openai',
            'stt_provider': 'whisper',
            'tts_provider': 'coqui'
        }

        cleaner = self._create_cleaner()

        # Mock _clear_stt_cache and _clear_tts_cache to verify they're called
        cleaner._clear_stt_cache = AsyncMock(return_value=['stt:whisper'])
        cleaner._clear_tts_cache = AsyncMock(return_value=['tts:coqui'])
        cleaner._clear_store_cache = AsyncMock(return_value=[])
        cleaner._clear_datasource_cache = AsyncMock(return_value=[])

        cleared = await cleaner.clear_adapter_dependencies('test_adapter', adapter_config)

        cleaner._clear_stt_cache.assert_awaited_once()
        cleaner._clear_tts_cache.assert_awaited_once()
        cleaner._clear_store_cache.assert_awaited_once()
        cleaner._clear_datasource_cache.assert_awaited_once()


class TestAIServiceFactoryCacheClearing:
    """Tests for AIServiceFactory cache clearing during adapter reload"""

    def setup_method(self):
        """Set up test fixtures"""
        self.config = {'general': {'inference_provider': 'default'}}
        self.provider_cache = Mock()
        self.provider_cache.build_cache_key = Mock(return_value='openai:gpt-4')
        self.provider_cache.contains = Mock(return_value=True)
        self.provider_cache.remove = AsyncMock()

        self.embedding_cache = Mock()
        self.embedding_cache.build_cache_key = Mock(return_value='openai')
        self.embedding_cache.contains = Mock(return_value=True)
        self.embedding_cache.remove = AsyncMock()

        self.reranker_cache = Mock()
        self.reranker_cache.build_cache_key = Mock(return_value='cohere')
        self.reranker_cache.contains = Mock(return_value=True)
        self.reranker_cache.remove = AsyncMock()

        self.vision_cache = Mock()
        self.vision_cache.build_cache_key = Mock(return_value='openai')
        self.vision_cache.contains = Mock(return_value=True)
        self.vision_cache.remove = AsyncMock()

        self.audio_cache = Mock()
        self.audio_cache.build_cache_key = Mock(return_value='openai')
        self.audio_cache.contains = Mock(return_value=True)
        self.audio_cache.remove = AsyncMock()

        self.app_state = Mock()
        self.app_state.store_manager = None

    def _create_cleaner(self):
        from services.reload.dependency_cache_cleaner import DependencyCacheCleaner
        return DependencyCacheCleaner(
            self.config,
            self.provider_cache,
            self.embedding_cache,
            self.reranker_cache,
            self.vision_cache,
            self.audio_cache,
            self.app_state
        )

    @pytest.mark.asyncio
    async def test_provider_cache_clear_calls_factory_clear(self):
        """Test that clearing provider cache also clears AIServiceFactory cache"""
        adapter_config = {
            'inference_provider': 'openai',
            'model': 'gpt-4'
        }

        cleaner = self._create_cleaner()

        with patch('services.reload.dependency_cache_cleaner.AIServiceFactory') as mock_factory:
            cleared = await cleaner._clear_provider_cache(adapter_config)

            # Verify AIServiceFactory.clear_cache was called with correct args
            mock_factory.clear_cache.assert_called_once()
            call_kwargs = mock_factory.clear_cache.call_args
            # Check it was called with ServiceType.INFERENCE and provider='openai'
            assert call_kwargs[1]['provider'] == 'openai'

    @pytest.mark.asyncio
    async def test_embedding_cache_clear_calls_factory_clear(self):
        """Test that clearing embedding cache also clears AIServiceFactory cache"""
        adapter_config = {
            'embedding_provider': 'openai'
        }

        cleaner = self._create_cleaner()

        with patch('services.reload.dependency_cache_cleaner.AIServiceFactory') as mock_factory:
            cleared = await cleaner._clear_embedding_cache(adapter_config)

            mock_factory.clear_cache.assert_called_once()
            call_kwargs = mock_factory.clear_cache.call_args
            assert call_kwargs[1]['provider'] == 'openai'

    @pytest.mark.asyncio
    async def test_audio_cache_clear_calls_factory_clear(self):
        """Test that clearing audio cache also clears AIServiceFactory cache"""
        adapter_config = {
            'audio_provider': 'openai'
        }

        cleaner = self._create_cleaner()

        with patch('services.reload.dependency_cache_cleaner.AIServiceFactory') as mock_factory:
            cleared = await cleaner._clear_audio_cache(adapter_config)

            mock_factory.clear_cache.assert_called_once()
            call_kwargs = mock_factory.clear_cache.call_args
            assert call_kwargs[1]['provider'] == 'openai'

    @pytest.mark.asyncio
    async def test_all_providers_clear_factory_cache(self):
        """Test that all provider cache clears also clear AIServiceFactory cache"""
        adapter_config = {
            'inference_provider': 'ollama',
            'embedding_provider': 'cohere',
            'reranker_provider': 'cohere',
            'vision_provider': 'openai',
            'audio_provider': 'openai'
        }

        cleaner = self._create_cleaner()

        with patch('services.reload.dependency_cache_cleaner.AIServiceFactory') as mock_factory:
            await cleaner.clear_adapter_dependencies('test_adapter', adapter_config)

            # Should be called once for each provider type
            assert mock_factory.clear_cache.call_count == 5


class TestPipelineChatServiceSharedAdapterManager:
    """Tests for verifying PipelineChatService uses shared adapter manager correctly"""

    def test_pipeline_chat_service_uses_shared_adapter_manager(self):
        """Test that PipelineChatService uses the shared adapter manager when provided"""
        from services.pipeline_chat_service import PipelineChatService
        from services.config.adapter_config_manager import AdapterConfigManager

        # Create a mock DynamicAdapterManager (without base_adapter_manager attribute)
        mock_adapter_manager = Mock(spec=['get_adapter_config', 'config_manager'])
        del mock_adapter_manager.base_adapter_manager  # Ensure it doesn't have this attribute
        mock_config_manager = AdapterConfigManager({
            'adapters': [{'name': 'test-adapter', 'inference_provider': 'openai'}]
        })
        mock_adapter_manager.config_manager = mock_config_manager
        mock_adapter_manager.get_adapter_config = Mock(
            return_value={'name': 'test-adapter', 'inference_provider': 'openai'}
        )

        # Create PipelineChatService with shared adapter manager
        config = {'general': {'inference_provider': 'ollama'}}
        mock_logger = Mock()

        with patch('services.pipeline_chat_service.PipelineFactory'):
            service = PipelineChatService(
                config=config,
                logger_service=mock_logger,
                adapter_manager=mock_adapter_manager
            )

            # Verify the context builder uses the shared adapter manager
            result = service.context_builder.get_adapter_config('test-adapter')
            mock_adapter_manager.get_adapter_config.assert_called_with('test-adapter')

    def test_pipeline_chat_service_extracts_base_adapter_manager(self):
        """Test that PipelineChatService extracts base_adapter_manager from FaultTolerantAdapterManager"""
        from services.pipeline_chat_service import PipelineChatService

        # Create a mock FaultTolerantAdapterManager
        mock_base_manager = Mock()
        mock_base_manager.get_adapter_config = Mock(return_value={'inference_provider': 'openai'})

        mock_fault_tolerant_manager = Mock()
        mock_fault_tolerant_manager.base_adapter_manager = mock_base_manager

        config = {'general': {'inference_provider': 'ollama'}}
        mock_logger = Mock()

        with patch('services.pipeline_chat_service.PipelineFactory'):
            service = PipelineChatService(
                config=config,
                logger_service=mock_logger,
                adapter_manager=mock_fault_tolerant_manager
            )

            # Verify the context builder uses the base_adapter_manager
            result = service.context_builder.get_adapter_config('test-adapter')
            mock_base_manager.get_adapter_config.assert_called_with('test-adapter')

    def test_request_context_builder_sees_config_changes_after_reload(self):
        """Test that RequestContextBuilder sees config changes when using shared adapter manager"""
        from services.chat_handlers import RequestContextBuilder
        from services.config.adapter_config_manager import AdapterConfigManager

        # Create a config manager with initial config
        config_manager = AdapterConfigManager({
            'adapters': [{'name': 'test-adapter', 'inference_provider': 'deepseek', 'enabled': True}]
        })

        # Create a mock adapter manager that uses this config manager
        mock_adapter_manager = Mock()
        mock_adapter_manager.config_manager = config_manager
        mock_adapter_manager.get_adapter_config = Mock(
            side_effect=lambda name: config_manager.get(name)
        )

        # Create RequestContextBuilder
        builder = RequestContextBuilder(
            config={'general': {}},
            adapter_manager=mock_adapter_manager
        )

        # Verify initial config
        initial_provider = builder.get_inference_provider('test-adapter')
        assert initial_provider == 'deepseek'

        # Simulate config reload - update the config_manager
        config_manager.put('test-adapter', {
            'name': 'test-adapter',
            'inference_provider': 'openai',
            'enabled': True
        })

        # Verify the builder now sees the updated config
        updated_provider = builder.get_inference_provider('test-adapter')
        assert updated_provider == 'openai', \
            f"Expected 'openai' after config reload, but got '{updated_provider}'"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
