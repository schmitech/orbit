"""Perplexity Search API provider."""
from __future__ import annotations

import logging

import httpx

from ..base import SearchResult, get_filtered_results, resolve_endpoint_url

log = logging.getLogger(__name__)

_DEFAULT_API_URL = 'https://api.perplexity.ai/search'
DEFAULT_ENDPOINT_URL = _DEFAULT_API_URL


async def search_perplexity(
    api_key: str,
    query: str,
    count: int,
    filter_list: list[str | None] | None = None,
    api_url: str | None = _DEFAULT_API_URL,
    *,
    endpoint_url: str | None = None,
) -> list[SearchResult]:
    """Search using the Perplexity Search API and return structured results.

    `endpoint_url` is the current, documented override; `api_url` is a
    deprecated alias kept for backward compatibility. `endpoint_url` wins
    when both are set, even if blank (Design §3 "blank overrides a valid
    alias" — an explicitly-set-but-empty new key is a config error on its
    own terms).

    `api_url` has a real string default (unlike `endpoint_url`, whose
    default is `None` to mean "omitted"), so an explicit `api_url: null`
    is distinguishable from an omitted `api_url`: an omitted one arrives
    here as that default string, while an explicit null arrives as
    `None` — and must be rejected rather than silently falling back to
    the public default.
    """
    if endpoint_url is not None:
        url = resolve_endpoint_url(endpoint_url, _DEFAULT_API_URL, provider='perplexity')
    elif api_url is None:
        raise ValueError("perplexity: 'api_url' must not be null")
    else:
        if api_url != _DEFAULT_API_URL:
            log.warning("perplexity: 'api_url' is deprecated, use 'endpoint_url'")
        url = resolve_endpoint_url(api_url, _DEFAULT_API_URL, provider='perplexity')

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
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
