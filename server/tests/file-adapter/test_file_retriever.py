"""
Tests for File Vector Retriever

Tests the FileVectorRetriever class for querying uploaded files via vector stores.
"""

import pytest
import pytest_asyncio
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# Add server directory to Python path
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from retrievers.implementations.file.file_retriever import FileVectorRetriever
from services.file_metadata.metadata_store import FileMetadataStore


@pytest_asyncio.fixture
async def mock_retriever(tmp_path):
    """Fixture to provide a FileVectorRetriever with mocked dependencies"""
    test_db_path = str(tmp_path / "test_orbit.db")
    
    config = {
        'collection_prefix': 'test_files_',
        'vector_store': 'chroma'
    }
    
    retriever = FileVectorRetriever(config=config)
    retriever.metadata_store = FileMetadataStore(db_path=test_db_path)
    
    yield retriever
    
    retriever.metadata_store.close()
    import os
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


def test_file_retriever_initialization_defaults():
    """Test FileVectorRetriever initialization with default configuration"""
    config = {}
    retriever = FileVectorRetriever(config=config)
    
    assert retriever.metadata_store is not None
    assert retriever.collection_prefix == 'files_'  # Default from global config or fallback
    assert retriever.store_manager is None
    assert retriever._default_store is None


def test_file_retriever_initialization_adapter_config():
    """Test FileVectorRetriever initialization with adapter-specific config"""
    # In production, DynamicAdapterManager places adapter config at config['adapter_config']
    config = {
        'adapter_config': {
            'collection_prefix': 'custom_prefix_',
            'vector_store': 'pinecone'
        }
    }

    retriever = FileVectorRetriever(config=config)

    assert retriever.collection_prefix == 'custom_prefix_'


def test_file_retriever_initialization_global_config():
    """Test FileVectorRetriever initialization reading from global files config"""
    # Updated to use modern config structure: files.default_* instead of files.retriever.*
    config = {
        'files': {
            'default_collection_prefix': 'global_files_',
            'default_vector_store': 'qdrant'
        }
    }

    retriever = FileVectorRetriever(config=config)

    assert retriever.collection_prefix == 'global_files_'


def test_file_retriever_config_priority_adapter_over_global():
    """Test that adapter config takes priority over global config"""
    # Updated to use modern config structure
    config = {
        'adapter_config': {
            'collection_prefix': 'adapter_prefix_',  # Adapter-specific config
        },
        'files': {
            'default_collection_prefix': 'global_prefix_',  # Global config
            'default_vector_store': 'chroma'
        }
    }

    retriever = FileVectorRetriever(config=config)

    # Adapter config should win
    assert retriever.collection_prefix == 'adapter_prefix_'


@pytest.mark.asyncio
async def test_get_collections_by_collection_name():
    """Test getting collections when collection_name is provided"""
    retriever = FileVectorRetriever(config={})
    
    collections = await retriever._get_collections_multiple(
        file_ids=None,
        api_key=None,
        collection_name='specific_collection'
    )
    
    assert collections == ['specific_collection']


@pytest.mark.asyncio
async def test_get_collections_by_file_id(mock_retriever):
    """Test getting collections when file_id is provided"""
    # Create a file in metadata store
    file_id = 'test_file_123'
    await mock_retriever.metadata_store.record_file_upload(
        file_id=file_id,
        api_key='test_key',
        filename='test.txt',
        mime_type='text/plain',
        file_size=100,
        storage_key='key',
        storage_type='vector'
    )
    
    # Update with collection name that matches provider signature format
    # Provider signature will be 'test_3' (provider='test', dimensions=3 from mock)
    collection_name = 'files_test_3_file_test_file_123'
    await mock_retriever.metadata_store.update_processing_status(
        file_id=file_id,
        status='completed',
        collection_name=collection_name
    )
    
    # Mock embedding to avoid dimension/provider checks
    mock_retriever.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
    mock_retriever.config = {'embedding': {'provider': 'test'}}
    
    collections = await mock_retriever._get_collections_multiple(
        file_ids=[file_id],
        api_key=None,
        collection_name=None
    )
    
    assert len(collections) == 1
    assert collection_name in collections


@pytest.mark.asyncio
async def test_get_collections_by_api_key(mock_retriever):
    """Test getting collections when api_key is provided"""
    api_key = 'test_api_key'
    
    # Create multiple files with collections that match provider signature format
    # Provider signature will be 'test_3' (provider='test', dimensions=3 from mock)
    for i in range(3):
        file_id = f'test_file_{i}'
        await mock_retriever.metadata_store.record_file_upload(
            file_id=file_id,
            api_key=api_key,
            filename=f'test_{i}.txt',
            mime_type='text/plain',
            file_size=100,
            storage_key=f'key_{i}',
            storage_type='vector'
        )
        # Collection name includes provider signature 'test_3'
        collection_name = f'files_test_3_collection_{i}'
        await mock_retriever.metadata_store.update_processing_status(
            file_id=file_id,
            status='completed',
            collection_name=collection_name
        )
    
    # Mock embedding to avoid dimension/provider checks
    mock_retriever.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
    mock_retriever.config = {'embedding': {'provider': 'test'}}
    
    collections = await mock_retriever._get_collections_multiple(
        file_ids=None,
        api_key=api_key,
        collection_name=None
    )
    
    assert len(collections) == 3
    assert all(f'files_test_3_collection_{i}' in collections for i in range(3))


@pytest.mark.asyncio
async def test_get_collections_empty():
    """Test getting collections when no filters provided"""
    retriever = FileVectorRetriever(config={})
    
    collections = await retriever._get_collections_multiple(
        file_ids=None,
        api_key=None,
        collection_name=None
    )
    
    assert collections == []


@pytest.mark.asyncio
async def test_search_collection_no_store():
    """Test searching collection when no vector store is available"""
    retriever = FileVectorRetriever(config={})
    retriever._default_store = None
    
    results = await retriever._search_collection(
        collection_name='test_collection',
        query_embedding=[0.1, 0.2, 0.3],
        file_ids=None
    )
    
    assert results == []


@pytest.mark.asyncio
async def test_search_collection_with_store():
    """Test searching collection with mocked vector store"""
    retriever = FileVectorRetriever(config={})
    
    # Mock vector store
    mock_store = AsyncMock()
    mock_store.search_vectors = AsyncMock(return_value=[
        {
            'id': 'chunk_1',
            'text': 'Relevant content',
            'score': 0.85,
            'metadata': {'file_id': 'file_1', 'chunk_index': 0}
        },
        {
            'id': 'chunk_2',
            'text': 'More content',
            'score': 0.75,
            'metadata': {'file_id': 'file_1', 'chunk_index': 1}
        }
    ])
    
    retriever._default_store = mock_store
    retriever.metadata_store = AsyncMock()
    retriever.metadata_store.get_chunk_info = AsyncMock(return_value={
        'chunk_id': 'chunk_1',
        'file_id': 'file_1',
        'chunk_index': 0
    })
    
    results = await retriever._search_collection(
        collection_name='test_collection',
        query_embedding=[0.1, 0.2, 0.3],
        file_ids=None
    )
    
    assert len(results) == 2
    assert mock_store.search_vectors.called
    # Verify filter metadata if file_ids provided
    call_args = mock_store.search_vectors.call_args
    assert call_args[1]['collection_name'] == 'test_collection'


@pytest.mark.asyncio
async def test_search_collection_with_file_id_filter():
    """Test searching collection with file_ids filter"""
    retriever = FileVectorRetriever(config={})
    
    # Mock vector store
    mock_store = AsyncMock()
    mock_store.search_vectors = AsyncMock(return_value=[])
    retriever._default_store = mock_store
    
    await retriever._search_collection(
        collection_name='test_collection',
        query_embedding=[0.1, 0.2, 0.3],
        file_ids=['specific_file_id']
    )
    
    # Verify filter_metadata included file_id
    call_args = mock_store.search_vectors.call_args
    assert call_args[1]['filter_metadata'] == {'file_id': 'specific_file_id'}


@pytest.mark.asyncio
async def test_format_results():
    """Test formatting search results"""
    retriever = FileVectorRetriever(config={'files': {}})
    
    results = [
        {
            'id': 'chunk_1',
            'text': 'Content here',
            'score': 0.9,
            'metadata': {
                'file_id': 'file_123',
                'chunk_index': 0
            },
            'chunk_metadata': {
                'chunk_id': 'chunk_1',
                'file_id': 'file_123'
            }
        }
    ]
    
    formatted = retriever._format_results(results)
    
    assert len(formatted) == 1
    assert formatted[0]['content'] == 'Content here'
    assert formatted[0]['metadata']['chunk_id'] == 'chunk_1'
    assert formatted[0]['metadata']['file_id'] == 'file_123'
    assert formatted[0]['metadata']['confidence'] == 0.9


@pytest.mark.asyncio
async def test_format_results_no_file_id():
    """Test formatting results without file_id in metadata"""
    retriever = FileVectorRetriever(config={'files': {}})
    
    results = [
        {
            'id': 'chunk_1',
            'text': 'Content',
            'score': 0.8,
            'metadata': {}  # No file_id
        }
    ]
    
    formatted = retriever._format_results(results)
    
    # Should skip results without file_id
    assert len(formatted) == 0


@pytest.mark.asyncio
@patch('vector_stores.base.store_manager.StoreManager')
@patch('services.api_key_service.ApiKeyService')
async def test_initialize(mock_api_key_service_class, mock_store_manager_class):
    """Test retriever initialization"""
    config = {
        'vector_store': 'chroma'
    }
    
    retriever = FileVectorRetriever(config=config)
    
    # Mock API key service to avoid MongoDB initialization
    mock_api_key_service = AsyncMock()
    mock_api_key_service.initialize = AsyncMock()
    mock_api_key_service_class.return_value = mock_api_key_service
    
    # Mock embeddings
    retriever.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
    
    # Mock store manager
    mock_store_manager = Mock()
    mock_store = AsyncMock()
    mock_store_manager.get_store = AsyncMock(return_value=mock_store)
    mock_store_manager_class.return_value = mock_store_manager
    
    # Ensure the retriever's store_manager uses the mocked one
    retriever.store_manager = mock_store_manager
    
    await retriever.initialize()
    
    assert retriever.initialized is True
    assert retriever.store_manager is not None
    assert retriever._default_store is not None


@pytest.mark.asyncio
@patch('vector_stores.base.store_manager.StoreManager')
@patch('services.api_key_service.ApiKeyService')
async def test_initialize_uses_global_vector_store_config(mock_api_key_service_class, mock_store_manager_class):
    """Test initialization uses global files.default_vector_store config"""
    # Updated to use modern config structure
    config = {
        'files': {
            'default_vector_store': 'qdrant'  # Global config
        }
    }
    
    retriever = FileVectorRetriever(config=config)
    
    # Mock API key service to avoid MongoDB initialization
    mock_api_key_service = AsyncMock()
    mock_api_key_service.initialize = AsyncMock()
    mock_api_key_service_class.return_value = mock_api_key_service
    
    # Mock embeddings
    retriever.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
    
    # Mock store manager
    mock_store_manager = Mock()
    mock_store = AsyncMock()
    mock_store_manager.get_store = AsyncMock(return_value=mock_store)
    mock_store_manager_class.return_value = mock_store_manager
    
    # Ensure the retriever's store_manager uses the mocked one
    retriever.store_manager = mock_store_manager
    
    await retriever.initialize()
    
    # Verify get_store was called with 'qdrant'
    call_args = mock_store_manager.get_store.call_args
    assert call_args[0][0] == 'qdrant'


@pytest.mark.asyncio
@patch('vector_stores.base.store_manager.StoreManager')
@patch('services.api_key_service.ApiKeyService')
async def test_initialize_adapter_config_overrides_global(mock_api_key_service_class, mock_store_manager_class):
    """Test initialization uses adapter config over global config"""
    # Updated to use modern config structure
    config = {
        'adapter_config': {
            'vector_store': 'pinecone',  # Adapter config (should win)
        },
        'files': {
            'default_vector_store': 'chroma'  # Global config (should be ignored)
        }
    }
    
    retriever = FileVectorRetriever(config=config)
    
    # Mock API key service to avoid MongoDB initialization
    mock_api_key_service = AsyncMock()
    mock_api_key_service.initialize = AsyncMock()
    mock_api_key_service_class.return_value = mock_api_key_service
    
    # Mock embeddings
    retriever.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
    
    # Mock store manager
    mock_store_manager = Mock()
    mock_store = AsyncMock()
    mock_store_manager.get_store = AsyncMock(return_value=mock_store)
    mock_store_manager_class.return_value = mock_store_manager
    
    # Ensure the retriever's store_manager uses the mocked one
    retriever.store_manager = mock_store_manager
    
    await retriever.initialize()
    
    # Verify get_store was called with 'pinecone' (adapter config)
    call_args = mock_store_manager.get_store.call_args
    assert call_args[0][0] == 'pinecone'


@pytest.mark.asyncio
async def test_get_relevant_context_requires_initialization():
    """Test that get_relevant_context calls ensure_initialized"""
    retriever = FileVectorRetriever(config={'files': {}})
    retriever.initialized = False
    
    # Mock ensure_initialized to track if it's called
    ensure_called = []
    async def mock_ensure_initialized():
        ensure_called.append(True)
        retriever.initialized = True
    
    retriever.ensure_initialized = mock_ensure_initialized
    retriever.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
    retriever._get_collections_multiple = AsyncMock(return_value=[])
    
    result = await retriever.get_relevant_context("test query")
    
    # Should have called ensure_initialized
    assert len(ensure_called) > 0
    assert result == []  # Empty because no collections


@pytest.mark.asyncio
async def test_get_relevant_context_basic(mock_retriever):
    """Test basic context retrieval"""
    # Initialize retriever
    mock_retriever.initialized = True
    mock_retriever.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])

    # Mock store and search
    mock_store = AsyncMock()
    mock_store.search_vectors = AsyncMock(return_value=[
        {
            'id': 'chunk_1',
            'text': 'Relevant content',
            'score': 0.9,
            'metadata': {'file_id': 'file_1', 'chunk_index': 0}
        }
    ])
    mock_retriever._default_store = mock_store
    mock_retriever.store_manager = Mock()

    # Mock collection retrieval with provider-aware collection name
    # Format: files_{provider}_{dimensions}_{apikey}_{timestamp}
    provider_aware_collection = 'files_ollama_3_test_key_12345'
    async def mock_get_collections_multiple(file_ids, api_key, collection_name):
        return [provider_aware_collection]

    mock_retriever._get_collections_multiple = mock_get_collections_multiple
    mock_retriever._format_results = lambda x: x

    # Create a file for metadata lookup
    await mock_retriever.metadata_store.record_file_upload(
        file_id='file_1',
        api_key='test_key',
        filename='test.txt',
        mime_type='text/plain',
        file_size=100,
        storage_key='key',
        storage_type='vector'
    )
    await mock_retriever.metadata_store.update_processing_status(
        file_id='file_1',
        status='completed',
        collection_name=provider_aware_collection
    )

    results = await mock_retriever.get_relevant_context(
        query="test query",
        api_key="test_key"
    )

    assert len(results) > 0
    assert mock_retriever.embed_query.called


@pytest.mark.asyncio
async def test_index_file_chunks(mock_retriever):
    """Test indexing file chunks into vector store"""
    mock_retriever.initialized = True
    
    # Mock vector store
    mock_store = AsyncMock()
    mock_store.add_vectors = AsyncMock(return_value=True)
    mock_retriever._default_store = mock_store
    
    # Mock embeddings
    async def mock_embed(text):
        return [0.1, 0.2, 0.3]
    
    mock_retriever.embed_query = mock_embed
    
    # Create chunk objects
    from services.file_processing.chunking import Chunk
    
    chunks = [
        Chunk(
            chunk_id='chunk_1',
            file_id='file_1',
            text='Chunk 1 content',
            chunk_index=0,
            metadata={'key': 'value'}
        ),
        Chunk(
            chunk_id='chunk_2',
            file_id='file_1',
            text='Chunk 2 content',
            chunk_index=1,
            metadata={}
        )
    ]
    
    result = await mock_retriever.index_file_chunks(
        file_id='file_1',
        chunks=chunks,
        collection_name='test_collection'
    )
    
    assert result is True
    assert mock_store.add_vectors.called
    
    # Verify add_vectors was called with correct parameters
    call_args = mock_store.add_vectors.call_args
    assert call_args[1]['collection_name'] == 'test_collection'
    assert 'documents' in call_args[1]  # Should include documents parameter
    assert len(call_args[1]['documents']) == 2  # Should have 2 chunk texts
    
    # Note: Chunks are no longer recorded in metadata store here.
    # They are recorded earlier in FileProcessingService.process_file() before indexing.
    # This method only handles vector store indexing.


@pytest.mark.asyncio
async def test_index_file_chunks_no_store():
    """Test indexing when no vector store available"""
    mock_retriever = FileVectorRetriever(config={'files': {}})
    mock_retriever._default_store = None
    
    result = await mock_retriever.index_file_chunks(
        file_id='file_1',
        chunks=[],
        collection_name='test_collection'
    )
    
    assert result is False


@pytest.mark.asyncio
async def test_delete_file_chunks(mock_retriever):
    """Test deleting file chunks from both vector store and metadata store"""
    file_id = 'test_file_123'
    collection_name = 'test_collection'
    
    # Create file with chunks
    await mock_retriever.metadata_store.record_file_upload(
        file_id=file_id,
        api_key='test_key',
        filename='test.txt',
        mime_type='text/plain',
        file_size=100,
        storage_key='key',
        storage_type='vector'
    )
    
    # Update with collection name
    await mock_retriever.metadata_store.update_processing_status(
        file_id=file_id,
        status='completed',
        collection_name=collection_name
    )
    
    # Record chunks
    chunk_ids = []
    for i in range(3):
        chunk_id = f'chunk_{i}'
        chunk_ids.append(chunk_id)
        await mock_retriever.metadata_store.record_chunk(
            chunk_id=chunk_id,
            file_id=file_id,
            chunk_index=i,
            collection_name=collection_name
        )
    
    # Mock vector store
    mock_store = AsyncMock()
    mock_store.delete_vector = AsyncMock(return_value=True)
    mock_retriever._default_store = mock_store
    mock_retriever.initialized = True
    
    # Delete chunks
    result = await mock_retriever.delete_file_chunks(file_id)
    
    # Verify deletion was successful
    assert result is True
    
    # Verify chunks were deleted from vector store
    assert mock_store.delete_vector.call_count == 3
    # Verify each chunk was deleted with correct collection name
    for chunk_id in chunk_ids:
        calls = [call for call in mock_store.delete_vector.call_args_list 
                if call[1]['vector_id'] == chunk_id and 
                   call[1]['collection_name'] == collection_name]
        assert len(calls) == 1, f"Chunk {chunk_id} was not deleted from vector store"
    
    # Verify chunks were deleted from metadata store
    chunks = await mock_retriever.metadata_store.get_file_chunks(file_id)
    assert len(chunks) == 0


@pytest.mark.asyncio
async def test_delete_file_chunks_no_vector_store(mock_retriever):
    """Test deleting file chunks when vector store is not available"""
    file_id = 'test_file_no_store'
    
    # Create file with chunks
    await mock_retriever.metadata_store.record_file_upload(
        file_id=file_id,
        api_key='test_key',
        filename='test.txt',
        mime_type='text/plain',
        file_size=100,
        storage_key='key',
        storage_type='vector'
    )
    
    # Record chunks
    for i in range(2):
        await mock_retriever.metadata_store.record_chunk(
            chunk_id=f'chunk_{i}',
            file_id=file_id,
            chunk_index=i,
            collection_name='test_collection'
        )
    
    # No vector store available
    mock_retriever._default_store = None
    
    # Delete chunks - should still work for metadata store
    result = await mock_retriever.delete_file_chunks(file_id)
    
    # Should succeed (metadata deletion)
    assert result is True
    
    # Chunks should be gone from metadata store
    chunks = await mock_retriever.metadata_store.get_file_chunks(file_id)
    assert len(chunks) == 0


@pytest.mark.asyncio
async def test_delete_file_chunks_no_collection_name(mock_retriever):
    """Test deleting file chunks when file has no collection_name"""
    file_id = 'test_file_no_collection'
    
    # Create file without collection name
    await mock_retriever.metadata_store.record_file_upload(
        file_id=file_id,
        api_key='test_key',
        filename='test.txt',
        mime_type='text/plain',
        file_size=100,
        storage_key='key',
        storage_type='vector'
    )
    
    # Record chunks
    for i in range(2):
        await mock_retriever.metadata_store.record_chunk(
            chunk_id=f'chunk_{i}',
            file_id=file_id,
            chunk_index=i
        )
    
    # Delete chunks - should skip vector store deletion but still delete from metadata
    result = await mock_retriever.delete_file_chunks(file_id)
    
    assert result is True
    
    # Chunks should be gone from metadata store
    chunks = await mock_retriever.metadata_store.get_file_chunks(file_id)
    assert len(chunks) == 0


@pytest.mark.asyncio
async def test_get_collections_multiple_file_ids(mock_retriever):
    """Test getting collections when multiple file_ids are provided"""
    # Create multiple files with different collections
    file_ids = ['file_1', 'file_2', 'file_3']
    collections = ['files_test_3_collection_1', 'files_test_3_collection_2', 'files_test_3_collection_3']
    
    for file_id, collection_name in zip(file_ids, collections):
        await mock_retriever.metadata_store.record_file_upload(
            file_id=file_id,
            api_key='test_key',
            filename=f'test_{file_id}.txt',
            mime_type='text/plain',
            file_size=100,
            storage_key=f'key_{file_id}',
            storage_type='vector'
        )
        await mock_retriever.metadata_store.update_processing_status(
            file_id=file_id,
            status='completed',
            collection_name=collection_name
        )
    
    # Mock embedding to avoid dimension/provider checks
    mock_retriever.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
    mock_retriever.config = {'embedding': {'provider': 'test'}}
    
    result_collections = await mock_retriever._get_collections_multiple(
        file_ids=file_ids,
        api_key=None,
        collection_name=None
    )
    
    assert len(result_collections) == 3
    assert all(col in result_collections for col in collections)


@pytest.mark.asyncio
async def test_get_collections_file_without_collection_name(mock_retriever):
    """Test getting collections when file has no collection_name in metadata"""
    file_id = 'file_no_collection'
    
    # Create file without collection_name
    await mock_retriever.metadata_store.record_file_upload(
        file_id=file_id,
        api_key='test_key',
        filename='test.txt',
        mime_type='text/plain',
        file_size=100,
        storage_key='key',
        storage_type='vector'
    )
    # Don't update with collection_name
    
    mock_retriever.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
    mock_retriever.config = {'embedding': {'provider': 'test'}}
    
    collections = await mock_retriever._get_collections_multiple(
        file_ids=[file_id],
        api_key=None,
        collection_name=None
    )
    
    # Should return empty since file has no collection_name
    assert collections == []


@pytest.mark.asyncio
async def test_get_collections_provider_signature_mismatch(mock_retriever):
    """Test that collections with mismatched provider signatures are filtered out"""
    file_id = 'file_wrong_provider'
    
    # Create file with collection that doesn't match provider signature
    await mock_retriever.metadata_store.record_file_upload(
        file_id=file_id,
        api_key='test_key',
        filename='test.txt',
        mime_type='text/plain',
        file_size=100,
        storage_key='key',
        storage_type='vector'
    )
    # Collection name has different provider signature (wrong_provider_5 vs test_3)
    await mock_retriever.metadata_store.update_processing_status(
        file_id=file_id,
        status='completed',
        collection_name='files_wrong_provider_5_collection'
    )
    
    mock_retriever.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
    mock_retriever.config = {'embedding': {'provider': 'test'}}
    
    collections = await mock_retriever._get_collections_multiple(
        file_ids=[file_id],
        api_key=None,
        collection_name=None
    )
    
    # Should be filtered out due to provider signature mismatch
    assert len(collections) == 0


@pytest.mark.asyncio
async def test_get_collections_provider_signature_exception(mock_retriever):
    """Test that provider signature exception is handled gracefully"""
    file_id = 'file_with_collection'
    
    await mock_retriever.metadata_store.record_file_upload(
        file_id=file_id,
        api_key='test_key',
        filename='test.txt',
        mime_type='text/plain',
        file_size=100,
        storage_key='key',
        storage_type='vector'
    )
    await mock_retriever.metadata_store.update_processing_status(
        file_id=file_id,
        status='completed',
        collection_name='files_test_3_collection'
    )
    
    # Mock embed_query to raise exception
    mock_retriever.embed_query = AsyncMock(side_effect=Exception("Embedding failed"))
    mock_retriever.config = {'embedding': {}}
    mock_retriever.embeddings = None  # No embeddings object
    
    # Should fall back to backward compatibility mode (include all collections)
    collections = await mock_retriever._get_collections_multiple(
        file_ids=[file_id],
        api_key=None,
        collection_name=None
    )
    
    # Should still return collection (backward compatibility)
    assert len(collections) == 1
    assert 'files_test_3_collection' in collections


@pytest.mark.asyncio
async def test_search_collection_multiple_file_ids_post_filtering():
    """Test searching collection with multiple file_ids post-filtering"""
    retriever = FileVectorRetriever(config={})
    
    # Mock vector store
    mock_store = AsyncMock()
    # Return results from multiple files
    mock_store.search_vectors = AsyncMock(return_value=[
        {
            'id': 'chunk_1',
            'text': 'Content from file_1',
            'score': 0.9,
            'metadata': {'file_id': 'file_1', 'chunk_index': 0}
        },
        {
            'id': 'chunk_2',
            'text': 'Content from file_2',
            'score': 0.8,
            'metadata': {'file_id': 'file_2', 'chunk_index': 0}
        },
        {
            'id': 'chunk_3',
            'text': 'Content from file_3',
            'score': 0.7,
            'metadata': {'file_id': 'file_3', 'chunk_index': 0}
        }
    ])
    
    retriever._default_store = mock_store
    retriever.metadata_store = AsyncMock()
    retriever.metadata_store.get_chunk_info = AsyncMock(return_value={
        'chunk_id': 'chunk_1',
        'file_id': 'file_1'
    })
    
    # Search with multiple file_ids (should post-filter)
    results = await retriever._search_collection(
        collection_name='test_collection',
        query_embedding=[0.1, 0.2, 0.3],
        file_ids=['file_1', 'file_2']  # Only want results from these files
    )
    
    # Should filter out file_3 results
    assert len(results) == 2
    file_ids_in_results = [r.get('metadata', {}).get('file_id') for r in results]
    assert 'file_1' in file_ids_in_results
    assert 'file_2' in file_ids_in_results
    assert 'file_3' not in file_ids_in_results


@pytest.mark.asyncio
async def test_search_collection_exception_handling():
    """Test that exceptions during search are handled gracefully"""
    retriever = FileVectorRetriever(config={})
    
    # Mock vector store that raises exception
    mock_store = AsyncMock()
    mock_store.search_vectors = AsyncMock(side_effect=Exception("Search failed"))
    retriever._default_store = mock_store
    
    results = await retriever._search_collection(
        collection_name='test_collection',
        query_embedding=[0.1, 0.2, 0.3],
        file_ids=None
    )
    
    # Should return empty list on error
    assert results == []


@pytest.mark.asyncio
async def test_search_collection_no_chunk_id():
    """Test searching collection when results have no chunk id"""
    retriever = FileVectorRetriever(config={})
    
    mock_store = AsyncMock()
    mock_store.search_vectors = AsyncMock(return_value=[
        {
            'id': None,  # No chunk ID
            'text': 'Content',
            'score': 0.8,
            'metadata': {'file_id': 'file_1'}
        },
        {
            'id': 'chunk_1',  # Has chunk ID
            'text': 'Content 2',
            'score': 0.9,
            'metadata': {'file_id': 'file_1'}
        }
    ])
    
    retriever._default_store = mock_store
    retriever.metadata_store = AsyncMock()
    retriever.metadata_store.get_chunk_info = AsyncMock(return_value={
        'chunk_id': 'chunk_1'
    })
    
    results = await retriever._search_collection(
        collection_name='test_collection',
        query_embedding=[0.1, 0.2, 0.3],
        file_ids=None
    )
    
    # Should only include results with chunk_id
    assert len(results) == 1
    assert results[0]['id'] == 'chunk_1'


@pytest.mark.asyncio
async def test_search_collection_with_limit():
    """Test searching collection with custom limit"""
    retriever = FileVectorRetriever(config={})
    
    mock_store = AsyncMock()
    mock_store.search_vectors = AsyncMock(return_value=[])
    retriever._default_store = mock_store
    
    await retriever._search_collection(
        collection_name='test_collection',
        query_embedding=[0.1, 0.2, 0.3],
        file_ids=None,
        limit=5
    )
    
    # Verify limit was passed to search_vectors
    call_args = mock_store.search_vectors.call_args
    assert call_args[1]['limit'] == 5


@pytest.mark.asyncio
async def test_format_results_missing_fields():
    """Test formatting results with missing optional fields"""
    retriever = FileVectorRetriever(config={'files': {}})
    
    results = [
        {
            'id': 'chunk_1',
            # No 'text' or 'content' field
            'score': 0.9,
            'metadata': {'file_id': 'file_123', 'chunk_index': 0}
        },
        {
            'id': 'chunk_2',
            'text': 'Has text',
            # No 'score' field
            'metadata': {'file_id': 'file_123', 'chunk_index': 1}
        },
        {
            'id': 'chunk_3',
            'content': 'Has content',
            'score': 0.8,
            'metadata': {'file_id': 'file_123', 'chunk_index': 2},
            'chunk_metadata': {'chunk_id': 'chunk_3', 'file_id': 'file_123'}
        }
    ]
    
    formatted = retriever._format_results(results)
    
    assert len(formatted) == 3
    # First result should have empty content
    assert formatted[0]['content'] == ''
    # Second result should have text as content and default score
    assert formatted[1]['content'] == 'Has text'
    assert formatted[1]['metadata']['confidence'] == 0.0  # Default when score missing
    # Third result should have content and chunk_metadata
    assert formatted[2]['content'] == 'Has content'
    assert 'file_metadata' in formatted[2]
    assert formatted[2]['file_metadata']['chunk_id'] == 'chunk_3'


@pytest.mark.asyncio
async def test_get_relevant_context_multiple_collections(mock_retriever):
    """Test get_relevant_context with multiple collections"""
    mock_retriever.initialized = True
    mock_retriever.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
    
    # Mock multiple collections
    collections = ['collection_1', 'collection_2']
    mock_retriever._get_collections_multiple = AsyncMock(return_value=collections)
    
    # Mock store with different results per collection
    mock_store = AsyncMock()
    call_count = [0]
    def mock_search_side_effect(*args, **kwargs):
        call_count[0] += 1
        collection = kwargs.get('collection_name')
        if collection == 'collection_1':
            return [{'id': 'chunk_1', 'text': 'Content 1', 'score': 0.9, 'metadata': {'file_id': 'file_1'}}]
        else:
            return [{'id': 'chunk_2', 'text': 'Content 2', 'score': 0.8, 'metadata': {'file_id': 'file_2'}}]
    
    mock_store.search_vectors = AsyncMock(side_effect=mock_search_side_effect)
    mock_retriever._default_store = mock_store
    mock_retriever.metadata_store.get_chunk_info = AsyncMock(return_value={'chunk_id': 'chunk_1'})
    mock_retriever._format_results = lambda x: x
    mock_retriever.apply_domain_filtering = lambda x, y: x  # No domain filtering
    
    results = await mock_retriever.get_relevant_context(
        query="test query",
        api_key="test_key"
    )
    
    # Should search both collections
    assert mock_store.search_vectors.call_count == 2
    assert len(results) == 2


@pytest.mark.asyncio
async def test_get_relevant_context_multiple_file_ids(mock_retriever):
    """Test get_relevant_context with multiple file_ids"""
    mock_retriever.initialized = True
    mock_retriever.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
    mock_retriever.config = {'embedding': {'provider': 'test'}}

    # Create files with collections
    file_ids = ['file_1', 'file_2']
    for file_id in file_ids:
        await mock_retriever.metadata_store.record_file_upload(
            file_id=file_id,
            api_key='test_key',
            filename=f'test_{file_id}.txt',
            mime_type='text/plain',
            file_size=100,
            storage_key=f'key_{file_id}',
            storage_type='vector'
        )
        await mock_retriever.metadata_store.update_processing_status(
            file_id=file_id,
            status='completed',
            collection_name=f'files_test_3_collection_{file_id}'
        )
    
    mock_store = AsyncMock()
    mock_store.search_vectors = AsyncMock(return_value=[
        {'id': 'chunk_1', 'text': 'Content', 'score': 0.9, 'metadata': {'file_id': 'file_1'}},
        {'id': 'chunk_2', 'text': 'Content 2', 'score': 0.8, 'metadata': {'file_id': 'file_2'}}
    ])
    mock_retriever._default_store = mock_store
    mock_retriever.metadata_store.get_chunk_info = AsyncMock(return_value={'chunk_id': 'chunk_1'})
    mock_retriever._format_results = lambda x: x
    mock_retriever.apply_domain_filtering = lambda x, y: x
    
    results = await mock_retriever.get_relevant_context(
        query="test query",
        api_key="test_key",
        file_ids=file_ids
    )
    
    assert len(results) > 0


@pytest.mark.asyncio
async def test_index_file_chunks_exception_during_embedding(mock_retriever):
    """Test indexing when embedding generation fails"""
    mock_retriever.initialized = True
    
    mock_store = AsyncMock()
    mock_retriever._default_store = mock_store
    
    # Mock embedding to raise exception
    mock_retriever.embed_query = AsyncMock(side_effect=Exception("Embedding failed"))
    
    from services.file_processing.chunking import Chunk
    chunks = [
        Chunk(chunk_id='chunk_1', file_id='file_1', text='Content', chunk_index=0)
    ]
    
    result = await mock_retriever.index_file_chunks(
        file_id='file_1',
        chunks=chunks,
        collection_name='test_collection'
    )
    
    assert result is False
    assert not mock_store.add_vectors.called


@pytest.mark.asyncio
async def test_index_file_chunks_exception_during_vector_store_add(mock_retriever):
    """Test indexing when vector store add fails"""
    mock_retriever.initialized = True
    
    mock_store = AsyncMock()
    mock_store.add_vectors = AsyncMock(side_effect=Exception("Vector store error"))
    mock_retriever._default_store = mock_store
    
    mock_retriever.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
    
    from services.file_processing.chunking import Chunk
    chunks = [
        Chunk(chunk_id='chunk_1', file_id='file_1', text='Content', chunk_index=0)
    ]
    
    result = await mock_retriever.index_file_chunks(
        file_id='file_1',
        chunks=chunks,
        collection_name='test_collection'
    )
    
    assert result is False


@pytest.mark.asyncio
async def test_delete_file_chunks_file_not_found(mock_retriever):
    """Test deleting chunks when file is not found"""
    mock_retriever.metadata_store.get_file_info = AsyncMock(return_value=None)
    
    result = await mock_retriever.delete_file_chunks('nonexistent_file')
    
    assert result is False


@pytest.mark.asyncio
async def test_delete_file_chunks_partial_vector_store_failure(mock_retriever):
    """Test deleting chunks when some vector store deletions fail"""
    file_id = 'test_file_partial_failure'
    collection_name = 'test_collection'
    
    await mock_retriever.metadata_store.record_file_upload(
        file_id=file_id,
        api_key='test_key',
        filename='test.txt',
        mime_type='text/plain',
        file_size=100,
        storage_key='key',
        storage_type='vector'
    )
    await mock_retriever.metadata_store.update_processing_status(
        file_id=file_id,
        status='completed',
        collection_name=collection_name
    )
    
    # Record chunks
    chunk_ids = ['chunk_1', 'chunk_2', 'chunk_3']
    for chunk_id in chunk_ids:
        await mock_retriever.metadata_store.record_chunk(
            chunk_id=chunk_id,
            file_id=file_id,
            chunk_index=int(chunk_id.split('_')[1]),
            collection_name=collection_name
        )
    
    # Mock vector store with partial failures
    mock_store = AsyncMock()
    delete_call_count = [0]
    def mock_delete_side_effect(*args, **kwargs):
        delete_call_count[0] += 1
        vector_id = kwargs.get('vector_id')
        if vector_id == 'chunk_2':
            return False  # Simulate failure
        return True
    
    mock_store.delete_vector = AsyncMock(side_effect=mock_delete_side_effect)
    mock_retriever._default_store = mock_store
    mock_retriever.initialized = True
    
    result = await mock_retriever.delete_file_chunks(file_id)
    
    # Should still succeed (metadata deletion succeeds)
    assert result is True
    assert delete_call_count[0] == 3  # All chunks attempted
    # Verify chunks deleted from metadata store
    chunks = await mock_retriever.metadata_store.get_file_chunks(file_id)
    assert len(chunks) == 0


@pytest.mark.asyncio
async def test_delete_file_chunks_no_chunks(mock_retriever):
    """Test deleting chunks when file has no chunks"""
    file_id = 'test_file_no_chunks'
    
    await mock_retriever.metadata_store.record_file_upload(
        file_id=file_id,
        api_key='test_key',
        filename='test.txt',
        mime_type='text/plain',
        file_size=100,
        storage_key='key',
        storage_type='vector'
    )
    await mock_retriever.metadata_store.update_processing_status(
        file_id=file_id,
        status='completed',
        collection_name='test_collection'
    )
    # Don't record any chunks
    
    result = await mock_retriever.delete_file_chunks(file_id)
    
    # Should succeed even though no chunks exist
    assert result is True


@pytest.mark.asyncio
@patch('vector_stores.base.store_manager.StoreManager')
@patch('services.api_key_service.ApiKeyService')
async def test_initialize_exception_handling(mock_api_key_service_class, mock_store_manager_class):
    """Test initialization when vector store creation fails"""
    config = {'vector_store': 'nonexistent_store'}

    retriever = FileVectorRetriever(config=config)

    # Mock API key service to avoid MongoDB initialization
    mock_api_key_service = AsyncMock()
    mock_api_key_service.initialize = AsyncMock()
    mock_api_key_service_class.return_value = mock_api_key_service

    # Mock store manager to raise exception
    mock_store_manager = Mock()
    mock_store_manager.get_store = AsyncMock(return_value=None)
    mock_store_manager.get_or_create_store = AsyncMock(side_effect=Exception("Store creation failed"))
    mock_store_manager_class.return_value = mock_store_manager
    retriever.store_manager = mock_store_manager

    # Mock embeddings
    retriever.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])

    await retriever.initialize()

    # Should still be initialized (but with no store)
    assert retriever.initialized is True
    assert retriever._default_store is None

