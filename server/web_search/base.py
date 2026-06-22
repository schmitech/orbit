"""
Shared types and utilities for web search providers.
"""
from __future__ import annotations

from urllib.parse import urlparse

from pydantic import BaseModel


class SearchResult(BaseModel):
    link: str
    title: str | None
    snippet: str | None


def get_filtered_results(results: list, filter_list: list[str | None] | None) -> list:
    """Filter results to only those whose domain matches the filter list.

    filter_list entries are treated as allowed domain substrings; a result
    passes if any entry is a substring of its URL's netloc.
    """
    if not filter_list:
        return results

    cleaned = [f for f in filter_list if f]
    if not cleaned:
        return results

    filtered = []
    for result in results:
        url = result.get('url') or result.get('link') or result.get('href', '')
        domain = urlparse(url).netloc
        if any(entry in domain for entry in cleaned):
            filtered.append(result)
    return filtered
