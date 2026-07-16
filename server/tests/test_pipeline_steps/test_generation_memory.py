"""
Tests for the generation-memory helpers in inference/pipeline/steps/_utils.py.

Covers:
- Round trip through a REAL ThreadDatasetService (sqlite-backed) — proves the
  store_dataset -> get_dataset key transform lines up (regression test for a bug
  where get_generation_memory looked up the raw thread_id instead of the
  transformed dataset_key that store_dataset actually wrote under).
- Guard clauses: no session_id, no thread_dataset_service registered, disabled
  service, and exceptions from the underlying service are swallowed.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_asyncio import fixture

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SERVER_DIR))

from services.thread_dataset_service import ThreadDatasetService
from services.sqlite_service import SQLiteService
from inference.pipeline.steps._utils import get_generation_memory, store_generation_memory


def _make_container(thread_dataset_service):
    """Minimal ServiceContainer mock exposing only thread_dataset_service."""
    container = MagicMock()
    container.has.side_effect = lambda key: key == "thread_dataset_service" and thread_dataset_service is not None
    container.get.side_effect = lambda key: thread_dataset_service if key == "thread_dataset_service" else None
    return container


# ---------------------------------------------------------------------------
# Real ThreadDatasetService round trip (database-backed, no Redis required)
# ---------------------------------------------------------------------------

@fixture(scope="function")
async def real_dataset_service():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_orbit.db")

    config = {
        'internal_services': {'backend': {'type': 'sqlite', 'sqlite': {'database_path': db_path}}},
        'conversation_threading': {
            'enabled': True,
            'dataset_ttl_hours': 24,
            'storage_backend': 'database',  # exercise the DB key-formatting path
            'cache_key_prefix': 'thread_dataset:',
        },
    }

    sqlite_service = SQLiteService(config)
    await sqlite_service.initialize()

    service = ThreadDatasetService(config)
    await service.initialize()

    yield service

    sqlite_service.close()
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestGenerationMemoryRoundTrip:
    @pytest.mark.asyncio
    async def test_store_then_get_returns_same_memory(self, real_dataset_service):
        container = _make_container(real_dataset_service)

        await store_generation_memory(
            container, "image-generator", "session-1", {"prompt": "a fluffy dog in a forest"},
        )
        memory = await get_generation_memory(container, "image-generator", "session-1")

        assert memory == {"prompt": "a fluffy dog in a forest"}

    @pytest.mark.asyncio
    async def test_different_sessions_do_not_collide(self, real_dataset_service):
        container = _make_container(real_dataset_service)

        await store_generation_memory(container, "image-generator", "session-1", {"prompt": "prompt A"})
        await store_generation_memory(container, "image-generator", "session-2", {"prompt": "prompt B"})

        assert await get_generation_memory(container, "image-generator", "session-1") == {"prompt": "prompt A"}
        assert await get_generation_memory(container, "image-generator", "session-2") == {"prompt": "prompt B"}

    @pytest.mark.asyncio
    async def test_different_adapters_same_session_do_not_collide(self, real_dataset_service):
        container = _make_container(real_dataset_service)

        await store_generation_memory(container, "image-generator", "session-1", {"prompt": "image prompt"})
        await store_generation_memory(container, "video-generator", "session-1", {"prompt": "video prompt"})

        assert await get_generation_memory(container, "image-generator", "session-1") == {"prompt": "image prompt"}
        assert await get_generation_memory(container, "video-generator", "session-1") == {"prompt": "video prompt"}

    @pytest.mark.asyncio
    async def test_store_overwrites_previous_memory_for_same_session(self, real_dataset_service):
        container = _make_container(real_dataset_service)

        await store_generation_memory(container, "image-generator", "session-1", {"prompt": "first"})
        await store_generation_memory(container, "image-generator", "session-1", {"prompt": "second"})

        assert await get_generation_memory(container, "image-generator", "session-1") == {"prompt": "second"}

    @pytest.mark.asyncio
    async def test_get_returns_none_when_nothing_stored(self, real_dataset_service):
        container = _make_container(real_dataset_service)
        assert await get_generation_memory(container, "image-generator", "never-stored") is None


# ---------------------------------------------------------------------------
# Guard clauses
# ---------------------------------------------------------------------------

class TestGenerationMemoryGuards:
    @pytest.mark.asyncio
    async def test_get_returns_none_without_session_id(self):
        container = _make_container(MagicMock())
        assert await get_generation_memory(container, "image-generator", None) is None
        assert await get_generation_memory(container, "image-generator", "") is None

    @pytest.mark.asyncio
    async def test_get_returns_none_without_adapter_name(self):
        container = _make_container(MagicMock())
        assert await get_generation_memory(container, "", "session-1") is None

    @pytest.mark.asyncio
    async def test_get_returns_none_when_service_not_registered(self):
        container = _make_container(None)
        assert await get_generation_memory(container, "image-generator", "session-1") is None

    @pytest.mark.asyncio
    async def test_get_returns_none_when_service_disabled(self):
        disabled_service = MagicMock()
        disabled_service.enabled = False
        container = _make_container(disabled_service)
        assert await get_generation_memory(container, "image-generator", "session-1") is None

    @pytest.mark.asyncio
    async def test_get_swallows_exceptions_from_underlying_service(self):
        broken_service = MagicMock()
        broken_service.enabled = True
        broken_service._generate_dataset_key = MagicMock(side_effect=Exception("boom"))
        container = _make_container(broken_service)
        assert await get_generation_memory(container, "image-generator", "session-1") is None

    @pytest.mark.asyncio
    async def test_store_is_noop_without_session_id(self):
        service = MagicMock()
        service.enabled = True
        service.store_dataset = AsyncMock()
        container = _make_container(service)

        await store_generation_memory(container, "image-generator", None, {"prompt": "x"})

        service.store_dataset.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_store_is_noop_when_service_not_registered(self):
        container = _make_container(None)
        # Should not raise even though there's nowhere to store.
        await store_generation_memory(container, "image-generator", "session-1", {"prompt": "x"})

    @pytest.mark.asyncio
    async def test_store_swallows_exceptions_from_underlying_service(self):
        broken_service = MagicMock()
        broken_service.enabled = True
        broken_service.store_dataset = AsyncMock(side_effect=Exception("boom"))
        container = _make_container(broken_service)
        # Should not raise.
        await store_generation_memory(container, "image-generator", "session-1", {"prompt": "x"})
