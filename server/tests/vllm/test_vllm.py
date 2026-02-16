"""
vLLM Service Test Suite

This module contains tests for the vLLM service functionality:
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

#  Quick test
# curl http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" -d '{"model": "Qwen/Qwen2.5-1.5B-Instruct", "messages": [{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": "Hello, how are you?"}], "temperature": 0.7, "max_tokens": 100}' | jq

# Get the absolute path to the server directory (parent of tests)
server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Get the absolute path to the project root directory (parent of server)
project_root = os.path.dirname(server_dir)

# Add server directory to Python path
sys.path.append(server_dir)

# Constants
DEFAULT_TIMEOUT = 30

@pytest.fixture
def config() -> Dict[str, Any]:
    """Load and return the configuration"""
    # Use the server's config loading function to handle the modular config structure
    try:
        from config.config_manager import load_config as load_server_config
        config = load_server_config()
        if config is None:
            raise Exception("Config loading returned None")
        return config
    except Exception as e:
        print(f"Failed to load config using server config manager: {e}")
        # Fallback to manual loading if that fails
        # Look for config.yaml in the config directory first, then fallback to root
        config_paths = [
            os.path.join(project_root, 'config', 'config.yaml'),
            os.path.join(project_root, 'config.yaml'),
            os.path.join(server_dir, 'config', 'config.yaml'),
            os.path.join(server_dir, 'config.yaml'),
        ]
        
        for config_path in config_paths:
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r') as file:
                        config = yaml.safe_load(file)
                        if config is None:
                            continue
                        
                        # If this is the main config.yaml, we need to load the inference.yaml separately
                        if 'import' in config:
                            # Load inference.yaml manually
                            inference_path = os.path.join(os.path.dirname(config_path), 'inference.yaml')
                            if os.path.exists(inference_path):
                                with open(inference_path, 'r') as inf_file:
                                    inference_config = yaml.safe_load(inf_file)
                                    if inference_config:
                                        config.update(inference_config)
                        
                        print(f"Loaded config from: {config_path}")
                        return config
                except Exception as e:
                    print(f"Failed to load config from {config_path}: {e}")
                    continue
        
        # If we get here, we couldn't load any config
        pytest.fail("Could not load configuration from any expected location")

@pytest.fixture
def vllm_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and return vLLM configuration"""
    if config is None:
        pytest.fail("Configuration is None - cannot extract vLLM config")
    
    vllm_config = config.get('inference', {}).get('vllm', {})
    
    if not vllm_config:
        pytest.skip("vLLM configuration not found in config. Skipping vLLM tests.")
    
    # Check for required fields but don't fail if they're missing - just warn
    missing_fields = []
    if not vllm_config.get('host'):
        missing_fields.append('host')
    if not vllm_config.get('port'):
        missing_fields.append('port')
    if not vllm_config.get('model'):
        missing_fields.append('model')
    
    if missing_fields:
        pytest.skip(f"vLLM configuration missing required fields: {missing_fields}. Skipping vLLM tests.")
    
    return vllm_config

@pytest.fixture
def test_query() -> str:
    """Return a test query"""
    return "What is the capital of France?"

def test_config_loading(vllm_config: Dict[str, Any]):
    """Test that the configuration is loaded correctly"""
    assert vllm_config, "vLLM configuration should not be empty"
    assert "model" in vllm_config, "Model should be specified in config"
    assert "host" in vllm_config, "Host should be specified in config"
    assert "port" in vllm_config, "Port should be specified in config"
    assert vllm_config["host"], "Host should not be empty"
    assert vllm_config["port"], "Port should not be empty"
    assert vllm_config["model"], "Model should not be empty"

def test_vllm_connection(vllm_config: Dict[str, Any]):
    """Test that vLLM service is accessible"""
    base_url = f"http://{vllm_config['host']}:{vllm_config['port']}"
    
    try:
        response = requests.get(
            f"{base_url}/v1/models",
            timeout=DEFAULT_TIMEOUT
        )
        assert response.status_code == 200, f"vLLM service returned status code {response.status_code}"
        
        # Verify the model is available
        models_data = response.json()
        assert "data" in models_data, "Response should contain 'data' field"
        
        model_ids = [model["id"] for model in models_data["data"]]
        assert vllm_config["model"] in model_ids, f"Model {vllm_config['model']} not found in available models: {model_ids}"
        
    except ConnectionError as e:
        pytest.fail(f"Could not connect to vLLM service at {base_url}. Is vLLM running? Error: {str(e)}")
    except ReadTimeout as e:
        pytest.fail(f"Connection to vLLM service timed out after {DEFAULT_TIMEOUT} seconds. Is vLLM running? Error: {str(e)}")

def test_vllm_chat_completion(vllm_config: Dict[str, Any], test_query: str):
    """Test that vLLM generates a valid chat completion response"""
    base_url = f"http://{vllm_config['host']}:{vllm_config['port']}"
    
    # Create request payload
    payload = {
        "model": vllm_config["model"],
        "messages": [{"role": "user", "content": test_query}],
        "temperature": vllm_config.get("temperature", 0.1),
        "top_p": vllm_config.get("top_p", 0.8),
        "top_k": vllm_config.get("top_k", 20),
        "max_tokens": vllm_config.get("max_tokens", 1024),
        "stream": False
    }
    
    try:
        # Make request to vLLM
        response = requests.post(
            f"{base_url}/v1/chat/completions",
            json=payload,
            timeout=DEFAULT_TIMEOUT
        )
        
        # Check response
        assert response.status_code == 200, f"Request failed with status code {response.status_code}"
        
        # Parse and validate response
        response_data = response.json()
        assert "choices" in response_data, "Response should contain 'choices' field"
        assert len(response_data["choices"]) > 0, "Response should have at least one choice"
        
        choice = response_data["choices"][0]
        assert "message" in choice, "Choice should contain 'message' field"
        assert "content" in choice["message"], "Message should contain 'content' field"
        
        content = choice["message"]["content"]
        assert isinstance(content, str), "Content should be a string"
        assert len(content) > 0, "Content should not be empty"
        
        print(f"vLLM response: {content[:100]}...")
        
    except ConnectionError as e:
        pytest.fail(f"Could not connect to vLLM service at {base_url}. Is vLLM running? Error: {str(e)}")
    except ReadTimeout as e:
        pytest.fail(f"Request to vLLM service timed out after {DEFAULT_TIMEOUT} seconds. Is vLLM running? Error: {str(e)}")

def test_vllm_error_handling(vllm_config: Dict[str, Any]):
    """Test error handling with invalid requests"""
    base_url = f"http://{vllm_config['host']}:{vllm_config['port']}"
    
    # Test with invalid model
    payload = {
        "model": "nonexistent_model",
        "messages": [{"role": "user", "content": "test"}],
        "stream": False
    }
    
    try:
        response = requests.post(
            f"{base_url}/v1/chat/completions",
            json=payload,
            timeout=DEFAULT_TIMEOUT
        )
        
        # Should get an error response
        assert response.status_code != 200, "Invalid model should result in an error"
        
    except ConnectionError as e:
        pytest.fail(f"Could not connect to vLLM service at {base_url}. Is vLLM running? Error: {str(e)}")
    except ReadTimeout as e:
        pytest.fail(f"Request to vLLM service timed out after {DEFAULT_TIMEOUT} seconds. Is vLLM running? Error: {str(e)}")

def test_vllm_provider_integration(vllm_config: Dict[str, Any], test_query: str):
    """Test the vLLM provider integration"""
    try:
        from inference.pipeline.providers.vllm_provider import VLLMProvider
        
        # Create a minimal config for the provider
        provider_config = {
            'inference': {
                'vllm': vllm_config
            },
            'general': {
            }
        }
        
        # Initialize the provider
        provider = VLLMProvider(provider_config)
        
        # Test connection validation
        import asyncio
        is_valid = asyncio.run(provider.validate_config())
        assert is_valid, "vLLM provider configuration should be valid"
        
        # Initialize the provider
        asyncio.run(provider.initialize())
        
        # Test generation
        response = asyncio.run(provider.generate(test_query))
        assert response, "vLLM provider should generate a response"
        assert isinstance(response, str), "Response should be a string"
        assert len(response) > 0, "Response should not be empty"
        
        # Clean up
        asyncio.run(provider.close())
        
        print("vLLM provider integration test passed")
        
    except ImportError as e:
        pytest.fail(f"Could not import vLLM provider: {str(e)}")
    except Exception as e:
        pytest.fail(f"vLLM provider integration test failed: {str(e)}")

def test_vllm_provider_streaming(vllm_config: Dict[str, Any], test_query: str):
    """Test the vLLM provider streaming functionality"""
    try:
        from inference.pipeline.providers.vllm_provider import VLLMProvider
        import asyncio
        
        # Create a minimal config for the provider
        provider_config = {
            'inference': {
                'vllm': vllm_config
            },
            'general': {
            }
        }
        
        # Initialize the provider
        provider = VLLMProvider(provider_config)
        
        # Initialize the provider
        asyncio.run(provider.initialize())
        
        # Test streaming generation
        async def test_stream():
            chunks = []
            async for chunk in provider.generate_stream(test_query):
                assert isinstance(chunk, str), "Stream chunk should be a string"
                chunks.append(chunk)
            
            # Verify we got some chunks
            assert len(chunks) > 0, "Should receive at least one chunk"
            
            # Verify the complete response
            complete_response = ''.join(chunks)
            assert len(complete_response) > 0, "Complete response should not be empty"
            
            return complete_response
        
        response = asyncio.run(test_stream())
        print(f"vLLM streaming response (first 100 chars): {response[:100]}...")
        
        # Clean up
        asyncio.run(provider.close())
        
        print("vLLM provider streaming test passed")
        
    except ImportError as e:
        pytest.fail(f"Could not import vLLM provider: {str(e)}")
    except Exception as e:
        pytest.fail(f"vLLM provider streaming test failed: {str(e)}") 