"""Tavily AI search provider."""
from __future__ import annotations

import logging

import httpx

from ..base import SearchResult, get_filtered_results

log = logging.getLogger(__name__)


async def search_tavily(
    api_key: str,
    query: str,
    count: int,
    filter_list: list[str | None] | None = None,
) -> list[SearchResult]:
    """Search using the Tavily Search API."""
    url = 'https://api.tavily.com/search'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json={'query': query, 'max_results': count})
        response.raise_for_status()
        payload = response.json()

    results = payload.get('results', [])
    if filter_list:
        results = get_filtered_results(results, filter_list)

    return [
        SearchResult(
            link=result['url'],
            title=result.get('title', ''),
            snippet=result.get('content'),
        )
        for result in results
    ]
