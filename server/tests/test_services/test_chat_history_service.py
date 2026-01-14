"""
Chat History Service Tests
==========================

Tests the chat history service behaviours that cascade through
conversation threads, ensuring that clearing history removes
thread sessions and stored datasets.
"""

import os
import sys
import json
import shutil
import tempfile
from datetime import datetime, timedelta, UTC
from pathlib import Path

import pytest
from pytest_asyncio import fixture

# Ensure server modules can be imported
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.sqlite_service import SQLiteService
from services.chat_history_service import ChatHistoryService
from services.thread_dataset_service import ThreadDatasetService
from utils.id_utils import generate_id
from utils.text_utils import mask_api_key


@fixture(scope="function")
async def chat_history_services():
  """Set up chat history + thread dataset services backed by SQLite."""
  temp_dir = tempfile.mkdtemp()
  db_path = os.path.join(temp_dir, "test_orbit.db")

  config = {
    'internal_services': {
      'backend': {
        'type': 'sqlite',
        'sqlite': {
          'database_path': db_path
        }
      }
    },
    'conversation_threading': {
      'enabled': True,
      'dataset_ttl_hours': 24,
      'storage_backend': 'database',
      'redis_key_prefix': 'thread_dataset:'
    },
    'chat_history': {
      'enabled': True,
      'default_limit': 50
    }
  }

  sqlite_service = SQLiteService(config)
  await sqlite_service.initialize()

  thread_dataset_service = ThreadDatasetService(config)
  await thread_dataset_service.initialize()

  chat_history_service = ChatHistoryService(
    config,
    database_service=sqlite_service,
    thread_dataset_service=thread_dataset_service
  )
  await chat_history_service.initialize()

  yield {
    'chat_history': chat_history_service,
    'dataset': thread_dataset_service,
    'db': sqlite_service,
    'config': config
  }

  await chat_history_service.close()
  await thread_dataset_service.close()
  sqlite_service.close()
  shutil.rmtree(temp_dir, ignore_errors=True)


async def _seed_conversation_with_thread(services):
  """Create a parent conversation plus a thread with its own session."""
  chat_history = services['chat_history']
  dataset_service = services['dataset']
  db = services['db']

  # Determine backend type from config
  backend_type = services['config']['internal_services']['backend']['type']

  session_id = f"session_{generate_id(backend_type)}"
  thread_session_id = f"thread_{generate_id(backend_type)}"
  metadata = {
    "adapter_name": "intent-test",
    "retrieved_docs": [
      {"content": "Doc 1", "metadata": {"score": 0.9}},
      {"content": "Doc 2", "metadata": {"score": 0.7}}
    ],
    "original_query": "What is Orbit?",
    "template_id": "test_template",
    "parameters_used": {"foo": "bar"}
  }

  _, assistant_msg_id = await chat_history.add_conversation_turn(
    session_id=session_id,
    user_message="Tell me about Orbit",
    assistant_response="Orbit is a platform.",
    metadata=metadata
  )

  thread_id = generate_id(backend_type)
  query_context = {
    "original_query": metadata["original_query"],
    "template_id": metadata["template_id"],
    "parameters_used": metadata["parameters_used"]
  }
  dataset_key = await dataset_service.store_dataset(
    thread_id=thread_id,
    query_context=query_context,
    raw_results=metadata["retrieved_docs"]
  )

  await db.insert_one('conversation_threads', {
    'id': thread_id,
    'parent_message_id': assistant_msg_id,
    'parent_session_id': session_id,
    'thread_session_id': thread_session_id,
    'adapter_name': metadata["adapter_name"],
    'query_context': json.dumps(query_context),
    'dataset_key': dataset_key,
    'created_at': datetime.now(UTC).isoformat(),
    'expires_at': (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
    'metadata_json': json.dumps({})
  })

  await chat_history.add_message(
    session_id=thread_session_id,
    role='user',
    content='Follow-up question?',
    metadata=metadata
  )
  await chat_history.add_message(
    session_id=thread_session_id,
    role='assistant',
    content='Threaded answer.',
    metadata=metadata
  )

  return {
    'session_id': session_id,
    'thread_session_id': thread_session_id,
    'dataset_key': dataset_key
  }


@pytest.mark.asyncio
async def test_clear_session_history_removes_thread_data(chat_history_services):
  services = chat_history_services
  seeded = await _seed_conversation_with_thread(services)

  # Baseline assertions
  assert await services['dataset'].get_dataset(seeded['dataset_key']) is not None
  assert await services['db'].find_many('chat_history', {'session_id': seeded['thread_session_id']})

  result = await services['chat_history'].clear_session_history(seeded['session_id'])
  assert result is True

  parent_messages = await services['db'].find_many('chat_history', {'session_id': seeded['session_id']})
  thread_messages = await services['db'].find_many('chat_history', {'session_id': seeded['thread_session_id']})
  thread_records = await services['db'].find_many('conversation_threads', {'parent_session_id': seeded['session_id']})

  assert parent_messages == []
  assert thread_messages == []
  assert thread_records == []
  assert await services['dataset'].get_dataset(seeded['dataset_key']) is None


class _DummyApiKeyService:
  async def validate_api_key(self, api_key, adapter_manager=None):
    if api_key != "valid-key":
      return False, None, None
    return True, "intent-test", None


@pytest.mark.asyncio
async def test_clear_conversation_history_reports_thread_counts(chat_history_services):
  services = chat_history_services
  seeded = await _seed_conversation_with_thread(services)

  services['chat_history'].api_key_service = _DummyApiKeyService()

  result = await services['chat_history'].clear_conversation_history(
    session_id=seeded['session_id'],
    api_key="valid-key"
  )

  assert result["success"] is True
  assert result["deleted_count"] == 2  # user + assistant
  assert result["deleted_threads"] == 1
  assert result["deleted_thread_messages"] == 2
  assert result["session_id"] == seeded['session_id']

  assert await services['db'].find_many('conversation_threads', {'parent_session_id': seeded['session_id']}) == []
  assert await services['db'].find_many('chat_history', {'session_id': seeded['thread_session_id']}) == []
  assert await services['dataset'].get_dataset(seeded['dataset_key']) is None


@pytest.mark.asyncio
async def test_clear_session_with_multiple_threads(chat_history_services):
  """Test that clearing a session with multiple threads deletes all of them."""
  services = chat_history_services
  chat_history = services['chat_history']
  dataset_service = services['dataset']
  db = services['db']
  backend_type = services['config']['internal_services']['backend']['type']

  # Create parent session
  session_id = f"session_{generate_id(backend_type)}"
  metadata = {"adapter_name": "intent-test", "original_query": "Test query"}

  _, assistant_msg_id = await chat_history.add_conversation_turn(
    session_id=session_id,
    user_message="Parent message",
    assistant_response="Parent response",
    metadata=metadata
  )

  # Create 3 threads for the same parent session
  thread_ids = []
  thread_session_ids = []
  dataset_keys = []

  for i in range(3):
    thread_id = generate_id(backend_type)
    thread_session_id = f"thread_{generate_id(backend_type)}"
    query_context = {"original_query": f"Query {i}"}

    dataset_key = await dataset_service.store_dataset(
      thread_id=thread_id,
      query_context=query_context,
      raw_results=[{"content": f"Doc {i}"}]
    )

    await db.insert_one('conversation_threads', {
      'id': thread_id,
      'parent_message_id': assistant_msg_id,
      'parent_session_id': session_id,
      'thread_session_id': thread_session_id,
      'adapter_name': "intent-test",
      'query_context': json.dumps(query_context),
      'dataset_key': dataset_key,
      'created_at': datetime.now(UTC).isoformat(),
      'expires_at': (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
      'metadata_json': json.dumps({})
    })

    await chat_history.add_message(
      session_id=thread_session_id,
      role='user',
      content=f'Thread {i} question',
      metadata=metadata
    )

    thread_ids.append(thread_id)
    thread_session_ids.append(thread_session_id)
    dataset_keys.append(dataset_key)

  # Verify all threads exist
  threads = await db.find_many('conversation_threads', {'parent_session_id': session_id})
  assert len(threads) == 3

  # Clear the parent session
  result = await chat_history.clear_session_history(session_id)
  assert result is True

  # Verify all threads and their data are deleted
  assert await db.find_many('conversation_threads', {'parent_session_id': session_id}) == []

  for thread_session_id in thread_session_ids:
    assert await db.find_many('chat_history', {'session_id': thread_session_id}) == []

  for dataset_key in dataset_keys:
    assert await dataset_service.get_dataset(dataset_key) is None


@pytest.mark.asyncio
async def test_clear_session_isolation(chat_history_services):
  """Test that clearing one session doesn't affect another session's data."""
  services = chat_history_services

  # Create two separate conversations with threads
  seeded1 = await _seed_conversation_with_thread(services)
  seeded2 = await _seed_conversation_with_thread(services)

  # Verify both exist
  assert await services['dataset'].get_dataset(seeded1['dataset_key']) is not None
  assert await services['dataset'].get_dataset(seeded2['dataset_key']) is not None

  threads1 = await services['db'].find_many('conversation_threads', {'parent_session_id': seeded1['session_id']})
  threads2 = await services['db'].find_many('conversation_threads', {'parent_session_id': seeded2['session_id']})
  assert len(threads1) == 1
  assert len(threads2) == 1

  # Clear only session 1
  result = await services['chat_history'].clear_session_history(seeded1['session_id'])
  assert result is True

  # Verify session 1 is deleted
  assert await services['db'].find_many('chat_history', {'session_id': seeded1['session_id']}) == []
  assert await services['db'].find_many('chat_history', {'session_id': seeded1['thread_session_id']}) == []
  assert await services['db'].find_many('conversation_threads', {'parent_session_id': seeded1['session_id']}) == []
  assert await services['dataset'].get_dataset(seeded1['dataset_key']) is None

  # Verify session 2 is UNTOUCHED
  assert len(await services['db'].find_many('chat_history', {'session_id': seeded2['session_id']})) == 2
  assert len(await services['db'].find_many('chat_history', {'session_id': seeded2['thread_session_id']})) == 2
  assert len(await services['db'].find_many('conversation_threads', {'parent_session_id': seeded2['session_id']})) == 1
  assert await services['dataset'].get_dataset(seeded2['dataset_key']) is not None


@pytest.mark.asyncio
async def test_clear_session_with_no_threads(chat_history_services):
  """Test that clearing a session with no threads works correctly."""
  services = chat_history_services
  chat_history = services['chat_history']
  backend_type = services['config']['internal_services']['backend']['type']

  # Create session without threads
  session_id = f"session_{generate_id(backend_type)}"

  await chat_history.add_conversation_turn(
    session_id=session_id,
    user_message="Simple message",
    assistant_response="Simple response"
  )

  # Verify messages exist
  messages = await services['db'].find_many('chat_history', {'session_id': session_id})
  assert len(messages) == 2

  # Clear the session
  result = await chat_history.clear_session_history(session_id)
  assert result is True

  # Verify messages are deleted
  assert await services['db'].find_many('chat_history', {'session_id': session_id}) == []
  assert await services['db'].find_many('conversation_threads', {'parent_session_id': session_id}) == []


@pytest.mark.asyncio
async def test_clear_nonexistent_session(chat_history_services):
  """Test that clearing a non-existent session doesn't cause errors."""
  services = chat_history_services
  backend_type = services['config']['internal_services']['backend']['type']

  # Try to clear a session that doesn't exist
  fake_session_id = f"session_{generate_id(backend_type)}"
  result = await services['chat_history'].clear_session_history(fake_session_id)

  # Should return False (no messages deleted) but not raise an error
  assert result is False


@pytest.mark.asyncio
async def test_clear_conversation_history_invalid_api_key(chat_history_services):
  """Test that clear_conversation_history rejects invalid API keys."""
  services = chat_history_services
  seeded = await _seed_conversation_with_thread(services)

  services['chat_history'].api_key_service = _DummyApiKeyService()

  # Try to clear with invalid API key
  result = await services['chat_history'].clear_conversation_history(
    session_id=seeded['session_id'],
    api_key="invalid-key"
  )

  assert result["success"] is False
  assert result["error"] == "Invalid API key"
  assert result["deleted_count"] == 0

  # Verify nothing was deleted
  assert len(await services['db'].find_many('chat_history', {'session_id': seeded['session_id']})) == 2
  assert len(await services['db'].find_many('conversation_threads', {'parent_session_id': seeded['session_id']})) == 1


@pytest.mark.asyncio
async def test_thread_without_messages(chat_history_services):
  """Test that clearing works even when a thread has no messages."""
  services = chat_history_services
  chat_history = services['chat_history']
  dataset_service = services['dataset']
  db = services['db']
  backend_type = services['config']['internal_services']['backend']['type']

  # Create parent session
  session_id = f"session_{generate_id(backend_type)}"
  metadata = {"adapter_name": "intent-test"}

  _, assistant_msg_id = await chat_history.add_conversation_turn(
    session_id=session_id,
    user_message="Parent message",
    assistant_response="Parent response",
    metadata=metadata
  )

  # Create thread WITHOUT adding any messages to it
  thread_id = generate_id(backend_type)
  thread_session_id = f"thread_{generate_id(backend_type)}"
  query_context = {"original_query": "Test"}

  dataset_key = await dataset_service.store_dataset(
    thread_id=thread_id,
    query_context=query_context,
    raw_results=[{"content": "Doc"}]
  )

  await db.insert_one('conversation_threads', {
    'id': thread_id,
    'parent_message_id': assistant_msg_id,
    'parent_session_id': session_id,
    'thread_session_id': thread_session_id,
    'adapter_name': "intent-test",
    'query_context': json.dumps(query_context),
    'dataset_key': dataset_key,
    'created_at': datetime.now(UTC).isoformat(),
    'expires_at': (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
    'metadata_json': json.dumps({})
  })

  # Clear the session
  result = await chat_history.clear_session_history(session_id)
  assert result is True

  # Verify thread is deleted even though it had no messages
  assert await db.find_many('conversation_threads', {'parent_session_id': session_id}) == []
  assert await dataset_service.get_dataset(dataset_key) is None


@pytest.mark.asyncio
async def test_api_key_is_masked_when_stored(chat_history_services):
  """Test that API keys are masked before being stored in chat history."""
  services = chat_history_services
  chat_history = services['chat_history']
  db = services['db']
  backend_type = services['config']['internal_services']['backend']['type']

  session_id = f"session_{generate_id(backend_type)}"
  raw_api_key = "sk-test-1234567890abcdef"

  # Add a message with an API key
  await chat_history.add_message(
    session_id=session_id,
    role='user',
    content='Test message',
    api_key=raw_api_key
  )

  # Retrieve the message directly from the database
  messages = await db.find_many('chat_history', {'session_id': session_id})
  assert len(messages) == 1

  stored_api_key = messages[0].get('api_key')

  # Verify the API key is NOT stored in plain text
  assert stored_api_key != raw_api_key

  # Verify the API key is masked correctly (matches mask_api_key output)
  expected_masked = mask_api_key(raw_api_key, show_last=True, num_chars=6)
  assert stored_api_key == expected_masked

  # Verify the masked key shows only the last 6 characters
  assert stored_api_key.endswith(raw_api_key[-6:])
