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
from pathlib import Path
from dotenv import load_dotenv

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Get the project root (parent of server directory)
PROJECT_ROOT = SCRIPT_DIR.parent.parent

# Add server directory to Python path
SERVER_DIR = SCRIPT_DIR.parent
sys.path.append(str(SERVER_DIR))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file in project root
env_path = PROJECT_ROOT / '.env'
if not env_path.exists():
    raise FileNotFoundError(f".env file not found at {env_path}")

load_dotenv(env_path)

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
    'general': {
        'verbose': True
    },
    'adapters': [
        {
            'name': 'qa-sql',
            'type': 'retriever',
            'datasource': 'sqlite',
            'adapter': 'qa',
            'implementation': 'retrievers.implementations.qa.QASQLRetriever'
        },
        {
            'name': 'qa-vector-chroma',
            'type': 'retriever',
            'datasource': 'chroma',
            'adapter': 'qa',
            'implementation': 'retrievers.implementations.qa.QAChromaRetriever'
        },
        {
            'name': 'file-vector',
            'type': 'retriever',
            'datasource': 'chroma',
            'adapter': 'file',
            'implementation': 'retrievers.implementations.file.FileChromaRetriever'
        }
    ],
    'api_keys': {
        'prefix': 'test_',
        'allow_default': True
    },
    'internal_services': {
        'mongodb': {
            'host': os.getenv("INTERNAL_SERVICES_MONGODB_HOST"),
            'port': int(os.getenv("INTERNAL_SERVICES_MONGODB_PORT", 27017)),
            'database': os.getenv("INTERNAL_SERVICES_MONGODB_DATABASE", "orbit_test"),
            'apikey_collection': 'api_keys_test',
            'username': os.getenv("INTERNAL_SERVICES_MONGODB_USERNAME"),
            'password': os.getenv("INTERNAL_SERVICES_MONGODB_PASSWORD")
        }
    }
}

# Validate required environment variables
required_vars = ["INTERNAL_SERVICES_MONGODB_HOST", "INTERNAL_SERVICES_MONGODB_USERNAME", 
                 "INTERNAL_SERVICES_MONGODB_PASSWORD"]
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    pytest.skip(f"Missing required environment variables: {', '.join(missing_vars)}")

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
    service = ApiKeyService(TEST_CONFIG, database_service=mongodb_service)
    await service.initialize()

    # Set collection name from config to ensure consistent use
    service.collection_name = TEST_CONFIG['internal_services']['mongodb']['apikey_collection']

    return service

@pytest_asyncio.fixture
async def prompt_service(mongodb_service):
    """Fixture to provide a prompt service instance"""
    service = PromptService(TEST_CONFIG, database_service=mongodb_service)
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
    # Create API key with adapter_name
    result = await api_key_service.create_api_key(
        client_name="test_client",
        adapter_name="qa-sql",
        notes="Test API key"
    )
    
    assert result is not None
    assert "api_key" in result
    assert result["adapter_name"] == "qa-sql"
    assert result["client_name"] == "test_client"
    assert result["notes"] == "Test API key"
    assert result["active"] is True

@pytest.mark.asyncio
async def test_list_api_keys(api_key_service):
    """Test listing API keys"""
    # Create multiple API keys
    for i in range(3):
        await api_key_service.create_api_key(
            client_name=f"client_{i}",
            adapter_name="qa-sql",
            notes=f"Test key {i}"
        )

    # List API keys using database abstraction
    api_keys = await api_key_service.database.find_many(
        api_key_service.collection_name,
        {},
        limit=100
    )

    # There should be at least 3 keys (plus the one from the previous test)
    assert len(api_keys) >= 3
    for key in api_keys:
        assert "api_key" in key
        assert "adapter_name" in key
        assert "client_name" in key
        assert "active" in key

@pytest.mark.asyncio
async def test_get_api_key_status(api_key_service):
    """Test getting API key status"""
    # Create an API key
    result = await api_key_service.create_api_key(
        client_name="test_client",
        adapter_name="qa-sql",
        notes="Test API key"
    )
    
    api_key = result["api_key"]
    
    # Get status
    status = await api_key_service.get_api_key_status(api_key)
    
    assert status is not None
    assert status.get("active") is True
    assert status.get("adapter_name") == "qa-sql"
    assert status.get("client_name") == "test_client"

@pytest.mark.asyncio
async def test_deactivate_api_key(api_key_service):
    """Test deactivating an API key"""
    # Create an API key
    result = await api_key_service.create_api_key(
        client_name="test_client",
        adapter_name="qa-sql",
        notes="Test API key"
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
        client_name="test_client",
        adapter_name="qa-sql",
        notes="Test API key"
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
        client_name="test_client",
        adapter_name="qa-sql",
        notes="Test API key"
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
        client_name="test_client",
        adapter_name="qa-sql",
        notes="Test API key"
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
        client_name="test_client",
        adapter_name="qa-sql",
        notes="Test API key",
        system_prompt_id=string_prompt_id
    )
    
    assert result is not None
    assert "api_key" in result
    assert result["adapter_name"] == "qa-sql"
    assert result["client_name"] == "test_client"
    assert result["system_prompt_id"] == string_prompt_id
    
    # Verify the association in the database
    status = await api_key_service.get_api_key_status(result["api_key"])
    assert status.get("system_prompt", {}).get("id") == string_prompt_id

# ========================
# ADAPTER MIGRATION TESTS
# ========================

@pytest.mark.asyncio
async def test_adapter_config_lookup(api_key_service):
    """Test adapter configuration lookup"""
    # Test valid adapter
    config = api_key_service._get_adapter_config("qa-sql")
    assert config is not None
    assert config['name'] == 'qa-sql'
    assert config['type'] == 'retriever'
    assert config['datasource'] == 'sqlite'
    
    # Test invalid adapter
    config = api_key_service._get_adapter_config("non-existent-adapter")
    assert config is None



@pytest.mark.asyncio
async def test_create_adapter_based_api_key(api_key_service):
    """Test creating an adapter-based API key"""
    result = await api_key_service.create_api_key(
        client_name="Test Client",
        notes="Test adapter-based key",
        adapter_name="qa-sql"
    )
    
    assert result is not None
    assert "api_key" in result
    assert result["adapter_name"] == "qa-sql"
    assert result["client_name"] == "Test Client"
    assert result["notes"] == "Test adapter-based key"
    assert result["active"] is True
    
    # Test validation
    is_valid, adapter_name, prompt_id = await api_key_service.validate_api_key(result['api_key'])
    assert is_valid is True
    assert adapter_name == "qa-sql"
    assert prompt_id is None



@pytest.mark.asyncio
async def test_adapter_validation_error(api_key_service):
    """Test that creating API key with non-existent adapter fails"""
    with pytest.raises(Exception) as exc_info:
        await api_key_service.create_api_key(
            client_name="Invalid Client",
            adapter_name="non-existent-adapter"
        )
    
    assert "not found in configuration" in str(exc_info.value)



@pytest.mark.asyncio
async def test_api_key_status_with_adapter(api_key_service):
    """Test API key status includes adapter information"""
    # Create adapter-based key
    result = await api_key_service.create_api_key(
        client_name="Status Test Client",
        adapter_name="qa-sql",
        notes="Status test key"
    )
    
    api_key = result["api_key"]
    status = await api_key_service.get_api_key_status(api_key)
    
    assert status is not None
    assert status.get('exists') is True
    assert status.get('adapter_name') == "qa-sql"
    assert status.get('active') is True
    assert status.get('client_name') == "Status Test Client"



@pytest.mark.asyncio
async def test_validate_api_key_with_adapter_config_check(api_key_service):
    """Test that API key validation checks adapter configuration exists"""
    # Create key with valid adapter
    result = await api_key_service.create_api_key(
        client_name="Valid Config Client",
        adapter_name="qa-sql"
    )
    
    api_key = result["api_key"]
    
    # Temporarily remove adapter from config to simulate missing adapter
    original_adapters = api_key_service.config['adapters']
    api_key_service.config['adapters'] = [
        adapter for adapter in original_adapters if adapter['name'] != 'qa-sql'
    ]
    
    # Validation should fail now
    is_valid, adapter_name, prompt_id = await api_key_service.validate_api_key(api_key)
    assert is_valid is False
    
    # Restore config
    api_key_service.config['adapters'] = original_adapters

@pytest.mark.asyncio
async def test_create_api_key_requires_adapter_name(api_key_service):
    """Test that creating API key requires adapter_name"""
    with pytest.raises(Exception) as exc_info:
        await api_key_service.create_api_key(
            client_name="Invalid Client"
            # No adapter_name provided
        )
    
    assert "adapter_name must be provided" in str(exc_info.value)



@pytest.mark.asyncio
async def test_api_key_with_system_prompt_adapter_based(api_key_service):
    """Test creating adapter-based API key with system prompt"""
    # Create a mock prompt ID
    prompt_id = ObjectId()

    result = await api_key_service.create_api_key(
        client_name="Prompt Test Client",
        adapter_name="qa-sql",
        system_prompt_id=prompt_id
    )

    assert result is not None
    assert result["system_prompt_id"] == str(prompt_id)

    # Test validation returns prompt ID (as string for backend compatibility)
    is_valid, adapter_name, returned_prompt_id = await api_key_service.validate_api_key(result['api_key'])
    assert is_valid is True
    assert adapter_name == "qa-sql"
    assert str(returned_prompt_id) == str(prompt_id)

@pytest.mark.asyncio
async def test_default_api_key_behavior_with_adapters(api_key_service):
    """Test default API key behavior when allow_default is True"""
    # Test with empty API key when allow_default is True
    is_valid, adapter_name, prompt_id = await api_key_service.validate_api_key("")
    # Should return default adapter from config
    assert is_valid is True
    assert adapter_name == "qa-sql"  # First adapter in the list

@pytest.mark.asyncio
async def test_no_default_api_key_behavior_with_adapters(api_key_service):
    """Test API key behavior when allow_default is False"""
    # Temporarily disable allow_default
    original_allow_default = api_key_service.config['api_keys']['allow_default']
    api_key_service.config['api_keys']['allow_default'] = False
    
    # Test with empty API key when allow_default is False
    is_valid, adapter_name, prompt_id = await api_key_service.validate_api_key("")
    # Should fail validation
    assert is_valid is False
    assert adapter_name is None
    
    # Restore original setting
    api_key_service.config['api_keys']['allow_default'] = original_allow_default

@pytest.mark.asyncio
async def test_deactivated_api_key_validation_with_adapters(api_key_service):
    """Test that deactivated API keys fail validation"""
    # Create and deactivate key
    result = await api_key_service.create_api_key(
        client_name="Deactivate Test Client",
        adapter_name="qa-sql"
    )

    api_key = result["api_key"]
    await api_key_service.deactivate_api_key(api_key)

    # Should fail validation
    is_valid, adapter_name, prompt_id = await api_key_service.validate_api_key(api_key)
    assert is_valid is False

# ========================
# API KEY RENAME TESTS
# ========================

@pytest.mark.asyncio
async def test_rename_api_key_success(api_key_service):
    """Test successfully renaming an API key"""
    # Create an API key
    result = await api_key_service.create_api_key(
        client_name="Rename Test Client",
        adapter_name="qa-sql",
        notes="Test rename key"
    )

    old_api_key = result["api_key"]
    new_api_key = f"{api_key_service.config['api_keys']['prefix']}renamed_key_123"

    # Rename the key
    success = await api_key_service.rename_api_key(old_api_key, new_api_key)
    assert success is True

    # Verify old key no longer exists
    old_status = await api_key_service.get_api_key_status(old_api_key)
    assert old_status is None or old_status.get("exists") is False

    # Verify new key exists and has correct properties
    new_status = await api_key_service.get_api_key_status(new_api_key)
    assert new_status is not None
    assert new_status.get("exists") is True
    assert new_status.get("active") is True
    assert new_status.get("adapter_name") == "qa-sql"
    assert new_status.get("client_name") == "Rename Test Client"

    # Verify new key validates correctly
    is_valid, adapter_name, prompt_id = await api_key_service.validate_api_key(new_api_key)
    assert is_valid is True
    assert adapter_name == "qa-sql"


@pytest.mark.asyncio
async def test_rename_api_key_to_existing_key(api_key_service):
    """Test that renaming to an existing key fails"""
    # Create two API keys
    result1 = await api_key_service.create_api_key(
        client_name="Test Client 1",
        adapter_name="qa-sql"
    )
    result2 = await api_key_service.create_api_key(
        client_name="Test Client 2",
        adapter_name="qa-vector-chroma"
    )

    old_api_key = result1["api_key"]
    existing_api_key = result2["api_key"]

    # Try to rename to existing key - should raise HTTPException with 409
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await api_key_service.rename_api_key(old_api_key, existing_api_key)

    assert exc_info.value.status_code == 409
    assert "already exists" in str(exc_info.value.detail)

    # Verify original keys still exist
    status1 = await api_key_service.get_api_key_status(old_api_key)
    assert status1.get("exists") is True

    status2 = await api_key_service.get_api_key_status(existing_api_key)
    assert status2.get("exists") is True


@pytest.mark.asyncio
async def test_rename_nonexistent_api_key(api_key_service):
    """Test that renaming a non-existent key fails"""
    old_api_key = "nonexistent_key_123"
    new_api_key = f"{api_key_service.config['api_keys']['prefix']}new_key_456"

    # Try to rename non-existent key - should raise HTTPException with 404
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await api_key_service.rename_api_key(old_api_key, new_api_key)

    assert exc_info.value.status_code == 404
    assert "not found" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_rename_api_key_preserves_associations(api_key_service, prompt_service):
    """Test that renaming an API key preserves system prompt associations"""
    # Create a prompt
    prompt_id = await prompt_service.create_prompt(
        "Test Prompt for Rename",
        "This is a test system prompt",
        "1.0"
    )

    # Create an API key with associated prompt
    result = await api_key_service.create_api_key(
        client_name="Rename Test Client",
        adapter_name="qa-sql",
        notes="Test rename with prompt",
        system_prompt_id=str(prompt_id)
    )

    old_api_key = result["api_key"]
    new_api_key = f"{api_key_service.config['api_keys']['prefix']}renamed_key_with_prompt"

    # Rename the key
    success = await api_key_service.rename_api_key(old_api_key, new_api_key)
    assert success is True

    # Verify new key has the prompt association
    new_status = await api_key_service.get_api_key_status(new_api_key)
    assert new_status is not None

    # Check prompt association is preserved
    stored_prompt_id = new_status.get("system_prompt", {}).get("id") if isinstance(new_status.get("system_prompt"), dict) else new_status.get("system_prompt_id")

    if stored_prompt_id:
        assert str(stored_prompt_id) == str(prompt_id)
    else:
        # Also check via validation
        is_valid, adapter_name, returned_prompt_id = await api_key_service.validate_api_key(new_api_key)
        assert is_valid is True
        assert str(returned_prompt_id) == str(prompt_id)


@pytest.mark.asyncio
async def test_rename_api_key_preserves_notes_and_metadata(api_key_service):
    """Test that renaming an API key preserves all metadata"""
    # Create an API key with notes
    result = await api_key_service.create_api_key(
        client_name="Metadata Test Client",
        adapter_name="qa-vector-chroma",
        notes="Important notes about this key"
    )

    old_api_key = result["api_key"]
    new_api_key = f"{api_key_service.config['api_keys']['prefix']}renamed_key_metadata"

    # Get original created_at timestamp
    original_status = await api_key_service.get_api_key_status(old_api_key)
    original_created_at = original_status.get("created_at")

    # Rename the key
    success = await api_key_service.rename_api_key(old_api_key, new_api_key)
    assert success is True

    # Verify all metadata is preserved
    new_status = await api_key_service.get_api_key_status(new_api_key)
    assert new_status.get("client_name") == "Metadata Test Client"
    assert new_status.get("adapter_name") == "qa-vector-chroma"
    # Note: notes are not returned in get_api_key_status, would need to query directly

    # Verify created_at is preserved by querying the database directly
    key_doc = await api_key_service.database.find_one(
        api_key_service.collection_name,
        {"api_key": new_api_key}
    )
    assert key_doc is not None
    assert key_doc.get("notes") == "Important notes about this key"
    # Created_at should be preserved (comparing datetime objects from MongoDB)
    created_at = key_doc.get("created_at")
    if created_at and original_created_at:
        # Both should be datetime objects - compare them directly
        # If original_created_at is a timestamp, convert created_at to timestamp for comparison
        if hasattr(created_at, 'timestamp') and hasattr(original_created_at, 'timestamp'):
            # Both are datetime objects
            assert created_at == original_created_at
        elif hasattr(created_at, 'timestamp') and isinstance(original_created_at, (int, float)):
            # created_at is datetime, original_created_at is timestamp
            assert created_at.timestamp() == original_created_at
        else:
            # Just compare directly
            assert created_at == original_created_at


@pytest.mark.asyncio
async def test_rename_deactivated_api_key(api_key_service):
    """Test that deactivated API keys can be renamed"""
    # Create and deactivate an API key
    result = await api_key_service.create_api_key(
        client_name="Deactivated Rename Test",
        adapter_name="qa-sql"
    )

    old_api_key = result["api_key"]
    await api_key_service.deactivate_api_key(old_api_key)

    new_api_key = f"{api_key_service.config['api_keys']['prefix']}renamed_deactivated_key"

    # Rename the deactivated key - should succeed
    success = await api_key_service.rename_api_key(old_api_key, new_api_key)
    assert success is True

    # Verify new key exists and is still deactivated
    new_status = await api_key_service.get_api_key_status(new_api_key)
    assert new_status is not None
    assert new_status.get("exists") is True
    assert new_status.get("active") is False
