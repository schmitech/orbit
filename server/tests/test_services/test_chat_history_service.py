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
from unittest.mock import MagicMock

import pytest
from pytest_asyncio import fixture

# Ensure server modules can be imported
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.sqlite_service import SQLiteService
from services.chat_history_service import ChatHistoryService, SessionOwnershipError
from services.thread_dataset_service import ThreadDatasetService
from utils.id_utils import generate_id
from utils.text_utils import hash_api_key, mask_api_key


def test_runtime_provider_selects_its_own_history_budget_without_param_overrides():
  """A runtime allowed_models provider must not inherit the adapter's budget."""
  adapter_manager = MagicMock()
  adapter_manager.get_adapter_config.return_value = {
    'inference_provider': 'openai',
  }
  service = ChatHistoryService(
    {
      'general': {'inference_provider': 'openai'},
      'inference': {
        'openai': {'context_window': 128000, 'max_tokens': 4096},
        'mistral': {'context_window': 32000, 'max_tokens': 2048},
      },
    },
    database_service=MagicMock(),
    thread_dataset_service=MagicMock(),
    adapter_manager=adapter_manager,
  )
  service.max_token_budget = service._calculate_max_token_budget()

  default_budget = service._get_token_budget_for_adapter('simple-chat')
  mistral_budget = service._get_token_budget_for_adapter(
    'simple-chat', runtime_provider='mistral'
  )

  assert default_budget == 123204
  assert mistral_budget == 29252
  assert mistral_budget < default_budget


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
      'cache_key_prefix': 'thread_dataset:'
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


async def _seed_conversation_with_thread(services, api_key="valid-key"):
  """
  Create a parent conversation plus a thread with its own session.

  Seeds with an owning API key by default so the session has an owner marker, which
  is what an authenticated chat request produces. Pass api_key=None to simulate the
  ownerless rows written by paths that don't propagate a key.
  """
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
    api_key=api_key,
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
    api_key=api_key,
    metadata=metadata
  )
  await chat_history.add_message(
    session_id=thread_session_id,
    role='assistant',
    content='Threaded answer.',
    api_key=api_key,
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


class _GenerationMemoryContainer:
  """Minimal container satisfying inference.pipeline.steps._utils' contract
  (has/get for 'thread_dataset_service') so store/get_generation_memory can be
  exercised against the fixture's real ThreadDatasetService."""
  def __init__(self, dataset_service):
    self._dataset_service = dataset_service

  def has(self, key):
    return key == 'thread_dataset_service'

  def get(self, key):
    return self._dataset_service if key == 'thread_dataset_service' else None


@pytest.mark.asyncio
async def test_clear_session_history_removes_generation_memory_with_existing_thread(chat_history_services):
  """A session that has both a normal intent-SQL thread AND generation memory —
  both must be cleaned up together."""
  from inference.pipeline.steps._utils import get_generation_memory, store_generation_memory

  services = chat_history_services
  services['config']['adapters'] = [
    {'name': 'image-generator', 'type': 'image_generation'},
    {'name': 'pdf-generator', 'type': 'document_generation'},
  ]
  container = _GenerationMemoryContainer(services['dataset'])

  seeded = await _seed_conversation_with_thread(services)
  await store_generation_memory(
    container, "image-generator", seeded['session_id'], {"prompt": "a dog in a forest"}
  )
  assert await get_generation_memory(container, "image-generator", seeded['session_id']) is not None

  result = await services['chat_history'].clear_session_history(seeded['session_id'])
  assert result is True

  assert await services['dataset'].get_dataset(seeded['dataset_key']) is None
  assert await get_generation_memory(container, "image-generator", seeded['session_id']) is None


@pytest.mark.asyncio
async def test_clear_session_history_removes_generation_memory_with_no_thread(chat_history_services):
  """Regression test: a session that ONLY ever used generation adapters (no
  conversation_threads row at all) must still have its generation memory
  cleaned up — the conversation_threads lookup returning empty must not skip
  this cleanup."""
  from inference.pipeline.steps._utils import get_generation_memory, store_generation_memory

  services = chat_history_services
  services['config']['adapters'] = [
    {'name': 'image-generator', 'type': 'image_generation'},
    {'name': 'video-generator', 'type': 'video_generation'},
    {'name': 'pdf-generator', 'type': 'document_generation'},
  ]
  container = _GenerationMemoryContainer(services['dataset'])

  backend_type = services['config']['internal_services']['backend']['type']
  session_id = f"session_{generate_id(backend_type)}"

  await store_generation_memory(container, "image-generator", session_id, {"prompt": "a dog in a forest"})
  await store_generation_memory(container, "pdf-generator", session_id, {"spec": {"title": "Q1 report"}})
  # video-generator was never used this session — its cleanup attempt should no-op, not error.

  assert await get_generation_memory(container, "image-generator", session_id) is not None
  assert await get_generation_memory(container, "pdf-generator", session_id) is not None

  # No conversation_threads row exists for this session — confirm the baseline.
  assert await services['db'].find_many('conversation_threads', {'parent_session_id': session_id}) == []

  result = await services['chat_history'].clear_session_history(session_id)
  assert result is False  # no chat_history rows were ever added for this session

  assert await get_generation_memory(container, "image-generator", session_id) is None
  assert await get_generation_memory(container, "pdf-generator", session_id) is None
  assert await get_generation_memory(container, "video-generator", session_id) is None


@pytest.mark.asyncio
async def test_clear_session_history_removes_generation_memory_stored_inside_thread(chat_history_services):
  """Regression test: a generation skill (e.g. PDF) invoked WHILE a thread is
  active stores its memory under the thread's own thread_session_id, not the
  parent conversation's session_id (ContextRetrievalStep reassigns
  context.session_id to thread_session_id for thread follow-ups — see
  inference/pipeline/steps/context_retrieval.py). Deleting the parent
  conversation must still clean this up."""
  from inference.pipeline.steps._utils import get_generation_memory, store_generation_memory

  services = chat_history_services
  services['config']['adapters'] = [
    {'name': 'pdf-generator', 'type': 'document_generation'},
  ]
  container = _GenerationMemoryContainer(services['dataset'])

  seeded = await _seed_conversation_with_thread(services)
  await store_generation_memory(
    container, "pdf-generator", seeded['thread_session_id'], {"spec": {"title": "Q1 report"}}
  )
  assert await get_generation_memory(container, "pdf-generator", seeded['thread_session_id']) is not None

  result = await services['chat_history'].clear_session_history(seeded['session_id'])
  assert result is True

  assert await services['dataset'].get_dataset(seeded['dataset_key']) is None
  assert await get_generation_memory(container, "pdf-generator", seeded['thread_session_id']) is None


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


class _MultiTenantApiKeyService:
  """Treats every key starting with 'api_' as valid, so two tenants can coexist."""
  async def validate_api_key(self, api_key, adapter_manager=None):
    if not api_key.startswith("api_"):
      return False, None, None
    return True, "intent-test", None


@pytest.mark.asyncio
async def test_clear_conversation_history_rejects_cross_tenant_key(chat_history_services):
  """A valid key must not be able to clear a session created by a different key."""
  services = chat_history_services
  chat_history = services['chat_history']
  backend_type = services['config']['internal_services']['backend']['type']

  key_a = "api_tenantAAAAAAAAAAAAAAAAAAAAAAA"
  key_b = "api_tenantBBBBBBBBBBBBBBBBBBBBBBB"

  session_a = f"session_{generate_id(backend_type)}"
  await chat_history.add_conversation_turn(
    session_id=session_a,
    user_message="Confidential question",
    assistant_response="Confidential answer",
    api_key=key_a
  )
  assert len(await services['db'].find_many('chat_history', {'session_id': session_a})) == 2

  chat_history.api_key_service = _MultiTenantApiKeyService()

  # Tenant B holds a perfectly valid key, but does not own session_a.
  result = await chat_history.clear_conversation_history(
    session_id=session_a,
    api_key=key_b
  )

  assert result["success"] is False
  assert result["error"] == "Access denied"
  assert result["deleted_count"] == 0

  # Tenant A's conversation must survive the attempt.
  assert len(await services['db'].find_many('chat_history', {'session_id': session_a})) == 2

  # The owning key still works.
  owner_result = await chat_history.clear_conversation_history(
    session_id=session_a,
    api_key=key_a
  )
  assert owner_result["success"] is True
  assert owner_result["deleted_count"] == 2
  assert await services['db'].find_many('chat_history', {'session_id': session_a}) == []


@pytest.mark.asyncio
async def test_clear_conversation_history_rejects_key_with_matching_suffix(chat_history_services):
  """
  Ownership must use the full key, not a suffix.

  These two keys are distinct but share their last 6 characters, so they collapse to
  the same mask_api_key() output. A suffix-based check would let the attacker through.
  """
  services = chat_history_services
  chat_history = services['chat_history']
  backend_type = services['config']['internal_services']['backend']['type']

  key_a = "api_tenantA_colliding_SUFFIX"
  key_b = "api_tenantB_different_SUFFIX"
  assert mask_api_key(key_a, show_last=True, num_chars=6) == mask_api_key(key_b, show_last=True, num_chars=6)

  session_a = f"session_{generate_id(backend_type)}"
  await chat_history.add_conversation_turn(
    session_id=session_a,
    user_message="Confidential question",
    assistant_response="Confidential answer",
    api_key=key_a
  )

  chat_history.api_key_service = _MultiTenantApiKeyService()

  result = await chat_history.clear_conversation_history(session_id=session_a, api_key=key_b)

  assert result["success"] is False
  assert result["error"] == "Access denied"
  assert len(await services['db'].find_many('chat_history', {'session_id': session_a})) == 2


@pytest.mark.asyncio
async def test_clear_conversation_history_legacy_rows_without_hash(chat_history_services):
  """
  Rows predating api_key_hash fall back to the masked comparison.

  Cross-tenant deletion is still refused, and the owner can still clear the session,
  so un-backfilled history is neither exposed nor stranded.
  """
  services = chat_history_services
  chat_history = services['chat_history']
  db = services['db']
  backend_type = services['config']['internal_services']['backend']['type']

  key_a = "api_tenantAAAAAAAAAAAAAAAAAAAAAAA"
  key_b = "api_tenantBBBBBBBBBBBBBBBBBBBBBBB"

  session_a = f"session_{generate_id(backend_type)}"
  await chat_history.add_conversation_turn(
    session_id=session_a,
    user_message="Legacy question",
    assistant_response="Legacy answer",
    api_key=key_a
  )

  # Simulate pre-migration rows: masked key present, fingerprint absent.
  for msg in await db.find_many('chat_history', {'session_id': session_a}):
    await db.update_one('chat_history', {'_id': msg['_id']}, {'$set': {'api_key_hash': None}})
  assert all(
    m.get('api_key_hash') is None
    for m in await db.find_many('chat_history', {'session_id': session_a})
  )

  chat_history.api_key_service = _MultiTenantApiKeyService()

  denied = await chat_history.clear_conversation_history(session_id=session_a, api_key=key_b)
  assert denied["success"] is False
  assert denied["error"] == "Access denied"
  assert len(await db.find_many('chat_history', {'session_id': session_a})) == 2

  allowed = await chat_history.clear_conversation_history(session_id=session_a, api_key=key_a)
  assert allowed["success"] is True
  assert allowed["deleted_count"] == 2


@pytest.mark.asyncio
async def test_append_to_foreign_session_is_refused(chat_history_services):
  """
  A key must not be able to write into a session it does not own.

  session_id is client-supplied and unvalidated, so without this guard key B could
  append one message to key A's session and thereby manufacture the ownership that
  clear_conversation_history() checks.
  """
  services = chat_history_services
  chat_history = services['chat_history']
  db = services['db']
  backend_type = services['config']['internal_services']['backend']['type']

  key_a = "api_tenantAAAAAAAAAAAAAAAAAAAAAAA"
  key_b = "api_tenantBBBBBBBBBBBBBBBBBBBBBBB"

  session_a = f"session_{generate_id(backend_type)}"
  await chat_history.add_conversation_turn(
    session_id=session_a,
    user_message="Confidential question",
    assistant_response="Confidential answer",
    api_key=key_a
  )

  with pytest.raises(SessionOwnershipError):
    await chat_history.add_message(
      session_id=session_a,
      role='user',
      content='B injected',
      api_key=key_b
    )

  # The session is untouched, so it still has exactly one owner.
  assert len(await db.find_many('chat_history', {'session_id': session_a})) == 2
  assert await chat_history._api_key_owns_session(session_a, key_a) is True
  assert await chat_history._api_key_owns_session(session_a, key_b) is False


@pytest.mark.asyncio
async def test_ownership_poisoning_cannot_authorize_deletion(chat_history_services):
  """
  End-to-end: the reported escalation must fail at both steps.

  Even if a mixed-owner session were somehow produced, ownership requires ALL rows to
  match, so a single injected row grants nothing.
  """
  services = chat_history_services
  chat_history = services['chat_history']
  db = services['db']
  backend_type = services['config']['internal_services']['backend']['type']

  key_a = "api_tenantAAAAAAAAAAAAAAAAAAAAAAA"
  key_b = "api_tenantBBBBBBBBBBBBBBBBBBBBBBB"

  session_a = f"session_{generate_id(backend_type)}"
  await chat_history.add_conversation_turn(
    session_id=session_a,
    user_message="Confidential question",
    assistant_response="Confidential answer",
    api_key=key_a
  )
  chat_history.api_key_service = _MultiTenantApiKeyService()

  # Step 1: the append guard refuses the poisoning write.
  with pytest.raises(SessionOwnershipError):
    await chat_history.add_message(
      session_id=session_a, role='user', content='B injected', api_key=key_b
    )

  # Step 2: force a poisoned row in directly, bypassing the guard entirely, to prove
  # the delete check does not rely on the guard alone.
  await db.insert_one('chat_history', {
    'session_id': session_a,
    'role': 'user',
    'content': 'B injected',
    'timestamp': datetime.now(UTC),
    'api_key': mask_api_key(key_b, show_last=True, num_chars=6),
    'api_key_hash': hash_api_key(key_b),
  })

  result = await chat_history.clear_conversation_history(session_id=session_a, api_key=key_b)
  assert result["success"] is False
  assert result["error"] == "Access denied"

  # A's messages survive.
  remaining = await db.find_many('chat_history', {'session_id': session_a})
  assert len([m for m in remaining if m['content'].startswith('Confidential')]) == 2


@pytest.mark.asyncio
async def test_clear_conversation_history_denies_markerless_session(chat_history_services):
  """
  A non-empty session with no owner marker cannot be attributed to anyone, so no
  caller may delete it. This is what ownerless A2A history used to look like.
  """
  services = chat_history_services
  chat_history = services['chat_history']
  db = services['db']

  seeded = await _seed_conversation_with_thread(services, api_key=None)
  assert all(
    not m.get('api_key') and not m.get('api_key_hash')
    for m in await db.find_many('chat_history', {'session_id': seeded['session_id']})
  )

  chat_history.api_key_service = _MultiTenantApiKeyService()

  result = await chat_history.clear_conversation_history(
    session_id=seeded['session_id'],
    api_key="api_someUnrelatedTenantKey"
  )

  assert result["success"] is False
  assert result["error"] == "Access denied"
  assert len(await db.find_many('chat_history', {'session_id': seeded['session_id']})) == 2


def _context_handler(services):
  """A ConversationHistoryHandler wired to the fixture, with history always enabled."""
  from services.chat_handlers.conversation_history_handler import ConversationHistoryHandler
  handler = ConversationHistoryHandler(
    config=services['config'],
    chat_history_service=services['chat_history'],
    adapter_manager=None
  )
  handler.should_enable = lambda adapter_name: True
  return handler


@pytest.mark.asyncio
async def test_get_context_refuses_foreign_session(chat_history_services):
  """
  Reading context for a foreign session must raise, not return empty.

  Empty context would hide the authorization failure and still let the caller drive
  a turn against another tenant's session id.
  """
  services = chat_history_services
  chat_history = services['chat_history']
  backend_type = services['config']['internal_services']['backend']['type']

  key_a = "api_tenantAAAAAAAAAAAAAAAAAAAAAAA"
  key_b = "api_tenantBBBBBBBBBBBBBBBBBBBBBBB"

  session_a = f"session_{generate_id(backend_type)}"
  await chat_history.add_conversation_turn(
    session_id=session_a,
    user_message="Confidential question",
    assistant_response="Confidential answer",
    api_key=key_a
  )

  handler = _context_handler(services)

  # The owner reads their own history.
  assert len(await handler.get_context(session_a, "demo", api_key=key_a)) == 2

  # A foreign key is refused outright.
  with pytest.raises(SessionOwnershipError):
    await handler.get_context(session_a, "demo", api_key=key_b)

  # Deployments without key enforcement are unaffected.
  assert len(await handler.get_context(session_a, "demo", api_key=None)) == 2


@pytest.mark.asyncio
async def test_get_context_refuses_markerless_session(chat_history_services):
  """Ownerless history must not be readable by an arbitrary key either."""
  services = chat_history_services
  await services['chat_history'].add_message(
    session_id="markerless-session", role="user", content="ownerless"
  )

  handler = _context_handler(services)

  with pytest.raises(SessionOwnershipError):
    await handler.get_context("markerless-session", "demo", api_key="api_someTenantKey")


@pytest.mark.asyncio
async def test_authorize_session_access_raises_403(chat_history_services):
  """The route-level gate returns 403 for a foreign session, and passes for the owner."""
  from fastapi import HTTPException
  from services.pipeline_chat_service import PipelineChatService

  services = chat_history_services
  chat_history = services['chat_history']
  backend_type = services['config']['internal_services']['backend']['type']

  key_a = "api_tenantAAAAAAAAAAAAAAAAAAAAAAA"
  key_b = "api_tenantBBBBBBBBBBBBBBBBBBBBBBB"

  session_a = f"session_{generate_id(backend_type)}"
  await chat_history.add_conversation_turn(
    session_id=session_a,
    user_message="Confidential question",
    assistant_response="Confidential answer",
    api_key=key_a
  )

  svc = object.__new__(PipelineChatService)
  svc.chat_history_service = chat_history
  svc.conversation_handler = None
  svc.pipeline = None

  # Owner passes.
  await svc.authorize_session_access(session_id=session_a, api_key=key_a)

  # Foreign key is rejected with 403, not 500 or a silent empty result.
  with pytest.raises(HTTPException) as exc:
    await svc.authorize_session_access(session_id=session_a, api_key=key_b)
  assert exc.value.status_code == 403

  # No key configured (enforcement disabled) is a no-op.
  await svc.authorize_session_access(session_id=session_a, api_key=None)


@pytest.mark.asyncio
async def test_thread_owner_hash_binds_thread_to_parent_owner(chat_history_services):
  """
  A thread carries its parent's owner hash, which authorizes turn 1.

  On the first turn the thread session is still empty and has no owner rows of its
  own, so without the persisted binding there would be nothing to check.
  """
  from fastapi import HTTPException
  from services.pipeline_chat_service import PipelineChatService

  services = chat_history_services
  key_a = "api_tenantAAAAAAAAAAAAAAAAAAAAAAA"
  key_b = "api_tenantBBBBBBBBBBBBBBBBBBBBBBB"

  class _Container:
    def __init__(self, thread_service):
      self._ts = thread_service
    def has(self, key):
      return key == 'thread_service'
    def get(self, key):
      return self._ts if key == 'thread_service' else None

  class _ThreadService:
    def __init__(self, info):
      self._info = info
    async def get_thread(self, thread_id):
      return self._info

  class _Pipeline:
    def __init__(self, container):
      self.container = container

  thread_info = {
    'thread_session_id': 'thread-sess-1',
    'parent_session_id': 'parent-sess-1',
    'owner_api_key_hash': hash_api_key(key_a),
  }

  svc = object.__new__(PipelineChatService)
  svc.chat_history_service = services['chat_history']
  svc.conversation_handler = None
  svc.pipeline = _Pipeline(_Container(_ThreadService(thread_info)))

  # Parent's owner may use the thread even though the thread session is empty.
  await svc.authorize_session_access(
    session_id='parent-sess-1', api_key=key_a, thread_id='t1'
  )

  # Anyone else is refused.
  with pytest.raises(HTTPException) as exc:
    await svc.authorize_session_access(
      session_id='parent-sess-1', api_key=key_b, thread_id='t1'
    )
  assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_thread_returns_owner_hash(chat_history_services):
  """
  create_thread persists owner_api_key_hash and get_thread must return it.

  Regression test: the field was originally stored but dropped from get_thread()'s
  projection, so every ownership check silently fell through to the legacy path.
  Uses the real ThreadService rather than a stub, which is what hid the bug.
  """
  from services.thread_service import ThreadService

  services = chat_history_services
  thread_service = ThreadService(
    services['config'],
    database_service=services['db'],
    dataset_service=services['dataset']
  )
  await thread_service.initialize()

  key_a = "api_tenantAAAAAAAAAAAAAAAAAAAAAAA"

  created = await thread_service.create_thread(
    parent_message_id="msg-1",
    parent_session_id="parent-sess-1",
    adapter_name="intent-test",
    query_context={"original_query": "q"},
    raw_results=[{"content": "Doc 1"}],
    owner_api_key_hash=hash_api_key(key_a)
  )

  fetched = await thread_service.get_thread(created['thread_id'])
  assert fetched['owner_api_key_hash'] == hash_api_key(key_a)


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

  # The ownership fingerprint is stored alongside it, and is also not the raw key
  stored_hash = messages[0].get('api_key_hash')
  assert stored_hash == hash_api_key(raw_api_key)
  assert raw_api_key not in stored_hash
  assert stored_hash != hash_api_key(raw_api_key + "x")


# ============================================================================
# get_conversation_history tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_conversation_history_returns_chronological_order(chat_history_services):
  """Messages come back oldest-first regardless of insertion order."""
  services = chat_history_services
  chat_history = services['chat_history']
  backend_type = services['config']['internal_services']['backend']['type']

  session_id = f"session_{generate_id(backend_type)}"
  await chat_history.add_conversation_turn(
    session_id=session_id,
    user_message="First",
    assistant_response="Second",
  )
  await chat_history.add_conversation_turn(
    session_id=session_id,
    user_message="Third",
    assistant_response="Fourth",
  )

  messages = await chat_history.get_conversation_history(session_id)

  assert len(messages) == 4
  assert messages[0]['content'] == "First"
  assert messages[0]['role'] == "user"
  assert messages[-1]['content'] == "Fourth"
  assert messages[-1]['role'] == "assistant"


@pytest.mark.asyncio
async def test_get_conversation_history_message_shape(chat_history_services):
  """Each returned message has the expected fields including a string message_id."""
  services = chat_history_services
  chat_history = services['chat_history']
  backend_type = services['config']['internal_services']['backend']['type']

  session_id = f"session_{generate_id(backend_type)}"
  await chat_history.add_message(session_id=session_id, role="user", content="Hello")

  messages = await chat_history.get_conversation_history(session_id)

  assert len(messages) == 1
  msg = messages[0]
  assert set(msg.keys()) >= {"message_id", "role", "content", "timestamp"}
  assert isinstance(msg['message_id'], str), "message_id must be a string"
  assert msg['role'] == "user"
  assert msg['content'] == "Hello"


@pytest.mark.asyncio
async def test_get_conversation_history_limit(chat_history_services):
  """The limit parameter caps the number of returned messages."""
  services = chat_history_services
  chat_history = services['chat_history']
  backend_type = services['config']['internal_services']['backend']['type']

  session_id = f"session_{generate_id(backend_type)}"
  for i in range(6):
    await chat_history.add_message(session_id=session_id, role="user", content=f"msg {i}")

  messages = await chat_history.get_conversation_history(session_id, limit=3)

  assert len(messages) == 3
  # Should be the 3 most-recent messages in chronological order
  assert messages[-1]['content'] == "msg 5"


@pytest.mark.asyncio
async def test_get_conversation_history_empty_session(chat_history_services):
  """Returns an empty list for a session that has no messages."""
  services = chat_history_services
  backend_type = services['config']['internal_services']['backend']['type']
  session_id = f"session_{generate_id(backend_type)}"

  messages = await services['chat_history'].get_conversation_history(session_id)

  assert messages == []


# ============================================================================
# get_context_messages tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_context_messages_format(chat_history_services):
  """Returned messages are formatted for LLM context (role + content only)."""
  services = chat_history_services
  chat_history = services['chat_history']
  backend_type = services['config']['internal_services']['backend']['type']

  session_id = f"session_{generate_id(backend_type)}"
  await chat_history.add_conversation_turn(
    session_id=session_id,
    user_message="Hello",
    assistant_response="Hi there",
  )

  context, token_count = await chat_history.get_context_messages(session_id)

  assert len(context) == 2
  assert context[0] == {"role": "user", "content": "Hello"}
  assert context[1] == {"role": "assistant", "content": "Hi there"}
  assert token_count > 0


@pytest.mark.asyncio
async def test_get_context_messages_chronological_order(chat_history_services):
  """Context messages are returned oldest-first."""
  services = chat_history_services
  chat_history = services['chat_history']
  backend_type = services['config']['internal_services']['backend']['type']

  session_id = f"session_{generate_id(backend_type)}"
  await chat_history.add_conversation_turn(
    session_id=session_id, user_message="A", assistant_response="B"
  )
  await chat_history.add_conversation_turn(
    session_id=session_id, user_message="C", assistant_response="D"
  )

  context, _ = await chat_history.get_context_messages(session_id)

  contents = [m['content'] for m in context]
  assert contents == ["A", "B", "C", "D"]


@pytest.mark.asyncio
async def test_get_context_messages_respects_token_budget(chat_history_services):
  """Messages that exceed the token budget are excluded (oldest dropped first)."""
  services = chat_history_services
  chat_history = services['chat_history']
  backend_type = services['config']['internal_services']['backend']['type']

  session_id = f"session_{generate_id(backend_type)}"

  # Add several messages so we can enforce a tight budget
  for i in range(5):
    await chat_history.add_message(
      session_id=session_id, role="user", content=f"message number {i}"
    )

  # Fetch all to establish an unconstrained baseline
  all_context, total_tokens = await chat_history.get_context_messages(session_id)
  assert len(all_context) == 5

  # Request with a budget that fits only a subset
  half_budget = total_tokens // 2
  trimmed_context, trimmed_tokens = await chat_history.get_context_messages(
    session_id, max_tokens=half_budget
  )

  assert len(trimmed_context) < 5, "Tight budget should exclude some messages"
  assert trimmed_tokens <= half_budget
  # Remaining messages should be the most-recent ones (newest kept, oldest dropped)
  assert trimmed_context[-1]['content'] == all_context[-1]['content']


@pytest.mark.asyncio
async def test_get_context_messages_empty_session(chat_history_services):
  """Returns empty list and zero tokens for a session with no messages."""
  services = chat_history_services
  backend_type = services['config']['internal_services']['backend']['type']
  session_id = f"session_{generate_id(backend_type)}"

  context, token_count = await services['chat_history'].get_context_messages(session_id)

  assert context == []
  assert token_count == 0


@pytest.mark.asyncio
async def test_regenerate_replaces_assistant_message_in_place(chat_history_services):
  """A regenerate (regenerate_of_message_id set) must overwrite the existing
  assistant turn instead of inserting a new user+assistant pair — otherwise
  clicking "regenerate" duplicates the turn in chat_history, and the duplicate
  reappears in the UI on reload via get_conversation_history."""
  chat_history = chat_history_services['chat_history']
  backend_type = chat_history_services['config']['internal_services']['backend']['type']
  session_id = f"session_{generate_id(backend_type)}"

  user_msg_id, assistant_msg_id = await chat_history.add_conversation_turn(
    session_id=session_id,
    user_message="Give me a one-paragraph summary of WebSockets.",
    assistant_response="WebSockets are a protocol that enables persistent, full-duplex communication.",
  )
  assert user_msg_id is not None
  assert assistant_msg_id is not None

  regen_user_id, regen_assistant_id = await chat_history.add_conversation_turn(
    session_id=session_id,
    user_message="Give me a one-paragraph summary of WebSockets.",
    assistant_response="WebSockets are a communication protocol that upgrades an initial HTTP request.",
    regenerate_of_message_id=assistant_msg_id,
  )

  # No new rows inserted — both the existing user and assistant rows are reused.
  assert regen_user_id == user_msg_id
  assert regen_assistant_id == assistant_msg_id

  history = await chat_history.get_conversation_history(session_id)
  assert len(history) == 2, f"Expected exactly one user+assistant pair, got {len(history)}: {history}"
  roles = [m['role'] for m in history]
  assert roles == ["user", "assistant"]
  assert history[1]['content'] == "WebSockets are a communication protocol that upgrades an initial HTTP request."


@pytest.mark.asyncio
async def test_edit_and_regenerate_replaces_both_messages_in_place(chat_history_services):
  """Editing a user message and regenerating (regenerate_of_message_id set, and the
  user text itself changed) must overwrite BOTH the original user and assistant rows
  in place — not just skip re-inserting the user row with its stale text — otherwise
  chat_history ends up with an old prompt paired against the new response, or a
  second duplicate turn, on reload."""
  chat_history = chat_history_services['chat_history']
  backend_type = chat_history_services['config']['internal_services']['backend']['type']
  session_id = f"session_{generate_id(backend_type)}"

  user_msg_id, assistant_msg_id = await chat_history.add_conversation_turn(
    session_id=session_id,
    user_message="Give me three colors.",
    assistant_response="Red, green, blue.",
  )

  edit_user_id, edit_assistant_id = await chat_history.add_conversation_turn(
    session_id=session_id,
    user_message="Give me three fruits.",
    assistant_response="Apple, banana, cherry.",
    regenerate_of_message_id=assistant_msg_id,
  )

  # No new rows inserted — both existing rows are reused and updated.
  assert edit_user_id == user_msg_id
  assert edit_assistant_id == assistant_msg_id

  history = await chat_history.get_conversation_history(session_id)
  assert len(history) == 2, f"Expected exactly one user+assistant pair, got {len(history)}: {history}"
  assert history[0]['content'] == "Give me three fruits."
  assert history[1]['content'] == "Apple, banana, cherry."


@pytest.mark.asyncio
async def test_regenerate_of_unknown_message_id_falls_back_to_insert(chat_history_services):
  """If the referenced assistant message doesn't exist (e.g. stale/cleared history),
  regenerate must fall back to a normal insert rather than silently losing the turn."""
  chat_history = chat_history_services['chat_history']
  backend_type = chat_history_services['config']['internal_services']['backend']['type']
  session_id = f"session_{generate_id(backend_type)}"

  user_msg_id, assistant_msg_id = await chat_history.add_conversation_turn(
    session_id=session_id,
    user_message="Give me three colors.",
    assistant_response="Red, green, blue.",
    regenerate_of_message_id="nonexistent-message-id",
  )

  assert user_msg_id is not None
  assert assistant_msg_id is not None

  history = await chat_history.get_conversation_history(session_id)
  assert len(history) == 2
  assert history[1]['content'] == "Red, green, blue."


@pytest.mark.asyncio
async def test_regenerate_cannot_target_message_in_another_session(chat_history_services):
  """A regenerate_of_message_id belonging to a different session must not be
  overwritten — otherwise one session's caller could pass an id from another
  session (guessed, leaked, or forged) and corrupt that unrelated conversation."""
  chat_history = chat_history_services['chat_history']
  backend_type = chat_history_services['config']['internal_services']['backend']['type']
  session_a = f"session_{generate_id(backend_type)}"
  session_b = f"session_{generate_id(backend_type)}"

  _, assistant_msg_id_a = await chat_history.add_conversation_turn(
    session_id=session_a,
    user_message="What is the capital of France?",
    assistant_response="Paris.",
  )

  # session_b regenerates using session_a's assistant message id.
  regen_user_id, regen_assistant_id = await chat_history.add_conversation_turn(
    session_id=session_b,
    user_message="What is the capital of Italy?",
    assistant_response="Rome.",
    regenerate_of_message_id=assistant_msg_id_a,
  )

  # session_a's turn must be untouched.
  history_a = await chat_history.get_conversation_history(session_a)
  assert len(history_a) == 2
  assert history_a[0]['content'] == "What is the capital of France?"
  assert history_a[1]['content'] == "Paris."

  # session_b must have fallen back to a normal insert of its own new turn, not
  # silently disappear or overwrite session_a's row.
  assert regen_user_id is not None
  assert regen_assistant_id is not None
  assert regen_assistant_id != assistant_msg_id_a
  history_b = await chat_history.get_conversation_history(session_b)
  assert len(history_b) == 2
  assert history_b[0]['content'] == "What is the capital of Italy?"
  assert history_b[1]['content'] == "Rome."


@pytest.mark.asyncio
async def test_regenerate_of_non_final_turn_preserves_conversation_order(chat_history_services):
  """Regenerating an earlier (non-final) turn must not reorder it after later turns —
  get_conversation_history sorts by timestamp, so bumping the replaced rows' timestamp
  to "now" would move them past subsequent messages and corrupt branch order on the
  next reload or context build."""
  chat_history = chat_history_services['chat_history']
  backend_type = chat_history_services['config']['internal_services']['backend']['type']
  session_id = f"session_{generate_id(backend_type)}"

  _, first_assistant_id = await chat_history.add_conversation_turn(
    session_id=session_id,
    user_message="Give me one color.",
    assistant_response="Blue.",
  )
  await chat_history.add_conversation_turn(
    session_id=session_id,
    user_message="Give me one animal.",
    assistant_response="Dog.",
  )

  # Regenerate the FIRST (non-final) turn.
  await chat_history.add_conversation_turn(
    session_id=session_id,
    user_message="Give me one color.",
    assistant_response="Green.",
    regenerate_of_message_id=first_assistant_id,
  )

  history = await chat_history.get_conversation_history(session_id)
  assert len(history) == 4, f"Expected 4 messages (no duplicate insert), got {len(history)}: {history}"
  contents = [m['content'] for m in history]
  assert contents == ["Give me one color.", "Green.", "Give me one animal.", "Dog."], (
    "Regenerating the first turn should not move it after the second turn"
  )
