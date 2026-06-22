"""
Web Search Step

Executes for adapters of type 'web-search'. Calls a configured external
search provider, formats results into context.formatted_context, and
populates context.sources — then lets LLMInferenceStep synthesize a response.
"""
import logging

from ..base import PipelineStep, ProcessingContext
from ._utils import get_adapter_type as _get_adapter_type

logger = logging.getLogger(__name__)


class WebSearchStep(PipelineStep):
    """
    Fetch web search results for adapters of type 'web-search'.

    Reads provider config from the adapter's 'web_search' block, calls the
    configured provider, and stores formatted results in context.formatted_context
    so LLMInferenceStep can synthesize an answer.
    """

    def should_execute(self, context: ProcessingContext) -> bool:
        if context.is_blocked:
            return False
        return _get_adapter_type(self.container, context.adapter_name) == 'web-search'

    def supports_streaming(self) -> bool:
        return False

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        # Load adapter config
        adapter_config: dict = {}
        if context.adapter_name and self.container.has('adapter_manager'):
            try:
                adapter_config = (
                    self.container.get('adapter_manager')
                    .get_adapter_config(context.adapter_name) or {}
                )
            except Exception:
                pass

        ws_config: dict = adapter_config.get('web_search', {})
        provider_name: str = ws_config.get('provider', 'duckduckgo')
        result_count: int = int(ws_config.get('result_count', 5))
        filter_list: list | None = ws_config.get('filter_list')

        # Build provider-specific kwargs from the web_search config block,
        # excluding the fields we already consumed above.
        _reserved = {'provider', 'result_count', 'filter_list'}
        provider_kwargs = {k: v for k, v in ws_config.items() if k not in _reserved}

        try:
            from web_search.registry import get_provider
            search_fn = get_provider(provider_name)
        except ValueError as e:
            context.set_error(str(e))
            return context

        query = context.message
        logger.debug("WebSearchStep: provider=%s query=%r count=%d", provider_name, query, result_count)

        try:
            results = await search_fn(
                query=query,
                count=result_count,
                filter_list=filter_list,
                **provider_kwargs,
            )
        except Exception as e:
            msg = f"Web search failed ({provider_name}): {e}"
            logger.error(msg)
            context.set_error(msg)
            return context

        if not results:
            context.formatted_context = f'No web search results found for: "{query}"'
            return context

        # Format results as numbered list for LLM context
        lines = [f'Web search results for: "{query}"', '']
        for i, result in enumerate(results, 1):
            lines.append(f'[{i}] {result.title or "(no title)"}')
            lines.append(f'URL: {result.link}')
            if result.snippet:
                lines.append(f'Snippet: {result.snippet}')
            lines.append('')

        context.formatted_context = '\n'.join(lines).rstrip()

        # Populate sources for the response envelope
        context.sources = [
            {'title': r.title or '', 'url': r.link, 'snippet': r.snippet or ''}
            for r in results
        ]

        return context
