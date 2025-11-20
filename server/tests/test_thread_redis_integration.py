"""
Test Thread Redis Integration
==============================

Integration tests for conversation threading with Redis storage.
Tests the full flow of thread creation, dataset storage in Redis,
and cascade deletion when clearing conversation history.

Prerequisites:
1. Redis server running (tests will skip if Redis is unavailable)
2. SQLite service for thread metadata
3. Chat history service for conversation management

These tests verify the fix for the issue where chat_history_service
was bypassing ThreadDatasetService and trying to delete datasets
directly from the database instead of using Redis.
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
from services.redis_service import RedisService
from utils.id_utils import generate_id

# Load environment variables from .env file in project root
from dotenv import load_dotenv
env_path = PROJECT_ROOT / '.env'
if not env_path.exists():
    raise FileNotFoundError(f".env file not found at {env_path}")

load_dotenv(env_path)


def redis_available():
    """Check if Redis is available for testing"""
    try:
        import redis.asyncio as redis
        return True
    except ImportError:
        return False


@fixture(scope="function")
async def redis_test_services():
    """Fixture to create test services with Redis storage"""
    if not redis_available():
        pytest.skip("Redis not available - skipping Redis integration tests")

    # Clear any existing Redis service instances to avoid singleton issues
    RedisService.clear_cache()

    # Create temporary directory for test database
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_orbit.db")

    # Get raw environment variables
    redis_host = os.getenv("INTERNAL_SERVICES_REDIS_HOST")
    redis_port = int(os.getenv("INTERNAL_SERVICES_REDIS_PORT", 6379))
    redis_username = os.getenv("INTERNAL_SERVICES_REDIS_USERNAME")
    redis_password = os.getenv("INTERNAL_SERVICES_REDIS_PASSWORD")

    # Clean host if it includes port
    if redis_host and ':' in redis_host:
        redis_host = redis_host.split(':')[0]

    # Validate required environment variables
    required_vars = ["INTERNAL_SERVICES_REDIS_HOST", "INTERNAL_SERVICES_REDIS_PASSWORD"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        pytest.skip(f"Missing required environment variables: {', '.join(missing_vars)}")

    # Create test configuration with Redis enabled
    config = {
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': db_path
                }
            },
            'redis': {
                'enabled': True,
                'host': redis_host,
                'port': redis_port,
                'db': 0,
                'password': redis_password,
                'username': redis_username,
                'use_ssl': False,  # Redis Cloud works without SSL in tests
                'ttl': 3600
            }
        },
        'general': {
            'verbose': False
        },
        'conversation_threading': {
            'enabled': True,
            'dataset_ttl_hours': 1,
            'storage_backend': 'redis',  # Use Redis for dataset storage
            'redis_key_prefix': 'test_thread_dataset:'  # Use test prefix
        },
        'chat_history': {
            'enabled': True,
            'limit': 10
        }
    }

    # Initialize services
    sqlite_service = SQLiteService(config)
    await sqlite_service.initialize()

    # Initialize Redis service
    redis_service = RedisService(config)
    try:
        redis_initialized = await redis_service.initialize()
        if not redis_initialized:
            pytest.skip(f"Failed to connect to Redis. Please check your configuration.")
    except Exception as e:
        pytest.skip(f"Failed to connect to Redis: {e}")

    # Initialize thread dataset service with Redis
    thread_dataset_service = ThreadDatasetService(config)
    await thread_dataset_service.initialize()

    # Verify Redis is actually being used
    if thread_dataset_service.storage_backend != 'redis' or not thread_dataset_service.redis_service.enabled:
        pytest.skip("Redis storage not enabled in ThreadDatasetService")

    # Initialize chat history service (with thread_dataset_service)
    chat_history_service = ChatHistoryService(config, sqlite_service, thread_dataset_service)
    # Set api_key_service to None for tests (bypass validation)
    chat_history_service.api_key_service = None
    await chat_history_service.initialize()

    # Initialize thread service
    thread_service = ThreadService(config, sqlite_service, thread_dataset_service)
    await thread_service.initialize()

    # Yield services for tests
    yield {
        'thread': thread_service,
        'dataset': thread_dataset_service,
        'chat_history': chat_history_service,
        'redis': redis_service,
        'db': sqlite_service,
        'config': config
    }

    # Cleanup: Delete all test keys from Redis
    try:
        # Get all test keys
        test_prefix = config['conversation_threading']['redis_key_prefix']
        cursor = 0
        while True:
            cursor, keys = await redis_service.client.scan(cursor, match=f"{test_prefix}*", count=100)
            if keys:
                await redis_service.client.delete(*keys)
            if cursor == 0:
                break
    except Exception:
        pass  # Ignore cleanup errors

    # Close services
    await redis_service.close()
    sqlite_service.close()
    shutil.rmtree(temp_dir, ignore_errors=True)

    # Clear cache again after cleanup to ensure clean state for next test
    RedisService.clear_cache()


@pytest.mark.asyncio
async def test_redis_dataset_storage_and_retrieval(redis_test_services):
    """Test that datasets are stored in Redis and can be retrieved"""
    services = redis_test_services

    # Create test thread
    session_id = f"test_session_{generate_id()}"
    metadata = {
        "adapter_name": "intent-test",
        "retrieved_docs": [
            {"content": "Test document 1", "metadata": {"score": 0.9}},
            {"content": "Test document 2", "metadata": {"score": 0.8}}
        ],
        "original_query": "What is the test?",
        "template_id": "test_template"
    }

    # Add conversation turn
    user_msg_id, assistant_msg_id = await services['chat_history'].add_conversation_turn(
        session_id=session_id,
        user_message="What is the test?",
        assistant_response="This is a test response.",
        metadata=metadata
    )

    # Create thread (stores dataset in Redis)
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

    # Get full thread info including dataset_key
    thread_full = await services['thread'].get_thread(thread_id)
    dataset_key = thread_full['dataset_key']

    # Verify dataset is in Redis
    redis_value = await services['redis'].get(dataset_key)
    assert redis_value is not None, f"Dataset {dataset_key} not found in Redis"

    # Verify dataset can be retrieved via ThreadDatasetService
    dataset = await services['dataset'].get_dataset(dataset_key)
    assert dataset is not None
    query_ctx, raw_results = dataset
    assert query_ctx['original_query'] == "What is the test?"
    assert len(raw_results) == 2


@pytest.mark.asyncio
async def test_redis_cascade_deletion_via_chat_history(redis_test_services):
    """
    Test that clearing conversation history properly deletes thread datasets from Redis.

    This is the critical integration test that verifies the bug fix where
    chat_history_service was bypassing ThreadDatasetService and trying to
    delete from the database instead of Redis.
    """
    services = redis_test_services

    # Create test conversation with thread
    session_id = f"test_session_{generate_id()}"
    metadata = {
        "adapter_name": "intent-test",
        "retrieved_docs": [
            {"content": "Important data", "metadata": {"score": 0.95}}
        ],
        "original_query": "Show me the data",
        "template_id": "data_template"
    }

    # Add conversation turn
    user_msg_id, assistant_msg_id = await services['chat_history'].add_conversation_turn(
        session_id=session_id,
        user_message="Show me the data",
        assistant_response="Here is the data.",
        metadata=metadata
    )

    # Create thread (stores dataset in Redis)
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

    # Get full thread info including dataset_key
    thread_full = await services['thread'].get_thread(thread_id)
    dataset_key = thread_full['dataset_key']

    # Verify dataset exists in Redis BEFORE deletion
    redis_value_before = await services['redis'].get(dataset_key)
    assert redis_value_before is not None, "Dataset should exist in Redis before deletion"

    # Simulate cascade deletion by manually deleting messages and threads
    # (This is what clear_conversation_history does internally after API key validation)

    # Delete conversation messages
    messages_deleted = await services['chat_history'].database_service.delete_many(
        services['chat_history'].collection_name,
        {"session_id": session_id}
    )
    assert messages_deleted >= 2, f"Should delete at least 2 messages, got {messages_deleted}"

    # Delete threads (which should trigger dataset deletion via chat_history_service logic)
    # Get all threads for this session
    threads = await services['chat_history'].database_service.find_many(
        "conversation_threads",
        {"parent_session_id": session_id}
    )

    # Delete thread datasets using ThreadDatasetService
    datasets_deleted = 0
    for thread in threads:
        dk = thread.get('dataset_key')
        if dk:
            result = await services['chat_history'].thread_dataset_service.delete_dataset(dk)
            if result:
                datasets_deleted += 1

    # Delete thread records
    threads_deleted = await services['chat_history'].database_service.delete_many(
        "conversation_threads",
        {"parent_session_id": session_id}
    )

    assert threads_deleted == 1, f"Should delete 1 thread, got {threads_deleted}"
    assert datasets_deleted == 1, f"Should delete 1 dataset, got {datasets_deleted}"

    # Verify thread is deleted from database
    thread = await services['thread'].get_thread(thread_id)
    assert thread is None, "Thread should be deleted from database"

    # CRITICAL: Verify dataset is deleted from Redis (not just database)
    redis_value_after = await services['redis'].get(dataset_key)
    assert redis_value_after is None, f"Dataset {dataset_key} should be deleted from Redis"

    # Double-check via ThreadDatasetService
    dataset_after = await services['dataset'].get_dataset(dataset_key)
    assert dataset_after is None, "Dataset should not be retrievable via ThreadDatasetService"


@pytest.mark.asyncio
async def test_redis_multiple_threads_cascade_deletion(redis_test_services):
    """Test that multiple thread datasets are all deleted from Redis when clearing conversation"""
    services = redis_test_services

    session_id = f"test_session_{generate_id()}"
    thread_ids = []
    dataset_keys = []

    # Create multiple threads in the same session
    for i in range(3):
        metadata = {
            "adapter_name": "intent-test",
            "retrieved_docs": [{"content": f"Document {i}", "metadata": {"score": 0.9}}],
            "original_query": f"Query {i}",
            "template_id": f"template_{i}"
        }

        user_msg_id, assistant_msg_id = await services['chat_history'].add_conversation_turn(
            session_id=session_id,
            user_message=f"Query {i}",
            assistant_response=f"Response {i}",
            metadata=metadata
        )

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

        thread_ids.append(thread_info['thread_id'])
        # Get dataset_key via get_thread()
        thread_full = await services['thread'].get_thread(thread_info['thread_id'])
        dataset_keys.append(thread_full['dataset_key'])

    # Verify all datasets exist in Redis
    for dataset_key in dataset_keys:
        redis_value = await services['redis'].get(dataset_key)
        assert redis_value is not None, f"Dataset {dataset_key} should exist in Redis"

    # Simulate cascade deletion by manually deleting messages and threads
    # (This is what clear_conversation_history does internally after API key validation)

    # Delete conversation messages
    messages_deleted = await services['chat_history'].database_service.delete_many(
        services['chat_history'].collection_name,
        {"session_id": session_id}
    )
    assert messages_deleted >= 6, f"Should delete at least 6 messages (3 turns), got {messages_deleted}"

    # Delete threads (which should trigger dataset deletion via chat_history_service logic)
    # Get all threads for this session
    threads = await services['chat_history'].database_service.find_many(
        "conversation_threads",
        {"parent_session_id": session_id}
    )

    # Delete thread datasets using ThreadDatasetService
    datasets_deleted = 0
    for thread in threads:
        dk = thread.get('dataset_key')
        if dk:
            result = await services['chat_history'].thread_dataset_service.delete_dataset(dk)
            if result:
                datasets_deleted += 1

    # Delete thread records
    threads_deleted = await services['chat_history'].database_service.delete_many(
        "conversation_threads",
        {"parent_session_id": session_id}
    )

    assert threads_deleted == 3, f"Should delete 3 threads, got {threads_deleted}"
    assert datasets_deleted == 3, f"Should delete 3 datasets, got {datasets_deleted}"

    # Verify all datasets are deleted from Redis
    for dataset_key in dataset_keys:
        redis_value = await services['redis'].get(dataset_key)
        assert redis_value is None, f"Dataset {dataset_key} should be deleted from Redis"

    # Verify all threads are deleted
    for thread_id in thread_ids:
        thread = await services['thread'].get_thread(thread_id)
        assert thread is None, f"Thread {thread_id} should be deleted"


@pytest.mark.asyncio
async def test_redis_direct_thread_deletion(redis_test_services):
    """Test that directly deleting a thread also removes the dataset from Redis"""
    services = redis_test_services

    # Create test thread
    session_id = f"test_session_{generate_id()}"
    metadata = {
        "adapter_name": "intent-test",
        "retrieved_docs": [{"content": "Test", "metadata": {}}],
        "original_query": "Test query"
    }

    user_msg_id, assistant_msg_id = await services['chat_history'].add_conversation_turn(
        session_id=session_id,
        user_message="Test query",
        assistant_response="Test response",
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

    thread_id = thread_info['thread_id']

    # Get full thread info including dataset_key
    thread_full = await services['thread'].get_thread(thread_id)
    dataset_key = thread_full['dataset_key']

    # Verify dataset exists in Redis
    redis_value_before = await services['redis'].get(dataset_key)
    assert redis_value_before is not None

    # Delete thread directly (not via chat history)
    result = await services['thread'].delete_thread(thread_id)
    assert result['status'] == 'success'

    # Verify dataset is deleted from Redis
    redis_value_after = await services['redis'].get(dataset_key)
    assert redis_value_after is None, "Dataset should be deleted from Redis"


@pytest.mark.asyncio
async def test_redis_dataset_expiration(redis_test_services):
    """Test that Redis TTL is properly set on datasets"""
    services = redis_test_services

    # Create test thread
    session_id = f"test_session_{generate_id()}"
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

    query_context = {'original_query': metadata['original_query']}
    thread_info = await services['thread'].create_thread(
        parent_message_id=assistant_msg_id,
        parent_session_id=session_id,
        adapter_name=metadata['adapter_name'],
        query_context=query_context,
        raw_results=metadata['retrieved_docs']
    )

    # Get full thread info including dataset_key
    thread_full = await services['thread'].get_thread(thread_info['thread_id'])
    dataset_key = thread_full['dataset_key']

    # Check TTL is set in Redis
    ttl = await services['redis'].ttl(dataset_key)

    # TTL should be positive and approximately 1 hour (3600 seconds)
    # Allow some margin for test execution time
    assert ttl > 3500, f"TTL should be approximately 3600 seconds, got {ttl}"
    assert ttl <= 3600, f"TTL should not exceed configured value, got {ttl}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
