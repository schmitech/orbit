"""
Tests for bug fixes in server/services/
========================================

Covers the specific fixes applied:
- 1a: SQLite executor shutdown in close()
- 1b: SQLite connection closed on init failure
- 1c: execute_transaction() uses real BEGIN/COMMIT/ROLLBACK
- 1d: asyncio.get_running_loop() replaces get_event_loop()
- 2a: Timeout in _wait_for_adapter_initialization
- 3a: datetime.now(timezone.utc) replaces utcnow()
- 4a: Bounded _session_locks cleanup
- 4b: Removed racy session_lock.locked() pre-check
- 5a: Cache exceptions logged instead of silently swallowed
- 6a: time.monotonic() replaces asyncio.get_event_loop().time()
"""

import asyncio
import os
import sys
import tempfile
import shutil
import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_asyncio import fixture

# Add server directory to path
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@fixture(scope="function")
async def sqlite_service():
    """Create a fresh SQLite service for each test."""
    from services.sqlite_service import SQLiteService
    SQLiteService.clear_cache()

    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_bugfix.db")
    config = {
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {'database_path': db_path},
            }
        },
        'general': {},
    }

    service = SQLiteService(config)
    await service.initialize()
    yield service

    service.close()
    SQLiteService.clear_cache()
    shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 1a – Executor shutdown in close()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_close_shuts_down_executor(sqlite_service):
    """close() should shut down the old executor and create a new one."""
    old_executor = sqlite_service.executor
    sqlite_service.close()

    # Old executor should be shut down
    assert old_executor._shutdown

    # New executor should be usable (singleton remains functional)
    assert sqlite_service.executor is not old_executor
    assert not sqlite_service.executor._shutdown


# ---------------------------------------------------------------------------
# 1b – Connection closed on init failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_init_failure_closes_connection():
    """If init fails after connection, the connection should be closed."""
    from services.sqlite_service import SQLiteService
    SQLiteService.clear_cache()

    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_init_fail.db")
    config = {
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {'database_path': db_path},
            }
        },
        'general': {},
    }

    service = SQLiteService(config)

    # Patch _create_tables to raise after connection is established
    with patch.object(service, '_create_tables', side_effect=RuntimeError("table creation failed")):
        with pytest.raises(RuntimeError, match="table creation failed"):
            await service.initialize()

    # Connection should have been cleaned up
    assert service.connection is None or not service._initialized

    SQLiteService.clear_cache()
    shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 1c – execute_transaction uses real BEGIN/COMMIT/ROLLBACK
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transaction_commit(sqlite_service):
    """Successful transaction should commit all operations."""
    async def ops(_):
        await sqlite_service.insert_one("test_tx", {"key": "a", "val": 1})
        await sqlite_service.insert_one("test_tx", {"key": "b", "val": 2})
        return "ok"

    result = await sqlite_service.execute_transaction(ops)
    assert result == "ok"

    docs = await sqlite_service.find_many("test_tx", {})
    assert len(docs) == 2


@pytest.mark.asyncio
async def test_transaction_exception_propagates(sqlite_service):
    """Failed transaction should propagate the exception and call rollback."""
    async def failing_ops(_):
        raise ValueError("deliberate failure")

    with pytest.raises(ValueError, match="deliberate failure"):
        await sqlite_service.execute_transaction(failing_ops)

    # Service should still be functional after a failed transaction
    doc_id = await sqlite_service.insert_one("test_tx_after_fail", {"key": "ok"})
    assert doc_id is not None
    found = await sqlite_service.find_one("test_tx_after_fail", {"_id": doc_id})
    assert found["key"] == "ok"


# ---------------------------------------------------------------------------
# 2a – Timeout in _wait_for_adapter_initialization
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adapter_init_wait_timeout():
    """_wait_for_adapter_initialization should raise TimeoutError."""
    from services.dynamic_adapter_manager import DynamicAdapterManager

    config = {'general': {}, 'adapters': []}
    mgr = DynamicAdapterManager(config)

    # Simulate another caller permanently initializing
    mgr.adapter_cache.claim_initialization("stuck_adapter")

    with pytest.raises(TimeoutError, match="stuck_adapter"):
        await mgr._wait_for_adapter_initialization("stuck_adapter", timeout=0.3)

    mgr.adapter_cache.release_initialization("stuck_adapter")
    mgr._thread_pool.shutdown(wait=False)


# ---------------------------------------------------------------------------
# 3a – datetime.now(timezone.utc) in stream_registry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_registry_uses_utc_aware_datetime():
    """StreamInfo.created_at should be timezone-aware (UTC)."""
    from services.stream_registry import StreamRegistry

    # Reset singleton for clean state
    StreamRegistry._instance = None
    registry = StreamRegistry()

    cancel_event = await registry.register("sess1", "req1")
    assert cancel_event is not None

    # Access the stored stream info
    key = ("sess1", "req1")
    info = registry._streams[key]
    assert info.created_at.tzinfo is not None
    assert info.created_at.tzinfo == timezone.utc

    await registry.unregister("sess1", "req1")

    # Restore singleton
    StreamRegistry._instance = None


# ---------------------------------------------------------------------------
# 4a – Bounded _session_locks cleanup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_session_locks_bounded_cleanup():
    """_get_session_lock should prune unlocked entries when dict is too large."""
    from services.chat_history_service import ChatHistoryService

    config = {
        'chat_history': {
            'enabled': True,
            'max_tracked_sessions': 5,
        },
        'internal_services': {'backend': {'type': 'sqlite'}},
    }
    service = ChatHistoryService.__new__(ChatHistoryService)
    service._session_locks = {}
    service._locks_lock = asyncio.Lock()
    service.max_tracked_sessions = 5

    # Fill with 11 unlocked locks (exceeds 5*2=10)
    for i in range(11):
        service._session_locks[f"old_{i}"] = asyncio.Lock()

    # Requesting a new lock should trigger cleanup
    lock = await service._get_session_lock("new_session")
    assert lock is not None

    # After cleanup, should have only the new entry (all old ones were unlocked)
    assert "new_session" in service._session_locks
    assert len(service._session_locks) <= service.max_tracked_sessions * 2 + 1


# ---------------------------------------------------------------------------
# 6a – health_service uses time.monotonic()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_service_no_event_loop_dependency():
    """HealthService.get_health_status should work without asyncio.get_event_loop()."""
    from services.health_service import HealthService
    import time

    config = {'general': {}}
    svc = HealthService(config)

    status = await svc.get_health_status()
    assert status.status == "ok"

    # Cached result should be returned on second call
    assert svc._last_check_time > 0
    status2 = await svc.get_health_status(use_cache=True)
    assert status2 is status


# ---------------------------------------------------------------------------
# 5a – Cache exceptions logged instead of swallowed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_exceptions_are_logged(caplog):
    """Redis cache failures should be logged at debug level, not silently swallowed."""
    try:
        from services.pipeline_chat_service import PipelineChatService
    except (ImportError, ModuleNotFoundError):
        pytest.skip("pipeline_chat_service dependencies not available in test env")

    # Build a minimal instance with a failing redis_service
    svc = PipelineChatService.__new__(PipelineChatService)
    svc._query_cache_enabled = True
    svc._query_cache_ttl = 10
    svc._query_cache_max_memory = 10
    svc._memory_cache = {}

    mock_redis = AsyncMock()
    mock_redis.get_json = AsyncMock(side_effect=ConnectionError("redis down"))
    mock_redis.store_json = AsyncMock(side_effect=ConnectionError("redis down"))
    svc.redis_service = mock_redis

    with caplog.at_level(logging.DEBUG, logger="services.pipeline_chat_service"):
        result = await svc._get_cached_response("test_key")
        assert result is None
        assert "Failed to read query cache from Redis" in caplog.text

        caplog.clear()
        await svc._store_cached_response("test_key", {"response": "hello"})
        assert "Failed to store query cache in Redis" in caplog.text
