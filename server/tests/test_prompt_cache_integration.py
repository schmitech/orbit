"""
Integration tests for PromptService Redis caching functionality.
Tests the complete cache flow including hits, misses, and invalidation.
"""

import pytest
import sys
import os
import asyncio
from bson import ObjectId
from unittest.mock import AsyncMock, MagicMock

# Add server directory to path
server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, server_dir)

from services.prompt_service import PromptService


class MockMongoDBService:
    """Mock MongoDB service for testing cache behavior"""

    def __init__(self):
        self.find_one_calls = 0
        self.update_one_calls = 0
        self.insert_one_calls = 0
        self.delete_one_calls = 0
        self.prompts = {}

    async def initialize(self):
        pass

    async def create_index(self, collection, field, unique=False):
        pass

    async def ensure_id_is_object_id(self, value):
        if isinstance(value, str):
            return ObjectId(value)
        return value

    async def find_one(self, collection, query):
        self.find_one_calls += 1
        prompt_id = query.get("_id")
        if prompt_id and str(prompt_id) in self.prompts:
            return self.prompts[str(prompt_id)]

        name = query.get("name")
        if name:
            for prompt in self.prompts.values():
                if prompt.get("name") == name:
                    return prompt
        return None

    async def insert_one(self, collection, document):
        self.insert_one_calls += 1
        prompt_id = ObjectId()
        document["_id"] = prompt_id
        self.prompts[str(prompt_id)] = document
        return prompt_id

    async def update_one(self, collection, query, update):
        self.update_one_calls += 1
        prompt_id = query.get("_id")
        if prompt_id and str(prompt_id) in self.prompts:
            if "$set" in update:
                self.prompts[str(prompt_id)].update(update["$set"])
            return True
        return False

    async def delete_one(self, collection, query):
        self.delete_one_calls += 1
        prompt_id = query.get("_id")
        if prompt_id and str(prompt_id) in self.prompts:
            del self.prompts[str(prompt_id)]
            return True
        return False


class MockRedisService:
    """Mock Redis service for testing cache behavior"""

    def __init__(self):
        self.storage = {}
        self.get_calls = 0
        self.set_calls = 0
        self.delete_calls = 0

    async def initialize(self):
        return True

    async def get(self, key):
        self.get_calls += 1
        return self.storage.get(key)

    async def set(self, key, value, ttl=None):
        self.set_calls += 1
        self.storage[key] = value
        return True

    async def delete(self, *keys):
        self.delete_calls += 1
        deleted = 0
        for key in keys:
            if key in self.storage:
                del self.storage[key]
                deleted += 1
        return deleted

    async def exists(self, key):
        return key in self.storage

    async def ttl(self, key):
        return 300 if key in self.storage else -2


@pytest.fixture
def mock_mongodb():
    """Fixture providing a mock MongoDB service"""
    return MockMongoDBService()


@pytest.fixture
def mock_redis():
    """Fixture providing a mock Redis service"""
    return MockRedisService()


@pytest.fixture
def prompt_service_config():
    """Fixture providing configuration for PromptService"""
    return {
        "general": {
            "verbose": True  # Enable verbose logging for testing
        },
        "mongodb": {
            "prompts_collection": "system_prompts"
        },
        "internal_services": {
            "redis": {
                "enabled": True,
                "ttl": 3600
            }
        },
        "prompt_service": {
            "cache": {
                "ttl_seconds": 300  # 5 minutes for testing
            }
        }
    }


@pytest.fixture
async def prompt_service(prompt_service_config, mock_mongodb, mock_redis):
    """Fixture providing an initialized PromptService with mocked dependencies"""
    service = PromptService(
        config=prompt_service_config,
        database_service=mock_mongodb,
        redis_service=mock_redis
    )
    await service.initialize()
    return service


@pytest.mark.asyncio
async def test_cache_miss_then_hit_flow(prompt_service, mock_mongodb, mock_redis):
    """Test the basic cache miss -> hit flow"""
    # Create a test prompt
    prompt_id = await prompt_service.create_prompt(
        name="test_cache_flow",
        prompt_text="This is a test prompt for cache flow testing.",
        version="1.0"
    )

    # Reset call counters after creation
    mock_mongodb.find_one_calls = 0
    mock_redis.get_calls = 0
    mock_redis.set_calls = 0

    # First fetch - should be cache miss, fetch from MongoDB, and cache result
    prompt1 = await prompt_service.get_prompt_by_id(prompt_id)
    assert prompt1 is not None
    assert prompt1["name"] == "test_cache_flow"
    assert prompt1["version"] == "1.0"
    assert mock_mongodb.find_one_calls == 1  # Hit MongoDB
    assert mock_redis.get_calls == 1  # Checked cache (miss)
    assert mock_redis.set_calls == 1  # Cached result

    # Second fetch - should be cache hit, no MongoDB access
    prompt2 = await prompt_service.get_prompt_by_id(prompt_id)
    assert prompt2 is not None
    assert prompt2["name"] == "test_cache_flow"
    assert prompt2["version"] == "1.0"
    assert mock_mongodb.find_one_calls == 1  # No additional MongoDB calls
    assert mock_redis.get_calls == 2  # Additional cache check
    assert mock_redis.set_calls == 1  # No additional cache writes

    # Third fetch - should still be cache hit
    prompt3 = await prompt_service.get_prompt_by_id(prompt_id)
    assert prompt3 is not None
    assert mock_mongodb.find_one_calls == 1  # Still no additional MongoDB calls
    assert mock_redis.get_calls == 3  # Another cache check


@pytest.mark.asyncio
async def test_cache_invalidation_on_update(prompt_service, mock_mongodb, mock_redis):
    """Test that cache is invalidated when prompt is updated"""
    # Create and cache a prompt
    prompt_id = await prompt_service.create_prompt(
        name="test_cache_invalidation",
        prompt_text="Original prompt text.",
        version="1.0"
    )

    # Fetch to populate cache
    await prompt_service.get_prompt_by_id(prompt_id)

    # Reset call counters
    mock_mongodb.find_one_calls = 0
    mock_redis.get_calls = 0
    mock_redis.set_calls = 0
    mock_redis.delete_calls = 0

    # Update the prompt - should invalidate cache
    success = await prompt_service.update_prompt(
        prompt_id,
        "Updated prompt text.",
        version="2.0"
    )
    assert success is True
    assert mock_redis.delete_calls == 1  # Cache was cleared

    # Reset counters after update (update itself made a MongoDB call)
    mock_mongodb.find_one_calls = 0

    # Fetch after update - should miss cache and fetch from MongoDB
    updated_prompt = await prompt_service.get_prompt_by_id(prompt_id)
    assert updated_prompt is not None
    assert updated_prompt["prompt"] == "Updated prompt text."
    assert updated_prompt["version"] == "2.0"
    assert mock_mongodb.find_one_calls == 1  # Had to fetch from MongoDB
    assert mock_redis.get_calls == 1  # Checked cache (miss)
    assert mock_redis.set_calls == 1  # Cached new result


@pytest.mark.asyncio
async def test_cache_invalidation_on_delete(prompt_service, mock_mongodb, mock_redis):
    """Test that cache is invalidated when prompt is deleted"""
    # Create and cache a prompt
    prompt_id = await prompt_service.create_prompt(
        name="test_cache_delete",
        prompt_text="Prompt to be deleted.",
        version="1.0"
    )

    # Fetch to populate cache
    await prompt_service.get_prompt_by_id(prompt_id)

    # Reset call counters
    mock_redis.delete_calls = 0

    # Delete the prompt - should invalidate cache
    success = await prompt_service.delete_prompt(prompt_id)
    assert success is True
    assert mock_redis.delete_calls == 1  # Cache was cleared


@pytest.mark.asyncio
async def test_manual_cache_clearing(prompt_service, mock_mongodb, mock_redis):
    """Test manual cache clearing functionality"""
    # Create and cache a prompt
    prompt_id = await prompt_service.create_prompt(
        name="test_manual_clear",
        prompt_text="Prompt for manual clearing test.",
        version="1.0"
    )

    # Fetch to populate cache
    await prompt_service.get_prompt_by_id(prompt_id)

    # Verify cache is populated
    cache_key = f"prompt:{prompt_id}"
    assert cache_key in mock_redis.storage

    # Clear cache manually
    cleared = await prompt_service.clear_prompt_cache(prompt_id)
    assert cleared is True
    assert cache_key not in mock_redis.storage


@pytest.mark.asyncio
async def test_cache_stats(prompt_service, mock_mongodb, mock_redis):
    """Test cache statistics functionality"""
    # Create a prompt
    prompt_id = await prompt_service.create_prompt(
        name="test_cache_stats",
        prompt_text="Prompt for cache stats testing.",
        version="1.0"
    )

    # Check stats before caching
    stats = await prompt_service.get_cache_stats(prompt_id)
    assert stats["redis_enabled"] is True
    assert stats["cache_ttl"] == 300
    assert stats["is_cached"] is False

    # Fetch to populate cache
    await prompt_service.get_prompt_by_id(prompt_id)

    # Check stats after caching
    stats = await prompt_service.get_cache_stats(prompt_id)
    assert stats["is_cached"] is True
    assert "cache_size_bytes" in stats
    assert stats["cached_prompt_name"] == "test_cache_stats"
    assert stats["cached_prompt_version"] == "1.0"


@pytest.mark.asyncio
async def test_cache_with_string_id(prompt_service, mock_mongodb, mock_redis):
    """Test that caching works when using string prompt IDs"""
    # Create a prompt
    prompt_id = await prompt_service.create_prompt(
        name="test_string_id",
        prompt_text="Prompt for string ID testing.",
        version="1.0"
    )

    # Reset call counters
    mock_mongodb.find_one_calls = 0
    mock_redis.get_calls = 0
    mock_redis.set_calls = 0

    # Fetch using string ID - should work and cache properly
    prompt1 = await prompt_service.get_prompt_by_id(str(prompt_id))
    assert prompt1 is not None
    assert mock_mongodb.find_one_calls == 1
    assert mock_redis.get_calls == 1
    assert mock_redis.set_calls == 1

    # Fetch again with string ID - should hit cache
    prompt2 = await prompt_service.get_prompt_by_id(str(prompt_id))
    assert prompt2 is not None
    assert mock_mongodb.find_one_calls == 1  # No additional MongoDB calls
    assert mock_redis.get_calls == 2  # Additional cache check


@pytest.mark.asyncio
async def test_cache_disabled_scenario(prompt_service_config, mock_mongodb):
    """Test that service works correctly when Redis is disabled"""
    # Create service without Redis
    service = PromptService(
        config=prompt_service_config,
        database_service=mock_mongodb,
        redis_service=None
    )
    await service.initialize()

    # Create a prompt
    prompt_id = await service.create_prompt(
        name="test_no_redis",
        prompt_text="Prompt without Redis caching.",
        version="1.0"
    )

    # Reset call counters
    mock_mongodb.find_one_calls = 0

    # Fetch prompt multiple times - should hit MongoDB each time
    await service.get_prompt_by_id(prompt_id)
    await service.get_prompt_by_id(prompt_id)
    await service.get_prompt_by_id(prompt_id)

    # Should have made 3 MongoDB calls (no caching)
    assert mock_mongodb.find_one_calls == 3

    # Cache stats should indicate Redis is disabled
    stats = await service.get_cache_stats(prompt_id)
    assert stats["redis_enabled"] is False


if __name__ == "__main__":
    # Allow running this test file directly
    pytest.main([__file__, "-v"])