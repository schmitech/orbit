"""DuckDuckGo search provider. Free, no API key required."""
from __future__ import annotations

import asyncio
import logging
import urllib.request

from ddgs import DDGS
from ddgs.exceptions import RatelimitException

from ..base import SearchResult, get_filtered_results

log = logging.getLogger(__name__)


def _search_sync(
    query: str,
    count: int,
    filter_list: list[str | None] | None,
    concurrent_requests: int | None,
    backend: str | None,
) -> list[SearchResult]:
    env_proxies = urllib.request.getproxies()
    proxy = env_proxies.get('https') or env_proxies.get('http')
    search_results = []
    with DDGS(proxy=proxy) as ddgs:
        if concurrent_requests:
            ddgs.threads = concurrent_requests
        try:
            kwargs: dict = {'safesearch': 'moderate', 'max_results': count}
            if backend and backend != 'auto':
                kwargs['backend'] = backend
            results = ddgs.text(query, **kwargs)
            search_results = results if results is not None else []
        except RatelimitException as e:
            log.error('DuckDuckGo RatelimitException: %s', e)
            search_results = []

    if filter_list:
        search_results = get_filtered_results(search_results, filter_list)

    return [
        SearchResult(
            link=result['href'],
            title=result.get('title'),
            snippet=result.get('body'),
        )
        for result in search_results
    ]


async def search_duckduckgo(
    query: str,
    count: int,
    filter_list: list[str | None] | None = None,
    concurrent_requests: int | None = None,
    backend: str | None = 'auto',
) -> list[SearchResult]:
    """Search using DuckDuckGo. Runs the sync ddgs library in a thread."""
    return await asyncio.to_thread(
        _search_sync, query, count, filter_list, concurrent_requests, backend
    )
