"""
Tests for FileVectorRetriever Multiple File Support

Tests the new functionality for querying multiple files simultaneously
using the file_ids parameter.
"""

import pytest
import pytest_asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock
import os

# Add server directory to Python path
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from retrievers.implementations.file.file_retriever import FileVectorRetriever
from services.file_metadata.metadata_store import FileMetadataStore


def create_test_config(db_path: str) -> dict:
    """Helper to create test config with SQLite database path"""
    return {
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': db_path
                }
            }
        }
    }


@pytest_asyncio.fixture
async def retriever_with_metadata(tmp_path):
    """Fixture providing retriever with metadata store"""
    db_path = str(tmp_path / "test_metadata.db")

    # Reset singleton to ensure test isolation
    FileMetadataStore.reset_instance()

    config = {
        'collection_prefix': 'test_files_',
        'vector_store': 'chroma',
        'embedding': {'provider': 'test'}  # Add provider for signature matching
    }

    retriever = FileVectorRetriever(config=config)
    metadata_config = create_test_config(db_path)
    retriever.metadata_store = FileMetadataStore(config=metadata_config)
    await retriever.metadata_store._ensure_initialized()
    retriever.initialized = True

    # Mock embeddings - 3 dimensions to match provider signature 'test_3'
    retriever.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])

    yield retriever

    retriever.metadata_store.close()
    FileMetadataStore.reset_instance()
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.mark.asyncio
async def test_get_collections_multiple_file_ids(retriever_with_metadata):
    """Test _get_collections_multiple with multiple file_ids"""
    api_key = 'test_key'

    # Create multiple files with different collections
    # Collection names include provider signature 'test_3' (provider='test', dimensions=3)
    file_data = [
        ('file_1', 'files_test_3_collection_1'),
        ('file_2', 'files_test_3_collection_2'),
        ('file_3', 'files_test_3_collection_3'),
    ]

    for file_id, collection_name in file_data:
        await retriever_with_metadata.metadata_store.record_file_upload(
            file_id=file_id,
            api_key=api_key,
            filename=f'{file_id}.txt',
            mime_type='text/plain',
            file_size=1024,
            storage_key=f'key_{file_id}',
            storage_type='vector'
        )
        await retriever_with_metadata.metadata_store.update_processing_status(
            file_id=file_id,
            status='completed',
            collection_name=collection_name
        )

    # Get collections for specific file_ids
    target_file_ids = ['file_1', 'file_2']
    collections = await retriever_with_metadata._get_collections_multiple(
        file_ids=target_file_ids,
        api_key=None,
        collection_name=None
    )

    # Should return collections for specified files only
    assert len(collections) == 2
    assert 'files_test_3_collection_1' in collections
    assert 'files_test_3_collection_2' in collections
    assert 'files_test_3_collection_3' not in collections


@pytest.mark.asyncio
async def test_get_collections_multiple_with_none_file_ids(retriever_with_metadata):
    """Test _get_collections_multiple with None file_ids (uses api_key)"""
    api_key = 'test_key'

    # Create files
    for i in range(3):
        file_id = f'file_{i}'
        await retriever_with_metadata.metadata_store.record_file_upload(
            file_id=file_id,
            api_key=api_key,
            filename=f'{file_id}.txt',
            mime_type='text/plain',
            file_size=1024,
            storage_key=f'key_{i}',
            storage_type='vector'
        )
        await retriever_with_metadata.metadata_store.update_processing_status(
            file_id=file_id,
            status='completed',
            collection_name=f'files_test_3_collection_{i}'
        )

    # Get all collections for API key
    collections = await retriever_with_metadata._get_collections_multiple(
        file_ids=None,
        api_key=api_key,
        collection_name=None
    )

    # Should return all collections for this API key
    assert len(collections) == 3
    assert all(f'files_test_3_collection_{i}' in collections for i in range(3))


@pytest.mark.asyncio
async def test_get_collections_multiple_with_collection_name_override(retriever_with_metadata):
    """Test that collection_name parameter overrides file_ids"""
    # When collection_name is provided, it should return that collection
    # regardless of file_ids
    collections = await retriever_with_metadata._get_collections_multiple(
        file_ids=['file_1', 'file_2'],
        api_key='test_key',
        collection_name='specific_collection'
    )

    assert collections == ['specific_collection']


@pytest.mark.asyncio
async def test_get_collections_multiple_empty_file_ids(retriever_with_metadata):
    """Test _get_collections_multiple with empty file_ids array"""
    api_key = 'test_key'

    # Create file
    await retriever_with_metadata.metadata_store.record_file_upload(
        file_id='file_1',
        api_key=api_key,
        filename='test.txt',
        mime_type='text/plain',
        file_size=1024,
        storage_key='key',
        storage_type='vector'
    )
    await retriever_with_metadata.metadata_store.update_processing_status(
        file_id='file_1',
        status='completed',
        collection_name='files_test_3_collection_1'
    )

    # Empty file_ids should fall back to api_key lookup
    collections = await retriever_with_metadata._get_collections_multiple(
        file_ids=[],
        api_key=api_key,
        collection_name=None
    )

    # Should return collections for API key
    assert len(collections) > 0


@pytest.mark.asyncio
async def test_get_collections_multiple_nonexistent_files(retriever_with_metadata):
    """Test _get_collections_multiple with file_ids that don't exist"""
    collections = await retriever_with_metadata._get_collections_multiple(
        file_ids=['nonexistent_1', 'nonexistent_2'],
        api_key=None,
        collection_name=None
    )

    # Should return empty list (no collections found)
    assert collections == []


@pytest.mark.asyncio
async def test_search_collection_with_multiple_file_ids_filter():
    """Test _search_collection with multiple file_ids post-filtering"""
    config = {
        'collection_prefix': 'test_files_',
        'vector_store': 'chroma'
    }

    retriever = FileVectorRetriever(config=config)
    retriever.initialized = True
    retriever.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])

    # Mock vector store that returns results from different files
    mock_store = AsyncMock()
    mock_store.search_vectors = AsyncMock(return_value=[
        {
            'id': 'chunk_1',
            'content': 'Content from file 1',
            'score': 0.95,
            'metadata': {'file_id': 'file_1', 'chunk_index': 0}
        },
        {
            'id': 'chunk_2',
            'content': 'Content from file 2',
            'score': 0.90,
            'metadata': {'file_id': 'file_2', 'chunk_index': 0}
        },
        {
            'id': 'chunk_3',
            'content': 'Content from file 3',
            'score': 0.85,
            'metadata': {'file_id': 'file_3', 'chunk_index': 0}
        }
    ])
    retriever._default_store = mock_store

    # Mock metadata store
    retriever.metadata_store = AsyncMock()
    retriever.metadata_store.get_chunk_info = AsyncMock(return_value={})

    # Search with specific file_ids
    target_file_ids = ['file_1', 'file_2']
    results = await retriever._search_collection(
        collection_name='test_collection',
        query_embedding=[0.1, 0.2, 0.3],
        file_ids=target_file_ids
    )

    # Results should be filtered to only include file_1 and file_2
    assert len(results) == 2
    result_file_ids = [r['metadata']['file_id'] for r in results]
    assert 'file_1' in result_file_ids
    assert 'file_2' in result_file_ids
    assert 'file_3' not in result_file_ids


@pytest.mark.asyncio
async def test_get_relevant_context_with_multiple_file_ids(retriever_with_metadata):
    """Test get_relevant_context with multiple file_ids"""
    api_key = 'test_key'

    # Create multiple files
    for i in range(3):
        file_id = f'file_{i}'
        await retriever_with_metadata.metadata_store.record_file_upload(
            file_id=file_id,
            api_key=api_key,
            filename=f'doc_{i}.txt',
            mime_type='text/plain',
            file_size=1024,
            storage_key=f'key_{i}',
            storage_type='vector'
        )
        await retriever_with_metadata.metadata_store.update_processing_status(
            file_id=file_id,
            status='completed',
            collection_name=f'files_test_3_collection_{i}'
        )

    # Mock vector store
    mock_store = AsyncMock()
    mock_store.search_vectors = AsyncMock(return_value=[
        {
            'id': 'chunk_0',
            'text': 'Content 0',
            'score': 0.9,
            'metadata': {'file_id': 'file_0', 'chunk_index': 0}
        },
        {
            'id': 'chunk_1',
            'text': 'Content 1',
            'score': 0.85,
            'metadata': {'file_id': 'file_1', 'chunk_index': 0}
        }
    ])
    retriever_with_metadata._default_store = mock_store
    retriever_with_metadata.metadata_store.get_chunk_info = AsyncMock(return_value={})
    retriever_with_metadata._format_results = lambda x: x
    retriever_with_metadata.apply_domain_filtering = lambda x, y: x

    # Query specific files
    target_file_ids = ['file_0', 'file_1']
    results = await retriever_with_metadata.get_relevant_context(
        query="Test query",
        api_key=api_key,
        file_ids=target_file_ids
    )

    # Should have results
    assert len(results) > 0

    # Vector store should have been queried
    assert mock_store.search_vectors.called


@pytest.mark.asyncio
async def test_single_file_id_in_array(retriever_with_metadata):
    """Test using single file_id in file_ids array"""
    api_key = 'test_key'

    # Create file
    file_id = 'file_123'
    await retriever_with_metadata.metadata_store.record_file_upload(
        file_id=file_id,
        api_key=api_key,
        filename='test.txt',
        mime_type='text/plain',
        file_size=1024,
        storage_key='key',
        storage_type='vector'
    )
    await retriever_with_metadata.metadata_store.update_processing_status(
        file_id=file_id,
        status='completed',
        collection_name='files_test_3_collection_123'
    )

    # Mock vector store
    mock_store = AsyncMock()
    mock_store.search_vectors = AsyncMock(return_value=[])
    retriever_with_metadata._default_store = mock_store

    # Call with single file_id in file_ids array
    results = await retriever_with_metadata.get_relevant_context(
        query="Test",
        api_key=api_key,
        file_ids=[file_id]  # Use file_ids array with single file
    )

    # Should work
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_multiple_file_ids_in_array(retriever_with_metadata):
    """Test using multiple file_ids in array"""
    api_key = 'test_key'

    # Create files
    for i in range(3):
        file_id = f'file_{i}'
        await retriever_with_metadata.metadata_store.record_file_upload(
            file_id=file_id,
            api_key=api_key,
            filename=f'doc_{i}.txt',
            mime_type='text/plain',
            file_size=1024,
            storage_key=f'key_{i}',
            storage_type='vector'
        )
        await retriever_with_metadata.metadata_store.update_processing_status(
            file_id=file_id,
            status='completed',
            collection_name=f'files_test_3_collection_{i}'
        )

    # Mock vector store
    mock_store = AsyncMock()
    mock_store.search_vectors = AsyncMock(return_value=[])
    retriever_with_metadata._default_store = mock_store
    retriever_with_metadata._format_results = lambda x: x
    retriever_with_metadata.apply_domain_filtering = lambda x, y: x

    # Call with multiple file_ids
    results = await retriever_with_metadata.get_relevant_context(
        query="Test",
        api_key=api_key,
        file_ids=['file_1', 'file_2']  # Use file_ids array
    )

    # Should work
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_get_collections_multiple_mixed_existence(retriever_with_metadata):
    """Test _get_collections_multiple with mix of existing and non-existing file_ids"""
    api_key = 'test_key'

    # Create only some files
    await retriever_with_metadata.metadata_store.record_file_upload(
        file_id='file_exists',
        api_key=api_key,
        filename='exists.txt',
        mime_type='text/plain',
        file_size=1024,
        storage_key='key',
        storage_type='vector'
    )
    await retriever_with_metadata.metadata_store.update_processing_status(
        file_id='file_exists',
        status='completed',
        collection_name='files_test_3_collection_exists'
    )

    # Query with mix of existing and non-existing
    file_ids = ['file_exists', 'file_not_exists', 'file_also_not_exists']
    collections = await retriever_with_metadata._get_collections_multiple(
        file_ids=file_ids,
        api_key=None,
        collection_name=None
    )

    # Should return only collections for existing files
    assert len(collections) == 1
    assert 'files_test_3_collection_exists' in collections


@pytest.mark.asyncio
async def test_search_collection_single_file_id_uses_filter_metadata():
    """Test that single file_id uses filter_metadata in vector search"""
    config = {'collection_prefix': 'test_files_', 'vector_store': 'chroma'}
    retriever = FileVectorRetriever(config=config)
    retriever.initialized = True

    # Mock vector store
    mock_store = AsyncMock()
    mock_store.search_vectors = AsyncMock(return_value=[])
    retriever._default_store = mock_store
    retriever.metadata_store = AsyncMock()
    retriever.metadata_store.get_chunk_info = AsyncMock(return_value={})

    # Search with single file_id in file_ids array
    await retriever._search_collection(
        collection_name='test_collection',
        query_embedding=[0.1, 0.2, 0.3],
        file_ids=['single_file']
    )

    # Verify filter_metadata was used
    call_kwargs = mock_store.search_vectors.call_args[1]
    assert 'filter_metadata' in call_kwargs
    assert call_kwargs['filter_metadata'] == {'file_id': 'single_file'}


@pytest.mark.asyncio
async def test_search_collection_multiple_file_ids_post_filters():
    """Test that multiple file_ids use post-filtering"""
    config = {'collection_prefix': 'test_files_', 'vector_store': 'chroma'}
    retriever = FileVectorRetriever(config=config)
    retriever.initialized = True

    # Mock vector store returning diverse results
    mock_store = AsyncMock()
    mock_store.search_vectors = AsyncMock(return_value=[
        {'id': '1', 'content': 'A', 'score': 0.9, 'metadata': {'file_id': 'file_1', 'chunk_index': 0}},
        {'id': '2', 'content': 'B', 'score': 0.8, 'metadata': {'file_id': 'file_2', 'chunk_index': 0}},
        {'id': '3', 'content': 'C', 'score': 0.7, 'metadata': {'file_id': 'file_3', 'chunk_index': 0}},
    ])
    retriever._default_store = mock_store
    retriever.metadata_store = AsyncMock()
    retriever.metadata_store.get_chunk_info = AsyncMock(return_value={})

    # Search with multiple file_ids
    target_file_ids = ['file_1', 'file_3']
    results = await retriever._search_collection(
        collection_name='test_collection',
        query_embedding=[0.1, 0.2, 0.3],
        file_ids=target_file_ids
    )

    # Should filter results to only target files
    assert len(results) == 2
    result_file_ids = [r['metadata']['file_id'] for r in results]
    assert 'file_1' in result_file_ids
    assert 'file_3' in result_file_ids
    assert 'file_2' not in result_file_ids


@pytest.mark.asyncio
async def test_get_relevant_context_aggregates_across_collections(retriever_with_metadata):
    """Test that get_relevant_context aggregates results from multiple collections"""
    api_key = 'test_key'

    # Create files in different collections
    for i in range(2):
        file_id = f'file_{i}'
        await retriever_with_metadata.metadata_store.record_file_upload(
            file_id=file_id,
            api_key=api_key,
            filename=f'doc_{i}.txt',
            mime_type='text/plain',
            file_size=1024,
            storage_key=f'key_{i}',
            storage_type='vector'
        )
        await retriever_with_metadata.metadata_store.update_processing_status(
            file_id=file_id,
            status='completed',
            collection_name=f'files_test_3_collection_{i}'
        )

    # Mock vector store to return different results per collection
    call_count = [0]

    async def mock_search_vectors(*args, **kwargs):
        result_index = call_count[0]
        call_count[0] += 1
        return [
            {
                'id': f'chunk_{result_index}',
                'text': f'Content from collection {result_index}',
                'score': 0.9 - (result_index * 0.1),
                'metadata': {
                    'file_id': f'file_{result_index}',
                    'chunk_index': 0
                }
            }
        ]

    mock_store = AsyncMock()
    mock_store.search_vectors = mock_search_vectors
    retriever_with_metadata._default_store = mock_store
    retriever_with_metadata.metadata_store.get_chunk_info = AsyncMock(return_value={})
    retriever_with_metadata._format_results = lambda x: x
    retriever_with_metadata.apply_domain_filtering = lambda x, y: x

    # Query multiple files
    results = await retriever_with_metadata.get_relevant_context(
        query="Test query",
        api_key=api_key,
        file_ids=['file_0', 'file_1']
    )

    # Should have results from both collections
    assert len(results) > 0  # Should have results from both collections


@pytest.mark.asyncio
async def test_file_ids_empty_vs_none(retriever_with_metadata):
    """Test difference between empty file_ids [] and None"""
    api_key = 'test_key'

    # Create file
    await retriever_with_metadata.metadata_store.record_file_upload(
        file_id='file_1',
        api_key=api_key,
        filename='test.txt',
        mime_type='text/plain',
        file_size=1024,
        storage_key='key',
        storage_type='vector'
    )
    await retriever_with_metadata.metadata_store.update_processing_status(
        file_id='file_1',
        status='completed',
        collection_name='files_test_3_collection_1'
    )

    # Mock store
    mock_store = AsyncMock()
    mock_store.search_vectors = AsyncMock(return_value=[])
    retriever_with_metadata._default_store = mock_store
    retriever_with_metadata._format_results = lambda x: x
    retriever_with_metadata.apply_domain_filtering = lambda x, y: x

    # Test with None (should use api_key)
    await retriever_with_metadata.get_relevant_context(
        query="Test",
        api_key=api_key,
        file_ids=None
    )

    # Test with empty list (should also use api_key)
    await retriever_with_metadata.get_relevant_context(
        query="Test",
        api_key=api_key,
        file_ids=[]
    )

    # Both should work similarly
    assert mock_store.search_vectors.call_count >= 2
