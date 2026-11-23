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


def resolve_endpoint_url(value: str | None, default: str | None, *, provider: str) -> str:
    """Resolve a provider's request URL from an optional override.

    - Omitted (``value is None``): returns ``default``. Raises if ``default``
      is also ``None`` (providers with no hardcoded default must pass their
      own fallback logic before calling this, e.g. SearXNG's two-key case).
    - Blank or malformed (not an absolute ``http``/``https`` URL with a
      hostname): raises ``ValueError`` naming the provider, even if a valid
      ``default`` exists — an explicitly-set-but-empty value is a config
      error, not a reason to fall back.
    """
    if value is None:
        if default is None:
            raise ValueError(f"{provider}: 'endpoint_url' is required")
        return default

    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
        _ = parsed.port  # triggers ValueError for an invalid port (e.g. non-numeric)
    except ValueError as exc:
        raise ValueError(
            f"{provider}: 'endpoint_url' must be an absolute http(s) URL, got {value!r} ({exc})"
        ) from exc

    if parsed.scheme not in ("http", "https") or not hostname:
        raise ValueError(
            f"{provider}: 'endpoint_url' must be an absolute http(s) URL, got {value!r}"
        )
    return value


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
