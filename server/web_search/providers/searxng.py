"""SearXNG self-hosted metasearch engine provider."""
from __future__ import annotations

import logging

import httpx

from ..base import SearchResult, get_filtered_results, resolve_endpoint_url

log = logging.getLogger(__name__)

_HEADERS = {
    'User-Agent': 'OrbitBot/1.0 (https://github.com/schmitech/orbit) RAG Bot',
    'Accept': 'text/html',
    'Accept-Encoding': 'gzip, deflate',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
}

# `query_url` becoming optional (to let `endpoint_url` precede it) forces
# Python's syntax rules to require a default on `query`/`count` too, since
# they sit after it positionally — but they must stay genuinely required.
# This sentinel satisfies the interpreter while an omitted `query`/`count`
# still raises `TypeError`, instead of silently searching for `""`/`None`.
_REQUIRED = object()


async def search_searxng(
    query_url: str | None = None,
    query: str = _REQUIRED,
    count: int = _REQUIRED,
    filter_list: list[str | None] | None = None,
    *,
    endpoint_url: str | None = None,
    **kwargs,
) -> list[SearchResult]:
    """Query a SearXNG instance and return results sorted by relevance score.

    Optional kwargs (language, safesearch, time_range, categories) are forwarded
    as SearXNG query parameters.

    `endpoint_url` is the current, documented override; `query_url` is a
    deprecated alias. `endpoint_url` wins when both are set, even if blank
    (Design §3 "blank overrides a valid alias"). Exactly one of the two
    must resolve to a usable URL — SearXNG has no hardcoded default, since
    there's no single correct public instance.
    """
    if query is _REQUIRED or count is _REQUIRED:
        raise TypeError("search_searxng() missing required argument: 'query' and/or 'count'")

    if endpoint_url is not None:
        resolved_url = resolve_endpoint_url(endpoint_url, None, provider='searxng')
    elif query_url is not None:
        resolved_url = resolve_endpoint_url(query_url, None, provider='searxng')
    else:
        raise ValueError("searxng: one of 'endpoint_url' or 'query_url' is required")

    if '<query>' in resolved_url:
        resolved_url = resolved_url.split('?')[0]

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

    log.debug('SearXNG: searching %s', resolved_url)

    async with httpx.AsyncClient() as client:
        response = await client.get(resolved_url, headers=_HEADERS, params=params)
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
