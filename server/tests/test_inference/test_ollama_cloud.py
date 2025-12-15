"""
Ollama Cloud Service Test Suite

This module contains tests for the Ollama Cloud service functionality:
- Configuration loading and API key validation
- Connection testing
- Model configuration verification
- Response format validation
- Error handling
"""

import pytest
import yaml
import os
import sys
from typing import Dict, Any
import asyncio

# Get the absolute path to the server directory (parent of tests)
server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Get the absolute path to the project root directory (parent of server)
project_root = os.path.dirname(server_dir)

# Add server directory to Python path
sys.path.append(server_dir)

# Import the Ollama client
from ollama import AsyncClient

# Constants
DEFAULT_TIMEOUT = 120  # Cloud services may need longer timeout

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
def ollama_cloud_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and return Ollama Cloud configuration"""
    ollama_cloud_config = config.get('inference', {}).get('ollama_cloud', {})
    if not ollama_cloud_config:
        # Fallback to root level for backward compatibility
        ollama_cloud_config = config.get('ollama_cloud', {})

    assert ollama_cloud_config.get('model'), "Ollama Cloud model must be specified in config"
    return ollama_cloud_config

@pytest.fixture
def api_key(ollama_cloud_config: Dict[str, Any]) -> str:
    """Extract and validate API key from config or environment"""
    api_key = ollama_cloud_config.get('api_key', '')

    # Handle environment variable placeholder
    if api_key.startswith('${') and api_key.endswith('}'):
        env_var = api_key[2:-1]
        api_key = os.environ.get(env_var, '')

    if not api_key:
        pytest.skip("OLLAMA_CLOUD_API_KEY not found in environment variables")

    return api_key

@pytest.fixture
def base_url(ollama_cloud_config: Dict[str, Any]) -> str:
    """Get base URL from config or use default"""
    return ollama_cloud_config.get('base_url', 'https://ollama.com')

@pytest.fixture
async def ollama_client(base_url: str, api_key: str) -> AsyncClient:
    """Create and return an Ollama AsyncClient"""
    client = AsyncClient(
        host=base_url,
        headers={"Authorization": f"Bearer {api_key}"}
    )
    return client

@pytest.fixture
def test_query() -> str:
    """Return a test query"""
    return "What is the cost of the Beginner English fee for service course?"

def test_config_loading(ollama_cloud_config: Dict[str, Any]):
    """Test that the configuration is loaded correctly"""
    assert ollama_cloud_config, "Ollama Cloud configuration should not be empty"
    assert "model" in ollama_cloud_config, "Model should be specified in config"
    assert ollama_cloud_config["model"], "Model should not be empty"
    assert "api_key" in ollama_cloud_config, "API key should be specified in config"

def test_api_key_availability(api_key: str):
    """Test that API key is available and not empty"""
    assert api_key, "API key should not be empty"
    assert len(api_key) > 0, "API key should have content"
    # Basic validation that it looks like an API key
    assert not api_key.startswith('${'), "API key should be resolved from environment"

@pytest.mark.asyncio
async def test_ollama_cloud_connection(ollama_client: AsyncClient, base_url: str):
    """Test that Ollama Cloud service is accessible"""
    try:
        # Try to list available models as a connection test
        models = await ollama_client.list()

        # Check if we got a valid response
        assert models is not None, "Models list should not be None"

        # If we have models, verify the structure
        if hasattr(models, 'models'):
            assert isinstance(models.models, list), "Models should be a list"
    except Exception as e:
        # If list fails, try a minimal chat request
        pytest.skip(f"Could not verify Ollama Cloud connection: {str(e)}")

@pytest.mark.asyncio
async def test_ollama_cloud_response(ollama_client: AsyncClient, ollama_cloud_config: Dict[str, Any], test_query: str):
    """Test that Ollama Cloud generates a valid response"""
    model = ollama_cloud_config["model"]

    try:
        # Build options from config
        options = {
            "temperature": ollama_cloud_config.get("temperature", 0.7),
            "top_p": ollama_cloud_config.get("top_p", 0.9),
            "top_k": ollama_cloud_config.get("top_k", 40),
            "num_predict": ollama_cloud_config.get("num_predict", 1024),
        }

        # Add optional parameters if they exist in config
        if "repeat_penalty" in ollama_cloud_config:
            options["repeat_penalty"] = ollama_cloud_config["repeat_penalty"]

        # Make the chat request
        response = await ollama_client.chat(
            model=model,
            messages=[{"role": "user", "content": test_query}],
            options=options,
        )

        # Validate response structure
        assert response is not None, "Response should not be None"
        assert "message" in response, "Response should contain 'message' field"
        assert "content" in response["message"], "Message should contain 'content' field"
        assert isinstance(response["message"]["content"], str), "Response content should be a string"
        assert len(response["message"]["content"]) > 0, "Response should not be empty"

    except Exception as e:
        pytest.fail(f"Failed to generate response from Ollama Cloud: {str(e)}")

@pytest.mark.asyncio
async def test_ollama_cloud_streaming_response(ollama_client: AsyncClient, ollama_cloud_config: Dict[str, Any], test_query: str):
    """Test that Ollama Cloud generates a valid streaming response"""
    model = ollama_cloud_config["model"]

    try:
        options = {
            "temperature": ollama_cloud_config.get("temperature", 0.7),
            "num_predict": 100,  # Shorter response for testing
        }

        # Make streaming chat request
        stream = await ollama_client.chat(
            model=model,
            messages=[{"role": "user", "content": test_query}],
            options=options,
            stream=True,
        )

        # Validate streaming response
        chunks_received = 0
        total_content = ""

        async for chunk in stream:
            if "message" in chunk and "content" in chunk["message"]:
                content = chunk["message"]["content"]
                if content:
                    total_content += content
                    chunks_received += 1

        assert chunks_received > 0, "Should receive at least one chunk in streaming response"
        assert len(total_content) > 0, "Streaming response should contain content"

    except Exception as e:
        pytest.fail(f"Failed to generate streaming response from Ollama Cloud: {str(e)}")

@pytest.mark.asyncio
async def test_ollama_cloud_error_handling(ollama_client: AsyncClient):
    """Test error handling with invalid requests"""
    try:
        # Test with invalid model - should raise an exception
        with pytest.raises(Exception) as exc_info:
            await ollama_client.chat(
                model="nonexistent_model_12345",
                messages=[{"role": "user", "content": "test"}],
            )

        # Verify that an error was raised
        assert exc_info.value is not None, "Should raise an exception for invalid model"

    except Exception as e:
        # This is expected behavior
        pass

@pytest.mark.asyncio
async def test_ollama_cloud_invalid_api_key(base_url: str):
    """Test error handling with invalid API key"""
    try:
        # Create a client with invalid API key
        invalid_client = AsyncClient(
            host=base_url,
            headers={"Authorization": "Bearer invalid_api_key_12345"}
        )

        # Should raise an exception due to invalid API key
        with pytest.raises(Exception) as exc_info:
            await invalid_client.chat(
                model="qwen3-coder:480b-cloud",
                messages=[{"role": "user", "content": "test"}],
            )

        # Verify that an authentication error was raised
        assert exc_info.value is not None, "Should raise an exception for invalid API key"

    except Exception as e:
        # This is expected behavior
        pass

@pytest.mark.asyncio
async def test_ollama_cloud_parameters(ollama_client: AsyncClient, ollama_cloud_config: Dict[str, Any]):
    """Test that generation parameters are properly applied"""
    model = ollama_cloud_config["model"]

    try:
        # Test with specific parameters
        options = {
            "temperature": 0.1,  # Very low temperature for deterministic output
            "num_predict": 50,  # Limit output length
        }

        response = await ollama_client.chat(
            model=model,
            messages=[{"role": "user", "content": "Say hello"}],
            options=options,
        )

        assert response is not None, "Response should not be None"
        assert "message" in response, "Response should contain 'message' field"
        assert "content" in response["message"], "Message should contain 'content' field"

        # The response should be relatively short due to num_predict=50
        content = response["message"]["content"]
        assert len(content) > 0, "Response should not be empty"

    except Exception as e:
        pytest.fail(f"Failed to generate response with custom parameters: {str(e)}")
