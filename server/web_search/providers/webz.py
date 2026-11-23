"""Webz.io News API Lite provider."""
from __future__ import annotations

import logging

import httpx

from ..base import SearchResult, get_filtered_results

log = logging.getLogger(__name__)


async def search_webz(
    api_key: str,
    query: str,
    count: int,
    filter_list: list[str | None] | None = None,
) -> list[SearchResult]:
    """Query the Webz.io News API Lite and return normalised results."""
    url = 'https://api.webz.io/newsApiLite'
    params = {'token': api_key, 'q': query}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()

    posts = payload.get('posts', [])
    if filter_list:
        posts = get_filtered_results(posts, filter_list)

    return [
        SearchResult(
            link=post.get('url', ''),
            title=post.get('title'),
            snippet=post.get('text'),
        )
        for post in posts[:count]
    ]
