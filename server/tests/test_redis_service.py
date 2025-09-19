import asyncio
import json
import os
import sys
import pytest
from pathlib import Path
from dotenv import load_dotenv
from pytest_asyncio import fixture

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Get the project root (parent of server directory)
PROJECT_ROOT = SCRIPT_DIR.parent.parent

# Add server directory to Python path
SERVER_DIR = SCRIPT_DIR.parent
sys.path.append(str(SERVER_DIR))

from services.redis_service import RedisService

# Load environment variables from .env file in project root
env_path = PROJECT_ROOT / '.env'
if not env_path.exists():
    raise FileNotFoundError(f".env file not found at {env_path}")

load_dotenv(env_path)

@fixture(scope="function")
async def redis_service():
    """Fixture to create and cleanup Redis service"""
    # Clear any existing Redis service instances to avoid singleton issues
    RedisService.clear_cache()
    
    # Get raw environment variables
    redis_host = os.getenv("INTERNAL_SERVICES_REDIS_HOST")
    redis_port = int(os.getenv("INTERNAL_SERVICES_REDIS_PORT", 6379))
    redis_username = os.getenv("INTERNAL_SERVICES_REDIS_USERNAME")
    redis_password = os.getenv("INTERNAL_SERVICES_REDIS_PASSWORD")
    
    # Clean host if it includes port
    if redis_host and ':' in redis_host:
        redis_host = redis_host.split(':')[0]
    
    # Create Redis configuration
    redis_config = {
        'internal_services': {
            'redis': {
                'enabled': True,
                'host': redis_host,
                'port': redis_port,
                'username': redis_username,
                'password': redis_password,
                'db': 0,
                'use_ssl': False  # Redis Cloud works without SSL
            }
        },
        'general': {
            'verbose': False  # Turn off verbose logging for tests
        }
    }

    # Validate required environment variables
    required_vars = ["INTERNAL_SERVICES_REDIS_HOST", "INTERNAL_SERVICES_REDIS_PASSWORD"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        pytest.skip(f"Missing required environment variables: {', '.join(missing_vars)}")

    # Initialize Redis service
    service = RedisService(redis_config)
    
    try:
        connected = await service.initialize()
        if not connected:
            pytest.skip("Failed to connect to Redis. Please check your configuration.")
    except Exception as e:
        pytest.skip(f"Failed to connect to Redis: {e}")

    # Yield the service for use in tests
    yield service
    
    # Cleanup after tests
    await service.aclose()
    # Clear cache again after cleanup to ensure clean state for next test
    RedisService.clear_cache()

@pytest.mark.asyncio
async def test_basic_operations(redis_service: RedisService):
    """Test basic key-value operations"""
    # Test set
    key = "test:mykey"
    value = "Hello, Redis Service!"
    success = await redis_service.set(key, value)
    assert success, "Failed to set key"
    
    # Test get
    retrieved = await redis_service.get(key)
    assert retrieved == value, f"Expected {value}, got {retrieved}"
    
    # Cleanup
    await redis_service.delete(key)

@pytest.mark.asyncio
async def test_json_operations(redis_service: RedisService):
    """Test JSON operations"""
    key = "test:user:101"
    data = {
        "name": "Test User",
        "email": "test@example.com",
        "source": "redis_service_test"
    }
    
    # Test store_json
    success = await redis_service.store_json(key, data)
    assert success, "Failed to store JSON"
    
    # Test get_json
    retrieved = await redis_service.get_json(key)
    assert retrieved == data, f"Expected {data}, got {retrieved}"
    
    # Cleanup
    await redis_service.delete(key)

@pytest.mark.asyncio
async def test_list_operations(redis_service: RedisService):
    """Test list operations"""
    key = "test:my_list"
    
    # Clean up any existing list
    await redis_service.delete(key)
    
    # Test rpush
    success = await redis_service.rpush(key, "item1", "item2")
    assert success, "Failed to push items to list"
    
    # Test lrange
    items = await redis_service.lrange(key, 0, -1)
    assert items == ["item1", "item2"], f"Expected ['item1', 'item2'], got {items}"
    
    # Cleanup
    await redis_service.delete(key)

@pytest.mark.asyncio
async def test_list_json_operations(redis_service: RedisService):
    """Test list JSON operations"""
    key = "test:json_list"
    data_list = [
        {"id": 1, "name": "Item 1"},
        {"id": 2, "name": "Item 2"}
    ]
    
    # Clean up any existing list
    await redis_service.delete(key)
    
    # Test store_list_json
    success = await redis_service.store_list_json(key, data_list)
    assert success, "Failed to store JSON list"
    
    # Test get_list_json
    retrieved = await redis_service.get_list_json(key)
    assert retrieved == data_list, f"Expected {data_list}, got {retrieved}"
    
    # Cleanup
    await redis_service.delete(key)

@pytest.mark.asyncio
async def test_expiration(redis_service: RedisService):
    """Test key expiration"""
    key = "test:expiring_key"
    value = "This will expire"
    
    # Set key with short expiration
    success = await redis_service.set(key, value)
    assert success, "Failed to set key"
    
    # Set expiration
    success = await redis_service.expire(key, 1)
    assert success, "Failed to set expiration"
    
    # Wait for expiration
    await asyncio.sleep(2)
    
    # Check if key exists
    exists = await redis_service.exists(key)
    assert not exists, "Key should have expired"

@pytest.mark.asyncio
async def test_cleanup(redis_service: RedisService):
    """Test cleanup operations"""
    # Create some test keys
    keys = ["test:key1", "test:key2", "test:key3"]
    for key in keys:
        await redis_service.set(key, "test_value")
    
    # Delete keys
    deleted = await redis_service.delete(*keys)
    assert deleted == len(keys), f"Expected to delete {len(keys)} keys, deleted {deleted}"
    
    # Verify keys are gone
    for key in keys:
        exists = await redis_service.exists(key)
        assert not exists, f"Key {key} should have been deleted"