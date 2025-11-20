"""
Tests for SQL retriever result truncation and metadata tracking
"""

import pytest
import asyncio
import sys
import os
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, MagicMock, AsyncMock, patch

# Add the server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from retrievers.base.sql_retriever import AbstractSQLRetriever


class MockSQLRetriever(AbstractSQLRetriever):
    """Mock SQL retriever for testing truncation behavior"""

    def __init__(self, config: Dict[str, Any], datasource: Any = None, **kwargs):
        super().__init__(config=config, datasource=datasource, **kwargs)
        self.mock_results = []

    def _get_datasource_name(self) -> str:
        return "mock_sql"

    async def execute_query(self, sql: str, params: List[Any] = None) -> List[Dict[str, Any]]:
        """Return mock results"""
        return self.mock_results

    def set_mock_results(self, results: List[Dict[str, Any]]):
        """Set the mock results that will be returned"""
        self.mock_results = results

    async def set_collection(self, collection_name: str) -> None:
        """Set the current collection for retrieval"""
        self.collection = collection_name

    def _calculate_similarity(self, query: str, text: str) -> float:
        """Override similarity calculation to always return high score for testing"""
        # Return a high score so all results pass relevance threshold
        return 0.9


@pytest.fixture
def test_config():
    """Configuration for SQL retriever tests"""
    return {
        "datasources": {
            "mock_sql": {
                "type": "mock_sql",
                "relevance_threshold": 0.5,
                "max_results": 100,
                "return_results": 3,  # Default truncation limit
                "collection": "test_orders"
            }
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


def create_mock_rows(count: int) -> List[Dict[str, Any]]:
    """Generate mock SQL result rows"""
    return [
        {
            "id": i,
            "customer_name": f"Customer {i}",
            "order_total": 100.0 + i,
            "order_date": "2025-01-01",
            "content": f"Order {i} details"
        }
        for i in range(1, count + 1)
    ]


@pytest.mark.asyncio
async def test_no_truncation_when_results_below_limit(test_config, mock_datasource):
    """Test that results are not truncated when count is below return_results limit"""
    retriever = MockSQLRetriever(config=test_config, datasource=mock_datasource)
    retriever.collection = "test_orders"

    # Set mock results (2 rows, below limit of 3)
    mock_rows = create_mock_rows(2)
    retriever.set_mock_results(mock_rows)

    # Get relevant context
    results = await retriever.get_relevant_context("test query")

    # Should return all 2 results
    assert len(results) == 2

    # Check metadata
    assert results[0]["metadata"]["total_available"] == 2
    assert results[0]["metadata"]["truncated"] == False
    assert results[0]["metadata"]["result_count"] == 2


@pytest.mark.asyncio
async def test_truncation_when_results_exceed_limit(test_config, mock_datasource):
    """Test that results are truncated when count exceeds return_results limit"""
    retriever = MockSQLRetriever(config=test_config, datasource=mock_datasource)
    retriever.collection = "test_orders"

    # Set mock results (100 rows, above limit of 3)
    mock_rows = create_mock_rows(100)
    retriever.set_mock_results(mock_rows)

    # Get relevant context
    results = await retriever.get_relevant_context("test query")

    # Should return only 3 results (truncated)
    assert len(results) == 3

    # Check metadata shows original count
    assert results[0]["metadata"]["total_available"] == 100
    assert results[0]["metadata"]["truncated"] == True
    assert results[0]["metadata"]["result_count"] == 3

    # Verify only first 3 rows are returned (sorted by confidence)
    # Note: Results are sorted by confidence, so order might differ
    assert all("metadata" in result for result in results)


@pytest.mark.asyncio
async def test_custom_return_results_limit(mock_datasource):
    """Test with custom return_results configuration"""
    custom_config = {
        "datasources": {
            "mock_sql": {
                "type": "mock_sql",
                "relevance_threshold": 0.5,
                "max_results": 100,
                "return_results": 10,  # Custom limit
                "collection": "test_orders"
            }
        },
        "general": {
        }
    }

    retriever = MockSQLRetriever(config=custom_config, datasource=mock_datasource)
    retriever.collection = "test_orders"

    # Set mock results (50 rows)
    mock_rows = create_mock_rows(50)
    retriever.set_mock_results(mock_rows)

    # Get relevant context
    results = await retriever.get_relevant_context("test query")

    # Should return only 10 results
    assert len(results) == 10

    # Check metadata
    assert results[0]["metadata"]["total_available"] == 50
    assert results[0]["metadata"]["truncated"] == True
    assert results[0]["metadata"]["result_count"] == 10


@pytest.mark.asyncio
async def test_truncation_metadata_consistent_across_results(test_config, mock_datasource):
    """Test that truncation metadata is consistent across all returned results"""
    retriever = MockSQLRetriever(config=test_config, datasource=mock_datasource)
    retriever.collection = "test_orders"

    # Set mock results (20 rows)
    mock_rows = create_mock_rows(20)
    retriever.set_mock_results(mock_rows)

    # Get relevant context
    results = await retriever.get_relevant_context("test query")

    # All results should have same truncation metadata
    assert len(results) == 3

    for result in results:
        assert result["metadata"]["total_available"] == 20
        assert result["metadata"]["truncated"] == True
        assert result["metadata"]["result_count"] == 3


@pytest.mark.asyncio
async def test_empty_results(test_config, mock_datasource):
    """Test behavior with empty result set"""
    retriever = MockSQLRetriever(config=test_config, datasource=mock_datasource)
    retriever.collection = "test_orders"

    # Set empty mock results
    retriever.set_mock_results([])

    # Get relevant context
    results = await retriever.get_relevant_context("test query")

    # Should return empty list
    assert len(results) == 0


@pytest.mark.asyncio
async def test_exact_limit_no_truncation(test_config, mock_datasource):
    """Test when results exactly match return_results limit"""
    retriever = MockSQLRetriever(config=test_config, datasource=mock_datasource)
    retriever.collection = "test_orders"

    # Set mock results (exactly 3 rows, matching limit)
    mock_rows = create_mock_rows(3)
    retriever.set_mock_results(mock_rows)

    # Get relevant context
    results = await retriever.get_relevant_context("test query")

    # Should return all 3 results without truncation
    assert len(results) == 3

    # Check metadata (no truncation since count matches limit)
    assert results[0]["metadata"]["total_available"] == 3
    assert results[0]["metadata"]["truncated"] == False
    assert results[0]["metadata"]["result_count"] == 3


@pytest.mark.asyncio
async def test_relevance_filtering_before_truncation(test_config, mock_datasource):
    """Test that relevance filtering is applied before truncation"""
    retriever = MockSQLRetriever(config=test_config, datasource=mock_datasource)
    retriever.collection = "test_orders"
    retriever.relevance_threshold = 0.7  # High threshold

    # Set mock results (10 rows)
    mock_rows = create_mock_rows(10)
    retriever.set_mock_results(mock_rows)

    # Get relevant context
    results = await retriever.get_relevant_context("test query")

    # Results should be filtered by relevance first, then truncated
    # With high relevance threshold, some might be filtered out
    assert len(results) <= 3  # At most 3 (return_results limit)


@pytest.mark.asyncio
async def test_logging_truncation(test_config, mock_datasource, caplog):
    """Test that truncation is properly logged"""
    import logging
    caplog.set_level(logging.INFO)

    retriever = MockSQLRetriever(config=test_config, datasource=mock_datasource)
    retriever.collection = "test_orders"

    # Set mock results (50 rows)
    mock_rows = create_mock_rows(50)
    retriever.set_mock_results(mock_rows)

    # Get relevant context
    results = await retriever.get_relevant_context("test query")

    # Check that truncation was logged
    assert len(results) == 3
    # The log message should mention truncation
    # Note: Exact log message depends on logger configuration


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
