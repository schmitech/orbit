"""
Integration test for the clean pipeline architecture.

This test verifies that the clean pipeline architecture works correctly
without any legacy compatibility layers.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from typing import Dict, Any

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inference.pipeline.base import ProcessingContext
from inference.pipeline_factory import PipelineFactory
from inference.pipeline.providers.llm_provider import LLMProvider
from services.pipeline_chat_service import PipelineChatService


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for testing."""
    
    async def initialize(self) -> None:
        """Mock initialization."""
        pass
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """Mock response generation."""
        return f"Mock response to: {prompt}"
    
    async def generate_stream(self, prompt: str, **kwargs):
        """Mock streaming response generation."""
        yield "Mock"
        yield " response"
        yield f" to: {prompt}"
    
    async def close(self) -> None:
        """Mock cleanup."""
        pass
    
    async def validate_config(self) -> bool:
        """Mock config validation."""
        return True


class MockRetriever:
    """Mock retriever for testing."""
    
    async def get_relevant_context(self, query: str, adapter_name: str) -> list:
        """Mock context retrieval."""
        return [
            {
                "content": f"Mock document about {query}",
                "metadata": {"source": "test_source"},
                "confidence": 0.8
            }
        ]


class MockPromptService:
    """Mock prompt service for testing."""
    
    async def get_prompt_by_id(self, prompt_id: str) -> Dict[str, Any]:
        """Mock prompt retrieval."""
        return {
            "prompt": "You are a helpful test assistant.",
            "name": "Test Prompt"
        }


@pytest.mark.asyncio
async def test_pipeline_factory_creation():
    """Test that the pipeline factory can create pipelines with clean providers."""
    config = {
        "general": {
            "inference_provider": "openai",
            "inference_only": False,
            "verbose": True
        },
        "inference": {
            "openai": {
                "api_key": "test_key",
                "model": "gpt-4"
            }
        }
    }
    
    factory = PipelineFactory(config)
    
    # Create mock services
    retriever = MockRetriever()
    prompt_service = MockPromptService()
    
    # Create pipeline
    pipeline = factory.create_pipeline_with_services(
        retriever=retriever,
        prompt_service=prompt_service
    )
    
    assert pipeline is not None
    assert len(pipeline.steps) > 0


@pytest.mark.asyncio
async def test_pipeline_processing():
    """Test that the pipeline can process a request with clean providers."""
    config = {
        "general": {
            "inference_provider": "openai",
            "inference_only": False,
            "verbose": True
        },
        "inference": {
            "openai": {
                "api_key": "test_key",
                "model": "gpt-4"
            }
        }
    }
    
    factory = PipelineFactory(config)
    
    # Create mock services
    retriever = MockRetriever()
    prompt_service = MockPromptService()
    
    # Create service container and replace LLM provider with mock
    container = factory.create_service_container(
        retriever=retriever,
        prompt_service=prompt_service
    )
    
    # Replace the real provider with our mock
    mock_provider = MockLLMProvider()
    container.register_singleton('llm_provider', mock_provider)
    
    # Create pipeline
    pipeline = factory.create_pipeline(container)
    
    # Create processing context
    context = ProcessingContext(
        message="What is AI?",
        adapter_name="test_collection",
        context_messages=[]
    )
    
    # Process through pipeline
    result = await pipeline.process(context)
    
    # Verify results
    assert not result.has_error()
    assert result.response is not None
    assert len(result.retrieved_docs) > 0


class MockablePipelineChatService(PipelineChatService):
    """Test version of PipelineChatService that allows mock provider injection."""
    
    def __init__(self, config: Dict[str, Any], logger_service, mock_provider=None,
                 chat_history_service=None, llm_guard_service=None, moderator_service=None,
                 retriever=None, reranker_service=None, prompt_service=None):
        """Initialize with option to inject mock provider."""
        super().__init__(config, logger_service, chat_history_service, llm_guard_service,
                        moderator_service, retriever, reranker_service, prompt_service)
        
        # If mock provider is provided, replace the real one
        if mock_provider:
            self.pipeline.container.register_singleton('llm_provider', mock_provider)


@pytest.mark.asyncio
async def test_pipeline_chat_service():
    """Test that the pipeline chat service works with clean providers."""
    config = {
        "general": {
            "inference_provider": "openai",
            "inference_only": False,
            "verbose": True
        },
        "inference": {
            "openai": {
                "api_key": "test_key",
                "model": "gpt-4"
            }
        },
        "chat_history": {
            "enabled": False
        },
        "messages": {}
    }
    
    # Create mock services
    retriever = MockRetriever()
    prompt_service = MockPromptService()
    logger_service = Mock()
    logger_service.log_conversation = AsyncMock()
    mock_provider = MockLLMProvider()
    
    # Create pipeline chat service with mock provider
    chat_service = MockablePipelineChatService(
        config=config,
        logger_service=logger_service,
        retriever=retriever,
        prompt_service=prompt_service,
        mock_provider=mock_provider
    )
    
    # Test chat processing
    result = await chat_service.process_chat(
        message="What is AI?",
        client_ip="127.0.0.1",
        adapter_name="test_collection"
    )
    
    # Verify results
    assert "error" not in result
    assert "response" in result
    assert result["metadata"]["pipeline_used"] is True


@pytest.mark.asyncio
async def test_pipeline_streaming():
    """Test that the pipeline supports streaming with clean providers."""
    config = {
        "general": {
            "inference_provider": "openai",
            "inference_only": False,
            "verbose": True
        },
        "inference": {
            "openai": {
                "api_key": "test_key",
                "model": "gpt-4"
            }
        }
    }
    
    factory = PipelineFactory(config)
    
    # Create mock services
    retriever = MockRetriever()
    prompt_service = MockPromptService()
    
    # Create pipeline
    pipeline = factory.create_pipeline_with_services(
        retriever=retriever,
        prompt_service=prompt_service
    )
    
    # Create processing context
    context = ProcessingContext(
        message="What is AI?",
        adapter_name="test_collection",
        context_messages=[]
    )
    
    # Process through pipeline with streaming
    chunks = []
    async for chunk in pipeline.process_stream(context):
        chunks.append(chunk)
    
    # Verify streaming results
    assert len(chunks) > 0


@pytest.mark.asyncio
async def test_ollama_provider_support():
    """Test that the pipeline supports Ollama provider."""
    config = {
        "general": {
            "inference_provider": "ollama",
            "inference_only": False,
            "verbose": True
        },
        "inference": {
            "ollama": {
                "base_url": "http://localhost:11434",
                "model": "gemma3:1b",
                "temperature": 0.1
            }
        }
    }
    
    factory = PipelineFactory(config)
    
    # Create mock services
    retriever = MockRetriever()
    prompt_service = MockPromptService()
    
    # Create pipeline with Ollama provider
    pipeline = factory.create_pipeline_with_services(
        retriever=retriever,
        prompt_service=prompt_service
    )
    
    assert pipeline is not None
    assert len(pipeline.steps) > 0


if __name__ == "__main__":
    # Run tests
    asyncio.run(test_pipeline_factory_creation())
    asyncio.run(test_pipeline_processing())
    asyncio.run(test_pipeline_chat_service())
    asyncio.run(test_pipeline_streaming())
    asyncio.run(test_ollama_provider_support())
    print("All clean pipeline integration tests passed!") 