"""
Ollama Service Test Suite

This module contains tests for the Ollama service functionality:
- Connection testing
- Model configuration verification
- Response format validation
- Error handling
"""

import pytest
import requests
import yaml
import json
import os
import sys
from typing import Dict, Any
from requests.exceptions import ReadTimeout, ConnectionError

# Get the absolute path to the server directory (parent of tests)
server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Get the absolute path to the project root directory (parent of server)
project_root = os.path.dirname(server_dir)

# Add server directory to Python path
sys.path.append(server_dir)

# Constants
DEFAULT_TIMEOUT = 120  # Increased timeout for local Ollama
LOCAL_OLLAMA_URL = "http://localhost:11434"

@pytest.fixture
def config() -> Dict[str, Any]:
    """Load and return the configuration"""
    config_path = os.path.join(project_root, 'config.yaml')
    with open(config_path, 'r') as file:
        return yaml.safe_load(file)

@pytest.fixture
def ollama_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and return Ollama configuration"""
    ollama_config = config.get('inference', {}).get('ollama', {})
    if not ollama_config:
        # Fallback to root level for backward compatibility
        ollama_config = config.get('ollama', {})
    
    # Ensure we're using local Ollama for tests
    ollama_config['base_url'] = LOCAL_OLLAMA_URL
    return ollama_config

@pytest.fixture
def test_query() -> str:
    """Return a test query"""
    return "What is the cost of the Beginner English fee for service course?"

def test_config_loading(ollama_config: Dict[str, Any]):
    """Test that the configuration is loaded correctly"""
    assert ollama_config, "Ollama configuration should not be empty"
    assert "model" in ollama_config, "Model should be specified in config"
    assert "base_url" in ollama_config, "Base URL should be specified in config"
    assert ollama_config["base_url"] == LOCAL_OLLAMA_URL, "Tests should use local Ollama instance"

def test_ollama_connection(ollama_config: Dict[str, Any]):
    """Test that Ollama service is accessible"""
    try:
        response = requests.get(
            f"{ollama_config['base_url']}/api/tags",
            timeout=DEFAULT_TIMEOUT
        )
        assert response.status_code == 200, f"Ollama service returned status code {response.status_code}"
    except ConnectionError as e:
        pytest.fail(f"Could not connect to Ollama service at {ollama_config['base_url']}. Is Ollama running? Error: {str(e)}")
    except ReadTimeout as e:
        pytest.fail(f"Connection to Ollama service timed out after {DEFAULT_TIMEOUT} seconds. Is Ollama running? Error: {str(e)}")

def test_ollama_response(ollama_config: Dict[str, Any], test_query: str):
    """Test that Ollama generates a valid response"""
    # Create request payload
    payload = {
        "model": ollama_config["model"],
        "prompt": test_query,
        "temperature": ollama_config.get("temperature", 0.1),
        "top_p": ollama_config.get("top_p", 0.8),
        "top_k": ollama_config.get("top_k", 20),
        "repeat_penalty": ollama_config.get("repeat_penalty", 1.1),
        "num_predict": ollama_config.get("num_predict", 1024),
        "stream": False
    }
    
    try:
        # Make request to Ollama
        response = requests.post(
            f"{ollama_config['base_url']}/api/generate",
            json=payload,
            timeout=DEFAULT_TIMEOUT
        )
        
        # Check response
        assert response.status_code == 200, f"Request failed with status code {response.status_code}"
        
        # Parse and validate response
        response_data = response.json()
        assert "response" in response_data, "Response should contain 'response' field"
        assert isinstance(response_data["response"], str), "Response should be a string"
        assert len(response_data["response"]) > 0, "Response should not be empty"
        
    except ConnectionError as e:
        pytest.fail(f"Could not connect to Ollama service at {ollama_config['base_url']}. Is Ollama running? Error: {str(e)}")
    except ReadTimeout as e:
        pytest.fail(f"Request to Ollama service timed out after {DEFAULT_TIMEOUT} seconds. Is Ollama running? Error: {str(e)}")

def test_ollama_error_handling(ollama_config: Dict[str, Any]):
    """Test error handling with invalid requests"""
    # Test with invalid model
    payload = {
        "model": "nonexistent_model",
        "prompt": "test",
        "stream": False
    }
    
    try:
        response = requests.post(
            f"{ollama_config['base_url']}/api/generate",
            json=payload,
            timeout=DEFAULT_TIMEOUT
        )
        
        # Should get an error response
        assert response.status_code != 200, "Invalid model should result in an error"
        response_data = response.json()
        assert "error" in response_data, "Error response should contain 'error' field"
        
    except ConnectionError as e:
        pytest.fail(f"Could not connect to Ollama service at {ollama_config['base_url']}. Is Ollama running? Error: {str(e)}")
    except ReadTimeout as e:
        pytest.fail(f"Request to Ollama service timed out after {DEFAULT_TIMEOUT} seconds. Is Ollama running? Error: {str(e)}")