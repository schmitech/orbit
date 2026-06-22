"""Serper (Google Search via serper.dev) provider."""
from __future__ import annotations

import logging

import httpx

from ..base import SearchResult, get_filtered_results

log = logging.getLogger(__name__)


async def search_serper(
    api_key: str,
    query: str,
    count: int,
    filter_list: list[str | None] | None = None,
) -> list[SearchResult]:
    """Query the serper.dev Google Search API and return normalised results."""
    url = 'https://google.serper.dev/search'
    headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json={'q': query})
        response.raise_for_status()
        payload = response.json()

    organic = sorted(payload.get('organic', []), key=lambda item: item.get('position', 0))
    if filter_list:
        organic = get_filtered_results(organic, filter_list)

    return [
        SearchResult(
            link=item.get('link', ''),
            title=item.get('title'),
            snippet=item.get('snippet'),
        )
        for item in organic[:count]
    ]
