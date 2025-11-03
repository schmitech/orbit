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
    
    collections = await retriever._get_collections(
        file_id=None,
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
    
    # Update with collection name
    await mock_retriever.metadata_store.update_processing_status(
        file_id=file_id,
        status='completed',
        collection_name='file_test_file_123'
    )
    
    collections = await mock_retriever._get_collections(
        file_id=file_id,
        api_key=None,
        collection_name=None
    )
    
    assert len(collections) == 1
    assert 'file_test_file_123' in collections


@pytest.mark.asyncio
async def test_get_collections_by_api_key(mock_retriever):
    """Test getting collections when api_key is provided"""
    api_key = 'test_api_key'
    
    # Create multiple files with collections
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
        await mock_retriever.metadata_store.update_processing_status(
            file_id=file_id,
            status='completed',
            collection_name=f'collection_{i}'
        )
    
    collections = await mock_retriever._get_collections(
        file_id=None,
        api_key=api_key,
        collection_name=None
    )
    
    assert len(collections) == 3
    assert all(f'collection_{i}' in collections for i in range(3))


@pytest.mark.asyncio
async def test_get_collections_empty():
    """Test getting collections when no filters provided"""
    retriever = FileVectorRetriever(config={})
    
    collections = await retriever._get_collections(
        file_id=None,
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
        file_id=None
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
        file_id=None
    )
    
    assert len(results) == 2
    assert mock_store.search_vectors.called
    # Verify filter metadata if file_id provided
    call_args = mock_store.search_vectors.call_args
    assert call_args[1]['collection_name'] == 'test_collection'


@pytest.mark.asyncio
async def test_search_collection_with_file_id_filter():
    """Test searching collection with file_id filter"""
    retriever = FileVectorRetriever(config={})
    
    # Mock vector store
    mock_store = AsyncMock()
    mock_store.search_vectors = AsyncMock(return_value=[])
    retriever._default_store = mock_store
    
    await retriever._search_collection(
        collection_name='test_collection',
        query_embedding=[0.1, 0.2, 0.3],
        file_id='specific_file_id'
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
    retriever._get_collections = AsyncMock(return_value=[])
    
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
    """Test deleting file chunks"""
    file_id = 'test_file_123'
    
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
    for i in range(3):
        await mock_retriever.metadata_store.record_chunk(
            chunk_id=f'chunk_{i}',
            file_id=file_id,
            chunk_index=i,
            collection_name='test_collection'
        )
    
    # Mock vector store deletion would be here if implemented
    result = await mock_retriever.delete_file_chunks(file_id)
    
    # Should delete from metadata store
    chunks = await mock_retriever.metadata_store.get_file_chunks(file_id)
    assert len(chunks) == 0  # Note: delete_file_chunks may not be fully implemented

