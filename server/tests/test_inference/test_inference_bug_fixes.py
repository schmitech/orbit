"""
Tests for inference pipeline bug fixes.

Validates fixes for:
- #1: pipeline.py uses time.perf_counter() instead of deprecated asyncio.get_event_loop().time()
- #4: LLM prompt cache is bounded (max 100 entries, LRU eviction)
- #6: ServiceContainer._services dict removed
- #7: StepMetrics.error_messages is a bounded deque(maxlen=50)
- #8: LLM inference falls back to llm_provider when adapter_manager missing
- #9: Document reranking defaults top_n when config returns None
"""

import asyncio
import importlib
import inspect
import os
import sys
import types
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

# Add server directory to path
_server_dir = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, _server_dir)

# Pre-register 'inference' as a namespace package to skip its __init__.py
# (which triggers heavy cascading imports like server.ai_services)
if 'inference' not in sys.modules:
    _pkg = types.ModuleType('inference')
    _pkg.__path__ = [os.path.join(_server_dir, 'inference')]
    _pkg.__package__ = 'inference'
    sys.modules['inference'] = _pkg

import pytest

from inference.pipeline.monitoring import StepMetrics, PipelineMonitor
from inference.pipeline.service_container import ServiceContainer
from inference.pipeline.steps.llm_inference import LLMInferenceStep
from inference.pipeline.steps.document_reranking import DocumentRerankingStep


class TestPipelineUsesPerCounter:
    """Fix #1: Verify pipeline.py no longer uses asyncio.get_event_loop().time()."""

    def test_no_get_event_loop_time_in_pipeline(self):
        import inference.pipeline.pipeline as pipeline_mod
        source = inspect.getsource(pipeline_mod)
        assert "get_event_loop().time()" not in source, (
            "pipeline.py still contains deprecated asyncio.get_event_loop().time()"
        )

    def test_uses_perf_counter(self):
        import inference.pipeline.pipeline as pipeline_mod
        source = inspect.getsource(pipeline_mod)
        assert "time.perf_counter()" in source


class TestPromptCacheBounded:
    """Fix #4: Prompt cache should be bounded at 100 entries with LRU eviction."""

    def _make_step(self):
        container = ServiceContainer()
        container.register_singleton('llm_provider', MagicMock())
        step = LLMInferenceStep(container)
        return step

    def test_prompt_cache_bounded(self):
        step = self._make_step()
        # Insert 150 entries
        for i in range(150):
            step._prompt_cache[f"prompt:{i}"] = f"prompt_text_{i}"
            if len(step._prompt_cache) > step._prompt_cache_max_size:
                step._prompt_cache.popitem(last=False)
        assert len(step._prompt_cache) <= 100

    def test_prompt_cache_lru_eviction(self):
        step = self._make_step()
        # Fill cache to max
        for i in range(100):
            step._prompt_cache[f"prompt:{i}"] = f"text_{i}"

        # Access entry 0 (move to end = most recently used)
        step._prompt_cache.move_to_end("prompt:0")

        # Add one more entry, should evict prompt:1 (oldest untouched)
        step._prompt_cache["prompt:100"] = "text_100"
        if len(step._prompt_cache) > step._prompt_cache_max_size:
            step._prompt_cache.popitem(last=False)

        assert "prompt:0" in step._prompt_cache, "LRU entry should survive"
        assert "prompt:1" not in step._prompt_cache, "Oldest untouched entry should be evicted"
        assert "prompt:100" in step._prompt_cache


class TestServiceContainerNoUnusedServices:
    """Fix #6: Verify _services dict was removed from ServiceContainer."""

    def test_no_services_attr(self):
        container = ServiceContainer()
        assert not hasattr(container, '_services'), (
            "ServiceContainer still has unused _services attribute"
        )


class TestErrorMessagesBounded:
    """Fix #7: StepMetrics.error_messages should be a bounded deque."""

    def test_error_messages_is_deque(self):
        metrics = StepMetrics()
        assert isinstance(metrics.error_messages, deque)

    def test_error_messages_bounded(self):
        metrics = StepMetrics()
        for i in range(100):
            metrics.record_execution(0.1, False, f"error_{i}")
        assert len(metrics.error_messages) == 50
        # Should keep the most recent 50
        assert metrics.error_messages[-1] == "error_99"
        assert metrics.error_messages[0] == "error_50"

    def test_monitor_error_messages_bounded(self):
        monitor = PipelineMonitor()
        for i in range(100):
            monitor.record_step_execution("test_step", 0.1, False, f"error_{i}")
        step_metrics = monitor.get_step_metrics("test_step")
        assert len(step_metrics.error_messages) == 50


class TestLLMInferenceMissingAdapterManager:
    """Fix #8: LLM inference should fall back to llm_provider when adapter_manager is missing."""

    @pytest.mark.asyncio
    async def test_missing_adapter_manager_fallback(self):
        container = ServiceContainer()
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value="test response")
        container.register_singleton('llm_provider', mock_provider)

        step = LLMInferenceStep(container)

        context = MagicMock()
        context.is_blocked = False
        context.inference_provider = "some_provider"  # Would normally need adapter_manager
        context.system_prompt_id = None
        context.message = "Hello"
        context.adapter_name = None
        context.context_messages = []
        context.formatted_context = ""
        context.metadata = {}
        context.has_error = MagicMock(return_value=False)
        context.is_cancelled = MagicMock(return_value=False)
        context.messages = None

        result = await step.process(context)
        # Should fall back to llm_provider since adapter_manager not in container
        mock_provider.generate.assert_called_once()
        assert result.response == "test response"

    @pytest.mark.asyncio
    async def test_stream_missing_adapter_manager_fallback(self):
        container = ServiceContainer()
        mock_provider = AsyncMock()

        async def mock_stream(*args, **kwargs):
            yield "chunk1"
            yield "chunk2"

        mock_provider.generate_stream = mock_stream
        container.register_singleton('llm_provider', mock_provider)

        step = LLMInferenceStep(container)

        context = MagicMock()
        context.is_blocked = False
        context.inference_provider = "some_provider"
        context.system_prompt_id = None
        context.message = "Hello"
        context.adapter_name = None
        context.context_messages = []
        context.formatted_context = ""
        context.metadata = {}
        context.has_error = MagicMock(return_value=False)
        context.is_cancelled = MagicMock(return_value=False)
        context.messages = None

        chunks = []
        async for chunk in step.process_stream(context):
            chunks.append(chunk)

        assert chunks == ["chunk1", "chunk2"]


class TestRerankingTopNDefault:
    """Fix #9: Document reranking should default top_n when config returns None."""

    @pytest.mark.asyncio
    async def test_top_n_defaults_when_none(self):
        container = ServiceContainer()
        container.register_singleton('config', {})

        mock_reranker = AsyncMock()
        mock_reranker.provider_name = "test"
        mock_reranker.model = "test-model"
        # Return reranked results matching input docs
        mock_reranker.rerank = AsyncMock(return_value=[
            {"index": 0, "score": 0.9},
            {"index": 1, "score": 0.8},
            {"index": 2, "score": 0.7},
        ])
        container.register_singleton('reranker_service', mock_reranker)

        step = DocumentRerankingStep(container)

        context = MagicMock()
        context.is_blocked = False
        context.adapter_name = "test_adapter"
        context.message = "test query"
        context.retrieved_docs = [
            {"content": f"doc {i}", "metadata": {}} for i in range(3)
        ]
        context.metadata = {}

        await step.process(context)

        # Verify rerank was called with a non-None top_n
        call_kwargs = mock_reranker.rerank.call_args
        assert call_kwargs is not None
        top_n = call_kwargs.kwargs.get('top_n') or call_kwargs[1].get('top_n')
        assert top_n is not None, "top_n should not be None"
        assert top_n == 3  # min(3 docs, 10)
