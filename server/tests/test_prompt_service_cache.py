import asyncio
from bson import ObjectId
import pytest

from services.prompt_service import PromptService


class FakeMongoService:
    def __init__(self, prompt_doc):
        self.prompt_doc = prompt_doc
        self.find_one_calls = 0

    async def initialize(self):
        return None

    async def create_index(self, *args, **kwargs):
        return None

    async def ensure_id_is_object_id(self, value):
        return ObjectId(value)

    async def find_one(self, collection, query):
        self.find_one_calls += 1
        return self.prompt_doc


class FakeRedisService:
    def __init__(self):
        self.storage = {}
        self.initialized = False

    async def initialize(self):
        self.initialized = True
        return True

    async def get(self, key):
        return self.storage.get(key)

    async def set(self, key, value, ttl=None):
        self.storage[key] = value
        return True


@pytest.mark.asyncio
async def test_prompt_service_caches_prompts_by_id():
    prompt_id = ObjectId()
    prompt_doc = {"_id": prompt_id, "prompt": "system instruction"}
    fake_mongo = FakeMongoService(prompt_doc)
    fake_redis = FakeRedisService()

    service = PromptService(
        config={
            "prompt_service": {"cache": {"ttl_seconds": 60}},
            "internal_services": {"redis": {"enabled": True}},
            "mongodb": {"prompts_collection": "system_prompts"},
            "general": {"verbose": False},
        },
        mongodb_service=fake_mongo,
        redis_service=fake_redis,
    )

    await service.initialize()

    first = await service.get_prompt_by_id(str(prompt_id))
    second = await service.get_prompt_by_id(str(prompt_id))

    assert first == prompt_doc
    assert second == prompt_doc
    assert fake_mongo.find_one_calls == 1
