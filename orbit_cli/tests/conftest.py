"""Shared pytest fixtures for ORBIT CLI tests."""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, MagicMock

from orbit_cli.config import ConfigManager
from orbit_cli.api import ApiManager
from orbit_cli.server import ServerController
from orbit_cli.output.formatter import OutputFormatter


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_config_dir(temp_dir):
    """Create a temporary configuration directory."""
    config_dir = temp_dir / ".orbit"
    config_dir.mkdir(exist_ok=True)
    return config_dir


@pytest.fixture
def mock_config_manager(temp_config_dir):
    """Create a mock configuration manager."""
    config_manager = ConfigManager(config_dir=temp_config_dir)
    return config_manager


@pytest.fixture
def mock_api_manager():
    """Create a mock API manager."""
    api_manager = Mock(spec=ApiManager)
    
    # Mock common methods
    api_manager.token = "test_token"
    api_manager.server_url = "http://localhost:3000"
    api_manager.ensure_authenticated = Mock()
    api_manager.login = Mock(return_value={"username": "admin", "token": "test_token"})
    api_manager.logout = Mock(return_value={"message": "Logged out"})
    api_manager.get_current_user = Mock(return_value={
        "username": "admin",
        "role": "admin",
        "id": "test_id"
    })
    
    # Mock sub-managers
    api_manager.auth = Mock()
    api_manager.users = Mock()
    api_manager.keys = Mock()
    api_manager.prompts = Mock()
    
    return api_manager


@pytest.fixture
def mock_server_controller():
    """Create a mock server controller."""
    controller = Mock(spec=ServerController)
    controller.start = Mock(return_value=True)
    controller.stop = Mock(return_value=True)
    controller.restart = Mock(return_value=True)
    controller.status = Mock(return_value={
        "status": "running",
        "pid": 12345,
        "uptime": "2h 30m",
        "memory_mb": 256.5,
        "cpu_percent": 2.5
    })
    return controller


@pytest.fixture
def mock_formatter():
    """Create a mock output formatter."""
    formatter = Mock(spec=OutputFormatter)
    formatter.format = "table"
    formatter.color = True
    formatter.console = MagicMock()
    return formatter


@pytest.fixture
def mock_api_response():
    """Create a mock successful API response."""
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"status": "success", "data": {}}
    response.text = '{"status": "success", "data": {}}'
    response.headers = {"content-type": "application/json"}
    response.raise_for_status = Mock()
    response.elapsed = Mock()
    response.elapsed.total_seconds.return_value = 0.1
    return response


@pytest.fixture
def mock_failed_api_response():
    """Create a mock failed API response."""
    response = Mock()
    response.status_code = 400
    response.json.return_value = {"error": "Bad request", "message": "Invalid parameters"}
    response.text = '{"error": "Bad request", "message": "Invalid parameters"}'
    response.headers = {"content-type": "application/json"}
    response.elapsed = Mock()
    response.elapsed.total_seconds.return_value = 0.1
    
    def raise_for_status():
        import requests
        raise requests.exceptions.HTTPError(response=response)
    
    response.raise_for_status = raise_for_status
    return response


@pytest.fixture
def sample_api_key():
    """Sample API key for testing."""
    return {
        "api_key": "api_test_key_123456789",
        "client_name": "Test Client",
        "collection": "test_collection",
        "active": True,
        "created_at": "2024-01-01T00:00:00Z"
    }


@pytest.fixture
def sample_user():
    """Sample user for testing."""
    return {
        "id": "user_123",
        "username": "testuser",
        "role": "user",
        "active": True,
        "created_at": "2024-01-01T00:00:00Z"
    }


@pytest.fixture
def sample_prompt():
    """Sample prompt for testing."""
    return {
        "id": "prompt_123",
        "name": "Test Prompt",
        "prompt": "You are a helpful assistant.",
        "version": "1.0",
        "created_at": "2024-01-01T00:00:00Z"
    }


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        "server": {
            "default_url": "http://localhost:3000",
            "timeout": 30,
            "retry_attempts": 3
        },
        "auth": {
            "credential_storage": "file",
            "use_keyring": False,
            "session_duration_hours": 12
        },
        "output": {
            "format": "table",
            "color": True,
            "verbose": False
        }
    }


@pytest.fixture
def mock_response():
    """Create a mock HTTP response."""
    class MockResponse:
        def __init__(self, json_data=None, status_code=200, text="", headers=None):
            self.json_data = json_data
            self.status_code = status_code
            self.text = text
            self.headers = headers or {"content-type": "application/json"}
            self.elapsed = Mock(total_seconds=Mock(return_value=0.1))
        
        def json(self):
            if self.json_data is not None:
                return self.json_data
            raise ValueError("No JSON data")
        
        def raise_for_status(self):
            if self.status_code >= 400:
                import requests
                raise requests.exceptions.HTTPError(response=self)
    
    return MockResponse


# Additional fixtures for test data consistency
@pytest.fixture
def sample_api_key_data():
    """Sample API key data structure."""
    return {
        "api_key": "test_api_key_12345",
        "client_name": "Test Client",
        "collection": "test_collection",
        "active": True,
        "created_at": "2024-01-01T10:00:00Z",
        "last_used": "2024-01-01T12:00:00Z"
    }


@pytest.fixture
def sample_user_data():
    """Sample user data structure."""
    return {
        "id": "user_12345",
        "username": "testuser",
        "email": "test@example.com",
        "role": "user",
        "active": True,
        "created_at": "2024-01-01T10:00:00Z",
        "last_login": "2024-01-01T12:00:00Z"
    }


@pytest.fixture
def sample_prompt_data():
    """Sample prompt data structure."""
    return {
        "id": "prompt_12345",
        "name": "Test Prompt",
        "prompt": "You are a helpful assistant specialized in testing.",
        "category": "testing",
        "version": "1.0",
        "active": True,
        "created_at": "2024-01-01T10:00:00Z"
    }


@pytest.fixture
def mock_base_client():
    """Create a mock base API client."""
    from orbit_cli.api.base_client import BaseAPIClient
    client = Mock(spec=BaseAPIClient)
    client.get = Mock()
    client.post = Mock()
    client.put = Mock()
    client.patch = Mock()
    client.delete = Mock()
    client.token = None
    client._get_headers = Mock(return_value={})
    client._build_url = Mock(side_effect=lambda endpoint: f"http://localhost:8000{endpoint}")
    return client