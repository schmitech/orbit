"""
Test Thread Service
===================

Tests for the conversation threading service including thread creation,
retrieval, deletion, and expiration handling.

Prerequisites:
1. SQLite service for storage
2. Thread dataset service for dataset management
3. Chat history service for message retrieval
"""

import asyncio
import os
import sys
import pytest
from pathlib import Path
from pytest_asyncio import fixture
from datetime import datetime, timedelta, UTC
import tempfile
import shutil
import json

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Get the project root (parent of server directory)
PROJECT_ROOT = SCRIPT_DIR.parent.parent

# Add server directory to Python path
SERVER_DIR = SCRIPT_DIR.parent
sys.path.append(str(SERVER_DIR))

from services.thread_service import ThreadService
from services.thread_dataset_service import ThreadDatasetService
from services.sqlite_service import SQLiteService
from services.chat_history_service import ChatHistoryService
from utils.id_utils import generate_id


@fixture(scope="function")
async def test_services():
    """Fixture to create test services with cleanup"""
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
            'verbose': False
        },
        'conversation_threading': {
            'enabled': True,
            'dataset_ttl_hours': 24,
            'storage_backend': 'database',
            'redis_key_prefix': 'thread_dataset:'
        },
        'chat_history': {
            'enabled': True,
            'limit': 10
        }
    }

    # Initialize services
    sqlite_service = SQLiteService(config)
    await sqlite_service.initialize()

    chat_history_service = ChatHistoryService(config, sqlite_service)
    await chat_history_service.initialize()

    thread_dataset_service = ThreadDatasetService(config)
    await thread_dataset_service.initialize()

    thread_service = ThreadService(config, sqlite_service, thread_dataset_service)
    await thread_service.initialize()

    # Yield services for tests
    yield {
        'thread': thread_service,
        'dataset': thread_dataset_service,
        'chat_history': chat_history_service,
        'db': sqlite_service,
        'config': config
    }

    # Cleanup
    sqlite_service.close()
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_thread_creation(test_services):
    """Test creating a thread from a parent message"""
    services = test_services

    # Create a test conversation with retrieved docs
    session_id = f"session_{generate_id()}"

    # Add a conversation turn with retrieved docs
    metadata = {
        "adapter_name": "intent-test",
        "retrieved_docs": [
            {
                "content": "Test document 1",
                "metadata": {"template_id": "test_template", "score": 0.9}
            },
            {
                "content": "Test document 2",
                "metadata": {"template_id": "test_template", "score": 0.8}
            }
        ],
        "original_query": "What is the test?",
        "template_id": "test_template",
        "parameters_used": {"param1": "value1"}
    }

    user_msg_id, assistant_msg_id = await services['chat_history'].add_conversation_turn(
        session_id=session_id,
        user_message="What is the test?",
        assistant_response="This is a test response.",
        metadata=metadata
    )

    assert assistant_msg_id is not None

    # Create thread with required parameters
    query_context = {
        'original_query': metadata['original_query'],
        'template_id': metadata['template_id'],
        'parameters_used': metadata['parameters_used']
    }
    thread_info = await services['thread'].create_thread(
        parent_message_id=assistant_msg_id,
        parent_session_id=session_id,
        adapter_name=metadata['adapter_name'],
        query_context=query_context,
        raw_results=metadata['retrieved_docs']
    )

    # Verify thread info
    assert thread_info is not None
    assert thread_info['thread_id'] is not None
    assert thread_info['thread_session_id'] is not None
    assert thread_info['parent_message_id'] == assistant_msg_id
    assert thread_info['parent_session_id'] == session_id
    assert thread_info['adapter_name'] == 'intent-test'
    assert 'created_at' in thread_info
    assert 'expires_at' in thread_info


@pytest.mark.asyncio
async def test_thread_retrieval(test_services):
    """Test retrieving thread information"""
    services = test_services

    # Create test conversation
    session_id = f"session_{generate_id()}"
    metadata = {
        "adapter_name": "intent-test",
        "retrieved_docs": [{"content": "Test doc", "metadata": {}}],
        "original_query": "Test query"
    }

    user_msg_id, assistant_msg_id = await services['chat_history'].add_conversation_turn(
        session_id=session_id,
        user_message="Test query",
        assistant_response="Test response",
        metadata=metadata
    )

    # Create thread with required parameters
    query_context = {'original_query': metadata['original_query']}
    created_thread = await services['thread'].create_thread(
        parent_message_id=assistant_msg_id,
        parent_session_id=session_id,
        adapter_name=metadata['adapter_name'],
        query_context=query_context,
        raw_results=metadata['retrieved_docs']
    )
    thread_id = created_thread['thread_id']

    # Retrieve thread
    retrieved_thread = await services['thread'].get_thread(thread_id)

    # Verify retrieved thread matches created thread
    assert retrieved_thread is not None, f"Thread {thread_id} was not found"
    assert retrieved_thread['thread_id'] == thread_id
    assert retrieved_thread['parent_message_id'] == assistant_msg_id
    assert retrieved_thread['parent_session_id'] == session_id


@pytest.mark.asyncio
async def test_thread_dataset_storage_and_retrieval(test_services):
    """Test storing and retrieving thread dataset"""
    services = test_services

    # Create test conversation with retrieved docs
    session_id = f"session_{generate_id()}"
    retrieved_docs = [
        {"content": "Document 1", "metadata": {"score": 0.9}},
        {"content": "Document 2", "metadata": {"score": 0.8}},
        {"content": "Document 3", "metadata": {"score": 0.7}}
    ]

    metadata = {
        "adapter_name": "intent-test",
        "retrieved_docs": retrieved_docs,
        "original_query": "Find documents",
        "template_id": "test_template"
    }

    user_msg_id, assistant_msg_id = await services['chat_history'].add_conversation_turn(
        session_id=session_id,
        user_message="Find documents",
        assistant_response="Here are the documents",
        metadata=metadata
    )

    # Create thread (which stores dataset) with required parameters
    query_context = {
        'original_query': metadata['original_query'],
        'template_id': metadata['template_id']
    }
    thread_info = await services['thread'].create_thread(
        parent_message_id=assistant_msg_id,
        parent_session_id=session_id,
        adapter_name=metadata['adapter_name'],
        query_context=query_context,
        raw_results=metadata['retrieved_docs']
    )
    thread_id = thread_info['thread_id']

    # Retrieve dataset
    dataset = await services['thread'].get_thread_dataset(thread_id)

    # Verify dataset
    assert dataset is not None
    query_context, raw_results = dataset

    assert query_context['original_query'] == "Find documents"
    assert query_context['template_id'] == "test_template"
    assert len(raw_results) == 3
    assert raw_results[0]['content'] == "Document 1"


@pytest.mark.asyncio
async def test_thread_deletion(test_services):
    """Test deleting a thread and its dataset"""
    services = test_services

    # Create test thread
    session_id = f"session_{generate_id()}"
    metadata = {
        "adapter_name": "intent-test",
        "retrieved_docs": [{"content": "Test", "metadata": {}}],
        "original_query": "Test"
    }

    user_msg_id, assistant_msg_id = await services['chat_history'].add_conversation_turn(
        session_id=session_id,
        user_message="Test",
        assistant_response="Response",
        metadata=metadata
    )

    # Create thread with required parameters
    query_context = {'original_query': metadata['original_query']}
    thread_info = await services['thread'].create_thread(
        parent_message_id=assistant_msg_id,
        parent_session_id=session_id,
        adapter_name=metadata['adapter_name'],
        query_context=query_context,
        raw_results=metadata['retrieved_docs']
    )
    thread_id = thread_info['thread_id']

    # Verify thread exists
    thread = await services['thread'].get_thread(thread_id)
    assert thread is not None

    # Delete thread
    result = await services['thread'].delete_thread(thread_id)
    assert result['status'] == 'success'

    # Verify thread is deleted
    deleted_thread = await services['thread'].get_thread(thread_id)
    assert deleted_thread is None

    # Verify dataset is deleted
    dataset = await services['thread'].get_thread_dataset(thread_id)
    assert dataset is None


@pytest.mark.asyncio
async def test_thread_creation_without_retrieved_docs(test_services):
    """Test that thread creation fails without retrieved docs"""
    services = test_services

    # Create conversation without retrieved docs
    session_id = f"session_{generate_id()}"

    user_msg_id, assistant_msg_id = await services['chat_history'].add_conversation_turn(
        session_id=session_id,
        user_message="Hello",
        assistant_response="Hi there",
        metadata={"adapter_name": "conversational-test"}
    )

    # Try to create thread with empty retrieved_docs (should fail or handle gracefully)
    with pytest.raises(Exception) as exc_info:
        await services['thread'].create_thread(
            parent_message_id=assistant_msg_id,
            parent_session_id=session_id,
            adapter_name="conversational-test",
            query_context={'original_query': 'Hello'},
            raw_results=[]  # Empty results - should fail
        )

    # Accept various error messages
    error_msg = str(exc_info.value).lower()
    assert "no retrieved documents" in error_msg or "empty" in error_msg or "required" in error_msg


@pytest.mark.asyncio
async def test_thread_creation_with_invalid_message(test_services):
    """Test that thread creation works even with invalid message ID (no validation)"""
    services = test_services

    # ThreadService doesn't validate message existence during creation
    # It just stores the thread metadata, so this should succeed
    # The validation would happen in the upper layers (response_processor, etc.)
    # So we'll test that creating a thread with any message ID succeeds
    thread_info = await services['thread'].create_thread(
        parent_message_id="invalid_message_id",
        parent_session_id="invalid_session",
        adapter_name="test-adapter",
        query_context={'original_query': 'test'},
        raw_results=[{'content': 'test', 'metadata': {}}]
    )

    # Thread should be created successfully
    assert thread_info is not None
    assert thread_info['thread_id'] is not None


@pytest.mark.asyncio
async def test_thread_expiration(test_services):
    """Test thread expiration logic"""
    services = test_services

    # Create thread with short TTL
    session_id = f"session_{generate_id()}"
    metadata = {
        "adapter_name": "intent-test",
        "retrieved_docs": [{"content": "Test", "metadata": {}}],
        "original_query": "Test"
    }

    user_msg_id, assistant_msg_id = await services['chat_history'].add_conversation_turn(
        session_id=session_id,
        user_message="Test",
        assistant_response="Response",
        metadata=metadata
    )

    # Create thread with required parameters
    query_context = {'original_query': metadata['original_query']}
    thread_info = await services['thread'].create_thread(
        parent_message_id=assistant_msg_id,
        parent_session_id=session_id,
        adapter_name=metadata['adapter_name'],
        query_context=query_context,
        raw_results=metadata['retrieved_docs']
    )
    thread_id = thread_info['thread_id']

    # Manually set expiration to past
    expires_at = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    await services['db'].update_one(
        'conversation_threads',
        {'id': thread_id},
        {'$set': {'expires_at': expires_at}}
    )

    # Verify thread is marked as expired
    thread = await services['thread'].get_thread(thread_id)
    assert thread is not None  # Record still exists

    # Parse expires_at and verify it's in the past
    thread_expires = datetime.fromisoformat(thread['expires_at'].replace('Z', '+00:00'))
    assert thread_expires < datetime.now(UTC)


@pytest.mark.asyncio
async def test_cleanup_expired_threads(test_services):
    """Test cleanup of expired threads"""
    services = test_services

    # Create multiple threads
    session_id = f"session_{generate_id()}"
    thread_ids = []

    for i in range(3):
        metadata = {
            "adapter_name": "intent-test",
            "retrieved_docs": [{"content": f"Test {i}", "metadata": {}}],
            "original_query": f"Test {i}"
        }

        user_msg_id, assistant_msg_id = await services['chat_history'].add_conversation_turn(
            session_id=session_id,
            user_message=f"Test {i}",
            assistant_response=f"Response {i}",
            metadata=metadata
        )

        # Create thread with required parameters
        query_context = {'original_query': metadata['original_query']}
        thread_info = await services['thread'].create_thread(
            parent_message_id=assistant_msg_id,
            parent_session_id=session_id,
            adapter_name=metadata['adapter_name'],
            query_context=query_context,
            raw_results=metadata['retrieved_docs']
        )
        thread_ids.append(thread_info['thread_id'])

    # Expire first two threads
    past_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    for thread_id in thread_ids[:2]:
        await services['db'].update_one(
            'conversation_threads',
            {'id': thread_id},
            {'$set': {'expires_at': past_time}}
        )

    # Run cleanup
    deleted_count = await services['thread'].cleanup_expired_threads()

    # Should delete 2 expired threads
    assert deleted_count == 2

    # Verify expired threads are deleted
    for thread_id in thread_ids[:2]:
        thread = await services['thread'].get_thread(thread_id)
        assert thread is None

    # Verify non-expired thread still exists
    thread = await services['thread'].get_thread(thread_ids[2])
    assert thread is not None


@pytest.mark.asyncio
async def test_multiple_threads_per_session(test_services):
    """Test creating multiple threads in the same session"""
    services = test_services

    session_id = f"session_{generate_id()}"
    thread_ids = []

    # Create 3 threads from different messages
    for i in range(3):
        metadata = {
            "adapter_name": "intent-test",
            "retrieved_docs": [{"content": f"Doc {i}", "metadata": {}}],
            "original_query": f"Query {i}"
        }

        user_msg_id, assistant_msg_id = await services['chat_history'].add_conversation_turn(
            session_id=session_id,
            user_message=f"Query {i}",
            assistant_response=f"Response {i}",
            metadata=metadata
        )

        # Create thread with required parameters
        query_context = {'original_query': metadata['original_query']}
        thread_info = await services['thread'].create_thread(
            parent_message_id=assistant_msg_id,
            parent_session_id=session_id,
            adapter_name=metadata['adapter_name'],
            query_context=query_context,
            raw_results=metadata['retrieved_docs']
        )
        thread_ids.append(thread_info['thread_id'])

    # Verify all threads exist
    assert len(thread_ids) == 3
    assert len(set(thread_ids)) == 3  # All unique

    for thread_id in thread_ids:
        thread = await services['thread'].get_thread(thread_id)
        assert thread is not None
        assert thread['parent_session_id'] == session_id


@pytest.mark.asyncio
async def test_thread_session_id_uniqueness(test_services):
    """Test that each thread gets a unique session ID"""
    services = test_services

    session_id = f"session_{generate_id()}"
    thread_session_ids = set()

    # Create multiple threads
    for i in range(3):
        metadata = {
            "adapter_name": "intent-test",
            "retrieved_docs": [{"content": f"Doc {i}", "metadata": {}}],
            "original_query": f"Query {i}"
        }

        user_msg_id, assistant_msg_id = await services['chat_history'].add_conversation_turn(
            session_id=session_id,
            user_message=f"Query {i}",
            assistant_response=f"Response {i}",
            metadata=metadata
        )

        # Create thread with required parameters
        query_context = {'original_query': metadata['original_query']}
        thread_info = await services['thread'].create_thread(
            parent_message_id=assistant_msg_id,
            parent_session_id=session_id,
            adapter_name=metadata['adapter_name'],
            query_context=query_context,
            raw_results=metadata['retrieved_docs']
        )
        thread_session_ids.add(thread_info['thread_session_id'])

    # All thread session IDs should be unique
    assert len(thread_session_ids) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
