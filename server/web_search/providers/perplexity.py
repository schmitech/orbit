"""Perplexity Search API provider."""
from __future__ import annotations

import logging

import httpx

from ..base import SearchResult, get_filtered_results

log = logging.getLogger(__name__)

_DEFAULT_API_URL = 'https://api.perplexity.ai/search'


async def search_perplexity(
    api_key: str,
    query: str,
    count: int,
    filter_list: list[str | None] | None = None,
    api_url: str = _DEFAULT_API_URL,
) -> list[SearchResult]:
    """Search using the Perplexity Search API and return structured results."""
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            api_url,
            headers=headers,
            json={'query': query, 'max_results': count},
        )
        response.raise_for_status()
        payload = response.json()

    results = payload.get('results', [])
    if filter_list:
        results = get_filtered_results(results, filter_list)

    return [
        SearchResult(
            link=item['url'],
            title=item.get('title'),
            snippet=item.get('snippet'),
        )
        for item in results
    ]
