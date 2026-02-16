"""
Ollama Embedding Service Test Suite

This module contains tests for the Ollama embedding service functionality:
- Connection testing
- Model configuration verification
- Embedding generation and format validation
- Dimensions validation
- Error handling
"""

import pytest
import requests
import yaml
import os
import sys
from typing import Dict, Any
from requests.exceptions import ReadTimeout, ConnectionError

# Get the absolute path to the server directory (parent of tests)
server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Get the absolute path to the project root directory (parent of server)
project_root = os.path.dirname(server_dir)

# Add server directory to Python path
sys.path.append(server_dir)

# Constants
DEFAULT_TIMEOUT = 120  # Increased timeout for local Ollama

@pytest.fixture
def config() -> Dict[str, Any]:
    """Load and return the configuration"""
    # Use the server's config loading function to handle the modular config structure
    try:
        from config.config_manager import load_config as load_server_config
        loaded_config = load_server_config()
        if loaded_config:
            return loaded_config
    except Exception as e:
        print(f"Failed to load config using config_manager: {e}")
        pass
    
    # Fallback to manual loading if that fails
    # Load embeddings.yaml from the config directory
    embeddings_path = os.path.join(project_root, 'config', 'embeddings.yaml')
    if not os.path.exists(embeddings_path):
        raise FileNotFoundError(f"Embeddings config file not found at {embeddings_path}")
    
    with open(embeddings_path, 'r') as file:
        embeddings_config = yaml.safe_load(file)
    
    # Also load base config.yaml if needed
    config_path = os.path.join(project_root, 'config', 'config.yaml')
    base_config = {}
    if os.path.exists(config_path):
        with open(config_path, 'r') as file:
            base_config = yaml.safe_load(file) or {}
    
    # Merge embeddings config into base config
    base_config.update(embeddings_config)
    
    return base_config

@pytest.fixture
def ollama_embedding_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and return Ollama embedding configuration"""
    ollama_config = config.get('embeddings', {}).get('ollama', {})
    
    assert ollama_config.get('base_url'), "Ollama base_url must be specified in config"
    assert ollama_config.get('model'), "Ollama model must be specified in config"
    return ollama_config

@pytest.fixture
def test_text() -> str:
    """Return a test text for embedding"""
    return "This is a test sentence for embedding generation."

def test_config_loading(ollama_embedding_config: Dict[str, Any]):
    """Test that the embedding configuration is loaded correctly"""
    assert ollama_embedding_config, "Ollama embedding configuration should not be empty"
    assert "model" in ollama_embedding_config, "Model should be specified in config"
    assert "base_url" in ollama_embedding_config, "Base URL should be specified in config"
    assert ollama_embedding_config["base_url"], "Base URL should not be empty"
    assert ollama_embedding_config["model"], "Model should not be empty"

def test_ollama_connection(ollama_embedding_config: Dict[str, Any]):
    """Test that Ollama service is accessible"""
    try:
        response = requests.get(
            f"{ollama_embedding_config['base_url']}/api/tags",
            timeout=DEFAULT_TIMEOUT
        )
        assert response.status_code == 200, f"Ollama service returned status code {response.status_code}"
    except ConnectionError as e:
        pytest.fail(f"Could not connect to Ollama service at {ollama_embedding_config['base_url']}. Is Ollama running? Error: {str(e)}")
    except ReadTimeout as e:
        pytest.fail(f"Connection to Ollama service timed out after {DEFAULT_TIMEOUT} seconds. Is Ollama running? Error: {str(e)}")

def test_ollama_embedding_generation(ollama_embedding_config: Dict[str, Any], test_text: str):
    """Test that Ollama generates a valid embedding"""
    model = ollama_embedding_config["model"]
    base_url = ollama_embedding_config["base_url"]
    
    try:
        payload = {
            "model": model,
            "prompt": test_text
        }
        
        # Optionally add dimensions if configured (some models support this)
        if "dimensions" in ollama_embedding_config:
            payload["options"] = {
                "embedding_size": ollama_embedding_config["dimensions"]
            }
        
        response = requests.post(
            f"{base_url}/api/embeddings",
            json=payload,
            timeout=DEFAULT_TIMEOUT
        )
        
        # Check response
        assert response.status_code == 200, f"Request failed with status code {response.status_code}: {response.text}"
        
        # Parse and validate response
        response_data = response.json()
        assert "embedding" in response_data, f"Response should contain 'embedding' field. Response: {response_data}"
        assert isinstance(response_data["embedding"], list), "Embedding should be a list"
        assert len(response_data["embedding"]) > 0, "Embedding should not be empty"
        
        # Verify all elements are floats
        for value in response_data["embedding"]:
            assert isinstance(value, (int, float)), f"All embedding values should be numeric, got {type(value)}"
        
        # Check dimensions if configured
        if "dimensions" in ollama_embedding_config:
            expected_dims = ollama_embedding_config["dimensions"]
            actual_dims = len(response_data["embedding"])
            # Some models may not respect the dimension option, so we'll just log it
            if actual_dims != expected_dims:
                print(f"Warning: Expected {expected_dims} dimensions, got {actual_dims}. This may be model-specific.")
        
    except ConnectionError as e:
        pytest.fail(f"Could not connect to Ollama service at {base_url}. Is Ollama running? Error: {str(e)}")
    except ReadTimeout as e:
        pytest.fail(f"Request to Ollama service timed out after {DEFAULT_TIMEOUT} seconds. Is Ollama running? Error: {str(e)}")

def test_ollama_embedding_dimensions(ollama_embedding_config: Dict[str, Any]):
    """Test that embeddings have consistent dimensions across multiple calls"""
    model = ollama_embedding_config["model"]
    base_url = ollama_embedding_config["base_url"]
    
    test_texts = [
        "First test sentence.",
        "Second test sentence with different length.",
        "Third sentence."
    ]
    
    try:
        dimensions = []
        for text in test_texts:
            payload = {
                "model": model,
                "prompt": text
            }
            
            response = requests.post(
                f"{base_url}/api/embeddings",
                json=payload,
                timeout=DEFAULT_TIMEOUT
            )
            
            assert response.status_code == 200, f"Request failed with status code {response.status_code}"
            response_data = response.json()
            assert "embedding" in response_data, "Response should contain 'embedding' field"
            
            dims = len(response_data["embedding"])
            dimensions.append(dims)
        
        # All embeddings should have the same dimensions
        assert len(set(dimensions)) == 1, f"Embeddings should have consistent dimensions, got: {dimensions}"
        
        # Log the dimension
        print(f"Embedding dimensions: {dimensions[0]}")
        
    except ConnectionError as e:
        pytest.fail(f"Could not connect to Ollama service at {base_url}. Is Ollama running? Error: {str(e)}")
    except ReadTimeout as e:
        pytest.fail(f"Request to Ollama service timed out after {DEFAULT_TIMEOUT} seconds. Is Ollama running? Error: {str(e)}")

def test_ollama_embedding_error_handling(ollama_embedding_config: Dict[str, Any]):
    """Test error handling with invalid requests"""
    base_url = ollama_embedding_config["base_url"]
    
    try:
        # Test with invalid model
        payload = {
            "model": "nonexistent_model",
            "prompt": "test"
        }
        
        response = requests.post(
            f"{base_url}/api/embeddings",
            json=payload,
            timeout=DEFAULT_TIMEOUT
        )
        
        # Should get an error response
        assert response.status_code != 200, "Invalid model should result in an error"
        response_data = response.json()
        assert "error" in response_data, f"Error response should contain 'error' field. Response: {response_data}"
        
    except ConnectionError as e:
        pytest.fail(f"Could not connect to Ollama service at {base_url}. Is Ollama running? Error: {str(e)}")
    except ReadTimeout as e:
        pytest.fail(f"Request to Ollama service timed out after {DEFAULT_TIMEOUT} seconds. Is Ollama running? Error: {str(e)}")

def test_ollama_embedding_empty_text(ollama_embedding_config: Dict[str, Any]):
    """Test that empty text is handled appropriately"""
    model = ollama_embedding_config["model"]
    base_url = ollama_embedding_config["base_url"]
    
    try:
        payload = {
            "model": model,
            "prompt": ""
        }
        
        response = requests.post(
            f"{base_url}/api/embeddings",
            json=payload,
            timeout=DEFAULT_TIMEOUT
        )
        
        # Some models may accept empty text, others may error
        # So we just check that we get a response (either success or error)
        assert response.status_code in [200, 400, 422], f"Unexpected status code: {response.status_code}"
        
        if response.status_code == 200:
            response_data = response.json()
            # If successful, should still return an embedding (possibly zeros or small values)
            if "embedding" in response_data:
                assert isinstance(response_data["embedding"], list), "Embedding should be a list"
        
    except ConnectionError as e:
        pytest.fail(f"Could not connect to Ollama service at {base_url}. Is Ollama running? Error: {str(e)}")
    except ReadTimeout as e:
        pytest.fail(f"Request to Ollama service timed out after {DEFAULT_TIMEOUT} seconds. Is Ollama running? Error: {str(e)}")

