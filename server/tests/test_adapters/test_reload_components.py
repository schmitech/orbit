"""
Unit tests for reload components.

Tests:
- DependencyCacheCleaner
- AdapterReloader
"""

import pytest
import sys
import os
from unittest.mock import Mock, AsyncMock, patch

# Add the server directory to the Python path for imports.
_server_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

# server/tests/inference/ shadows server/inference/.  Pre-load the real
# inference package from server/ to prevent the shadow package being used.
import importlib
_tests_dir = os.path.join(_server_dir, 'tests')
if 'inference' not in sys.modules or not hasattr(sys.modules.get('inference'), 'pipeline_factory'):
    for _k in [k for k in sys.modules if k == 'inference' or k.startswith('inference.')]:
        del sys.modules[_k]
    _saved = sys.path.copy()
    sys.path = [p for p in sys.path if os.path.normpath(p) != os.path.normpath(_tests_dir)]
    sys.path.insert(0, _server_dir)
    importlib.invalidate_caches()
    import inference  # noqa: F811 — force correct resolution
    sys.path = _saved

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
        self.embedding_cache.remove.assert_called_once_with('openai:text-embedding-3-small', close_service=False)
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

    @pytest.mark.asyncio
    async def test_retrieval_services_skip_global_defaults_when_capabilities_disable_retrieval(self):
        """Passthrough adapters should not preload global embedding/reranker/vision defaults."""
        self.config.update({
            'embedding': {'enabled': True, 'provider': 'openai'},
            'reranker': {'enabled': True, 'provider': 'cohere'},
            'vision': {'enabled': True, 'provider': 'gemini'},
        })
        adapter_config = {
            'name': 'simple_chat',
            'enabled': True,
            'type': 'passthrough',
            'capabilities': {'retrieval_behavior': 'none'},
            'implementation': 'retrievers.passthrough.PassthroughRetriever'
        }

        loader = self._create_loader()

        mock_retriever = Mock()
        mock_retriever.domain_adapter = None
        with patch.object(loader, '_create_adapter_sync', return_value=mock_retriever):
            await loader.load_adapter('simple_chat', adapter_config)

        self.embedding_cache.create_service.assert_not_awaited()
        self.reranker_cache.create_service.assert_not_awaited()
        self.vision_cache.create_service.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_retrieval_services_use_global_defaults_when_capabilities_enable_retrieval(self):
        """Retrieval adapters may still preload global service defaults."""
        self.config.update({
            'embedding': {'enabled': True, 'provider': 'openai'},
            'reranker': {'enabled': True, 'provider': 'cohere'},
            'vision': {'enabled': True, 'provider': 'gemini'},
        })
        adapter_config = {
            'name': 'retrieval_adapter',
            'enabled': True,
            'type': 'retriever',
            'capabilities': {'retrieval_behavior': 'always'},
            'implementation': 'retrievers.passthrough.PassthroughRetriever'
        }

        loader = self._create_loader()

        mock_retriever = Mock()
        mock_retriever.domain_adapter = None
        with patch.object(loader, '_create_adapter_sync', return_value=mock_retriever):
            await loader.load_adapter('retrieval_adapter', adapter_config)

        self.embedding_cache.create_service.assert_awaited_once_with('openai', 'retrieval_adapter')
        self.reranker_cache.create_service.assert_awaited_once_with('cohere', 'retrieval_adapter')
        self.vision_cache.create_service.assert_awaited_once_with('gemini', 'retrieval_adapter')

    @pytest.mark.asyncio
    async def test_image_video_services_do_not_use_global_defaults(self):
        """Image/video generation preload should require adapter-level providers."""
        self.config.update({
            'image': {'enabled': True, 'provider': 'gemini'},
            'video': {'enabled': True, 'provider': 'xai'},
        })
        adapter_config = {
            'name': 'simple_chat',
            'enabled': True,
            'type': 'passthrough',
            'capabilities': {'retrieval_behavior': 'none'},
            'implementation': 'retrievers.passthrough.PassthroughRetriever'
        }
        adapter_manager = Mock()
        adapter_manager.get_image_service = AsyncMock()
        adapter_manager.get_video_service = AsyncMock()

        from services.loader.adapter_loader import AdapterLoader
        loader = AdapterLoader(
            self.config,
            self.app_state,
            self.provider_cache,
            self.embedding_cache,
            self.reranker_cache,
            self.vision_cache,
            self.audio_cache,
            adapter_manager=adapter_manager,
        )

        mock_retriever = Mock()
        mock_retriever.domain_adapter = None
        with patch.object(loader, '_create_adapter_sync', return_value=mock_retriever):
            await loader.load_adapter('simple_chat', adapter_config)

        adapter_manager.get_image_service.assert_not_awaited()
        adapter_manager.get_video_service.assert_not_awaited()


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
    async def test_clear_stt_cache_does_not_use_global_default(self):
        """STT cleanup should match loader behavior and only clear explicit providers."""
        self.config['stt'] = {'provider': 'whisper'}
        adapter_config = {'name': 'test_adapter'}

        cleaner = self._create_cleaner()
        cleared = await cleaner._clear_stt_cache(adapter_config)

        self.audio_cache.remove.assert_not_awaited()
        assert cleared == []

    @pytest.mark.asyncio
    async def test_clear_tts_cache_does_not_use_global_default(self):
        """TTS cleanup should match loader behavior and only clear explicit providers."""
        self.config['tts'] = {'provider': 'openai'}
        adapter_config = {'name': 'test_adapter'}

        cleaner = self._create_cleaner()
        cleared = await cleaner._clear_tts_cache(adapter_config)

        self.audio_cache.remove.assert_not_awaited()
        assert cleared == []

    @pytest.mark.asyncio
    async def test_clear_retrieval_caches_skip_global_defaults_when_capabilities_disable_retrieval(self):
        """Retrieval cleanup should not evict global caches for passthrough adapters."""
        self.config.update({
            'embedding': {'provider': 'openai'},
            'reranker': {'provider': 'cohere'},
            'vision': {'provider': 'gemini'},
        })
        adapter_config = {
            'name': 'simple_chat',
            'type': 'passthrough',
            'capabilities': {'retrieval_behavior': 'none'},
        }

        cleaner = self._create_cleaner()

        embedding_cleared = await cleaner._clear_embedding_cache(adapter_config)
        reranker_cleared = await cleaner._clear_reranker_cache(adapter_config)
        vision_cleared = await cleaner._clear_vision_cache(adapter_config)

        self.embedding_cache.build_cache_key.assert_not_called()
        self.reranker_cache.build_cache_key.assert_not_called()
        self.vision_cache.build_cache_key.assert_not_called()
        assert embedding_cleared == []
        assert reranker_cleared == []
        assert vision_cleared == []

    @pytest.mark.asyncio
    async def test_clear_audio_cache_does_not_use_global_default(self):
        """Audio cleanup should match loader behavior and only clear explicit providers."""
        self.config['sound'] = {'provider': 'openai'}
        adapter_config = {'name': 'test_adapter'}

        cleaner = self._create_cleaner()
        cleared = await cleaner._clear_audio_cache(adapter_config)

        self.audio_cache.remove.assert_not_awaited()
        assert cleared == []

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

        await cleaner.clear_adapter_dependencies('test_adapter', adapter_config)

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
            await cleaner._clear_provider_cache(adapter_config)

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
            await cleaner._clear_embedding_cache(adapter_config)

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
            await cleaner._clear_audio_cache(adapter_config)

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
            service.context_builder.get_adapter_config('test-adapter')
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
            service.context_builder.get_adapter_config('test-adapter')
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


class TestDatasourceConfigIsolationDuringReload:
    """Regression: datasource invalidation must use the config held at cleanup time.

    Before the fix, reload_adapter_configs() called dependency_cleaner.update_config(new)
    before running cleanup. If the global datasource URL changed (e.g. postgres
    database: db_old → db_new), the cleaner built the cache key from db_new and missed
    the still-pooled db_old connection.

    The fix defers update_config() to a finally block after the reloader runs.
    These tests cover the layer below: DependencyCacheCleaner._clear_datasource_cache
    forwards self.config (whatever it holds at call time) to invalidate_datasource.
    """

    def _make_minimal_cleaner(self, config):
        from services.reload.dependency_cache_cleaner import DependencyCacheCleaner
        provider_cache = Mock()
        provider_cache.build_cache_key = Mock(return_value='provider:test')
        provider_cache.contains = Mock(return_value=False)
        provider_cache.remove_by_prefix = AsyncMock(return_value=[])
        embedding_cache = Mock()
        embedding_cache.build_cache_key = Mock(return_value='embedding:test')
        embedding_cache.contains = Mock(return_value=False)
        reranker_cache = Mock()
        reranker_cache.build_cache_key = Mock(return_value='reranker:test')
        reranker_cache.contains = Mock(return_value=False)
        return DependencyCacheCleaner(config, provider_cache, embedding_cache, reranker_cache)

    def _mock_registry_module(self, invalidate_fn):
        """Return a mock datasources.registry module whose get_registry() yields invalidate_fn."""
        mock_registry = Mock()
        mock_registry.invalidate_datasource = invalidate_fn
        mock_module = Mock()
        mock_module.get_registry.return_value = mock_registry
        return mock_module

    @pytest.mark.asyncio
    async def test_invalidate_receives_config_held_at_call_time(self):
        """_clear_datasource_cache passes self.config — whatever the cleaner holds right now.

        This is the contract the ordering fix relies on: as long as update_config() is
        deferred until after cleanup, the old cache key is resolved correctly.
        """
        old_config = {
            'datasources': {
                'postgres': {'host': 'db-host', 'port': 5432, 'database': 'db_old', 'username': 'appuser'}
            }
        }
        cleaner = self._make_minimal_cleaner(old_config)
        adapter_config = {'datasource': 'postgres'}

        configs_seen = []

        async def capture(datasource_name, config, database_override=None):
            configs_seen.append(config)
            return 'postgres:db-host:5432:db_old:appuser'

        with patch.dict(sys.modules, {'datasources.registry': self._mock_registry_module(capture)}):
            cleared = await cleaner._clear_datasource_cache('my_adapter', adapter_config)

        assert len(configs_seen) == 1
        assert configs_seen[0] is old_config
        assert cleared == ['datasource:postgres:db-host:5432:db_old:appuser']

    @pytest.mark.asyncio
    async def test_stale_connection_missed_when_update_config_runs_before_cleanup(self):
        """Demonstrates the bug: update_config(new) before cleanup misses the old pooled entry.

        The pool only contains an entry keyed by db_old. After premature update_config(new),
        the cleaner asks the registry to invalidate db_new — a miss — and the old stale
        connection is never released.
        """
        old_config = {
            'datasources': {
                'postgres': {'host': 'db-host', 'port': 5432, 'database': 'db_old', 'username': 'appuser'}
            }
        }
        new_config = {
            'datasources': {
                'postgres': {'host': 'db-host', 'port': 5432, 'database': 'db_new', 'username': 'appuser'}
            }
        }
        cleaner = self._make_minimal_cleaner(old_config)
        # Simulate the pre-fix bug: update config before cleanup runs
        cleaner.update_config(new_config)

        adapter_config = {'datasource': 'postgres'}

        async def pool_lookup(datasource_name, config, database_override=None):
            db = config.get('datasources', {}).get(datasource_name, {}).get('database')
            if db == 'db_old':
                return 'postgres:db-host:5432:db_old:appuser'
            return None  # db_new not in pool — miss

        with patch.dict(sys.modules, {'datasources.registry': self._mock_registry_module(pool_lookup)}):
            cleared = await cleaner._clear_datasource_cache('my_adapter', adapter_config)

        # With premature update_config the old connection is NOT released
        assert cleared == []

    @pytest.mark.asyncio
    async def test_old_pool_entry_released_when_config_not_yet_updated(self):
        """Old pooled connection is released when cleanup runs before update_config (post-fix).

        The cleaner still holds old_config, so the cache key resolves to db_old, which
        is present in the pool. The stale connection is correctly released.
        """
        old_config = {
            'datasources': {
                'postgres': {'host': 'db-host', 'port': 5432, 'database': 'db_old', 'username': 'appuser'}
            }
        }
        cleaner = self._make_minimal_cleaner(old_config)
        # Config is NOT updated before cleanup — this is the fix
        adapter_config = {'datasource': 'postgres'}

        OLD_KEY = 'postgres:db-host:5432:db_old:appuser'

        async def pool_lookup(datasource_name, config, database_override=None):
            db = config.get('datasources', {}).get(datasource_name, {}).get('database')
            if db == 'db_old':
                return OLD_KEY
            return None

        with patch.dict(sys.modules, {'datasources.registry': self._mock_registry_module(pool_lookup)}):
            cleared = await cleaner._clear_datasource_cache('my_adapter', adapter_config)

        # With deferred update_config the old connection IS released
        assert cleared == ['datasource:' + OLD_KEY]


class TestReloadAdapterConfigsOrdering:
    """Verify reload_adapter_configs() defers dependency_cleaner.update_config until after cleanup.

    This tests the orchestration-level fix: the DynamicAdapterManager must not call
    dependency_cleaner.update_config(new) until after the reloader (and its cleanup
    calls) have finished running.
    """

    def _make_manager(self, old_config):
        """Build a DynamicAdapterManager with all init methods patched out."""
        from services.dynamic_adapter_manager import DynamicAdapterManager

        with patch.object(DynamicAdapterManager, '_init_cache_managers'), \
             patch.object(DynamicAdapterManager, '_init_config_manager'), \
             patch.object(DynamicAdapterManager, '_init_loader'), \
             patch.object(DynamicAdapterManager, '_init_reloader'):
            manager = DynamicAdapterManager(old_config)

        manager.adapter_loader = Mock()
        manager.adapter_loader.update_config = Mock()
        manager.config_manager = Mock()
        manager.config_manager.config = old_config
        manager.dependency_cleaner = Mock()
        manager.dependency_cleaner.config = old_config
        manager.dependency_cleaner.update_config = Mock(
            side_effect=lambda c: setattr(manager.dependency_cleaner, 'config', c)
        )
        manager.reloader = Mock()
        return manager

    @pytest.mark.asyncio
    async def test_dependency_cleaner_holds_old_config_when_reload_runs(self):
        """dependency_cleaner.config is still old_config when reload_single_adapter is called."""
        old_config = {'datasources': {'postgres': {'database': 'db_old'}}, 'adapters': []}
        new_config = {'datasources': {'postgres': {'database': 'db_new'}}, 'adapters': []}

        manager = self._make_manager(old_config)

        config_at_reload_time = {}

        async def capture_reload(adapter_name, config):
            config_at_reload_time['cleaner'] = manager.dependency_cleaner.config
            return {'action': 'updated'}

        manager.reloader.reload_single_adapter = capture_reload

        await manager.reload_adapter_configs(new_config, adapter_name='my_adapter')

        # Cleaner still held old_config when reload (and cleanup) ran
        assert config_at_reload_time['cleaner'] is old_config
        # Cleaner was updated to new_config afterwards
        assert manager.dependency_cleaner.config is new_config

    @pytest.mark.asyncio
    async def test_dependency_cleaner_updated_after_reload_all(self):
        """dependency_cleaner.update_config is called after reload_all_adapters completes."""
        old_config = {'datasources': {'postgres': {'database': 'db_old'}}, 'adapters': []}
        new_config = {'datasources': {'postgres': {'database': 'db_new'}}, 'adapters': []}

        manager = self._make_manager(old_config)

        call_order = []
        manager.dependency_cleaner.update_config = Mock(
            side_effect=lambda c: call_order.append('update_config')
        )

        async def track_reload(config):
            call_order.append('reload_all')
            return {'added': 0, 'removed': 0, 'updated': 0, 'unchanged': 0, 'total': 0,
                    'added_names': [], 'removed_names': [], 'updated_names': []}

        manager.reloader.reload_all_adapters = track_reload

        await manager.reload_adapter_configs(new_config)

        assert call_order == ['reload_all', 'update_config']

    @pytest.mark.asyncio
    async def test_dependency_cleaner_updated_even_if_reload_raises(self):
        """update_config runs in a finally block — it fires even when reload raises."""
        old_config = {'adapters': []}
        new_config = {'adapters': []}

        manager = self._make_manager(old_config)
        manager.reloader.reload_all_adapters = AsyncMock(side_effect=RuntimeError("reload failed"))

        with pytest.raises(RuntimeError, match="reload failed"):
            await manager.reload_adapter_configs(new_config)

        # update_config still ran despite the exception
        manager.dependency_cleaner.update_config.assert_called_once_with(new_config)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
