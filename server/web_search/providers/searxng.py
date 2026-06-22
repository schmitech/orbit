"""SearXNG self-hosted metasearch engine provider."""
from __future__ import annotations

import logging

import httpx

from ..base import SearchResult, get_filtered_results

log = logging.getLogger(__name__)

_HEADERS = {
    'User-Agent': 'OrbitBot/1.0 (https://github.com/schmitech/orbit) RAG Bot',
    'Accept': 'text/html',
    'Accept-Encoding': 'gzip, deflate',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
}


async def search_searxng(
    query_url: str,
    query: str,
    count: int,
    filter_list: list[str | None] | None = None,
    **kwargs,
) -> list[SearchResult]:
    """Query a SearXNG instance and return results sorted by relevance score.

    Optional kwargs (language, safesearch, time_range, categories) are forwarded
    as SearXNG query parameters.
    """
    if '<query>' in query_url:
        query_url = query_url.split('?')[0]

    params = {
        'q': query,
        'format': 'json',
        'pageno': 1,
        'safesearch': kwargs.get('safesearch', '1'),
        'language': kwargs.get('language', 'all').strip().rstrip(','),
        'time_range': kwargs.get('time_range', ''),
        'categories': ''.join(kwargs.get('categories', [])),
        'theme': 'simple',
        'image_proxy': 0,
    }

    log.debug('SearXNG: searching %s', query_url)

    async with httpx.AsyncClient() as client:
        response = await client.get(query_url, headers=_HEADERS, params=params)
        response.raise_for_status()
        payload = response.json()

    results = sorted(payload.get('results', []), key=lambda x: x.get('score', 0), reverse=True)
    if filter_list:
        results = get_filtered_results(results, filter_list)

    return [
        SearchResult(
            link=item.get('url', ''),
            title=item.get('title'),
            snippet=item.get('content'),
        )
        for item in results[:count]
    ]
