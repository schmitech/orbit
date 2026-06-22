"""
Tests for WebSearchStep (server/inference/pipeline/steps/web_search.py).

Coverage:
- should_execute: only fires for type='web-search', skips when blocked or other type
- process: unknown provider sets error, search exception sets error, empty results,
  successful search populates formatted_context and sources
- result formatting: numbered list with title/url/snippet
- provider kwargs forwarding: api_key and extra fields passed through
"""

import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, server_dir)

if 'inference' not in sys.modules:
    _pkg = types.ModuleType('inference')
    _pkg.__path__ = [os.path.join(server_dir, 'inference')]
    _pkg.__package__ = 'inference'
    sys.modules['inference'] = _pkg

from inference.pipeline.base import ProcessingContext
from inference.pipeline.steps.web_search import WebSearchStep


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeContainer:
    def __init__(self, adapter_type: str = 'web-search', ws_config: dict | None = None):
        self._type = adapter_type
        self._ws_config = ws_config or {'provider': 'duckduckgo', 'result_count': 3}

    def has(self, name: str) -> bool:
        return name == 'adapter_manager'

    def get(self, name: str):
        if name == 'adapter_manager':
            mgr = MagicMock()
            mgr.get_adapter_config.return_value = {
                'type': self._type,
                'web_search': self._ws_config,
            }
            return mgr
        raise KeyError(name)


def _make_results(n: int):
    from web_search.base import SearchResult
    return [
        SearchResult(link=f'https://example.com/{i}', title=f'Result {i}', snippet=f'Snippet {i}')
        for i in range(1, n + 1)
    ]


# ---------------------------------------------------------------------------
# should_execute
# ---------------------------------------------------------------------------

class TestWebSearchStepShouldExecute:
    def test_executes_for_web_search_type(self):
        step = WebSearchStep(_FakeContainer(adapter_type='web-search'))
        ctx = ProcessingContext(adapter_name='my-adapter')
        assert step.should_execute(ctx) is True

    def test_skips_for_other_type(self):
        step = WebSearchStep(_FakeContainer(adapter_type='passthrough'))
        ctx = ProcessingContext(adapter_name='my-adapter')
        assert step.should_execute(ctx) is False

    def test_skips_for_fetch_type(self):
        step = WebSearchStep(_FakeContainer(adapter_type='fetch'))
        ctx = ProcessingContext(adapter_name='my-adapter')
        assert step.should_execute(ctx) is False

    def test_skips_when_blocked(self):
        step = WebSearchStep(_FakeContainer(adapter_type='web-search'))
        ctx = ProcessingContext(adapter_name='my-adapter')
        ctx.is_blocked = True
        assert step.should_execute(ctx) is False


# ---------------------------------------------------------------------------
# process: error paths
# ---------------------------------------------------------------------------

class TestWebSearchStepErrors:
    @pytest.mark.asyncio
    async def test_unknown_provider_sets_error(self):
        ws_cfg = {'provider': 'nonexistent_provider', 'result_count': 3}
        step = WebSearchStep(_FakeContainer(ws_config=ws_cfg))
        ctx = ProcessingContext(message='test query', adapter_name='my-adapter')

        result = await step.process(ctx)

        assert result.has_error()
        assert 'nonexistent_provider' in result.error

    @pytest.mark.asyncio
    async def test_search_exception_sets_error(self):
        step = WebSearchStep(_FakeContainer())
        ctx = ProcessingContext(message='test query', adapter_name='my-adapter')

        failing_fn = AsyncMock(side_effect=RuntimeError('network failure'))
        with patch('web_search.registry.get_provider', return_value=failing_fn):
            result = await step.process(ctx)

        assert result.has_error()
        assert 'network failure' in result.error

    @pytest.mark.asyncio
    async def test_empty_results_sets_no_results_message(self):
        step = WebSearchStep(_FakeContainer())
        ctx = ProcessingContext(message='obscure query', adapter_name='my-adapter')

        empty_fn = AsyncMock(return_value=[])
        with patch('web_search.registry.get_provider', return_value=empty_fn):
            result = await step.process(ctx)

        assert not result.has_error()
        assert 'No web search results' in result.formatted_context


# ---------------------------------------------------------------------------
# process: success path
# ---------------------------------------------------------------------------

class TestWebSearchStepSuccess:
    @pytest.mark.asyncio
    async def test_formatted_context_populated(self):
        step = WebSearchStep(_FakeContainer())
        ctx = ProcessingContext(message='what is orbit', adapter_name='my-adapter')

        results = _make_results(2)
        search_fn = AsyncMock(return_value=results)
        with patch('web_search.registry.get_provider', return_value=search_fn):
            result = await step.process(ctx)

        assert not result.has_error()
        assert 'what is orbit' in result.formatted_context
        assert '[1]' in result.formatted_context
        assert '[2]' in result.formatted_context
        assert 'https://example.com/1' in result.formatted_context
        assert 'Snippet 1' in result.formatted_context

    @pytest.mark.asyncio
    async def test_sources_populated(self):
        step = WebSearchStep(_FakeContainer())
        ctx = ProcessingContext(message='test', adapter_name='my-adapter')

        results = _make_results(3)
        search_fn = AsyncMock(return_value=results)
        with patch('web_search.registry.get_provider', return_value=search_fn):
            result = await step.process(ctx)

        assert len(result.sources) == 3
        assert result.sources[0]['url'] == 'https://example.com/1'
        assert result.sources[0]['title'] == 'Result 1'
        assert result.sources[0]['snippet'] == 'Snippet 1'

    @pytest.mark.asyncio
    async def test_provider_kwargs_forwarded(self):
        """Extra keys in web_search config (api_key, backend, etc.) are passed to provider."""
        ws_cfg = {'provider': 'brave', 'result_count': 5, 'api_key': 'test-key-123'}
        step = WebSearchStep(_FakeContainer(ws_config=ws_cfg))
        ctx = ProcessingContext(message='test', adapter_name='my-adapter')

        search_fn = AsyncMock(return_value=_make_results(1))
        with patch('web_search.registry.get_provider', return_value=search_fn):
            await step.process(ctx)

        call_kwargs = search_fn.call_args.kwargs
        assert call_kwargs.get('api_key') == 'test-key-123'
        assert call_kwargs.get('count') == 5
        assert call_kwargs.get('query') == 'test'

    @pytest.mark.asyncio
    async def test_result_without_snippet_still_formats(self):
        from web_search.base import SearchResult
        step = WebSearchStep(_FakeContainer())
        ctx = ProcessingContext(message='test', adapter_name='my-adapter')

        results = [SearchResult(link='https://example.com', title='Title', snippet=None)]
        search_fn = AsyncMock(return_value=results)
        with patch('web_search.registry.get_provider', return_value=search_fn):
            result = await step.process(ctx)

        assert not result.has_error()
        assert 'https://example.com' in result.formatted_context
        assert 'Title' in result.formatted_context


# ---------------------------------------------------------------------------
# base module: get_filtered_results
# ---------------------------------------------------------------------------

class TestGetFilteredResults:
    def test_no_filter_returns_all(self):
        from web_search.base import get_filtered_results
        items = [{'link': 'https://a.com/x'}, {'link': 'https://b.com/y'}]
        assert get_filtered_results(items, None) == items

    def test_filters_by_domain_substring(self):
        from web_search.base import get_filtered_results
        items = [
            {'link': 'https://allowed.com/page'},
            {'link': 'https://blocked.org/page'},
        ]
        result = get_filtered_results(items, ['allowed.com'])
        assert len(result) == 1
        assert result[0]['link'].startswith('https://allowed.com')

    def test_empty_filter_list_returns_all(self):
        from web_search.base import get_filtered_results
        items = [{'link': 'https://x.com'}]
        assert get_filtered_results(items, []) == items
