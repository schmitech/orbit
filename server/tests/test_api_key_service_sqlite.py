"""
Test API Key Service with SQLite Backend
=========================================

This script tests the API key service using SQLite as the backend database
to ensure feature parity with the MongoDB implementation.
"""

import pytest
import pytest_asyncio
import asyncio
import sys
import os
from datetime import datetime, UTC
from fastapi import FastAPI
from fastapi.testclient import TestClient
import logging
from pathlib import Path
import tempfile
import shutil

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

# Import services
from services.api_key_service import ApiKeyService
from services.prompt_service import PromptService
from services.sqlite_service import SQLiteService
from utils.id_utils import generate_id

# Create temporary directory for test databases
TEMP_DIR = None


def setup_module(module):
    """Setup temporary directory for all tests"""
    global TEMP_DIR
    TEMP_DIR = tempfile.mkdtemp()


def teardown_module(module):
    """Cleanup temporary directory after all tests"""
    global TEMP_DIR
    if TEMP_DIR:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)


def get_test_config():
    """Create test configuration"""
    db_path = os.path.join(TEMP_DIR, f"test_{os.getpid()}.db")
    return {
        'general': {
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
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': db_path
                }
            }
        },
        'mongodb': {
            'apikey_collection': 'api_keys',
            'prompts_collection': 'system_prompts'
        }
    }


@pytest_asyncio.fixture
async def sqlite_service():
    """Fixture to provide a SQLite service instance"""
    config = get_test_config()
    service = SQLiteService(config)
    await service.initialize()
    logger.info("Successfully initialized SQLite service")
    yield service
    # Cleanup
    service.close()


@pytest_asyncio.fixture
async def api_key_service(sqlite_service):
    """Fixture to provide an API key service instance with SQLite"""
    config = get_test_config()
    service = ApiKeyService(config, sqlite_service)
    await service.initialize()
    return service


@pytest_asyncio.fixture
async def prompt_service(sqlite_service):
    """Fixture to provide a prompt service instance with SQLite"""
    config = get_test_config()
    service = PromptService(config, sqlite_service)
    await service.initialize()
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


# Helper to ensure ID conversion is handled properly
def ensure_id(id_value):
    """Convert ID to string if needed (SQLite uses UUID strings)"""
    return str(id_value)


# API Key Tests
@pytest.mark.asyncio
async def test_create_api_key(api_key_service):
    """Test API key creation with SQLite"""
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
    """Test listing API keys with SQLite"""
    # Create multiple API keys
    for i in range(3):
        await api_key_service.create_api_key(
            client_name=f"client_{i}",
            adapter_name="qa-sql",
            notes=f"Test key {i}"
        )

    # List API keys
    api_keys = await api_key_service.database.find_many(
        api_key_service.collection_name,
        {}
    )

    # There should be at least 3 keys
    assert len(api_keys) >= 3
    for key in api_keys:
        assert "_id" in key
        assert "api_key" in key
        assert "adapter_name" in key
        assert "client_name" in key
        assert "active" in key


@pytest.mark.asyncio
async def test_get_api_key_status(api_key_service):
    """Test getting API key status with SQLite"""
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
    """Test deactivating an API key with SQLite"""
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
    """Test deleting an API key with SQLite"""
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
    """Test creating a system prompt with SQLite"""
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
    """Test listing system prompts with SQLite"""
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
    """Test getting a specific prompt with SQLite"""
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
    """Test updating a system prompt with SQLite"""
    # Create a prompt
    prompt_id = await prompt_service.create_prompt(
        "Test Prompt for Update",
        "This is a test system prompt",
        "1.0"
    )

    # Update the prompt
    success = await prompt_service.update_prompt(
        ensure_id(prompt_id),
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
    """Test deleting a system prompt with SQLite"""
    # Create a prompt
    prompt_id = await prompt_service.create_prompt(
        "Test Prompt for Deletion",
        "This is a test system prompt",
        "1.0"
    )

    # Delete the prompt
    success = await prompt_service.delete_prompt(ensure_id(prompt_id))
    assert success is True

    # Verify deletion
    prompt = await prompt_service.get_prompt_by_id(prompt_id)
    assert prompt is None


# API Key + Prompt Association Tests
@pytest.mark.asyncio
async def test_associate_prompt_with_api_key(api_key_service, prompt_service):
    """Test associating a prompt with an API key using SQLite"""
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

    # Associate prompt with API key
    success = await api_key_service.update_api_key_system_prompt(api_key, ensure_id(prompt_id))
    assert success is True

    # Verify association
    status = await api_key_service.get_api_key_status(api_key)
    stored_prompt_id = status.get("system_prompt", {}).get("id") if isinstance(status.get("system_prompt"), dict) else status.get("system_prompt_id")

    if stored_prompt_id:
        assert str(stored_prompt_id) == str(prompt_id)
    else:
        pytest.fail("Prompt ID not found in API key status")


# Error Cases
@pytest.mark.asyncio
async def test_invalid_api_key(api_key_service):
    """Test handling of invalid API key with SQLite"""
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
    """Test handling of invalid prompt ID with SQLite"""
    # Try to get non-existent prompt
    import uuid
    invalid_id = str(uuid.uuid4())
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
    """Test handling of invalid prompt association with SQLite"""
    # Create an API key
    result = await api_key_service.create_api_key(
        client_name="test_client",
        adapter_name="qa-sql",
        notes="Test API key"
    )

    api_key = result["api_key"]

    # Try to associate non-existent prompt
    import uuid
    invalid_id = str(uuid.uuid4())
    success = await api_key_service.update_api_key_system_prompt(api_key, invalid_id)
    assert success is False


@pytest.mark.asyncio
async def test_create_api_key_with_string_prompt_id(api_key_service, prompt_service):
    """Test creating an API key with a string system prompt ID using SQLite"""
    # Create a prompt first
    prompt_id = await prompt_service.create_prompt(
        "Test Prompt for String ID",
        "This is a test system prompt",
        "1.0"
    )

    # Convert to string
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


# Adapter Tests
@pytest.mark.asyncio
async def test_adapter_config_lookup(api_key_service):
    """Test adapter configuration lookup with SQLite"""
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
    """Test creating an adapter-based API key with SQLite"""
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
    """Test that creating API key with non-existent adapter fails with SQLite"""
    with pytest.raises(Exception) as exc_info:
        await api_key_service.create_api_key(
            client_name="Invalid Client",
            adapter_name="non-existent-adapter"
        )

    assert "not found in configuration" in str(exc_info.value)


@pytest.mark.asyncio
async def test_api_key_status_with_adapter(api_key_service):
    """Test API key status includes adapter information with SQLite"""
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
async def test_default_api_key_behavior_with_adapters(api_key_service):
    """Test default API key behavior when allow_default is True with SQLite"""
    # Test with empty API key when allow_default is True
    is_valid, adapter_name, prompt_id = await api_key_service.validate_api_key("")
    # Should return default adapter from config
    assert is_valid is True
    assert adapter_name == "qa-sql"  # First adapter in the list


@pytest.mark.asyncio
async def test_deactivated_api_key_validation_with_adapters(api_key_service):
    """Test that deactivated API keys fail validation with SQLite"""
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
