import pytest
import pytest_asyncio
import asyncio
import sys
import os
import json
from datetime import datetime, UTC
from fastapi import FastAPI
from fastapi.testclient import TestClient
import logging
from dotenv import load_dotenv
from pathlib import Path

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Get the project root (parent of server directory)
PROJECT_ROOT = SCRIPT_DIR.parent.parent

# Add server directory to Python path
SERVER_DIR = SCRIPT_DIR.parent
sys.path.append(str(SERVER_DIR))

from services.mongodb_service import MongoDBService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file in project root
env_path = PROJECT_ROOT / '.env'
if not env_path.exists():
    raise FileNotFoundError(f".env file not found at {env_path}")

load_dotenv(env_path)

# Configure pytest-asyncio
pytestmark = pytest.mark.asyncio

# Import modules for testing
try:
    from models.schema import ApiKeyCreate, SystemPromptCreate, SystemPromptUpdate, ApiKeyPromptAssociate
except ImportError as e:
    logger.error(f"Import error: {str(e)}")
    raise

# Test configuration - only include what's needed for the API key and prompt services
TEST_CONFIG = {
    'general': {
        'verbose': True,
        'inference_only': False  # Explicitly set to False to enable API key and prompt management
    },
    'mongodb': {  # Changed from internal_services.mongodb to match config manager structure
        'host': os.getenv("INTERNAL_SERVICES_MONGODB_HOST"),
        'port': int(os.getenv("INTERNAL_SERVICES_MONGODB_PORT", 27017)),
        'db': os.getenv("INTERNAL_SERVICES_MONGODB_DATABASE", "orbit_test_endpoints"),  # Changed from database to db
        'apikey_collection': 'api_keys_test',
        'username': os.getenv("INTERNAL_SERVICES_MONGODB_USERNAME"),
        'password': os.getenv("INTERNAL_SERVICES_MONGODB_PASSWORD")
    }
}

# Validate required environment variables
required_vars = ["INTERNAL_SERVICES_MONGODB_HOST", "INTERNAL_SERVICES_MONGODB_USERNAME", 
                 "INTERNAL_SERVICES_MONGODB_PASSWORD"]
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    pytest.skip(f"Missing required environment variables: {', '.join(missing_vars)}")

# Use a session-scoped event loop policy fixture to avoid deprecation warning
@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.get_event_loop_policy()

@pytest_asyncio.fixture
async def app():
    """Create a test application with test configuration."""
    # Set environment variable for test configuration
    os.environ['TEST_CONFIG'] = json.dumps(TEST_CONFIG)
    # Force use of test configuration
    os.environ['OIS_CONFIG_PATH'] = 'none'  # Prevent loading default config

    # Log MongoDB configuration values before creating app
    mongodb_config = TEST_CONFIG['mongodb']  # Updated path
    logger.info("MongoDB Configuration in test_orbit_endpoints.py:")
    logger.info(f"Host: {mongodb_config['host']}")
    logger.info(f"Port: {mongodb_config['port']}")
    logger.info(f"Database: {mongodb_config['db']}")  # Updated key
    logger.info(f"Username: {mongodb_config['username']}")
    logger.info(f"Password: {'*' * len(mongodb_config['password']) if mongodb_config['password'] else 'None'}")

    # Import the create_app function and create an app for testing
    from main import create_app
    app = create_app()
    
    # Force configuration to use test values
    app.state.config = TEST_CONFIG
    
    # Verify inference_only is False
    if app.state.config['general']['inference_only']:
        raise ValueError("Test configuration must have inference_only set to False")

    # Initialize MongoDB service first
    if hasattr(app.state, 'mongodb_service'):
        try:
            # Log MongoDB configuration values
            mongodb_config = TEST_CONFIG['mongodb']  # Updated path
            logger.info(f"MongoDB test configuration: host={mongodb_config['host']}, port={mongodb_config['port']}, database={mongodb_config['db']}")  # Updated key
            
            # Create a new MongoDB service instance with the test config
            mongodb_service = MongoDBService(TEST_CONFIG)
            await mongodb_service.initialize()
            
            # Replace the app's MongoDB service with our initialized one
            app.state.mongodb_service = mongodb_service
            
            # Initialize the database
            app.state.mongodb_service.database = app.state.mongodb_service.client[mongodb_config['db']]  # Updated key
            
            logger.info("MongoDB service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MongoDB service: {str(e)}")
            pytest.skip(f"Failed to connect to MongoDB: {e}")

    # Initialize other services
    if hasattr(app.state, 'api_key_service'):
        try:
            await app.state.api_key_service.initialize()
            logger.info("API key service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize API key service: {str(e)}")
            raise
    
    yield app
    
    # Cleanup: Drop the test database
    try:
        if hasattr(app.state, 'mongodb_service'):
            await app.state.mongodb_service.client.drop_database(TEST_CONFIG['internal_services']['mongodb']['database'])
            logger.info("Test database cleaned up successfully")
    except Exception as e:
        logger.error(f"Failed to clean up test database: {str(e)}")

@pytest_asyncio.fixture
async def client(app):
    """Fixture to provide a test client with the app configured."""
    with TestClient(app) as client:
        yield client

@pytest.mark.asyncio
async def test_api_key_endpoints(client):
    """Test the API key endpoints that orbit.py uses."""
    # 1. Create an API key - equivalent to 'orbit key create --collection docs --name "Test Client"'
    api_key_request = {
        "collection_name": "test_collection",
        "client_name": "Test Client",
        "notes": "Created by endpoint test"
    }
    response = client.post("/admin/api-keys", json=api_key_request)
    assert response.status_code == 200, f"Failed to create API key: {response.text}"
    result = response.json()
    
    # Check response structure
    assert "api_key" in result, "API key missing from response"
    assert "collection" in result, "Collection field missing from response"
    assert "created_at" in result, "created_at field missing from response"
    assert result["collection"] == "test_collection", "Wrong collection name"
    
    api_key = result["api_key"]
    logger.info(f"Created API key: ***{api_key[-4:]}")
    
    # 2. List API keys - equivalent to 'orbit key list'
    response = client.get("/admin/api-keys")
    assert response.status_code == 200, f"Failed to list API keys: {response.text}"
    api_keys = response.json()
    assert len(api_keys) >= 1, "Expected at least one API key"
    
    # 3. Get API key status - equivalent to 'orbit key status --key <KEY>'
    response = client.get(f"/admin/api-keys/{api_key}/status")
    assert response.status_code == 200, f"Failed to get API key status: {response.text}"
    status = response.json()
    assert status["active"] is True, "API key should be active"
    assert status["collection"] == "test_collection", "Wrong collection name in status"
    
    # 4. Deactivate API key - equivalent to 'orbit key deactivate --key <KEY>'
    deactivate_request = {"api_key": api_key}
    response = client.post("/admin/api-keys/deactivate", json=deactivate_request)
    assert response.status_code == 200, f"Failed to deactivate API key: {response.text}"
    
    # Verify deactivation
    response = client.get(f"/admin/api-keys/{api_key}/status")
    assert response.status_code == 200
    status = response.json()
    assert status["active"] is False, "API key should be inactive after deactivation"
    
    # 5. Delete API key - equivalent to 'orbit key delete --key <KEY>'
    response = client.delete(f"/admin/api-keys/{api_key}")
    assert response.status_code == 200, f"Failed to delete API key: {response.text}"
    
    # Verify deletion
    response = client.get(f"/admin/api-keys/{api_key}/status")
    assert response.status_code == 200
    status = response.json()
    assert status.get("exists") is False, "API key should not exist after deletion"

@pytest.mark.asyncio
async def test_prompt_endpoints(client):
    """Test the prompt endpoints that orbit.py uses."""
    # 1. Create a prompt - equivalent to 'orbit prompt create --name "Test Prompt" --file prompt.txt'
    prompt_request = {
        "name": "Test Prompt",
        "prompt": "This is a test system prompt for unit testing.",
        "version": "1.0"
    }
    response = client.post("/admin/prompts", json=prompt_request)
    assert response.status_code == 200, f"Failed to create prompt: {response.text}"
    result = response.json()
    
    # Check response structure
    assert "id" in result, "Prompt ID missing from response"
    assert "name" in result, "Prompt name missing from response"
    assert "prompt" in result, "Prompt text missing from response"
    assert "created_at" in result, "created_at field missing from response"
    assert result["name"] == "Test Prompt", "Wrong prompt name"
    
    prompt_id = result["id"]
    logger.info(f"Created prompt with ID: {prompt_id}")
    
    # 2. List prompts - equivalent to 'orbit prompt list'
    response = client.get("/admin/prompts")
    assert response.status_code == 200, f"Failed to list prompts: {response.text}"
    prompts = response.json()
    assert len(prompts) >= 1, "Expected at least one prompt"
    
    # 3. Get prompt - equivalent to 'orbit prompt get --id <ID>'
    response = client.get(f"/admin/prompts/{prompt_id}")
    assert response.status_code == 200, f"Failed to get prompt: {response.text}"
    prompt = response.json()
    assert prompt["name"] == "Test Prompt", "Wrong prompt name"
    assert prompt["prompt"] == "This is a test system prompt for unit testing.", "Wrong prompt text"
    
    # 4. Update prompt - equivalent to 'orbit prompt update --id <ID> --file new_prompt.txt'
    update_request = {
        "prompt": "This is an updated test system prompt.",
        "version": "1.1"
    }
    response = client.put(f"/admin/prompts/{prompt_id}", json=update_request)
    assert response.status_code == 200, f"Failed to update prompt: {response.text}"
    
    # Verify update
    response = client.get(f"/admin/prompts/{prompt_id}")
    assert response.status_code == 200
    prompt = response.json()
    assert prompt["prompt"] == "This is an updated test system prompt.", "Prompt wasn't updated"
    assert prompt["version"] == "1.1", "Prompt version wasn't updated"
    
    # 5. Delete prompt - equivalent to 'orbit prompt delete --id <ID>'
    response = client.delete(f"/admin/prompts/{prompt_id}")
    assert response.status_code == 200, f"Failed to delete prompt: {response.text}"
    
    # Verify deletion
    response = client.get(f"/admin/prompts/{prompt_id}")
    assert response.status_code == 404, "Prompt should not exist after deletion"

@pytest.mark.asyncio
async def test_integrated_operations(client):
    """Test operations that combine API key and prompt management that orbit.py uses."""
    # 1. Create a prompt
    prompt_request = {
        "name": "Integrated Test Prompt",
        "prompt": "This is a system prompt for integrated testing.",
        "version": "1.0"
    }
    response = client.post("/admin/prompts", json=prompt_request)
    assert response.status_code == 200
    prompt_result = response.json()
    prompt_id = prompt_result["id"]
    
    # 2. Create an API key
    api_key_request = {
        "collection_name": "integrated_test",
        "client_name": "Integrated Test Client",
        "notes": "For integrated testing"
    }
    response = client.post("/admin/api-keys", json=api_key_request)
    assert response.status_code == 200
    api_key_result = response.json()
    api_key = api_key_result["api_key"]
    
    # 3. Associate prompt with API key - equivalent to 'orbit prompt associate --key <KEY> --prompt-id <ID>'
    associate_request = {
        "prompt_id": prompt_id
    }
    response = client.post(f"/admin/api-keys/{api_key}/prompt", json=associate_request)
    assert response.status_code == 200, f"Failed to associate prompt with API key: {response.text}"
    
    # 4. Verify association in API key status
    response = client.get(f"/admin/api-keys/{api_key}/status")
    assert response.status_code == 200
    status = response.json()
    assert status.get("system_prompt") is not None, "No system prompt associated with API key"
    assert status["system_prompt"].get("id") == prompt_id, "Wrong prompt ID associated with API key"
    
    # 5. Clean up - delete API key and prompt
    client.delete(f"/admin/api-keys/{api_key}")
    client.delete(f"/admin/prompts/{prompt_id}")

@pytest.mark.asyncio
async def test_health_endpoint(client):
    """Test the health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200, f"Health check failed: {response.text}"
    health_status = response.json()
    assert "status" in health_status, "Status missing from health check response"
    assert health_status["status"] == "pass" or health_status["status"] == "ok", "Health check status not ok"

@pytest.mark.asyncio
async def test_key_create_with_prompt(client):
    """
    Test creating an API key with a prompt in one operation.
    
    This simulates the orbit.py command:
    orbit key create --collection test --name "Test" --prompt-file file.txt --prompt-name "Name"
    """
    # First create a prompt separately
    prompt_request = {
        "name": "CLI Test Prompt",
        "prompt": "This is a system prompt for CLI testing.",
        "version": "1.0"
    }
    response = client.post("/admin/prompts", json=prompt_request)
    assert response.status_code == 200
    prompt_result = response.json()
    prompt_id = prompt_result["id"]
    
    # Now create an API key
    api_key_request = {
        "collection_name": "cli_test",
        "client_name": "CLI Test Client",
        "notes": "For CLI testing"
    }
    response = client.post("/admin/api-keys", json=api_key_request)
    assert response.status_code == 200
    api_key_result = response.json()
    api_key = api_key_result["api_key"]
    
    # Associate the prompt with the API key
    associate_request = {
        "prompt_id": prompt_id
    }
    response = client.post(f"/admin/api-keys/{api_key}/prompt", json=associate_request)
    assert response.status_code == 200
    
    # Verify the API key has the prompt associated
    response = client.get(f"/admin/api-keys/{api_key}/status")
    assert response.status_code == 200
    status = response.json()
    assert status.get("system_prompt") is not None
    assert status["system_prompt"].get("id") == prompt_id
    
    # Clean up
    client.delete(f"/admin/api-keys/{api_key}")
    client.delete(f"/admin/prompts/{prompt_id}")
