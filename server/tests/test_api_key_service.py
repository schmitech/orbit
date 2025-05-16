import pytest
import pytest_asyncio
import asyncio
import sys
import os
from datetime import datetime, UTC
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file in project root
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env')
if os.path.exists(env_path):
    logger.info(f"Loading environment variables from: {env_path}")
    load_dotenv(env_path)
else:
    logger.warning(f".env file not found at expected path: {env_path}")

# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure pytest-asyncio
pytestmark = pytest.mark.asyncio

# Import services (with error handling)
try:
    from services.api_key_service import ApiKeyService
    from services.prompt_service import PromptService
    from services.mongodb_service import MongoDBService
    from models.schema import ApiKeyCreate, SystemPromptCreate, SystemPromptUpdate, ApiKeyPromptAssociate
except ImportError as e:
    logger.error(f"Import error: {e}")
    raise

# Test configuration
TEST_CONFIG = {
    'internal_services': {
        'mongodb': {
            'host': 'orbit.yp0onu1.mongodb.net',
            'port': 27017,
            'database': 'orbit_test',
            'apikey_collection': 'api_keys_test',
            'username': 'orbit',
            'password': 'mongodb-password'
        }
    },
    'general': {
        'verbose': True
    }
}

# Helper function to check MongoDB connection
async def check_mongodb_connection(config):
    """Check if MongoDB connection is possible with the given config"""
    try:
        logger.info(f"Checking MongoDB connection to: {config['internal_services']['mongodb']['host']}")
        logger.info(f"Using database: {config['internal_services']['mongodb']['database']}")
        # Log username (partially masked for security)
        username = config['internal_services']['mongodb']['username']
        if username:
            masked_username = username[:2] + '*' * (len(username) - 2) if len(username) > 2 else '*****'
            logger.info(f"Using username: {masked_username}")
        else:
            logger.warning("MongoDB username is not set")
            
        # Check if password is provided (don't log the password)
        if not config['internal_services']['mongodb']['password']:
            logger.warning("MongoDB password is not set")
            
        service = MongoDBService(config)
        await service.initialize()
        # Try a simple command to verify connection
        result = await service.client.admin.command('ping')
        logger.info("MongoDB connection successful")
        await service.client.close()
        return True
    except Exception as e:
        logger.error(f"MongoDB connection error: {e}")
        return False

# Use a module-scoped event_loop_policy fixture to avoid deprecation warning
@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.get_event_loop_policy()

# Use the loop_scope argument in the asyncio mark instead of redefining event_loop fixture
@pytest_asyncio.fixture
async def mongodb_service():
    """Fixture to provide a MongoDB service instance"""
    try:
        service = MongoDBService(TEST_CONFIG)
        await service.initialize()
        logger.info("Successfully connected to MongoDB")
        yield service
        # Cleanup after tests
        await service.client.drop_database(TEST_CONFIG['internal_services']['mongodb']['database'])
        # Explicitly close the connection when done
        service.close()
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {str(e)}")
        raise

@pytest_asyncio.fixture
async def api_key_service(mongodb_service):
    """Fixture to provide an API key service instance"""
    service = ApiKeyService(TEST_CONFIG, mongodb_service)
    await service.initialize()
    
    # Set collection name from config to ensure consistent use
    service.collection_name = TEST_CONFIG['internal_services']['mongodb']['apikey_collection']
    
    return service

@pytest_asyncio.fixture
async def prompt_service(mongodb_service):
    """Fixture to provide a prompt service instance"""
    service = PromptService(TEST_CONFIG, mongodb_service)
    await service.initialize()
    
    # Ensure prompt collection is set correctly
    service.collection_name = 'system_prompts'
    
    return service

@pytest_asyncio.fixture
async def app(api_key_service, prompt_service):
    """Fixture to provide a FastAPI test application"""
    app = FastAPI()
    app.state.api_key_service = api_key_service
    app.state.prompt_service = prompt_service
    return app

@pytest_asyncio.fixture
async def client(app):
    """Fixture to provide a test client"""
    return TestClient(app)

# Helper to ensure ObjectId conversion is handled properly
def ensure_object_id(id_value):
    """Convert string ID to ObjectId if needed"""
    if isinstance(id_value, str):
        return ObjectId(id_value)
    return id_value

# API Key Tests
@pytest.mark.asyncio
async def test_create_api_key(api_key_service):
    """Test API key creation"""
    # Create API key
    api_key_data = ApiKeyCreate(
        collection_name="test_collection",
        client_name="test_client",
        notes="Test API key"
    )
    
    result = await api_key_service.create_api_key(
        api_key_data.collection_name,
        api_key_data.client_name,
        api_key_data.notes
    )
    
    assert result is not None
    assert "api_key" in result
    assert result["collection_name"] == "test_collection"
    assert result["client_name"] == "test_client"
    assert result["notes"] == "Test API key"
    assert result["active"] is True

@pytest.mark.asyncio
async def test_list_api_keys(api_key_service):
    """Test listing API keys"""
    # Create multiple API keys
    for i in range(3):
        await api_key_service.create_api_key(
            f"collection_{i}",
            f"client_{i}",
            f"Test key {i}"
        )
    
    # List API keys - use the correct collection name
    collection = api_key_service.mongodb.database[api_key_service.collection_name]
    cursor = collection.find({})
    api_keys = await cursor.to_list(length=100)
    
    # There should be at least 3 keys (plus the one from the previous test)
    assert len(api_keys) >= 3
    for key in api_keys:
        assert "api_key" in key
        assert "collection_name" in key
        assert "client_name" in key
        assert "active" in key

@pytest.mark.asyncio
async def test_get_api_key_status(api_key_service):
    """Test getting API key status"""
    # Create an API key
    result = await api_key_service.create_api_key(
        "test_collection",
        "test_client",
        "Test API key"
    )
    
    api_key = result["api_key"]
    
    # Get status
    status = await api_key_service.get_api_key_status(api_key)
    
    assert status is not None
    assert status.get("active") is True
    assert status.get("collection", status.get("collection_name")) == "test_collection"
    assert status.get("client_name") == "test_client"

@pytest.mark.asyncio
async def test_deactivate_api_key(api_key_service):
    """Test deactivating an API key"""
    # Create an API key
    result = await api_key_service.create_api_key(
        "test_collection",
        "test_client",
        "Test API key"
    )
    
    api_key = result["api_key"]
    
    # Deactivate the key
    success = await api_key_service.deactivate_api_key(api_key)
    assert success is True
    
    # Verify status
    status = await api_key_service.get_api_key_status(api_key)
    assert status.get("active") is False

@pytest.mark.asyncio
async def test_delete_api_key(api_key_service):
    """Test deleting an API key"""
    # Create an API key
    result = await api_key_service.create_api_key(
        "test_collection",
        "test_client",
        "Test API key"
    )
    
    api_key = result["api_key"]
    
    # Delete the key
    success = await api_key_service.delete_api_key(api_key)
    assert success is True
    
    # Verify deletion
    status = await api_key_service.get_api_key_status(api_key)
    assert status is None or status.get("exists") is False

# System Prompt Tests
@pytest.mark.asyncio
async def test_create_prompt(prompt_service):
    """Test creating a system prompt"""
    # Create a prompt
    prompt_id = await prompt_service.create_prompt(
        "Test Prompt",
        "This is a test system prompt",
        "1.0"
    )
    
    assert prompt_id is not None
    
    # Verify prompt was created
    prompt = await prompt_service.get_prompt_by_id(prompt_id)
    assert prompt is not None
    assert prompt["name"] == "Test Prompt"
    assert prompt["prompt"] == "This is a test system prompt"
    assert prompt["version"] == "1.0"

@pytest.mark.asyncio
async def test_list_prompts(prompt_service):
    """Test listing system prompts"""
    # Create multiple prompts
    for i in range(3):
        await prompt_service.create_prompt(
            f"Test Prompt {i}",
            f"This is test prompt {i}",
            "1.0"
        )
    
    # List prompts
    prompts = await prompt_service.list_prompts()
    
    assert len(prompts) >= 3
    for prompt in prompts:
        assert "name" in prompt
        assert "prompt" in prompt
        assert "version" in prompt

@pytest.mark.asyncio
async def test_get_prompt(prompt_service):
    """Test getting a specific prompt"""
    # Create a prompt
    prompt_id = await prompt_service.create_prompt(
        "Test Prompt",
        "This is a test system prompt",
        "1.0"
    )
    
    # Get the prompt
    prompt = await prompt_service.get_prompt_by_id(prompt_id)
    
    assert prompt is not None
    assert prompt["name"] == "Test Prompt"
    assert prompt["prompt"] == "This is a test system prompt"
    assert prompt["version"] == "1.0"

@pytest.mark.asyncio
async def test_update_prompt(prompt_service):
    """Test updating a system prompt"""
    # Create a prompt
    prompt_id = await prompt_service.create_prompt(
        "Test Prompt for Update",
        "This is a test system prompt",
        "1.0"
    )
    
    # Update the prompt - ensure prompt_id is in the correct format
    prompt_id_obj = ensure_object_id(prompt_id)
    success = await prompt_service.update_prompt(
        prompt_id_obj,
        "This is an updated test system prompt",
        "1.1"
    )
    
    assert success is True
    
    # Verify update
    prompt = await prompt_service.get_prompt_by_id(prompt_id)
    assert prompt["prompt"] == "This is an updated test system prompt"
    assert prompt["version"] == "1.1"

@pytest.mark.asyncio
async def test_delete_prompt(prompt_service):
    """Test deleting a system prompt"""
    # Create a prompt
    prompt_id = await prompt_service.create_prompt(
        "Test Prompt for Deletion",
        "This is a test system prompt",
        "1.0"
    )
    
    # Delete the prompt - ensure prompt_id is in the correct format
    prompt_id_obj = ensure_object_id(prompt_id)
    success = await prompt_service.delete_prompt(prompt_id_obj)
    assert success is True
    
    # Verify deletion
    prompt = await prompt_service.get_prompt_by_id(prompt_id)
    assert prompt is None

# API Key + Prompt Association Tests
@pytest.mark.asyncio
async def test_associate_prompt_with_api_key(api_key_service, prompt_service):
    """Test associating a prompt with an API key"""
    # Create a prompt
    prompt_id = await prompt_service.create_prompt(
        "Test Prompt for Association",
        "This is a test system prompt",
        "1.0"
    )
    
    # Create an API key
    result = await api_key_service.create_api_key(
        "test_collection",
        "test_client",
        "Test API key"
    )
    
    api_key = result["api_key"]
    
    # Associate prompt with API key - ensure prompt_id is in the correct format
    prompt_id_obj = ensure_object_id(prompt_id)
    success = await api_key_service.update_api_key_system_prompt(api_key, prompt_id_obj)
    assert success is True
    
    # Verify association
    status = await api_key_service.get_api_key_status(api_key)
    # The comparison needs to handle potential string vs ObjectId differences
    stored_prompt_id = status.get("system_prompt", {}).get("id") if isinstance(status.get("system_prompt"), dict) else status.get("system_prompt_id")
    
    if stored_prompt_id:
        # Convert both to string for comparison
        assert str(stored_prompt_id) == str(prompt_id)
    else:
        pytest.fail("Prompt ID not found in API key status")

@pytest.mark.asyncio
async def test_get_collection_for_api_key(api_key_service, prompt_service):
    """Test getting collection and prompt ID for an API key"""
    # Create a prompt
    prompt_id = await prompt_service.create_prompt(
        "Test Prompt for Collection",
        "This is a test system prompt",
        "1.0"
    )
    
    # Create an API key
    result = await api_key_service.create_api_key(
        "test_collection_special",
        "test_client",
        "Test API key"
    )
    
    api_key = result["api_key"]
    
    # Associate prompt with API key
    prompt_id_obj = ensure_object_id(prompt_id)
    await api_key_service.update_api_key_system_prompt(api_key, prompt_id_obj)
    
    # Get collection and prompt ID
    collection_name, system_prompt_id = await api_key_service.get_collection_for_api_key(api_key)
    
    assert collection_name == "test_collection_special"
    if system_prompt_id:
        # Convert both to string for comparison
        assert str(system_prompt_id) == str(prompt_id)
    else:
        pytest.fail("System prompt ID not returned from get_collection_for_api_key")

# Error Cases
@pytest.mark.asyncio
async def test_invalid_api_key(api_key_service):
    """Test handling of invalid API key"""
    # Try to get status of non-existent API key
    status = await api_key_service.get_api_key_status("invalid_key")
    assert status is None or status.get("exists") is False
    
    # Try to deactivate non-existent API key
    success = await api_key_service.deactivate_api_key("invalid_key")
    assert success is False
    
    # Try to delete non-existent API key
    success = await api_key_service.delete_api_key("invalid_key")
    assert success is False

@pytest.mark.asyncio
async def test_invalid_prompt_id(prompt_service):
    """Test handling of invalid prompt ID"""
    # Try to get non-existent prompt
    invalid_id = str(ObjectId())  # Generate a valid but non-existent ObjectId
    prompt = await prompt_service.get_prompt_by_id(invalid_id)
    assert prompt is None
    
    # Try to update non-existent prompt
    success = await prompt_service.update_prompt(
        invalid_id,
        "Updated prompt",
        "1.1"
    )
    assert success is False
    
    # Try to delete non-existent prompt
    success = await prompt_service.delete_prompt(invalid_id)
    assert success is False

@pytest.mark.asyncio
async def test_invalid_prompt_association(api_key_service, prompt_service):
    """Test handling of invalid prompt association"""
    # Create an API key
    result = await api_key_service.create_api_key(
        "test_collection",
        "test_client",
        "Test API key"
    )
    
    api_key = result["api_key"]
    
    # Try to associate non-existent prompt
    invalid_id = str(ObjectId())  # Generate a valid but non-existent ObjectId
    success = await api_key_service.update_api_key_system_prompt(api_key, invalid_id)
    assert success is False

@pytest.mark.asyncio
async def test_create_api_key_with_string_prompt_id(api_key_service, prompt_service):
    """Test creating an API key with a string system prompt ID"""
    # Create a prompt first
    prompt_id = await prompt_service.create_prompt(
        "Test Prompt for String ID",
        "This is a test system prompt",
        "1.0"
    )
    
    # Convert ObjectId to string
    string_prompt_id = str(prompt_id)
    
    # Create API key with string prompt ID
    result = await api_key_service.create_api_key(
        "test_collection",
        "test_client",
        "Test API key",
        system_prompt_id=string_prompt_id
    )
    
    assert result is not None
    assert "api_key" in result
    assert result["collection_name"] == "test_collection"
    assert result["client_name"] == "test_client"
    assert result["system_prompt_id"] == string_prompt_id
    
    # Verify the association in the database
    status = await api_key_service.get_api_key_status(result["api_key"])
    assert status.get("system_prompt", {}).get("id") == string_prompt_id
