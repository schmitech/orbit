"""DeepSeek Search API provider (https://api-docs.deepseek.com/guides/search/)."""
from __future__ import annotations

import logging

import httpx

from ..base import SearchResult, get_filtered_results

log = logging.getLogger(__name__)


async def search_deepseek(
    api_key: str,
    query: str,
    count: int,
    filter_list: list[str | None] | None = None,
) -> list[SearchResult]:
    """Query the DeepSeek Search API and return normalised results."""
    log.debug("search_deepseek invoked: query=%r count=%d", query, count)
    url = 'https://api.deepseek.com/v1/tools/search'
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json={'query': query, 'count': count})
        response.raise_for_status()
        payload = response.json()

    results = payload.get('results', [])
    if filter_list:
        results = get_filtered_results(results, filter_list)

    return [
        SearchResult(
            link=result.get('url', ''),
            title=result.get('title'),
            # 'summary' is DeepSeek's longer, model-oriented field; 'snippet' is
            # the short UI-display text. Prefer summary so the LLM has enough
            # content to synthesize from.
            snippet=result.get('summary') or result.get('snippet'),
        )
        for result in results[:count]
    ]
