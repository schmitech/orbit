"""Brave Search API provider."""
from __future__ import annotations

import asyncio
import logging

import httpx

from ..base import SearchResult, get_filtered_results

log = logging.getLogger(__name__)

_RATE_LIMIT_RETRY_DELAY = 1.0


async def search_brave(
    api_key: str,
    query: str,
    count: int,
    filter_list: list[str | None] | None = None,
) -> list[SearchResult]:
    """Query the Brave Web Search API. Retries once on HTTP 429."""
    url = 'https://api.search.brave.com/res/v1/web/search'
    headers = {
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip',
        'X-Subscription-Token': api_key,
    }
    params = {'q': query, 'count': count}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params)
        if response.status_code == 429:
            log.info('Brave Search rate-limited (429); retrying after %.1fs', _RATE_LIMIT_RETRY_DELAY)
            await asyncio.sleep(_RATE_LIMIT_RETRY_DELAY)
            response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        payload = response.json()

    web_results = payload.get('web', {}).get('results', [])
    if filter_list:
        web_results = get_filtered_results(web_results, filter_list)

    return [
        SearchResult(
            link=item.get('url', ''),
            title=item.get('title'),
            snippet=item.get('description'),
        )
        for item in web_results[:count]
    ]
