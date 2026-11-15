"""
Tests for PineconeRetriever.get_relevant_context, verifying it relies on the
shared AbstractVectorRetriever pipeline instead of duplicating it.

Context: PineconeRetriever used to override get_relevant_context with its own
copy of the embed -> search -> filter -> sort -> limit pipeline, but its first
line called super().get_relevant_context(...) (running the base pipeline in
full) and discarded the result before re-embedding the query and re-running
vector_search a second time. Every Pinecone query therefore hit the embedding
service and the vector DB twice. The override has been removed; these tests
guard against it (or an equivalent duplication) coming back.
"""

import os
import sys
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from retrievers.implementations.vector.pinecone_retriever import PineconeRetriever


@pytest.fixture
def test_config():
    return {
        "datasources": {
            "pinecone": {
                "type": "pinecone",
                "confidence_threshold": 0.5,
                "max_results": 10,
                "return_results": 3,
                "collection": "test_index",
            }
        },
        "embedding": {
            "enabled": False
        },
        "general": {}
    }


@pytest.fixture
def mock_embeddings():
    embeddings = Mock(spec=["embed_query", "initialized", "close"])
    embeddings.embed_query = AsyncMock(return_value=[0.1] * 8)
    embeddings.initialized = True
    embeddings.close = AsyncMock()
    return embeddings


def _mock_search_results(count: int, base_score: float = 0.9) -> list[dict[str, Any]]:
    return [
        {
            "document": f"Document {i}",
            "metadata": {"id": i},
            "score": base_score - (i * 0.01),
        }
        for i in range(1, count + 1)
    ]


@pytest.mark.asyncio
async def test_embed_and_search_each_called_once(test_config, mock_embeddings):
    """
    get_relevant_context must generate the query embedding and run the vector
    search exactly once per call -- not twice via a discarded base-class call
    followed by a duplicate re-implementation.
    """
    retriever = PineconeRetriever(config=test_config, embeddings=mock_embeddings)
    retriever.collection = "test_index"

    search_calls = []

    async def fake_vector_search(query_embedding, top_k):
        search_calls.append((query_embedding, top_k))
        return _mock_search_results(2)

    retriever.vector_search = fake_vector_search

    results = await retriever.get_relevant_context("test query")

    assert mock_embeddings.embed_query.call_count == 1
    assert len(search_calls) == 1
    assert len(results) == 2


@pytest.mark.asyncio
async def test_metadata_includes_score_and_truncation_fields(test_config, mock_embeddings):
    """
    The shared base pipeline's output contract must include both Pinecone's
    raw score (previously only added by the now-removed override) and the
    base pipeline's truncation/diagnostic metadata.
    """
    retriever = PineconeRetriever(config=test_config, embeddings=mock_embeddings)
    retriever.collection = "test_index"
    retriever.vector_search = AsyncMock(return_value=_mock_search_results(2))

    results = await retriever.get_relevant_context("test query")

    assert len(results) == 2
    item = results[0]
    assert item["metadata"]["score"] == pytest.approx(0.89)
    assert item["metadata"]["similarity"] == pytest.approx(0.89)
    assert "total_available" in item["metadata"]
    assert "vector_search_count" in item["metadata"]


@pytest.mark.asyncio
async def test_confidence_threshold_filters_low_scores(test_config, mock_embeddings):
    retriever = PineconeRetriever(config=test_config, embeddings=mock_embeddings)
    retriever.collection = "test_index"
    retriever.confidence_threshold = 0.95
    retriever.vector_search = AsyncMock(return_value=_mock_search_results(2))

    results = await retriever.get_relevant_context("test query")

    assert results == []
