"""
Test Thread Dataset Service
============================

Tests for the thread dataset service including dataset storage,
compression, retrieval, and cleanup.

Prerequisites:
1. SQLite service for database storage
2. Test creates temporary database files
"""

import os
import sys
import pytest
from pathlib import Path
from pytest_asyncio import fixture
import tempfile
import shutil
import json
import gzip

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Get the project root (parent of server directory)
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent

# Add server directory to Python path
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.thread_dataset_service import ThreadDatasetService
from services.sqlite_service import SQLiteService
from utils.id_utils import generate_id


@fixture(scope="function")
async def dataset_service():
    """Fixture to create thread dataset service with cleanup"""
    # Create temporary directory for test database
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_orbit.db")

    # Create test configuration
    config = {
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': db_path
                }
            }
        },
        'general': {
        },
        'conversation_threading': {
            'enabled': True,
            'dataset_ttl_hours': 24,
            'storage_backend': 'database',  # Use database for testing (no Redis required)
            'redis_key_prefix': 'thread_dataset:'
        }
    }

    # Initialize services
    sqlite_service = SQLiteService(config)
    await sqlite_service.initialize()

    service = ThreadDatasetService(config)
    await service.initialize()

    # Yield service for tests
    yield service

    # Cleanup
    sqlite_service.close()
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_dataset_storage(dataset_service):
    """Test storing a dataset"""
    thread_id = generate_id()
    query_context = {
        "original_query": "What is machine learning?",
        "template_id": "ml_template",
        "parameters_used": {"topic": "AI"}
    }
    raw_results = [
        {
            "content": "Machine learning is a subset of AI",
            "metadata": {"score": 0.95, "source": "doc1"}
        },
        {
            "content": "ML uses algorithms to learn from data",
            "metadata": {"score": 0.87, "source": "doc2"}
        }
    ]

    # Store dataset
    dataset_key = await dataset_service.store_dataset(
        thread_id=thread_id,
        query_context=query_context,
        raw_results=raw_results
    )

    # Verify dataset key
    assert dataset_key is not None
    assert str(thread_id) in dataset_key


@pytest.mark.asyncio
async def test_dataset_retrieval(dataset_service):
    """Test retrieving a stored dataset"""
    thread_id = generate_id()
    query_context = {
        "original_query": "Test query",
        "template_id": "test_template"
    }
    raw_results = [
        {"content": "Result 1", "metadata": {"score": 0.9}},
        {"content": "Result 2", "metadata": {"score": 0.8}}
    ]

    # Store dataset
    dataset_key = await dataset_service.store_dataset(
        thread_id=thread_id,
        query_context=query_context,
        raw_results=raw_results
    )

    # Retrieve dataset
    retrieved = await dataset_service.get_dataset(dataset_key)

    # Verify retrieval
    assert retrieved is not None
    retrieved_context, retrieved_results = retrieved

    assert retrieved_context['original_query'] == "Test query"
    assert retrieved_context['template_id'] == "test_template"
    assert len(retrieved_results) == 2
    assert retrieved_results[0]['content'] == "Result 1"


@pytest.mark.asyncio
async def test_dataset_compression(dataset_service):
    """Test that datasets are compressed properly"""
    # Create large dataset to test compression
    thread_id = generate_id()
    query_context = {"query": "test"}

    # Generate large dataset
    raw_results = [
        {
            "content": f"Document {i} with lots of text " * 100,
            "metadata": {"id": i, "score": 0.9 - (i * 0.01)}
        }
        for i in range(50)
    ]

    # Store dataset
    dataset_key = await dataset_service.store_dataset(
        thread_id=thread_id,
        query_context=query_context,
        raw_results=raw_results
    )

    # Retrieve and verify
    retrieved = await dataset_service.get_dataset(dataset_key)
    assert retrieved is not None

    retrieved_context, retrieved_results = retrieved
    assert len(retrieved_results) == 50
    assert retrieved_results[0]['content'].startswith("Document 0")


@pytest.mark.asyncio
async def test_dataset_deletion(dataset_service):
    """Test deleting a dataset"""
    thread_id = generate_id()
    query_context = {"query": "test"}
    raw_results = [{"content": "test", "metadata": {}}]

    # Store dataset
    dataset_key = await dataset_service.store_dataset(
        thread_id=thread_id,
        query_context=query_context,
        raw_results=raw_results
    )

    # Verify dataset exists
    retrieved = await dataset_service.get_dataset(dataset_key)
    assert retrieved is not None

    # Delete dataset
    deleted = await dataset_service.delete_dataset(dataset_key)
    assert deleted is True

    # Verify dataset is gone
    retrieved_after = await dataset_service.get_dataset(dataset_key)
    assert retrieved_after is None


@pytest.mark.asyncio
async def test_dataset_with_special_characters(dataset_service):
    """Test storing datasets with special characters and unicode"""
    thread_id = generate_id()
    query_context = {
        "original_query": "What is 机器学习?",
        "special_chars": "Test with 'quotes', \"double quotes\", and \n newlines"
    }
    raw_results = [
        {
            "content": "机器学习是人工智能的一个分支",
            "metadata": {"emoji": "🤖", "symbols": "< > & \""}
        }
    ]

    # Store dataset
    dataset_key = await dataset_service.store_dataset(
        thread_id=thread_id,
        query_context=query_context,
        raw_results=raw_results
    )

    # Retrieve and verify
    retrieved = await dataset_service.get_dataset(dataset_key)
    assert retrieved is not None

    retrieved_context, retrieved_results = retrieved
    assert "机器学习" in retrieved_context['original_query']
    assert retrieved_results[0]['metadata']['emoji'] == "🤖"


@pytest.mark.asyncio
async def test_dataset_with_nested_metadata(dataset_service):
    """Test storing datasets with deeply nested metadata"""
    thread_id = generate_id()
    query_context = {
        "query": "test",
        "nested": {
            "level1": {
                "level2": {
                    "level3": "deep value"
                }
            }
        }
    }
    raw_results = [
        {
            "content": "test",
            "metadata": {
                "complex": {
                    "array": [1, 2, 3],
                    "object": {"key": "value"},
                    "mixed": [{"a": 1}, {"b": 2}]
                }
            }
        }
    ]

    # Store dataset
    dataset_key = await dataset_service.store_dataset(
        thread_id=thread_id,
        query_context=query_context,
        raw_results=raw_results
    )

    # Retrieve and verify
    retrieved = await dataset_service.get_dataset(dataset_key)
    assert retrieved is not None

    retrieved_context, retrieved_results = retrieved
    assert retrieved_context['nested']['level1']['level2']['level3'] == "deep value"
    assert retrieved_results[0]['metadata']['complex']['array'] == [1, 2, 3]


@pytest.mark.asyncio
async def test_dataset_empty_results(dataset_service):
    """Test storing dataset with empty results"""
    thread_id = generate_id()
    query_context = {"query": "no results"}
    raw_results = []

    # Store dataset with empty results
    dataset_key = await dataset_service.store_dataset(
        thread_id=thread_id,
        query_context=query_context,
        raw_results=raw_results
    )

    # Retrieve and verify
    retrieved = await dataset_service.get_dataset(dataset_key)
    assert retrieved is not None

    retrieved_context, retrieved_results = retrieved
    assert retrieved_context['query'] == "no results"
    assert len(retrieved_results) == 0


@pytest.mark.asyncio
async def test_dataset_large_content(dataset_service):
    """Test storing very large dataset"""
    thread_id = generate_id()
    query_context = {"query": "large dataset"}

    # Create large content (1MB per document)
    large_content = "A" * (1024 * 1024)  # 1MB of 'A's

    raw_results = [
        {
            "content": large_content,
            "metadata": {"size": "1MB", "index": i}
        }
        for i in range(5)  # 5MB total
    ]

    # Store dataset
    dataset_key = await dataset_service.store_dataset(
        thread_id=thread_id,
        query_context=query_context,
        raw_results=raw_results
    )

    # Retrieve and verify
    retrieved = await dataset_service.get_dataset(dataset_key)
    assert retrieved is not None

    retrieved_context, retrieved_results = retrieved
    assert len(retrieved_results) == 5
    assert len(retrieved_results[0]['content']) == 1024 * 1024


@pytest.mark.asyncio
async def test_dataset_nonexistent_key(dataset_service):
    """Test retrieving nonexistent dataset"""
    # Try to get dataset that doesn't exist
    retrieved = await dataset_service.get_dataset("nonexistent_key")
    assert retrieved is None


@pytest.mark.asyncio
async def test_multiple_datasets(dataset_service):
    """Test storing and retrieving multiple datasets"""
    datasets = []

    # Create multiple datasets
    for i in range(5):
        thread_id = generate_id()
        query_context = {"query": f"Query {i}"}
        raw_results = [{"content": f"Result {i}", "metadata": {"index": i}}]

        dataset_key = await dataset_service.store_dataset(
            thread_id=thread_id,
            query_context=query_context,
            raw_results=raw_results
        )
        datasets.append((dataset_key, i))

    # Verify all datasets can be retrieved
    for dataset_key, i in datasets:
        retrieved = await dataset_service.get_dataset(dataset_key)
        assert retrieved is not None

        retrieved_context, retrieved_results = retrieved
        assert retrieved_context['query'] == f"Query {i}"
        assert retrieved_results[0]['metadata']['index'] == i


@pytest.mark.asyncio
async def test_compression_efficiency(dataset_service):
    """Test compression reduces data size"""
    # Create repetitive data (highly compressible)
    query_context = {"query": "compression test"}
    raw_results = [
        {
            "content": "This is a repetitive string. " * 1000,
            "metadata": {"repeated": "value" * 100}
        }
        for _ in range(10)
    ]

    # Manual compression test
    json_str = json.dumps({"query_context": query_context, "raw_results": raw_results})
    uncompressed_size = len(json_str.encode('utf-8'))
    compressed_size = len(gzip.compress(json_str.encode('utf-8')))

    # Compression should reduce size significantly
    compression_ratio = compressed_size / uncompressed_size
    assert compression_ratio < 0.3  # Should compress to less than 30% of original

    # Verify dataset service can store and retrieve
    thread_id = generate_id()
    dataset_key = await dataset_service.store_dataset(
        thread_id=thread_id,
        query_context=query_context,
        raw_results=raw_results
    )

    retrieved = await dataset_service.get_dataset(dataset_key)
    assert retrieved is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
