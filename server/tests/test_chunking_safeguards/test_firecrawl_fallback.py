"""
Phase 5 gate: bounded, visible retrieval degradation.

Covers IntentFirecrawlRetriever's consumption of the structured
IngestionResult (Phase 4) and bounded formatting of both the chunked-results
path and the raw-content fallback -- neither may send unbounded output, and
incomplete coverage (partial ingestion, no similarity matches, indexing
failure) must be disclosed rather than silently mixed in with full coverage.
"""

from unittest.mock import AsyncMock

import pytest
from retrievers.implementations.intent.intent_firecrawl_retriever import IntentFirecrawlRetriever
from utils.chunk_manager import IngestionResult, IngestionStatus
from utils.embedding_budget import resolve_embedding_budget

pytestmark = pytest.mark.unit


def _retriever(max_retrieval_context_tokens=6000):
    retriever = object.__new__(IntentFirecrawlRetriever)
    retriever.max_retrieval_context_tokens = max_retrieval_context_tokens
    retriever.retrieval_context_budget = resolve_embedding_budget(
        max_embedding_tokens=max_retrieval_context_tokens, safety_margin=1.0,
    )
    retriever.top_chunks_to_return = 3
    retriever.min_chunk_similarity = 0.3
    return retriever


def _chunk(content, position=0, total_chunks=1, score=0.9, hierarchy=None):
    return {
        "content": content,
        "similarity_score": score,
        "hierarchy": hierarchy or ["Intro"],
        "position": position,
        "total_chunks": total_chunks,
    }


# ---------------------------------------------------------------------------
# _format_chunked_results: bounded assembly, disclosed truncation/partial state
# ---------------------------------------------------------------------------

def test_chunked_results_fit_within_the_configured_budget():
    retriever = _retriever(max_retrieval_context_tokens=300)
    chunks = [_chunk("word " * 500, position=i, total_chunks=5, score=0.9 - i * 0.1) for i in range(5)]

    output = retriever._format_chunked_results(
        chunks=chunks, source_url="https://example.com", page_metadata={}, total_content_size=10000,
    )

    assert retriever.retrieval_context_budget.count(output).count <= retriever.retrieval_context_budget.effective_max_tokens
    assert "truncated" in output.lower() or "Showing" in output


def test_chunked_results_disclose_truncation_when_sections_are_dropped():
    retriever = _retriever(max_retrieval_context_tokens=400)
    chunks = [_chunk("word " * 500, position=i, total_chunks=3, score=0.9 - i * 0.1) for i in range(3)]

    output = retriever._format_chunked_results(
        chunks=chunks, source_url="https://example.com", page_metadata={}, total_content_size=10000,
    )

    assert "truncated to fit the available context budget" in output
    assert "Showing 1 of 3" in output or "Showing 0 of 3" in output


def test_chunked_results_disclose_partial_ingestion_status():
    retriever = _retriever(max_retrieval_context_tokens=6000)
    chunks = [_chunk("some relevant content")]

    output = retriever._format_chunked_results(
        chunks=chunks, source_url="https://example.com", page_metadata={},
        total_content_size=100, ingestion_status=IngestionStatus.PARTIAL,
    )

    assert "only part of this page" in output.lower()


def test_chunked_results_complete_ingestion_has_no_partial_disclosure():
    retriever = _retriever(max_retrieval_context_tokens=6000)
    chunks = [_chunk("some relevant content")]

    output = retriever._format_chunked_results(
        chunks=chunks, source_url="https://example.com", page_metadata={},
        total_content_size=100, ingestion_status=IngestionStatus.COMPLETE,
    )

    assert "only part of this page" not in output.lower()


def test_chunked_results_with_tiny_budget_returns_bounded_unavailable_message():
    retriever = _retriever(max_retrieval_context_tokens=5)
    chunks = [_chunk("word " * 500)]

    output = retriever._format_chunked_results(
        chunks=chunks, source_url="https://example.com/tiny", page_metadata={}, total_content_size=10000,
    )

    assert output == retriever._bounded_unavailable_message("https://example.com/tiny")
    assert "RELEVANT SECTION" not in output


# ---------------------------------------------------------------------------
# _format_firecrawl_results: bounded raw-content excerpt, never the full page
# ---------------------------------------------------------------------------

def test_raw_content_fallback_bounds_output_and_discloses_truncation():
    retriever = _retriever(max_retrieval_context_tokens=300)
    results = [{
        "url": "https://example.com/big",
        "success": True,
        "markdown": "word " * 5000,
    }]

    output = retriever._format_firecrawl_results(results, template={})

    assert retriever.retrieval_context_budget.count(output).count <= retriever.retrieval_context_budget.effective_max_tokens
    assert "truncated" in output.lower()
    assert "https://example.com/big" in output


def test_raw_content_fallback_does_not_truncate_small_content():
    retriever = _retriever(max_retrieval_context_tokens=6000)
    results = [{
        "url": "https://example.com/small",
        "success": True,
        "markdown": "This page is short.",
    }]

    output = retriever._format_firecrawl_results(results, template={})

    assert "This page is short." in output
    assert "truncated" not in output.lower()


def test_raw_content_fallback_with_tiny_budget_returns_bounded_unavailable_message():
    retriever = _retriever(max_retrieval_context_tokens=5)
    results = [{
        "url": "https://example.com/tiny",
        "success": True,
        "markdown": "word " * 5000,
        "metadata": {"title": "A Very Long Title " * 20},
    }]

    output = retriever._format_firecrawl_results(results, template={})

    assert output == retriever._bounded_unavailable_message("https://example.com/tiny")


def test_bounded_unavailable_message_itself_fits_a_tiny_budget():
    """A long source URL must not make the 'unavailable' message itself
    exceed the very budget it's reporting as too small."""
    retriever = _retriever(max_retrieval_context_tokens=5)
    long_url = "https://example.com/" + "a" * 500

    message = retriever._bounded_unavailable_message(long_url)

    assert retriever.retrieval_context_budget.fits(message)


def test_no_content_extracted_path_is_bounded_by_the_budget():
    """A successful scrape with no markdown/html/text still has metadata and
    links to assemble -- an arbitrarily long title or link list must not
    bypass the budget just because there's no main content."""
    retriever = _retriever(max_retrieval_context_tokens=20)
    results = [{
        "url": "https://example.com/empty",
        "success": True,
        "metadata": {"title": "A Very Long Title " * 50},
        "links": [f"https://example.com/link-{i}-{'x' * 50}" for i in range(20)],
    }]

    output = retriever._format_firecrawl_results(results, template={})

    assert retriever.retrieval_context_budget.fits(output)


def test_no_content_extracted_path_returns_full_details_when_small_enough():
    retriever = _retriever(max_retrieval_context_tokens=6000)
    results = [{
        "url": "https://example.com/empty",
        "success": True,
        "metadata": {"title": "A Short Title"},
        "links": ["https://example.com/a", "https://example.com/b"],
    }]

    output = retriever._format_firecrawl_results(results, template={})

    assert "No content was extracted from the page." in output
    assert "https://example.com/a" in output


def test_raw_content_fallback_preserves_scrape_failure_message():
    retriever = _retriever()
    results = [{"url": "https://example.com/fail", "success": False, "error": "404 Not Found"}]

    output = retriever._format_firecrawl_results(results, template={})

    assert "Failed to scrape content from: https://example.com/fail" in output


def test_no_results_message_is_bounded_for_a_tiny_budget():
    retriever = _retriever(max_retrieval_context_tokens=1)

    output = retriever._format_firecrawl_results([], template={})

    assert retriever.retrieval_context_budget.fits(output)


def test_no_results_message_returned_unbounded_when_it_fits():
    retriever = _retriever()

    output = retriever._format_firecrawl_results([], template={})

    assert output == "No content was scraped."


def test_scrape_failure_message_is_bounded_when_error_is_arbitrarily_long():
    retriever = _retriever(max_retrieval_context_tokens=10)
    results = [{
        "url": "https://example.com/fail",
        "success": False,
        "error": "provider error detail " * 200,
    }]

    output = retriever._format_firecrawl_results(results, template={})

    assert retriever.retrieval_context_budget.fits(output)


def test_scrape_failure_message_returned_in_full_when_it_fits():
    retriever = _retriever()
    results = [{"url": "https://example.com/fail", "success": False, "error": "404 Not Found"}]

    output = retriever._format_firecrawl_results(results, template={})

    assert "Failed to scrape content from: https://example.com/fail" in output
    assert "404 Not Found" in output


# ---------------------------------------------------------------------------
# _process_with_chunking: explicit consumption of IngestionResult
# ---------------------------------------------------------------------------

def _process_chunking_retriever():
    retriever = _retriever()
    retriever.content_chunker = AsyncMock()
    retriever.content_chunker.chunk_markdown = lambda content, meta: [{"content": content, "chunk_id": 0}]
    retriever.chunk_manager = AsyncMock()
    retriever.chunk_manager.has_cached_chunks = AsyncMock(return_value=False)
    return retriever


async def test_failed_ingestion_returns_bounded_excerpt_without_retrieving_chunks():
    retriever = _process_chunking_retriever()
    retriever.chunk_manager.store_chunks = AsyncMock(
        return_value=IngestionResult(IngestionStatus.FAILED, "https://example.com", "gen1", 3, 0, 3)
    )
    retriever.chunk_manager.retrieve_chunks = AsyncMock(return_value=[])

    results = [{"url": "https://example.com", "success": True, "markdown": "Some markdown content here."}]

    content, meta = await retriever._process_with_chunking(
        results, template={}, parameters={}, query="q", source_url="https://example.com",
    )

    assert meta["ingestion_status"] == "failed"
    assert "Some markdown content here." in content
    assert "RELEVANT SECTION" not in content
    retriever.chunk_manager.retrieve_chunks.assert_not_awaited()


async def test_partial_ingestion_discloses_status_and_still_retrieves_chunks():
    retriever = _process_chunking_retriever()
    retriever.chunk_manager.store_chunks = AsyncMock(
        return_value=IngestionResult(IngestionStatus.PARTIAL, "https://example.com", "gen1", 3, 2, 1)
    )
    retriever.chunk_manager.retrieve_chunks = AsyncMock(return_value=[_chunk("relevant text")])

    results = [{"url": "https://example.com", "success": True, "markdown": "Some markdown content here."}]

    content, meta = await retriever._process_with_chunking(
        results, template={}, parameters={}, query="q", source_url="https://example.com",
    )

    assert meta["ingestion_status"] == "partial"
    assert "only part of this page" in content.lower()


async def test_no_relevant_chunks_falls_back_to_bounded_excerpt():
    retriever = _process_chunking_retriever()
    retriever.chunk_manager.store_chunks = AsyncMock(
        return_value=IngestionResult(IngestionStatus.COMPLETE, "https://example.com", "gen1", 3, 3, 0)
    )
    retriever.chunk_manager.retrieve_chunks = AsyncMock(return_value=[])

    results = [{"url": "https://example.com", "success": True, "markdown": "Some markdown content here."}]

    content, meta = await retriever._process_with_chunking(
        results, template={}, parameters={}, query="q", source_url="https://example.com",
    )

    assert meta["ingestion_status"] == "complete"
    assert "Some markdown content here." in content
    assert "RELEVANT SECTION" not in content


async def test_complete_ingestion_with_matches_uses_chunked_formatting():
    retriever = _process_chunking_retriever()
    retriever.chunk_manager.store_chunks = AsyncMock(
        return_value=IngestionResult(IngestionStatus.COMPLETE, "https://example.com", "gen1", 1, 1, 0)
    )
    retriever.chunk_manager.retrieve_chunks = AsyncMock(return_value=[_chunk("relevant text")])

    results = [{"url": "https://example.com", "success": True, "markdown": "Some markdown content here."}]

    content, meta = await retriever._process_with_chunking(
        results, template={}, parameters={}, query="q", source_url="https://example.com",
    )

    assert meta["ingestion_status"] == "complete"
    assert "RELEVANT SECTION" in content


async def test_query_retrieval_uses_the_original_query_text():
    """Retrieval must stay query-semantic (embed_query, via ChunkManager) --
    verified here at the retriever boundary by asserting the retriever passes
    the user's query straight through to ChunkManager.retrieve_chunks."""
    retriever = _process_chunking_retriever()
    retriever.chunk_manager.store_chunks = AsyncMock(
        return_value=IngestionResult(IngestionStatus.COMPLETE, "https://example.com", "gen1", 1, 1, 0)
    )
    retriever.chunk_manager.retrieve_chunks = AsyncMock(return_value=[_chunk("relevant text")])

    results = [{"url": "https://example.com", "success": True, "markdown": "content"}]

    await retriever._process_with_chunking(
        results, template={}, parameters={}, query="what is the industrial revolution",
        source_url="https://example.com",
    )

    _, kwargs = retriever.chunk_manager.retrieve_chunks.call_args
    assert kwargs["query"] == "what is the industrial revolution"
