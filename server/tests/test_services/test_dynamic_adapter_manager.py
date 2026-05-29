"""
Unit tests for DynamicAdapterManager.

Focuses on the business logic that lives directly in DynamicAdapterManager:
- _build_adapter_info_parts (shared info builder)
- _build_preload_success_message
- _build_preload_error_result
- _handle_adapter_load_error
- get_allowed_models
- reload_templates (single and bulk paths)
- AdapterProxy delegation
"""

import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from services.dynamic_adapter_manager import DynamicAdapterManager, AdapterProxy


# ---------------------------------------------------------------------------
# Fixture: a DynamicAdapterManager with all heavy components mocked out
# ---------------------------------------------------------------------------

@pytest.fixture
def manager():
    """DynamicAdapterManager with all sub-components replaced by MagicMocks."""
    config = {
        'general': {'inference_provider': 'ollama'},
        'embedding': {'provider': 'ollama'},
        'embeddings': {'ollama': {'model': 'nomic-embed-text'}},
        'rerankers': {'cross-encoder': {'model': 'cross-encoder/ms-marco'}},
    }

    with patch.object(DynamicAdapterManager, '_init_cache_managers', lambda self: None), \
         patch.object(DynamicAdapterManager, '_init_config_manager', lambda self: None), \
         patch.object(DynamicAdapterManager, '_init_loader', lambda self: None), \
         patch.object(DynamicAdapterManager, '_init_reloader', lambda self: None), \
         patch('services.dynamic_adapter_manager.ThreadPoolExecutor', return_value=MagicMock()):
        mgr = DynamicAdapterManager(config)

    mgr.adapter_cache = MagicMock()
    mgr.provider_cache = MagicMock()
    mgr.embedding_cache = MagicMock()
    mgr.reranker_cache = MagicMock()
    mgr.vision_cache = MagicMock()
    mgr.audio_cache = MagicMock()
    mgr.config_manager = MagicMock()
    mgr.adapter_loader = MagicMock()
    mgr.dependency_cleaner = MagicMock()
    mgr.reloader = MagicMock()
    mgr._thread_pool = MagicMock()

    return mgr


# ---------------------------------------------------------------------------
# _build_adapter_info_parts
# ---------------------------------------------------------------------------

class TestBuildAdapterInfoParts:

    def test_minimal_config_uses_defaults(self, manager):
        """Falls back to general.inference_provider and embedding.provider."""
        parts = manager._build_adapter_info_parts({})
        assert any(p.startswith("inference: ollama") for p in parts)
        assert any(p.startswith("embedding: ollama") for p in parts)

    def test_inference_with_model_override(self, manager):
        parts = manager._build_adapter_info_parts({'model': 'llama3'})
        assert "inference: ollama/llama3" in parts

    def test_inference_without_model_override(self, manager):
        parts = manager._build_adapter_info_parts({})
        assert "inference: ollama" in parts

    def test_embedding_with_configured_model(self, manager):
        """When the embedding provider is in config.embeddings, its model appears."""
        parts = manager._build_adapter_info_parts({'embedding_provider': 'ollama'})
        assert "embedding: ollama/nomic-embed-text" in parts

    def test_embedding_without_model(self, manager):
        """Unknown embedding provider shows provider name only."""
        parts = manager._build_adapter_info_parts({'embedding_provider': 'unknown-provider'})
        assert "embedding: unknown-provider" in parts

    def test_reranker_with_model(self, manager):
        parts = manager._build_adapter_info_parts({'reranker_provider': 'cross-encoder'})
        assert "reranker: cross-encoder/cross-encoder/ms-marco" in parts

    def test_reranker_without_model(self, manager):
        """Reranker provider not in config shows provider name only."""
        parts = manager._build_adapter_info_parts({'reranker_provider': 'unknown-reranker'})
        assert "reranker: unknown-reranker" in parts

    def test_no_reranker_field_omitted(self, manager):
        parts = manager._build_adapter_info_parts({})
        assert not any(p.startswith("reranker:") for p in parts)

    def test_intent_adapter_with_store_name(self, manager):
        parts = manager._build_adapter_info_parts({
            'adapter': 'intent',
            'config': {'store_name': 'movies-store'}
        })
        assert "store: movies-store" in parts

    def test_intent_adapter_without_store_name(self, manager):
        parts = manager._build_adapter_info_parts({'adapter': 'intent', 'config': {}})
        assert not any(p.startswith("store:") for p in parts)

    def test_non_intent_adapter_no_store(self, manager):
        parts = manager._build_adapter_info_parts({
            'adapter': 'passthrough',
            'config': {'store_name': 'should-be-ignored'}
        })
        assert not any(p.startswith("store:") for p in parts)


# ---------------------------------------------------------------------------
# _build_preload_success_message
# ---------------------------------------------------------------------------

class TestBuildPreloadSuccessMessage:

    def test_message_starts_with_preloaded(self, manager):
        msg = manager._build_preload_success_message("my-adapter", {})
        assert msg.startswith("Preloaded successfully (")
        assert msg.endswith(")")

    def test_message_contains_inference_info(self, manager):
        msg = manager._build_preload_success_message("my-adapter", {'model': 'gpt-4'})
        assert "inference: ollama/gpt-4" in msg


# ---------------------------------------------------------------------------
# _build_preload_error_result
# ---------------------------------------------------------------------------

class TestBuildPreloadErrorResult:

    def test_provider_not_registered_error(self, manager):
        manager.config_manager.get.return_value = {'inference_provider': 'vllm'}
        error = ValueError("No service registered for inference with provider 'vllm'")

        result = manager._build_preload_error_result("my-adapter", error)

        assert result["success"] is False
        assert result["adapter_name"] == "my-adapter"
        assert "vllm" in result["error"]
        assert "disabled" in result["error"]

    def test_generic_error(self, manager):
        error = ValueError("Something else went wrong")

        result = manager._build_preload_error_result("my-adapter", error)

        assert result["success"] is False
        assert result["adapter_name"] == "my-adapter"
        assert result["error"] == "Something else went wrong"

    def test_provider_error_falls_back_to_general_provider(self, manager):
        """When adapter config has no inference_provider, falls back to general config."""
        manager.config_manager.get.return_value = {}
        error = ValueError("No service registered for inference with provider 'x'")

        result = manager._build_preload_error_result("my-adapter", error)

        assert "ollama" in result["error"]  # general.inference_provider default


# ---------------------------------------------------------------------------
# _handle_adapter_load_error
# ---------------------------------------------------------------------------

class TestHandleAdapterLoadError:

    def test_provider_error_raises_with_clear_message(self, manager):
        manager.config_manager.get.return_value = {'inference_provider': 'vllm'}
        original = ValueError("No service registered for inference with provider 'vllm'")

        with pytest.raises(ValueError, match="provider 'vllm' is disabled"):
            manager._handle_adapter_load_error("my-adapter", original)

    def test_other_error_does_not_raise(self, manager):
        """Generic ValueErrors are logged but not re-raised."""
        error = ValueError("Some other issue")
        manager._handle_adapter_load_error("my-adapter", error)  # should not raise


# ---------------------------------------------------------------------------
# get_allowed_models
# ---------------------------------------------------------------------------

class TestGetAllowedModels:

    def test_returns_allowed_models_list(self, manager):
        models = [{"name": "gpt-4", "provider": "openai", "model": "gpt-4"}]
        manager.config_manager.get.return_value = {'allowed_models': models}

        result = manager.get_allowed_models("my-adapter")

        assert result == models

    def test_returns_empty_list_when_adapter_not_found(self, manager):
        manager.config_manager.get.return_value = None
        assert manager.get_allowed_models("missing") == []

    def test_returns_empty_list_when_field_absent(self, manager):
        manager.config_manager.get.return_value = {}
        assert manager.get_allowed_models("my-adapter") == []


# ---------------------------------------------------------------------------
# reload_templates
# ---------------------------------------------------------------------------

class TestReloadTemplates:

    @pytest.mark.asyncio
    async def test_single_adapter_not_in_cache_raises(self, manager):
        manager.adapter_cache.contains.return_value = False

        with pytest.raises(ValueError, match="not found in cache"):
            await manager.reload_templates("missing-adapter")

    @pytest.mark.asyncio
    async def test_single_adapter_without_reload_templates_raises(self, manager):
        manager.adapter_cache.contains.return_value = True
        adapter = MagicMock(spec=[])  # no reload_templates attribute
        manager.adapter_cache.get.return_value = adapter

        with pytest.raises(ValueError, match="does not support template reloading"):
            await manager.reload_templates("passthrough-adapter")

    @pytest.mark.asyncio
    async def test_single_adapter_calls_reload_and_updates_summary(self, manager):
        manager.adapter_cache.contains.return_value = True
        adapter = MagicMock()
        adapter.reload_templates = AsyncMock(return_value={'templates_loaded': 7})
        manager.adapter_cache.get.return_value = adapter

        summary = await manager.reload_templates("intent-adapter")

        adapter.reload_templates.assert_awaited_once()
        assert summary['templates_loaded'] == 7
        assert "intent-adapter" in summary['adapters_updated']
        assert 'details' in summary

    @pytest.mark.asyncio
    async def test_bulk_reload_skips_non_intent_adapters(self, manager):
        intent_adapter = MagicMock()
        intent_adapter.reload_templates = AsyncMock(return_value={'templates_loaded': 3})

        passthrough_adapter = MagicMock(spec=[])  # no reload_templates

        manager.adapter_cache.get_cached_names.return_value = ["intent-one", "pass-one"]
        manager.adapter_cache.get.side_effect = lambda name: (
            intent_adapter if name == "intent-one" else passthrough_adapter
        )

        summary = await manager.reload_templates()

        assert summary['templates_loaded'] == 3
        assert summary['adapters_updated'] == ["intent-one"]
        assert summary['errors'] == []

    @pytest.mark.asyncio
    async def test_bulk_reload_records_errors_and_continues(self, manager):
        bad_adapter = MagicMock()
        bad_adapter.reload_templates = AsyncMock(side_effect=RuntimeError("disk full"))

        good_adapter = MagicMock()
        good_adapter.reload_templates = AsyncMock(return_value={'templates_loaded': 2})

        manager.adapter_cache.get_cached_names.return_value = ["bad", "good"]
        manager.adapter_cache.get.side_effect = lambda name: (
            bad_adapter if name == "bad" else good_adapter
        )

        summary = await manager.reload_templates()

        assert summary['templates_loaded'] == 2
        assert "good" in summary['adapters_updated']
        assert len(summary['errors']) == 1
        assert "bad" in summary['errors'][0]


# ---------------------------------------------------------------------------
# AdapterProxy
# ---------------------------------------------------------------------------

class TestAdapterProxy:

    @pytest.fixture
    def proxy(self, manager):
        return AdapterProxy(manager)

    @pytest.mark.asyncio
    async def test_get_relevant_context_delegates_to_adapter(self, proxy, manager):
        adapter = MagicMock()
        adapter.get_relevant_context = AsyncMock(return_value=[{"doc": "result"}])
        manager.get_adapter = AsyncMock(return_value=adapter)

        result = await proxy.get_relevant_context("my query", "my-adapter")

        manager.get_adapter.assert_awaited_once_with("my-adapter")
        assert result == [{"doc": "result"}]

    @pytest.mark.asyncio
    async def test_get_relevant_context_returns_empty_on_error(self, proxy, manager):
        manager.get_adapter = AsyncMock(side_effect=RuntimeError("adapter crashed"))

        result = await proxy.get_relevant_context("query", "bad-adapter")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_relevant_context_empty_adapter_name_raises(self, proxy):
        with pytest.raises(ValueError, match="Adapter name is required"):
            await proxy.get_relevant_context("query", "")
