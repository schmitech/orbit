"""
Registry mapping provider name → async search callable.

Each callable has the signature:
    async (query: str, count: int, **provider_kwargs) -> list[SearchResult]

Provider-specific parameters (api_key, query_url, search_engine_id, etc.) are
passed through **provider_kwargs from the adapter config's web_search block.
"""
from __future__ import annotations

from .providers.brave import search_brave
from .providers.duckduckgo import search_duckduckgo
from .providers.google_pse import search_google_pse
from .providers.perplexity import search_perplexity
from .providers.searxng import search_searxng
from .providers.serper import search_serper
from .providers.tavily import search_tavily

PROVIDERS: dict[str, callable] = {
    "duckduckgo": search_duckduckgo,
    "brave": search_brave,
    "searxng": search_searxng,
    "serper": search_serper,
    "tavily": search_tavily,
    "google_pse": search_google_pse,
    "perplexity": search_perplexity,
}


def get_provider(name: str):
    """Return the search callable for the given provider name, or raise ValueError."""
    fn = PROVIDERS.get(name)
    if fn is None:
        raise ValueError(
            f"Unknown web search provider '{name}'. "
            f"Available: {', '.join(PROVIDERS)}"
        )
    return fn
