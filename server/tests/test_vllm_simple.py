"""
Simple pytest test module for vLLM client
"""

import pytest
import asyncio
import yaml
import os
import sys

from typing import Dict, Any

# Always resolve project root as the parent of this file's parent directory
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(project_root)

from server.inference.clients.vllm import QAVLLMClient

@pytest.fixture(scope="module")
def vllm_config() -> Dict[str, Any]:
    """Load vLLM config from inference.yaml at project root config/"""
    config_path = os.path.join(project_root, 'config', 'inference.yaml')
    with open(config_path, 'r') as file:
        config = yaml.safe_load(file)
    vllm_conf = config['inference']['vllm']
    assert vllm_conf, "vLLM config not found in inference.yaml"
    return vllm_conf

@pytest.fixture(scope="module")
def vllm_client(vllm_config):
    """Create a QAVLLMClient instance for testing"""
    client_config = {
        'inference': {
            'vllm': vllm_config
        },
        'general': {
            'verbose': True,
            'inference_only': True
        }
    }
    return QAVLLMClient(client_config)

@pytest.mark.asyncio
async def test_vllm_connection(vllm_client):
    """Test connection to vLLM server"""
    is_connected = await vllm_client.verify_connection()
    assert is_connected, "Failed to connect to vLLM server"

@pytest.mark.asyncio
async def test_vllm_response_generation(vllm_client):
    """Test response generation from vLLM server"""
    test_message = "What is the capital of France?"
    response = await vllm_client.generate_response(
        message=test_message,
        adapter_name="test_adapter"
    )
    assert isinstance(response, dict), "Response should be a dict"
    assert "response" in response, f"No 'response' in result: {response}"
    assert "Paris" in response["response"], f"Expected 'Paris' in response, got: {response['response']}"
    assert response.get("tokens", 0) > 0, "Tokens used should be > 0"
    assert response.get("processing_time", 0) >= 0, "Processing time should be non-negative" 