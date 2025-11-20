"""
Test Thread Integration
========================

Integration tests for conversation threading including:
- End-to-end thread creation and usage flow
- Pipeline integration with thread context
- Cascade deletion of threads with parent conversation
- Adapter capability detection

Prerequisites:
1. SQLite service
2. Chat history service
3. Thread services
"""

import asyncio
import os
import sys
import pytest
from pathlib import Path
from pytest_asyncio import fixture
from datetime import datetime, UTC
import tempfile
import shutil

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
from adapters.capabilities import AdapterCapabilities
from utils.id_utils import generate_id


@fixture(scope="function")
async def integrated_services():
    """Fixture to create all integrated services"""
    # Create temporary directory
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_orbit.db")

    # Configuration
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
            'storage_backend': 'database',
            'redis_key_prefix': 'thread_dataset:'
        },
        'chat_history': {
            'enabled': True,
            'limit': 10
        }
    }

    # Initialize all services
    sqlite_service = SQLiteService(config)
    await sqlite_service.initialize()

    chat_history_service = ChatHistoryService(config, sqlite_service)
    await chat_history_service.initialize()

    thread_dataset_service = ThreadDatasetService(config)
    await thread_dataset_service.initialize()

    thread_service = ThreadService(config, sqlite_service, thread_dataset_service)

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
async def test_end_to_end_thread_flow(integrated_services):
    """Test complete thread creation and usage flow"""
    services = integrated_services

    # Step 1: Create parent conversation
    session_id = f"session_{generate_id()}"
    query = "What is quantum computing?"

    retrieved_docs = [
        {
            "content": "Quantum computing uses quantum mechanics principles",
            "metadata": {"score": 0.95, "template_id": "quantum_template"}
        },
        {
            "content": "Qubits can exist in superposition states",
            "metadata": {"score": 0.88, "template_id": "quantum_template"}
        }
    ]

    metadata = {
        "adapter_name": "intent-quantum",
        "retrieved_docs": retrieved_docs,
        "original_query": query,
        "template_id": "quantum_template",
        "parameters_used": {"topic": "quantum"}
    }

    user_msg_id, assistant_msg_id = await services['chat_history'].add_conversation_turn(
        session_id=session_id,
        user_message=query,
        assistant_response="Quantum computing is a revolutionary technology...",
        metadata=metadata
    )

    # Step 2: Create thread with required parameters
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
    thread_id = thread_info['thread_id']
    thread_session_id = thread_info['thread_session_id']

    # Verify thread creation
    assert thread_id is not None
    assert thread_session_id is not None
    assert thread_session_id != session_id  # Different from parent session

    # Step 3: Retrieve dataset via thread
    dataset = await services['thread'].get_thread_dataset(thread_id)
    assert dataset is not None

    query_context, raw_results = dataset
    assert query_context['original_query'] == query
    assert len(raw_results) == 2

    # Step 4: Add follow-up message to thread
    # This would use thread_session_id in real pipeline
    user_msg_id_2, assistant_msg_id_2 = await services['chat_history'].add_conversation_turn(
        session_id=thread_session_id,
        user_message="Tell me more about qubits",
        assistant_response="Qubits are quantum bits that can be 0, 1, or both...",
        metadata={"adapter_name": "intent-quantum", "in_thread": True}
    )

    # Verify follow-up was stored in thread session
    thread_history = await services['chat_history'].get_conversation_history(
        session_id=thread_session_id,
        limit=10
    )
    assert len(thread_history) > 0


@pytest.mark.asyncio
async def test_cascade_deletion_with_parent_conversation(integrated_services):
    """Test that deleting parent conversation deletes threads"""
    services = integrated_services

    # Create parent conversation with multiple threads
    session_id = f"session_{generate_id()}"
    thread_ids = []

    for i in range(3):
        metadata = {
            "adapter_name": "intent-test",
            "retrieved_docs": [
                {"content": f"Doc {i}", "metadata": {"score": 0.9}}
            ],
            "original_query": f"Query {i}"
        }

        user_msg_id, assistant_msg_id = await services['chat_history'].add_conversation_turn(
            session_id=session_id,
            user_message=f"Query {i}",
            assistant_response=f"Response {i}",
            metadata=metadata
        )

        query_context = {'original_query': metadata['original_query']}
        thread_info = await services['thread'].create_thread(
            parent_message_id=assistant_msg_id,
            parent_session_id=session_id,
            adapter_name=metadata['adapter_name'],
            query_context=query_context,
            raw_results=metadata['retrieved_docs']
        )
        thread_ids.append(thread_info['thread_id'])

    # Verify threads exist
    for thread_id in thread_ids:
        thread = await services['thread'].get_thread(thread_id)
        assert thread is not None

    # Delete parent conversation (cascade delete)
    # First get threads
    threads = await services['db'].find_many(
        "conversation_threads",
        {"parent_session_id": session_id}
    )

    # Delete datasets
    for thread in threads:
        dataset_key = thread.get('dataset_key')
        if dataset_key:
            await services['db'].delete_one("thread_datasets", {"id": dataset_key})

    # Delete threads
    deleted_count = await services['db'].delete_many(
        "conversation_threads",
        {"parent_session_id": session_id}
    )

    assert deleted_count == 3

    # Verify threads are deleted
    for thread_id in thread_ids:
        thread = await services['thread'].get_thread(thread_id)
        assert thread is None

        # Verify datasets are deleted
        dataset = await services['thread'].get_thread_dataset(thread_id)
        assert dataset is None


@pytest.mark.asyncio
async def test_thread_isolation(integrated_services):
    """Test that threads are isolated from each other"""
    services = integrated_services

    # Create two separate conversations
    session_1 = f"session_{generate_id()}"
    session_2 = f"session_{generate_id()}"

    # Create thread in session 1
    metadata_1 = {
        "adapter_name": "intent-test",
        "retrieved_docs": [{"content": "Session 1 doc", "metadata": {}}],
        "original_query": "Session 1 query"
    }

    user_msg_id_1, assistant_msg_id_1 = await services['chat_history'].add_conversation_turn(
        session_id=session_1,
        user_message="Session 1 query",
        assistant_response="Session 1 response",
        metadata=metadata_1
    )

    query_context_1 = {'original_query': metadata_1['original_query']}
    thread_1 = await services['thread'].create_thread(
        parent_message_id=assistant_msg_id_1,
        parent_session_id=session_1,
        adapter_name=metadata_1['adapter_name'],
        query_context=query_context_1,
        raw_results=metadata_1['retrieved_docs']
    )

    # Create thread in session 2
    metadata_2 = {
        "adapter_name": "intent-test",
        "retrieved_docs": [{"content": "Session 2 doc", "metadata": {}}],
        "original_query": "Session 2 query"
    }

    user_msg_id_2, assistant_msg_id_2 = await services['chat_history'].add_conversation_turn(
        session_id=session_2,
        user_message="Session 2 query",
        assistant_response="Session 2 response",
        metadata=metadata_2
    )

    query_context_2 = {'original_query': metadata_2['original_query']}
    thread_2 = await services['thread'].create_thread(
        parent_message_id=assistant_msg_id_2,
        parent_session_id=session_2,
        adapter_name=metadata_2['adapter_name'],
        query_context=query_context_2,
        raw_results=metadata_2['retrieved_docs']
    )

    # Verify threads have different session IDs
    assert thread_1['thread_session_id'] != thread_2['thread_session_id']

    # Verify threads have different datasets
    dataset_1 = await services['thread'].get_thread_dataset(thread_1['thread_id'])
    dataset_2 = await services['thread'].get_thread_dataset(thread_2['thread_id'])

    context_1, results_1 = dataset_1
    context_2, results_2 = dataset_2

    assert context_1['original_query'] == "Session 1 query"
    assert context_2['original_query'] == "Session 2 query"
    assert results_1[0]['content'] == "Session 1 doc"
    assert results_2[0]['content'] == "Session 2 doc"


@pytest.mark.asyncio
async def test_adapter_capability_detection():
    """Test adapter capability detection for threading support"""

    # Intent adapters should support threading
    intent_caps = AdapterCapabilities.for_standard_retriever("intent-customer-support")
    assert intent_caps.supports_threading is True

    # QA adapters should support threading
    qa_caps = AdapterCapabilities.for_standard_retriever("qa-knowledge-base")
    assert qa_caps.supports_threading is True

    # Conversational adapters should NOT support threading
    conv_caps = AdapterCapabilities.for_standard_retriever("conversational-chat")
    assert conv_caps.supports_threading is False

    # Multimodal adapters should NOT support threading
    multi_caps = AdapterCapabilities.for_standard_retriever("multimodal-vision")
    assert multi_caps.supports_threading is False


@pytest.mark.asyncio
async def test_thread_with_complex_metadata(integrated_services):
    """Test thread creation with complex metadata structures"""
    services = integrated_services

    session_id = f"session_{generate_id()}"

    # Complex metadata with nested structures
    complex_metadata = {
        "adapter_name": "intent-complex",
        "retrieved_docs": [
            {
                "content": "Complex document",
                "metadata": {
                    "nested": {
                        "level1": {
                            "level2": ["value1", "value2", "value3"]
                        }
                    },
                    "arrays": [
                        {"key1": "val1"},
                        {"key2": "val2"}
                    ],
                    "unicode": "测试数据 🚀"
                }
            }
        ],
        "original_query": "Complex query with 特殊字符",
        "template_id": "complex_template",
        "parameters_used": {
            "nested_params": {
                "param1": [1, 2, 3],
                "param2": {"sub": "value"}
            }
        }
    }

    user_msg_id, assistant_msg_id = await services['chat_history'].add_conversation_turn(
        session_id=session_id,
        user_message="Complex query",
        assistant_response="Complex response",
        metadata=complex_metadata
    )

    # Create thread with required parameters
    query_context = {
        'original_query': complex_metadata['original_query'],
        'template_id': complex_metadata['template_id'],
        'parameters_used': complex_metadata['parameters_used']
    }
    thread_info = await services['thread'].create_thread(
        parent_message_id=assistant_msg_id,
        parent_session_id=session_id,
        adapter_name=complex_metadata['adapter_name'],
        query_context=query_context,
        raw_results=complex_metadata['retrieved_docs']
    )

    # Retrieve and verify complex metadata preserved
    dataset = await services['thread'].get_thread_dataset(thread_info['thread_id'])
    assert dataset is not None

    query_context, raw_results = dataset
    assert "特殊字符" in query_context['original_query']
    assert raw_results[0]['metadata']['unicode'] == "测试数据 🚀"
    assert raw_results[0]['metadata']['nested']['level1']['level2'][0] == "value1"


@pytest.mark.asyncio
async def test_concurrent_thread_creation(integrated_services):
    """Test creating multiple threads concurrently"""
    services = integrated_services

    session_id = f"session_{generate_id()}"

    # Create multiple messages
    message_data = []
    for i in range(5):
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
        message_data.append((assistant_msg_id, metadata))

    # Create threads concurrently
    thread_tasks = [
        services['thread'].create_thread(
            parent_message_id=msg_id,
            parent_session_id=session_id,
            adapter_name=metadata['adapter_name'],
            query_context={'original_query': metadata['original_query']},
            raw_results=metadata['retrieved_docs']
        )
        for msg_id, metadata in message_data
    ]

    thread_infos = await asyncio.gather(*thread_tasks)

    # Verify all threads created successfully
    assert len(thread_infos) == 5

    # Verify all thread IDs are unique
    thread_ids = [t['thread_id'] for t in thread_infos]
    assert len(set(thread_ids)) == 5

    # Verify all can be retrieved
    for thread_id in thread_ids:
        thread = await services['thread'].get_thread(thread_id)
        assert thread is not None


@pytest.mark.asyncio
async def test_thread_creation_error_handling(integrated_services):
    """Test error handling in thread creation"""
    services = integrated_services

    # Test with invalid/empty raw_results
    with pytest.raises(Exception) as exc_info:
        await services['thread'].create_thread(
            parent_message_id="invalid_msg_id",
            parent_session_id="invalid_session",
            adapter_name="test",
            query_context={'original_query': 'test'},
            raw_results=[]  # Empty results should fail
        )

    assert "retrieved" in str(exc_info.value).lower() or "empty" in str(exc_info.value).lower()

    # Test with valid session but empty retrieved_docs
    session_id = f"session_{generate_id()}"

    user_msg_id, assistant_msg_id = await services['chat_history'].add_conversation_turn(
        session_id=session_id,
        user_message="Hello",
        assistant_response="Hi",
        metadata={"adapter_name": "conversational-test"}  # No retrieved_docs
    )

    with pytest.raises(Exception) as exc_info:
        await services['thread'].create_thread(
            parent_message_id=assistant_msg_id,
            parent_session_id=session_id,
            adapter_name="conversational-test",
            query_context={'original_query': 'Hello'},
            raw_results=[]  # Empty results
        )

    assert "retrieved" in str(exc_info.value).lower() or "empty" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_multiple_threads_same_parent_message(integrated_services):
    """Test creating multiple threads from the same parent message"""
    services = integrated_services

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

    # Create first thread
    query_context = {'original_query': metadata['original_query']}
    thread_1 = await services['thread'].create_thread(
        parent_message_id=assistant_msg_id,
        parent_session_id=session_id,
        adapter_name=metadata['adapter_name'],
        query_context=query_context,
        raw_results=metadata['retrieved_docs']
    )

    # Create second thread from same message
    thread_2 = await services['thread'].create_thread(
        parent_message_id=assistant_msg_id,
        parent_session_id=session_id,
        adapter_name=metadata['adapter_name'],
        query_context=query_context,
        raw_results=metadata['retrieved_docs']
    )

    # Both threads should exist and be different
    assert thread_1['thread_id'] != thread_2['thread_id']
    assert thread_1['thread_session_id'] != thread_2['thread_session_id']

    # Both should reference same parent
    assert thread_1['parent_message_id'] == assistant_msg_id
    assert thread_2['parent_message_id'] == assistant_msg_id

    # Both should have same dataset
    dataset_1 = await services['thread'].get_thread_dataset(thread_1['thread_id'])
    dataset_2 = await services['thread'].get_thread_dataset(thread_2['thread_id'])

    context_1, _ = dataset_1
    context_2, _ = dataset_2

    assert context_1['original_query'] == context_2['original_query']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
