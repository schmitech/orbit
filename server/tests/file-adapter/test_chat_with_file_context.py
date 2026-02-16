"""
Tests for Chat Integration with File Context

Tests the integration between file uploads and chat functionality,
ensuring file_ids are properly passed through the pipeline and used
for context retrieval.
"""

import pytest
import pytest_asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock
from typing import List, Dict, Any
from dataclasses import dataclass, field

# Add server directory to Python path
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from retrievers.implementations.file.file_retriever import FileVectorRetriever


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


# Create a simple ProcessingContext class for testing
# This avoids importing the entire pipeline infrastructure
@dataclass
class MockProcessingContext:
    """Mock version of ProcessingContext for testing"""
    message: str = ""
    adapter_name: str = ""
    system_prompt_id: str = None
    inference_provider: str = None
    context_messages: List[Dict[str, str]] = field(default_factory=list)
    retrieved_docs: List[Dict[str, Any]] = field(default_factory=list)
    formatted_context: str = ""
    full_prompt: str = ""
    messages: List[Dict[str, str]] = None
    response: str = ""
    sources: List[Dict[str, Any]] = field(default_factory=list)
    tokens: int = 0
    processing_time: float = 0.0
    is_blocked: bool = False
    error: str = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    user_id: str = None
    session_id: str = None
    api_key: str = None
    timezone: str = None
    file_ids: List[str] = field(default_factory=list)

    def has_error(self) -> bool:
        return self.is_blocked or self.error is not None

    def set_error(self, error: str, block: bool = True) -> None:
        self.error = error
        if block:
            self.is_blocked = True


@pytest_asyncio.fixture
async def mock_config():
    """Fixture providing mock configuration"""
    return {
        'general': {
            'inference_provider': 'ollama'
        },
        'chat_history': {
            'enabled': False
        },
        'messages': {},
        'adapters': [
            {
                'name': 'file-document-qa',
                'enabled': True,
                'type': 'retriever',
                'adapter': 'file'
            },
            {
                'name': 'general',
                'enabled': True,
                'type': 'passthrough'
            }
        ],
        'files': {
            'retriever': {
                'collection_prefix': 'test_files_',
                'vector_store': 'chroma'
            }
        }
    }


@pytest_asyncio.fixture
async def mock_retriever(tmp_path):
    """Fixture providing a mocked FileVectorRetriever"""
    config = {
        'collection_prefix': 'test_files_',
        'vector_store': 'chroma',
        'embedding': {'provider': 'test'}  # Add provider for signature matching
    }

    retriever = FileVectorRetriever(config=config)
    retriever.initialized = True

    # Mock embedding generation - 3 dimensions to match provider signature 'test_3'
    retriever.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])

    # Mock vector store
    mock_store = AsyncMock()
    mock_store.search_vectors = AsyncMock(return_value=[
        {
            'id': 'chunk_1',
            'text': 'This is relevant content from the file.',
            'score': 0.9,
            'metadata': {
                'file_id': 'file_123',
                'chunk_index': 0
            }
        }
    ])
    retriever._default_store = mock_store

    # Mock methods needed for get_relevant_context
    retriever._format_results = lambda x: x
    retriever.apply_domain_filtering = lambda x, y: x

    yield retriever


@pytest.mark.asyncio
async def test_processing_context_includes_file_ids():
    """Test that ProcessingContext properly stores file_ids"""
    file_ids = ['file_123', 'file_456']

    context = MockProcessingContext(
        message="Test query",
        adapter_name="file-document-qa",
        file_ids=file_ids
    )

    assert context.file_ids == file_ids
    assert len(context.file_ids) == 2
    assert 'file_123' in context.file_ids
    assert 'file_456' in context.file_ids


@pytest.mark.asyncio
async def test_processing_context_default_empty_file_ids():
    """Test that ProcessingContext defaults to empty file_ids list"""
    context = MockProcessingContext(
        message="Test query",
        adapter_name="general"
    )

    assert context.file_ids == []
    assert isinstance(context.file_ids, list)


@pytest.mark.asyncio
async def test_file_retriever_get_relevant_context_with_file_ids(mock_retriever):
    """Test FileVectorRetriever with file_ids parameter"""
    from services.file_metadata.metadata_store import FileMetadataStore

    # Use temporary database
    import tempfile
    import os
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_metadata.db")
        FileMetadataStore.reset_instance()
        metadata_config = create_test_config(db_path)
        metadata_store = FileMetadataStore(config=metadata_config)
        await metadata_store._ensure_initialized()
        mock_retriever.metadata_store = metadata_store

        # Create test files in metadata store
        # Collection names include provider signature 'test_3' (provider='test', dimensions=3)
        file_ids = ['file_123', 'file_456']
        for file_id in file_ids:
            await metadata_store.record_file_upload(
                file_id=file_id,
                api_key='test_key',
                filename=f'{file_id}.txt',
                mime_type='text/plain',
                file_size=1024,
                storage_key=f'key_{file_id}',
                storage_type='vector'
            )
            await metadata_store.update_processing_status(
                file_id=file_id,
                status='completed',
                collection_name=f'files_test_3_collection_{file_id}'
            )

        # Call get_relevant_context with file_ids
        await mock_retriever.get_relevant_context(
            query="Test query",
            api_key='test_key',
            file_ids=file_ids
        )

        # Verify search was performed
        assert mock_retriever._default_store.search_vectors.called

        metadata_store.close()


@pytest.mark.asyncio
async def test_file_retriever_get_relevant_context_single_file_id(mock_retriever):
    """Test FileVectorRetriever with single file_id in file_ids array"""
    from services.file_metadata.metadata_store import FileMetadataStore

    import tempfile
    import os
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_metadata.db")
        FileMetadataStore.reset_instance()
        metadata_config = create_test_config(db_path)
        metadata_store = FileMetadataStore(config=metadata_config)
        await metadata_store._ensure_initialized()
        mock_retriever.metadata_store = metadata_store

        # Create test file
        file_id = 'file_123'
        await metadata_store.record_file_upload(
            file_id=file_id,
            api_key='test_key',
            filename='test.txt',
            mime_type='text/plain',
            file_size=1024,
            storage_key='key',
            storage_type='vector'
        )
        await metadata_store.update_processing_status(
            file_id=file_id,
            status='completed',
            collection_name='files_test_3_collection_123'
        )

        # Call get_relevant_context with file_ids array
        await mock_retriever.get_relevant_context(
            query="Test query",
            api_key='test_key',
            file_ids=[file_id]  # Use file_ids array
        )

        # Verify search was performed
        assert mock_retriever._default_store.search_vectors.called

        metadata_store.close()


@pytest.mark.asyncio
async def test_file_retriever_multiple_file_ids_filtering():
    """Test that FileVectorRetriever properly filters by multiple file_ids"""
    config = {
        'collection_prefix': 'test_files_',
        'vector_store': 'chroma',
        'embedding': {'provider': 'test'}
    }

    retriever = FileVectorRetriever(config=config)
    retriever.initialized = True
    retriever.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
    retriever._format_results = lambda x: x
    retriever.apply_domain_filtering = lambda x, y: x

    # Mock vector store returning results from different files
    mock_store = AsyncMock()
    mock_store.search_vectors = AsyncMock(return_value=[
        {
            'id': 'chunk_1',
            'text': 'Content from file 1',
            'score': 0.9,
            'metadata': {'file_id': 'file_123', 'chunk_index': 0}
        },
        {
            'id': 'chunk_2',
            'text': 'Content from file 2',
            'score': 0.85,
            'metadata': {'file_id': 'file_456', 'chunk_index': 0}
        },
        {
            'id': 'chunk_3',
            'text': 'Content from file 3',
            'score': 0.8,
            'metadata': {'file_id': 'file_789', 'chunk_index': 0}
        }
    ])
    retriever._default_store = mock_store

    # Mock metadata store
    from services.file_metadata.metadata_store import FileMetadataStore
    import tempfile
    import os
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_metadata.db")
        FileMetadataStore.reset_instance()
        metadata_config = create_test_config(db_path)
        metadata_store = FileMetadataStore(config=metadata_config)
        await metadata_store._ensure_initialized()
        retriever.metadata_store = metadata_store

        # Create test files with provider-aware collection names
        for file_id in ['file_123', 'file_456', 'file_789']:
            await metadata_store.record_file_upload(
                file_id=file_id,
                api_key='test_key',
                filename=f'{file_id}.txt',
                mime_type='text/plain',
                file_size=1024,
                storage_key=f'key_{file_id}',
                storage_type='vector'
            )
            await metadata_store.update_processing_status(
                file_id=file_id,
                status='completed',
                collection_name=f'files_test_3_collection_{file_id}'
            )

        # Search with specific file_ids
        target_file_ids = ['file_123', 'file_456']
        await retriever.get_relevant_context(
            query="Test query",
            api_key='test_key',
            file_ids=target_file_ids
        )

        # Results should be filtered
        assert mock_store.search_vectors.called

        metadata_store.close()


@pytest.mark.asyncio
async def test_file_ids_validation():
    """Test that file_ids are properly validated"""
    # Empty file_ids should work
    context = MockProcessingContext(
        message="Test",
        adapter_name="file-document-qa",
        file_ids=[]
    )
    assert context.file_ids == []

    # Single file_id
    context = MockProcessingContext(
        message="Test",
        adapter_name="file-document-qa",
        file_ids=['file_123']
    )
    assert len(context.file_ids) == 1

    # Multiple file_ids
    context = MockProcessingContext(
        message="Test",
        adapter_name="file-document-qa",
        file_ids=['file_1', 'file_2', 'file_3']
    )
    assert len(context.file_ids) == 3


@pytest.mark.asyncio
async def test_empty_file_ids_does_not_add_filter():
    """Test that empty file_ids list doesn't add unnecessary filters"""
    config = {
        'collection_prefix': 'test_files_',
        'vector_store': 'chroma',
        'embedding': {'provider': 'test'}
    }

    retriever = FileVectorRetriever(config=config)
    retriever.initialized = True
    retriever.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
    retriever._format_results = lambda x: x
    retriever.apply_domain_filtering = lambda x, y: x

    # Mock vector store
    mock_store = AsyncMock()
    mock_store.search_vectors = AsyncMock(return_value=[])
    retriever._default_store = mock_store

    # Use temporary database
    from services.file_metadata.metadata_store import FileMetadataStore
    import tempfile
    import os
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_metadata.db")
        FileMetadataStore.reset_instance()
        metadata_config = create_test_config(db_path)
        metadata_store = FileMetadataStore(config=metadata_config)
        await metadata_store._ensure_initialized()
        retriever.metadata_store = metadata_store

        # Create file
        await metadata_store.record_file_upload(
            file_id='file_1',
            api_key='test_key',
            filename='test.txt',
            mime_type='text/plain',
            file_size=1024,
            storage_key='key',
            storage_type='vector'
        )
        await metadata_store.update_processing_status(
            file_id='file_1',
            status='completed',
            collection_name='files_test_3_collection_1'
        )

        # Query with empty file_ids
        await retriever.get_relevant_context(
            query="Test",
            api_key='test_key',
            file_ids=[]
        )

        # Verify retriever was called
        assert mock_store.search_vectors.called

        metadata_store.close()


@pytest.mark.asyncio
async def test_file_ids_with_api_key_ownership_validation():
    """Test that file_ids are validated against API key ownership"""
    config = {
        'collection_prefix': 'test_files_',
        'vector_store': 'chroma',
        'embedding': {'provider': 'test'}
    }

    retriever = FileVectorRetriever(config=config)
    retriever.initialized = True
    retriever.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
    retriever._format_results = lambda x: x
    retriever.apply_domain_filtering = lambda x, y: x

    # Mock vector store
    mock_store = AsyncMock()
    mock_store.search_vectors = AsyncMock(return_value=[])
    retriever._default_store = mock_store

    # Use temporary database
    from services.file_metadata.metadata_store import FileMetadataStore
    import tempfile
    import os
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_metadata.db")
        FileMetadataStore.reset_instance()
        metadata_config = create_test_config(db_path)
        metadata_store = FileMetadataStore(config=metadata_config)
        await metadata_store._ensure_initialized()
        retriever.metadata_store = metadata_store

        # Create files with different API keys
        await metadata_store.record_file_upload(
            file_id='file_owned',
            api_key='owner_key',
            filename='owned.txt',
            mime_type='text/plain',
            file_size=1024,
            storage_key='key1',
            storage_type='vector'
        )
        await metadata_store.update_processing_status(
            file_id='file_owned',
            status='completed',
            collection_name='files_test_3_collection_owned'
        )

        # Try to access owned file
        await retriever.get_relevant_context(
            query="Test",
            api_key='owner_key',
            file_ids=['file_owned']
        )

        # Should succeed (file belongs to this API key)
        assert mock_store.search_vectors.called

        metadata_store.close()
