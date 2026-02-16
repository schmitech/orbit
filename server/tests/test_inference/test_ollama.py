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
    # Look for config.yaml in the config directory first, then fallback to root
    config_path = os.path.join(project_root, 'config', 'config.yaml')
    if not os.path.exists(config_path):
        config_path = os.path.join(project_root, 'config.yaml')
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at {config_path}")
    
    with open(config_path, 'r') as file:
        base_config = yaml.safe_load(file)
        
    # Load inference.yaml separately if it exists
    inference_path = os.path.join(project_root, 'config', 'inference.yaml')
    if os.path.exists(inference_path):
        with open(inference_path, 'r') as file:
            inference_config = yaml.safe_load(file)
            if 'inference' not in base_config:
                base_config['inference'] = {}
            base_config['inference'].update(inference_config.get('inference', {}))
    
    return base_config

@pytest.fixture
def ollama_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and return Ollama configuration, resolving presets if needed"""
    ollama_config = config.get('inference', {}).get('ollama', {})
    if not ollama_config:
        # Fallback to root level for backward compatibility
        ollama_config = config.get('ollama', {})

    # Check if using a preset
    use_preset = ollama_config.get('use_preset')
    if use_preset:
        # Load ollama presets from config/ollama.yaml
        ollama_presets_path = os.path.join(project_root, 'config', 'ollama.yaml')
        if os.path.exists(ollama_presets_path):
            with open(ollama_presets_path, 'r') as file:
                presets_config = yaml.safe_load(file)
                presets = presets_config.get('ollama_presets', {})
                preset = presets.get(use_preset)
                if preset:
                    # Merge preset with any overrides from main config
                    merged_config = preset.copy()
                    for key, value in ollama_config.items():
                        if key != 'use_preset' and value is not None:
                            merged_config[key] = value
                    ollama_config = merged_config
                else:
                    pytest.skip(f"Ollama preset '{use_preset}' not found in ollama.yaml")
        else:
            pytest.skip("config/ollama.yaml not found for preset resolution")

    assert ollama_config.get('base_url'), "Ollama base_url must be specified in config"
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
    assert ollama_config["base_url"], "Base URL should not be empty"

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
    model = ollama_config["model"]
    
    # Check if model uses chat format (OpenAI-compatible models)
    use_chat_api = model.startswith('gpt-') or 'openai' in model.lower()
    
    try:
        if use_chat_api:
            # Use chat endpoint for OpenAI-compatible models
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": test_query}],
                "temperature": ollama_config.get("temperature", 0.1),
                "top_p": ollama_config.get("top_p", 0.8),
                "top_k": ollama_config.get("top_k", 20),
                "repeat_penalty": ollama_config.get("repeat_penalty", 1.1),
                "max_tokens": ollama_config.get("num_predict", 1024),
                "stream": False
            }
            
            response = requests.post(
                f"{ollama_config['base_url']}/api/chat",
                json=payload,
                timeout=DEFAULT_TIMEOUT
            )
            
            # Check response
            assert response.status_code == 200, f"Request failed with status code {response.status_code}"
            
            # Parse and validate response
            response_data = response.json()
            assert "message" in response_data, "Response should contain 'message' field"
            assert "content" in response_data["message"], "Message should contain 'content' field"
            assert isinstance(response_data["message"]["content"], str), "Response content should be a string"
            assert len(response_data["message"]["content"]) > 0, "Response should not be empty"
        else:
            # Use generate endpoint for traditional Ollama models
            payload = {
                "model": model,
                "prompt": test_query,
                "temperature": ollama_config.get("temperature", 0.1),
                "top_p": ollama_config.get("top_p", 0.8),
                "top_k": ollama_config.get("top_k", 20),
                "repeat_penalty": ollama_config.get("repeat_penalty", 1.1),
                "num_predict": ollama_config.get("num_predict", 1024),
                "stream": False
            }
            
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
    # Determine which API to test based on a real model in config
    real_model = ollama_config["model"]
    use_chat_api = real_model.startswith('gpt-') or 'openai' in real_model.lower()
    
    try:
        if use_chat_api:
            # Test with invalid model using chat endpoint
            payload = {
                "model": "nonexistent_model",
                "messages": [{"role": "user", "content": "test"}],
                "stream": False
            }
            
            response = requests.post(
                f"{ollama_config['base_url']}/api/chat",
                json=payload,
                timeout=DEFAULT_TIMEOUT
            )
        else:
            # Test with invalid model using generate endpoint
            payload = {
                "model": "nonexistent_model",
                "prompt": "test",
                "stream": False
            }
            
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