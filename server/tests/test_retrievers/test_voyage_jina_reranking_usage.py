"""
Unit tests for dedicated reranking usage reporting.

Both providers return a `usage.total_tokens` field in their rerank API
response; these tests verify that field is captured into usage_sink so
reranking cost tracking can price these calls instead of logging them as
unreported.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

SERVER_DIR = str(Path(__file__).resolve().parents[2])
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from ai_services.implementations.reranking.voyage_reranking_service import VoyageRerankingService
from ai_services.implementations.reranking.jina_reranking_service import JinaRerankingService


def _mock_session(response_json):
    response = MagicMock()
    response.status = 200
    response.json = AsyncMock(return_value=response_json)

    post_cm = MagicMock()
    post_cm.__aenter__ = AsyncMock(return_value=response)
    post_cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.post = MagicMock(return_value=post_cm)
    return session


@pytest.mark.asyncio
async def test_voyage_rerank_reports_usage():
    service = VoyageRerankingService({"rerankers": {"voyage": {
        "api_key": "test", "model": "rerank-2.5-lite",
    }}})
    service.initialized = True
    service.session = _mock_session({
        "data": [{"index": 0, "relevance_score": 0.9}],
        "usage": {"total_tokens": 42},
    })

    usage_sink = {}
    results = await service.rerank("query", ["doc"], top_n=1, usage_sink=usage_sink)

    assert len(results) == 1
    assert usage_sink["reported"] is True
    assert usage_sink["prompt_tokens"] == 42
    assert usage_sink["completion_tokens"] == 0
    assert usage_sink["provider"] == "voyage"
    assert usage_sink["model"] == "rerank-2.5-lite"


@pytest.mark.asyncio
async def test_jina_rerank_reports_usage():
    service = JinaRerankingService({"reranking": {"provider": "jina", "jina": {"api_key": "test"}}})
    service.initialized = True
    service.api_key = "test"
    service._get_session = AsyncMock(return_value=_mock_session({
        "results": [{"index": 0, "relevance_score": 0.9}],
        "usage": {"total_tokens": 17},
    }))

    usage_sink = {}
    results = await service.rerank("query", ["doc"], top_n=1, usage_sink=usage_sink)

    assert len(results) == 1
    assert usage_sink["reported"] is True
    assert usage_sink["prompt_tokens"] == 17
    assert usage_sink["completion_tokens"] == 0
    assert usage_sink["provider"] == "jina"


@pytest.mark.asyncio
async def test_cohere_rerank_reports_billed_search_units():
    pytest.importorskip("cohere")
    from ai_services.implementations.reranking.cohere_reranking_service import (
        CohereRerankingService,
    )

    service = CohereRerankingService({"reranking": {"provider": "cohere", "cohere": {"api_key": "test"}}})
    service.initialized = True
    service.api_key = "test"
    service.session = _mock_session({
        "results": [{"index": 0, "relevance_score": 0.9}],
        "meta": {"billed_units": {"search_units": 3}},
    })

    usage_sink = {}
    results = await service.rerank("query", ["doc"], top_n=1, usage_sink=usage_sink)

    assert len(results) == 1
    assert usage_sink["reported"] is True
    assert usage_sink["usage_unit"] == "search_units"
    assert usage_sink["usage_quantity"] == 3
    assert usage_sink["provider"] == "cohere"
