"""
Tests for vector retriever result truncation and metadata tracking
"""

import pytest
import asyncio
import sys
import os
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, MagicMock, AsyncMock, patch

# Add the server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from retrievers.base.abstract_vector_retriever import AbstractVectorRetriever


class MockVectorRetriever(AbstractVectorRetriever):
    """Mock vector retriever for testing truncation behavior"""

    def __init__(self, config: Dict[str, Any], embeddings=None, datasource: Any = None, **kwargs):
        super().__init__(config=config, embeddings=embeddings, datasource=datasource, **kwargs)
        self.mock_search_results = []

    def _get_datasource_name(self) -> str:
        return "mock_vector"

    async def vector_search(self, query_embedding: List[float], top_k: int) -> List[Dict[str, Any]]:
        """Return mock vector search results"""
        return self.mock_search_results[:top_k]

    async def set_collection(self, collection_name: str) -> None:
        """Set the collection name"""
        self.collection = collection_name

    async def initialize_client(self) -> None:
        """Mock initialization"""
        pass

    async def close_client(self) -> None:
        """Mock close"""
        pass

    def set_mock_search_results(self, results: List[Dict[str, Any]]):
        """Set the mock results that will be returned"""
        self.mock_search_results = results


@pytest.fixture
def test_config():
    """Configuration for vector retriever tests"""
    return {
        "datasources": {
            "mock_vector": {
                "type": "mock_vector",
                "relevance_threshold": 0.5,
                "confidence_threshold": 0.5,
                "max_results": 100,
                "return_results": 3,  # Default truncation limit
                "collection": "test_documents"
            }
        },
        "embedding": {
            "enabled": False  # Disable embeddings for testing
        },
        "general": {
        }
    }


@pytest.fixture
def mock_datasource():
    """Mock datasource for testing"""
    datasource = Mock()
    datasource.is_initialized = True
    datasource.get_client = Mock(return_value=Mock())

    async def mock_initialize():
        pass

    async def mock_close():
        pass

    datasource.initialize = AsyncMock(side_effect=mock_initialize)
    datasource.close = AsyncMock(side_effect=mock_close)

    return datasource


@pytest.fixture
def mock_embeddings():
    """Mock embedding service"""
    embeddings = Mock()

    async def mock_embed_query(query: str):
        # Return a fake embedding vector
        return [0.1] * 768

    embeddings.embed_query = AsyncMock(side_effect=mock_embed_query)
    embeddings.initialized = True
    embeddings.close = AsyncMock()

    return embeddings


def create_mock_vector_results(count: int, base_score: float = 0.9) -> List[Dict[str, Any]]:
    """Generate mock vector search results with decreasing scores"""
    return [
        {
            "document": f"Document {i} content about the topic",
            "metadata": {
                "id": i,
                "title": f"Document {i}",
                "source": "test"
            },
            "score": base_score - (i * 0.01),  # Decreasing scores
            "distance": 0.1 * i  # Increasing distance
        }
        for i in range(1, count + 1)
    ]


@pytest.mark.asyncio
async def test_no_truncation_when_results_below_limit(test_config, mock_datasource, mock_embeddings):
    """Test that results are not truncated when count is below return_results limit"""
    retriever = MockVectorRetriever(
        config=test_config,
        embeddings=mock_embeddings,
        datasource=mock_datasource
    )
    retriever.collection = "test_documents"

    # Set mock results (2 docs, below limit of 3)
    mock_results = create_mock_vector_results(2)
    retriever.set_mock_search_results(mock_results)

    # Get relevant context
    results = await retriever.get_relevant_context("test query")

    # Should return all 2 results
    assert len(results) == 2

    # Check metadata
    assert results[0]["metadata"]["total_available"] == 2
    assert results[0]["metadata"]["truncated"] == False
    assert results[0]["metadata"]["result_count"] == 2
    assert results[0]["metadata"]["vector_search_count"] == 2


@pytest.mark.asyncio
async def test_truncation_when_results_exceed_limit(test_config, mock_datasource, mock_embeddings):
    """Test that results are truncated when count exceeds return_results limit"""
    retriever = MockVectorRetriever(
        config=test_config,
        embeddings=mock_embeddings,
        datasource=mock_datasource
    )
    retriever.collection = "test_documents"

    # Set mock results (50 docs, above limit of 3)
    mock_results = create_mock_vector_results(50)
    retriever.set_mock_search_results(mock_results)

    # Get relevant context
    results = await retriever.get_relevant_context("test query")

    # Should return only 3 results (truncated)
    assert len(results) == 3

    # Check metadata shows original count
    assert results[0]["metadata"]["total_available"] == 40
    assert results[0]["metadata"]["truncated"] == True
    assert results[0]["metadata"]["result_count"] == 3
    assert results[0]["metadata"]["vector_search_count"] == 50


@pytest.mark.asyncio
async def test_confidence_filtering_tracked(test_config, mock_datasource, mock_embeddings):
    """Test that confidence filtering is tracked in metadata"""
    retriever = MockVectorRetriever(
        config=test_config,
        embeddings=mock_embeddings,
        datasource=mock_datasource
    )
    retriever.collection = "test_documents"
    retriever.confidence_threshold = 0.7  # Higher threshold

    # Create results with varying scores (some below threshold)
    mock_results = [
        {"document": "Doc 1", "metadata": {"id": 1}, "score": 0.95, "distance": 0.1},
        {"document": "Doc 2", "metadata": {"id": 2}, "score": 0.85, "distance": 0.2},
        {"document": "Doc 3", "metadata": {"id": 3}, "score": 0.75, "distance": 0.3},
        {"document": "Doc 4", "metadata": {"id": 4}, "score": 0.65, "distance": 0.4},  # Below threshold
        {"document": "Doc 5", "metadata": {"id": 5}, "score": 0.55, "distance": 0.5},  # Below threshold
    ]
    retriever.set_mock_search_results(mock_results)

    # Get relevant context
    results = await retriever.get_relevant_context("test query")

    # Should have filtered by confidence (3 above threshold) and return all 3 (within limit)
    assert len(results) == 3

    # Check metadata tracks filtering
    assert results[0]["metadata"]["vector_search_count"] == 5  # Original from vector DB
    assert results[0]["metadata"]["after_confidence_filtering"] == 3  # After filtering
    assert results[0]["metadata"]["total_available"] == 3  # Available after all filtering
    assert results[0]["metadata"]["truncated"] == False  # No truncation needed


@pytest.mark.asyncio
async def test_confidence_filtering_with_truncation(test_config, mock_datasource, mock_embeddings):
    """Test confidence filtering followed by truncation"""
    retriever = MockVectorRetriever(
        config=test_config,
        embeddings=mock_embeddings,
        datasource=mock_datasource
    )
    retriever.collection = "test_documents"
    retriever.confidence_threshold = 0.5  # Lower threshold to pass more results

    # Create 20 results all above threshold
    mock_results = create_mock_vector_results(20, base_score=0.9)
    retriever.set_mock_search_results(mock_results)

    # Get relevant context
    results = await retriever.get_relevant_context("test query")

    # Should return 3 (truncated from 20)
    assert len(results) == 3

    # Check metadata shows full pipeline
    assert results[0]["metadata"]["vector_search_count"] == 20  # Vector search returned 20
    assert results[0]["metadata"]["after_confidence_filtering"] == 20  # All passed confidence
    assert results[0]["metadata"]["total_available"] == 20  # 20 available before truncation
    assert results[0]["metadata"]["truncated"] == True  # Truncated to 3
    assert results[0]["metadata"]["result_count"] == 3


@pytest.mark.asyncio
async def test_custom_return_results_limit(mock_datasource, mock_embeddings):
    """Test with custom return_results configuration"""
    custom_config = {
        "datasources": {
            "mock_vector": {
                "type": "mock_vector",
                "relevance_threshold": 0.5,
                "confidence_threshold": 0.5,
                "max_results": 100,
                "return_results": 10,  # Custom limit
                "collection": "test_documents"
            }
        },
        "embedding": {
            "enabled": False
        },
        "general": {
        }
    }

    retriever = MockVectorRetriever(
        config=custom_config,
        embeddings=mock_embeddings,
        datasource=mock_datasource
    )
    retriever.collection = "test_documents"

    # Set mock results (30 docs)
    mock_results = create_mock_vector_results(30)
    retriever.set_mock_search_results(mock_results)

    # Get relevant context
    results = await retriever.get_relevant_context("test query")

    # Should return only 10 results
    assert len(results) == 10

    # Check metadata
    assert results[0]["metadata"]["total_available"] == 30
    assert results[0]["metadata"]["truncated"] == True
    assert results[0]["metadata"]["result_count"] == 10


@pytest.mark.asyncio
async def test_metadata_consistency_across_results(test_config, mock_datasource, mock_embeddings):
    """Test that truncation metadata is consistent across all returned results"""
    retriever = MockVectorRetriever(
        config=test_config,
        embeddings=mock_embeddings,
        datasource=mock_datasource
    )
    retriever.collection = "test_documents"

    # Set mock results (15 docs)
    mock_results = create_mock_vector_results(15)
    retriever.set_mock_search_results(mock_results)

    # Get relevant context
    results = await retriever.get_relevant_context("test query")

    # All results should have same truncation metadata
    assert len(results) == 3

    for result in results:
        assert result["metadata"]["total_available"] == 15
        assert result["metadata"]["truncated"] == True
        assert result["metadata"]["result_count"] == 3
        assert result["metadata"]["vector_search_count"] == 15


@pytest.mark.asyncio
async def test_empty_results(test_config, mock_datasource, mock_embeddings):
    """Test behavior with empty result set"""
    retriever = MockVectorRetriever(
        config=test_config,
        embeddings=mock_embeddings,
        datasource=mock_datasource
    )
    retriever.collection = "test_documents"

    # Set empty mock results
    retriever.set_mock_search_results([])

    # Get relevant context
    results = await retriever.get_relevant_context("test query")

    # Should return empty list
    assert len(results) == 0


@pytest.mark.asyncio
async def test_exact_limit_no_truncation(test_config, mock_datasource, mock_embeddings):
    """Test when results exactly match return_results limit"""
    retriever = MockVectorRetriever(
        config=test_config,
        embeddings=mock_embeddings,
        datasource=mock_datasource
    )
    retriever.collection = "test_documents"

    # Set mock results (exactly 3 docs, matching limit)
    mock_results = create_mock_vector_results(3)
    retriever.set_mock_search_results(mock_results)

    # Get relevant context
    results = await retriever.get_relevant_context("test query")

    # Should return all 3 results without truncation
    assert len(results) == 3

    # Check metadata (no truncation since count matches limit)
    assert results[0]["metadata"]["total_available"] == 3
    assert results[0]["metadata"]["truncated"] == False
    assert results[0]["metadata"]["result_count"] == 3


@pytest.mark.asyncio
async def test_max_results_limits_vector_search(test_config, mock_datasource, mock_embeddings):
    """Test that max_results limits the initial vector search"""
    retriever = MockVectorRetriever(
        config=test_config,
        embeddings=mock_embeddings,
        datasource=mock_datasource
    )
    retriever.collection = "test_documents"
    retriever.max_results = 20  # Limit vector search to 20

    # Create 100 results, but vector_search will only return first 20
    mock_results = create_mock_vector_results(100)
    retriever.set_mock_search_results(mock_results)

    # Get relevant context
    results = await retriever.get_relevant_context("test query")

    # Should return 3 (truncated from 20)
    assert len(results) == 3

    # Metadata should show vector search returned 20 (not 100)
    assert results[0]["metadata"]["vector_search_count"] == 20
    assert results[0]["metadata"]["total_available"] == 20
    assert results[0]["metadata"]["truncated"] == True


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
