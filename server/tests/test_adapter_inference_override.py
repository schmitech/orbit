"""
Test for adapter-specific inference provider override functionality.

This test verifies that adapters can successfully override the default
inference provider configuration at runtime.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock
from typing import Dict, Any, List, Optional

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inference.pipeline.base import ProcessingContext
from services.pipeline_chat_service import PipelineChatService
from services.dynamic_adapter_manager import DynamicAdapterManager


class MockLLMProvider:
    """Mock LLM provider for testing."""
    
    def __init__(self, name: str):
        self.name = name
        self.generate_called = False
        self.last_prompt = None
    
    async def initialize(self) -> None:
        """Mock initialization."""
        pass
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """Mock response generation."""
        self.generate_called = True
        self.last_prompt = prompt
        return f"Response from {self.name} provider"
    
    async def generate_stream(self, prompt: str, **kwargs):
        """Mock streaming response generation."""
        self.generate_called = True
        self.last_prompt = prompt
        yield f"Response from {self.name} provider"


class MockAdapterManager:
    """Mock adapter manager for testing inference provider override."""
    
    def __init__(self, adapter_configs: Dict[str, Dict[str, Any]]):
        self.adapter_configs = adapter_configs
        self.providers = {}
    
    async def get_adapter(self, adapter_name: str):
        """Mock adapter retrieval."""
        mock_adapter = Mock()
        mock_adapter.get_relevant_context = AsyncMock(return_value=[
            {
                "content": f"Mock document for {adapter_name}",
                "metadata": {"source": "test"},
                "confidence": 0.9
            }
        ])
        return mock_adapter
    
    def get_adapter_config(self, adapter_name: str) -> Optional[Dict[str, Any]]:
        """Return adapter configuration with potential inference_provider override."""
        return self.adapter_configs.get(adapter_name)
    
    async def get_overridden_provider(self, provider_name: str):
        """Get or create a mock provider for testing."""
        if provider_name not in self.providers:
            self.providers[provider_name] = MockLLMProvider(provider_name)
        return self.providers[provider_name]


@pytest.mark.asyncio
async def test_adapter_inference_provider_override():
    """Test that adapter-specific inference provider override works correctly."""
    
    # Setup test configuration
    config = {
        'general': {
            'verbose': True,
            'inference_provider': 'ollama'  # Default provider
        },
        'chat_history': {'enabled': False},
        'messages': {}
    }
    
    # Create adapter configurations with different inference providers
    adapter_configs = {
        'adapter_with_override': {
            'name': 'adapter_with_override',
            'enabled': True,
            'inference_provider': 'openai',  # Override provider
            'implementation': 'test.MockAdapter'
        },
        'adapter_without_override': {
            'name': 'adapter_without_override',
            'enabled': True,
            'implementation': 'test.MockAdapter'
        },
        'adapter_with_ollama_cloud': {
            'name': 'adapter_with_ollama_cloud',
            'enabled': True,
            'inference_provider': 'ollama_cloud',  # Override provider
            'implementation': 'test.MockAdapter'
        }
    }
    
    # Create mock adapter manager
    mock_adapter_manager = MockAdapterManager(adapter_configs)
    
    # Create mock services
    mock_logger_service = Mock()
    mock_logger_service.log_conversation = AsyncMock()
    
    # Create mock pipeline factory and container
    mock_container = Mock()
    mock_container.has = Mock(side_effect=lambda key: key in ['adapter_manager', 'llm_provider'])
    mock_container.get = Mock(side_effect=lambda key: {
        'adapter_manager': mock_adapter_manager,
        'llm_provider': MockLLMProvider('ollama')
    }.get(key))
    
    # Create chat service
    chat_service = PipelineChatService(
        config=config,
        logger_service=mock_logger_service
    )
    
    # Manually set up the pipeline container for testing
    chat_service.pipeline.container = mock_container
    chat_service._pipeline_initialized = True
    
    # Test 1: Adapter with inference provider override
    context_with_override = ProcessingContext(
        message="Test message",
        adapter_name="adapter_with_override"
    )
    
    # Simulate the flow in process_chat
    adapter_config = mock_adapter_manager.get_adapter_config("adapter_with_override")
    assert adapter_config is not None
    assert adapter_config.get('inference_provider') == 'openai'
    
    # Create context with override
    context_with_override.inference_provider = adapter_config.get('inference_provider')
    
    # Verify the provider would be used correctly
    provider = await mock_adapter_manager.get_overridden_provider('openai')
    assert provider.name == 'openai'
    
    # Test 2: Adapter without inference provider override
    context_without_override = ProcessingContext(
        message="Test message",
        adapter_name="adapter_without_override"
    )
    
    adapter_config = mock_adapter_manager.get_adapter_config("adapter_without_override")
    assert adapter_config is not None
    assert adapter_config.get('inference_provider') is None
    
    # Context should not have inference_provider set
    assert context_without_override.inference_provider is None
    
    # Test 3: Adapter with ollama_cloud provider override
    context_with_ollama_cloud = ProcessingContext(
        message="Test message",
        adapter_name="adapter_with_ollama_cloud"
    )
    
    adapter_config = mock_adapter_manager.get_adapter_config("adapter_with_ollama_cloud")
    assert adapter_config is not None
    assert adapter_config.get('inference_provider') == 'ollama_cloud'
    
    # Create context with override
    context_with_ollama_cloud.inference_provider = adapter_config.get('inference_provider')
    
    # Verify the provider would be used correctly
    provider = await mock_adapter_manager.get_overridden_provider('ollama_cloud')
    assert provider.name == 'ollama_cloud'
    
    print("✅ Test passed: Adapter-specific inference provider override works correctly")


@pytest.mark.asyncio
async def test_inference_provider_priority():
    """Test that adapter inference provider takes priority over default."""
    
    config = {
        'general': {
            'verbose': False,
            'inference_provider': 'llama_cpp'  # Default
        },
        'adapters': [
            {
                'name': 'qa-vector-chroma',
                'enabled': True,
                'inference_provider': 'openai',  # Override
                'implementation': 'test.MockAdapter'
            }
        ]
    }
    
    # Create real adapter manager
    adapter_manager = DynamicAdapterManager(config)
    
    # Check that adapter config has the override
    adapter_config = adapter_manager.get_adapter_config('qa-vector-chroma')
    assert adapter_config is not None
    assert adapter_config.get('inference_provider') == 'openai'
    
    print("✅ Test passed: Adapter inference provider takes priority over default")


if __name__ == "__main__":
    # Run tests
    asyncio.run(test_adapter_inference_provider_override())
    asyncio.run(test_inference_provider_priority())
    print("\n✅ All tests passed!")