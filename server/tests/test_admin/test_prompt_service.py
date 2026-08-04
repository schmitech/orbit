"""
Tests for PromptService datetime handling across cache round-trips.

Regression coverage for: updating a system prompt (PUT /admin/prompts/{id})
raising "'str' object has no attribute 'timestamp'" in admin_routes.py, which
calls `.timestamp()` on `created_at`/`updated_at` assuming they are always
datetime objects. This only reproduces when a cache service (Redis) is
enabled in front of the database, which is the case for MongoDB-backed
deployments but not the local SQLite default.
"""

import asyncio
import sys
import os
from datetime import datetime, UTC

import pytest

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, server_dir)

from services.prompt_service import PromptService
from routes.admin._shared import _serialize_created_at


class FakeMongoService:
    """Minimal in-memory stand-in for the Mongo-backed DatabaseService."""

    def __init__(self):
        self.docs = {}
        self.find_one_calls = 0

    async def initialize(self):
        return None

    async def create_index(self, *args, **kwargs):
        return None

    async def find_one(self, collection, query):
        self.find_one_calls += 1
        doc_id = query.get("_id")
        if doc_id is not None:
            return self.docs.get(str(doc_id))
        name = query.get("name")
        for doc in self.docs.values():
            if doc.get("name") == name:
                return doc
        return None

    async def insert_one(self, collection, document):
        doc_id = document.get("_id") or f"id-{len(self.docs) + 1}"
        document = dict(document)
        document["_id"] = doc_id
        self.docs[str(doc_id)] = document
        return doc_id

    async def update_one(self, collection, query, update):
        doc_id = query.get("_id")
        doc = self.docs.get(str(doc_id))
        if not doc:
            return False
        doc.update(update.get("$set", {}))
        return True


class FakeRedisService:
    """In-memory cache stand-in that mimics the real Redis provider's contract:
    values are plain strings, and set_if_not_exists actually enforces exclusivity."""

    def __init__(self):
        self.storage = {}

    async def initialize(self):
        return True

    async def get(self, key):
        return self.storage.get(key)

    async def set(self, key, value, ttl=None):
        self.storage[key] = value
        return True

    async def delete(self, key):
        existed = key in self.storage
        self.storage.pop(key, None)
        return 1 if existed else 0

    async def set_if_not_exists(self, key, value, ttl=None):
        if key in self.storage:
            return False
        self.storage[key] = value
        return True


def _make_service(mongo=None, redis=None):
    return PromptService(
        config={
            "prompt_service": {"cache": {"ttl_seconds": 60}},
            "internal_services": {
                "backend": {"type": "mongodb"},
                "mongodb": {"prompts_collection": "system_prompts"},
            },
            "general": {},
        },
        database_service=mongo or FakeMongoService(),
        cache_service=redis or FakeRedisService(),
    )


@pytest.mark.asyncio
async def test_get_prompt_by_id_returns_datetime_after_cache_hit():
    """Normal cache-hit path: created_at/updated_at must come back as datetime,
    not the ISO string they're serialized to for cache storage."""
    mongo = FakeMongoService()
    service = _make_service(mongo=mongo)
    await service.initialize()

    prompt_id = await service.create_prompt("persona-a", "You are helpful.", "1.0")

    # First call: cache miss, populates cache
    first = await service.get_prompt_by_id(prompt_id)
    assert isinstance(first["created_at"], datetime)
    assert isinstance(first["updated_at"], datetime)

    # Second call: cache hit, must still be datetime (not the raw ISO string)
    second = await service.get_prompt_by_id(prompt_id)
    assert isinstance(second["created_at"], datetime), (
        f"expected datetime from cache hit, got {type(second['created_at'])}"
    )
    assert isinstance(second["updated_at"], datetime)

    # .timestamp() must not raise, mirroring admin_routes.py usage
    second["created_at"].timestamp()
    second["updated_at"].timestamp()


@pytest.mark.asyncio
async def test_update_prompt_then_get_returns_datetime():
    """Reproduces the reported flow: update via the admin panel, then fetch the
    updated prompt the same way admin_routes.update_prompt does, and confirm
    the timestamps are still real datetimes end-to-end."""
    mongo = FakeMongoService()
    service = _make_service(mongo=mongo)
    await service.initialize()

    prompt_id = await service.create_prompt("persona-b", "Original prompt", "1.0")
    # Warm the cache the same way a prior GET from the admin UI would.
    await service.get_prompt_by_id(prompt_id)

    success = await service.update_prompt(prompt_id, "Updated prompt text", None)
    assert success is True

    updated = await service.get_prompt_by_id(prompt_id)
    assert updated is not None
    assert updated["prompt"] == "Updated prompt text"
    assert isinstance(updated["created_at"], datetime), (
        f"created_at should be datetime, got {type(updated['created_at'])}: {updated['created_at']!r}"
    )
    assert isinstance(updated["updated_at"], datetime), (
        f"updated_at should be datetime, got {type(updated['updated_at'])}: {updated['updated_at']!r}"
    )
    updated["created_at"].timestamp()
    updated["updated_at"].timestamp()


@pytest.mark.asyncio
async def test_get_prompt_by_id_stampede_lock_branch_returns_datetime():
    """When another request already holds the rebuild lock, the fallback branch
    that re-reads from cache must also convert ISO strings back to datetime."""
    mongo = FakeMongoService()
    redis = FakeRedisService()
    service = _make_service(mongo=mongo, redis=redis)
    await service.initialize()

    prompt_id = await service.create_prompt("persona-c", "Prompt text", "1.0")
    # Populate the cache first so there is something to re-read.
    await service.get_prompt_by_id(prompt_id)

    # Simulate a concurrent request already holding the rebuild lock.
    cache_key = service._get_cache_key(str(prompt_id))
    lock_key = f"lock:{cache_key}"
    redis.storage[lock_key] = "1"

    result = await service.get_prompt_by_id(prompt_id)
    assert result is not None
    assert isinstance(result["created_at"], datetime), (
        f"expected datetime from stampede-lock fallback, got {type(result['created_at'])}"
    )
    assert isinstance(result["updated_at"], datetime)
    result["created_at"].timestamp()
    result["updated_at"].timestamp()


def test_serialize_created_at_handles_datetime():
    now = datetime.now(UTC)
    assert _serialize_created_at(now) == now.timestamp()


def test_serialize_created_at_handles_iso_string():
    """Covers legacy/stale documents where created_at was persisted as a plain
    ISO string (e.g. a doc written before caching was introduced, or a stampede
    fallback that skipped datetime reconversion). admin_routes.py must not
    blindly call `.timestamp()` on this without going through this helper."""
    now = datetime.now(UTC)
    iso_string = now.isoformat()
    assert _serialize_created_at(iso_string) == pytest.approx(now.timestamp())


def test_serialize_created_at_handles_none():
    assert _serialize_created_at(None) is None
