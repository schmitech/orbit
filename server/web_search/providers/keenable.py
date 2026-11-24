"""Keenable web search provider.

Works with or without an API key: with one, ``POST /v1/search`` with the key in
``X-API-Key``; without one, the keyless ``POST /v1/search/public`` endpoint,
which Keenable rate limits per IP address. Every request names the calling app
in ``X-Keenable-Title``, which the keyless endpoint requires.
"""
from __future__ import annotations

import logging

import httpx

from ..base import SearchResult, get_filtered_results, resolve_endpoint_url

log = logging.getLogger(__name__)

DEFAULT_ENDPOINT_URL = 'https://api.keenable.ai/v1/search'
DEFAULT_PUBLIC_ENDPOINT_URL = 'https://api.keenable.ai/v1/search/public'
DEFAULT_APP_TITLE = 'orbit'
# Keenable accepts max_results from 1 to 50.
MAX_RESULTS = 50


async def search_keenable(
    query: str,
    count: int,
    filter_list: list[str | None] | None = None,
    *,
    api_key: str | None = None,
    endpoint_url: str | None = None,
    app_title: str | None = None,
) -> list[SearchResult]:
    """Search using the Keenable Search API, keyed or keyless."""
    api_key = (api_key or '').strip()
    default_url = DEFAULT_ENDPOINT_URL if api_key else DEFAULT_PUBLIC_ENDPOINT_URL
    url = resolve_endpoint_url(endpoint_url, default_url, provider='keenable')

    headers = {
        'Content-Type': 'application/json',
        'X-Keenable-Title': (app_title or '').strip() or DEFAULT_APP_TITLE,
    }
    if api_key:
        headers['X-API-Key'] = api_key

    body = {'query': query, 'max_results': max(1, min(int(count), MAX_RESULTS))}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=body)
        response.raise_for_status()
        payload = response.json()

    results = payload.get('results', [])
    if filter_list:
        results = get_filtered_results(results, filter_list)

    return [
        SearchResult(
            link=result['url'],
            title=result.get('title', ''),
            snippet=result.get('snippet'),
        )
        for result in results
        if result.get('url')
    ]
