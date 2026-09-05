"""
Test API Key Service with SQLite Backend
=========================================

This script tests the API key service using SQLite as the backend database
to ensure feature parity with the MongoDB implementation.
"""

import pytest
import pytest_asyncio
import sys
import os
from datetime import datetime, timedelta, UTC
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import logging
from pathlib import Path
import tempfile
import shutil

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Get the project root (parent of server directory)
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent

# Add server directory to Python path
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import services
from services.api_key_service import ApiKeyService
from services.prompt_service import PromptService
from services.sqlite_service import SQLiteService

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


@pytest.mark.asyncio
async def test_get_adapter_info_supports_realtime_voice_flag(api_key_service):
    """get_adapter_info() reflects capabilities.supports_realtime_audio as supportsRealtimeVoice"""
    # qa-sql has no capabilities block configured -> defaults to False
    result = await api_key_service.create_api_key(
        client_name="Realtime Flag Test Client",
        adapter_name="qa-sql"
    )
    adapter_info = await api_key_service.get_adapter_info(result["api_key"])
    assert adapter_info["supportsRealtimeVoice"] is False

    # Temporarily mark qa-sql as a real-time voice adapter
    for adapter in api_key_service.config['adapters']:
        if adapter['name'] == 'qa-sql':
            adapter['capabilities'] = {'supports_realtime_audio': True}
            break

    adapter_info = await api_key_service.get_adapter_info(result["api_key"])
    assert adapter_info["supportsRealtimeVoice"] is True

    # Restore original config
    for adapter in api_key_service.config['adapters']:
        if adapter['name'] == 'qa-sql':
            adapter.pop('capabilities', None)
            break


# ========================
# ALLOWED_USER_IDS TESTS
# ========================

@pytest.mark.asyncio
async def test_email_restricted_key_authorizes_case_insensitive_email(api_key_service):
    """An email-only restriction works before the user has an internal id."""
    result = await api_key_service.create_api_key(
        client_name="Preauthorized Client",
        adapter_name="qa-sql",
        allowed_emails=[" Alice@Company.COM "]
    )
    api_key = result["api_key"]
    assert result["allowed_emails"] == ["alice@company.com"]

    is_valid, adapter_name, _ = await api_key_service.validate_api_key(
        api_key, current_user_email="ALICE@company.com"
    )
    assert is_valid is True
    assert adapter_name == "qa-sql"


@pytest.mark.asyncio
async def test_email_restricted_key_fails_closed_and_allows_either_list(api_key_service):
    """Restricted keys require an ID or email match; the lists are ORed."""
    result = await api_key_service.create_api_key(
        client_name="Combined restriction",
        adapter_name="qa-sql",
        allowed_user_ids=["existing-user"],
        allowed_emails=["pending@company.com"],
    )
    api_key = result["api_key"]

    is_valid, _, _ = await api_key_service.validate_api_key(api_key)
    assert is_valid is False
    is_valid, _, _ = await api_key_service.validate_api_key(api_key, current_user_id="existing-user")
    assert is_valid is True
    is_valid, _, _ = await api_key_service.validate_api_key(api_key, current_user_email="pending@company.com")
    assert is_valid is True
    is_valid, _, _ = await api_key_service.validate_api_key(api_key, current_user_email="other@company.com")
    assert is_valid is False

@pytest.mark.asyncio
async def test_unrestricted_key_ignores_current_user_id(api_key_service):
    """A key with no allowlist is usable by anyone, authenticated or not."""
    result = await api_key_service.create_api_key(
        client_name="Unrestricted Client",
        adapter_name="qa-sql"
    )
    api_key = result["api_key"]
    assert result["allowed_user_ids"] is None

    is_valid, adapter_name, _ = await api_key_service.validate_api_key(api_key, current_user_id=None)
    assert is_valid is True
    assert adapter_name == "qa-sql"

    is_valid, adapter_name, _ = await api_key_service.validate_api_key(api_key, current_user_id="some-user-id")
    assert is_valid is True
    assert adapter_name == "qa-sql"


@pytest.mark.asyncio
async def test_restricted_key_accepts_allowed_user(api_key_service):
    """A key with an allowlist validates for a user id on that list."""
    result = await api_key_service.create_api_key(
        client_name="Restricted Client",
        adapter_name="qa-sql",
        allowed_user_ids=["user-a", "user-b"]
    )
    api_key = result["api_key"]
    assert result["allowed_user_ids"] == ["user-a", "user-b"]

    is_valid, adapter_name, _ = await api_key_service.validate_api_key(api_key, current_user_id="user-b")
    assert is_valid is True
    assert adapter_name == "qa-sql"


@pytest.mark.asyncio
async def test_restricted_key_rejects_unlisted_user(api_key_service):
    """A key with an allowlist fails validation for a user id not on that list."""
    result = await api_key_service.create_api_key(
        client_name="Restricted Client",
        adapter_name="qa-sql",
        allowed_user_ids=["user-a"]
    )
    api_key = result["api_key"]

    is_valid, adapter_name, _ = await api_key_service.validate_api_key(api_key, current_user_id="user-z")
    assert is_valid is False
    assert adapter_name is None


@pytest.mark.asyncio
async def test_restricted_key_rejects_anonymous_caller(api_key_service):
    """A restricted key fails closed when no authenticated user is present at all."""
    result = await api_key_service.create_api_key(
        client_name="Restricted Client",
        adapter_name="qa-sql",
        allowed_user_ids=["user-a"]
    )
    api_key = result["api_key"]

    is_valid, adapter_name, _ = await api_key_service.validate_api_key(api_key, current_user_id=None)
    assert is_valid is False
    assert adapter_name is None


@pytest.mark.asyncio
async def test_get_adapter_for_api_key_enforces_allowlist(api_key_service):
    """get_adapter_for_api_key propagates the allowlist check via validate_api_key."""
    from fastapi import HTTPException

    result = await api_key_service.create_api_key(
        client_name="Restricted Client",
        adapter_name="qa-sql",
        allowed_user_ids=["user-a"]
    )
    api_key = result["api_key"]

    adapter_name, _ = await api_key_service.get_adapter_for_api_key(api_key, current_user_id="user-a")
    assert adapter_name == "qa-sql"

    with pytest.raises(HTTPException) as exc_info:
        await api_key_service.get_adapter_for_api_key(api_key, current_user_id="user-z")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_adapter_info_enforces_allowlist(api_key_service):
    """get_adapter_info rejects callers not on the key's allowlist."""
    from fastapi import HTTPException

    result = await api_key_service.create_api_key(
        client_name="Restricted Client",
        adapter_name="qa-sql",
        allowed_user_ids=["user-a"]
    )
    api_key = result["api_key"]

    info = await api_key_service.get_adapter_info(api_key, current_user_id="user-a")
    assert info["adapter_name"] == "qa-sql"

    with pytest.raises(HTTPException) as exc_info:
        await api_key_service.get_adapter_info(api_key, current_user_id="user-z")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_update_api_key_metadata_sets_allowlist(api_key_service):
    """update_api_key_metadata can add and clear an allowlist on an existing key."""
    result = await api_key_service.create_api_key(
        client_name="Editable Client",
        adapter_name="qa-sql"
    )
    api_key = result["api_key"]
    key_doc = await api_key_service.database.find_one(api_key_service.collection_name, {"api_key": api_key})
    key_id = str(key_doc["_id"])

    success = await api_key_service.update_api_key_metadata(
        key_id,
        client_name="Editable Client",
        adapter_name="qa-sql",
        allowed_user_ids=["user-a", "user-b"]
    )
    assert success is True

    is_valid, _, _ = await api_key_service.validate_api_key(api_key, current_user_id="user-b")
    assert is_valid is True
    is_valid, _, _ = await api_key_service.validate_api_key(api_key, current_user_id="user-z")
    assert is_valid is False

    # Clearing the allowlist (empty list) restores unrestricted access
    success = await api_key_service.update_api_key_metadata(
        key_id,
        client_name="Editable Client",
        adapter_name="qa-sql",
        allowed_user_ids=[]
    )
    assert success is True

    is_valid, _, _ = await api_key_service.validate_api_key(api_key, current_user_id="user-z")
    assert is_valid is True


# --- API key expiration tests (Phase 8) --------------------------------------

@pytest.mark.asyncio
async def test_create_api_key_defaults_to_90_day_expiration(api_key_service):
    """A newly created key defaults to now + default_lifetime_days (90)."""
    before = datetime.now(UTC)
    result = await api_key_service.create_api_key(client_name="c", adapter_name="qa-sql")
    after = datetime.now(UTC)

    assert result["expiration_policy"] == "managed"
    assert result["expires_at"] is not None
    expires_at = datetime.fromtimestamp(result["expires_at"], tz=UTC)
    assert before + timedelta(days=89) < expires_at < after + timedelta(days=91)


@pytest.mark.asyncio
async def test_create_api_key_rejects_over_max_lifetime(api_key_service):
    """expires_at more than max_lifetime_days (365) in the future is rejected."""
    too_far = datetime.now(UTC) + timedelta(days=400)
    with pytest.raises(HTTPException) as exc_info:
        await api_key_service.create_api_key(client_name="c", adapter_name="qa-sql", expires_at=too_far)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_create_api_key_rejects_past_expiration(api_key_service):
    """A past expires_at is rejected."""
    past = datetime.now(UTC) - timedelta(days=1)
    with pytest.raises(HTTPException) as exc_info:
        await api_key_service.create_api_key(client_name="c", adapter_name="qa-sql", expires_at=past)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_create_api_key_rejects_timezone_naive_expiration(api_key_service):
    """A timezone-naive expires_at is rejected."""
    naive = datetime.now() + timedelta(days=10)
    with pytest.raises(HTTPException) as exc_info:
        await api_key_service.create_api_key(client_name="c", adapter_name="qa-sql", expires_at=naive)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_create_api_key_non_expiring_requires_justification(api_key_service):
    """A non-expiring exception without justification is rejected."""
    with pytest.raises(HTTPException) as exc_info:
        await api_key_service.create_api_key(client_name="c", adapter_name="qa-sql", non_expiring=True)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_create_api_key_non_expiring_exception_with_justification(api_key_service):
    """A justified non-expiring exception is accepted and stores no expiration."""
    result = await api_key_service.create_api_key(
        client_name="c", adapter_name="qa-sql", non_expiring=True,
        expiration_justification="Approved by security team for legacy integration",
    )
    assert result["expiration_policy"] == "non_expiring_exception"
    assert result["expires_at"] is None


@pytest.mark.asyncio
async def test_expired_key_is_rejected_by_validate_api_key(api_key_service):
    """A key whose expires_at is in the past fails validation like an unknown key."""
    result = await api_key_service.create_api_key(client_name="c", adapter_name="qa-sql")
    api_key = result["api_key"]

    # Force expiration directly (bypassing the creation-time validation).
    key_doc = await api_key_service._resolve_key_doc(api_key)
    await api_key_service.database.update_one(
        api_key_service.collection_name, {"_id": str(key_doc["_id"])},
        {"$set": {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}}
    )

    is_valid, adapter_name, _ = await api_key_service.validate_api_key(api_key)
    assert is_valid is False
    assert adapter_name is None


@pytest.mark.asyncio
async def test_expired_key_valid_immediately_before_expiration(api_key_service):
    """A key is still valid the instant before its expires_at."""
    result = await api_key_service.create_api_key(client_name="c", adapter_name="qa-sql")
    api_key = result["api_key"]

    key_doc = await api_key_service._resolve_key_doc(api_key)
    almost_expired = datetime.now(UTC) + timedelta(seconds=2)
    await api_key_service.database.update_one(
        api_key_service.collection_name, {"_id": str(key_doc["_id"])},
        {"$set": {"expires_at": almost_expired}}
    )

    is_valid, adapter_name, _ = await api_key_service.validate_api_key(api_key)
    assert is_valid is True
    assert adapter_name == "qa-sql"


@pytest.mark.asyncio
async def test_expired_explicit_key_does_not_fall_back_to_default_adapter(api_key_service):
    """An expired explicit key must not silently fall back to allow_default behavior."""
    api_key_service.config.setdefault('api_keys', {})['allow_default'] = True
    result = await api_key_service.create_api_key(client_name="c", adapter_name="qa-sql")
    api_key = result["api_key"]

    key_doc = await api_key_service._resolve_key_doc(api_key)
    await api_key_service.database.update_one(
        api_key_service.collection_name, {"_id": str(key_doc["_id"])},
        {"$set": {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}}
    )

    with pytest.raises(HTTPException) as exc_info:
        await api_key_service.get_adapter_for_api_key(api_key)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_expired_key_independent_of_disabled_state(api_key_service):
    """Expiration and the `active` flag are independent: disabling an expired key
    doesn't change its rejection reason, and re-enabling doesn't revive an expired key."""
    result = await api_key_service.create_api_key(client_name="c", adapter_name="qa-sql")
    api_key = result["api_key"]
    key_doc = await api_key_service._resolve_key_doc(api_key)
    doc_id = str(key_doc["_id"])

    await api_key_service.database.update_one(
        api_key_service.collection_name, {"_id": doc_id},
        {"$set": {"expires_at": datetime.now(UTC) - timedelta(seconds=1), "active": True}}
    )
    is_valid, _, _ = await api_key_service.validate_api_key(api_key)
    assert is_valid is False

    await api_key_service.deactivate_api_key_by_id(doc_id)
    is_valid, _, _ = await api_key_service.validate_api_key(api_key)
    assert is_valid is False


@pytest.mark.asyncio
async def test_get_api_key_status_reports_expiration_fields(api_key_service):
    """Status responses expose expires_at/expiration_policy/expired/days_remaining."""
    result = await api_key_service.create_api_key(client_name="c", adapter_name="qa-sql")
    status = await api_key_service.get_api_key_status(result["api_key"])

    assert status["expiration_policy"] == "managed"
    assert status["expired"] is False
    assert status["days_remaining"] is not None
    assert 88 < status["days_remaining"] <= 90


@pytest.mark.asyncio
async def test_renew_api_key_extends_expiration(api_key_service):
    """Renewal accepts a new absolute expires_at and records the previous value."""
    result = await api_key_service.create_api_key(client_name="c", adapter_name="qa-sql")
    key_doc = await api_key_service._resolve_key_doc(result["api_key"])
    doc_id = str(key_doc["_id"])

    new_expiry = datetime.now(UTC) + timedelta(days=200)
    renewal = await api_key_service.renew_api_key(doc_id, expires_at=new_expiry)

    assert renewal["expiration_policy"] == "managed"
    assert renewal["previous_expires_at"] is not None
    assert abs(renewal["expires_at"] - new_expiry.timestamp()) < 2

    status = await api_key_service.get_api_key_status_by_id(doc_id)
    assert abs(status["expires_at"].timestamp() - new_expiry.timestamp()) < 2


@pytest.mark.asyncio
async def test_renew_api_key_to_non_expiring_exception(api_key_service):
    """Renewal can grant a justified non-expiring exception."""
    result = await api_key_service.create_api_key(client_name="c", adapter_name="qa-sql")
    key_doc = await api_key_service._resolve_key_doc(result["api_key"])
    doc_id = str(key_doc["_id"])

    renewal = await api_key_service.renew_api_key(
        doc_id, non_expiring=True, expiration_justification="Board-approved integration key"
    )
    assert renewal["expiration_policy"] == "non_expiring_exception"
    assert renewal["expires_at"] is None


@pytest.mark.asyncio
async def test_renew_api_key_rejects_unjustified_non_expiring(api_key_service):
    """Renewal to non-expiring without justification is rejected."""
    result = await api_key_service.create_api_key(client_name="c", adapter_name="qa-sql")
    key_doc = await api_key_service._resolve_key_doc(result["api_key"])

    with pytest.raises(HTTPException) as exc_info:
        await api_key_service.renew_api_key(str(key_doc["_id"]), non_expiring=True)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_legacy_key_migration_assigns_finite_expiration(sqlite_service):
    """A pre-existing key with no expires_at is migrated to expiration_policy=legacy_migration
    with expires_at = now + legacy_migration_lifetime_days, on service initialize()."""
    # Insert a legacy-shaped document directly, bypassing create_api_key (which always
    # sets an expiration), to simulate a pre-Phase-8 record.
    legacy_doc = {
        "api_key": "legacy_test_key",
        "client_name": "legacy_client",
        "active": True,
        "created_at": datetime.now(UTC) - timedelta(days=400),
        "adapter_name": "qa-sql",
    }
    await sqlite_service.insert_one("api_keys", legacy_doc)

    # The service is a process-wide singleton keyed by backend config; clear it so this
    # test gets a fresh instance bound to `sqlite_service` instead of a cached one from
    # another test (whose connection may already be closed).
    ApiKeyService.clear_cache()
    config = get_test_config()
    service = ApiKeyService(config, sqlite_service)
    await service.initialize()

    migrated = await service.database.find_one("api_keys", {"api_key": "legacy_test_key"})
    assert migrated["expiration_policy"] == "legacy_migration"
    assert migrated["expires_at"] is not None
    assert migrated["expires_at"] > datetime.now(UTC) + timedelta(days=89)


@pytest.mark.asyncio
async def test_legacy_key_migration_is_idempotent(api_key_service):
    """Re-running the migration does not change an already-migrated expiration."""
    result = await api_key_service.create_api_key(client_name="c", adapter_name="qa-sql")
    before = (await api_key_service.get_api_key_status(result["api_key"]))["expires_at"]

    await api_key_service._migrate_legacy_expirations()

    after = (await api_key_service.get_api_key_status(result["api_key"]))["expires_at"]
    assert before == after


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
