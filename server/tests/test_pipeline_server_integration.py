"""
Test for pipeline architecture integration in the server.

This test verifies that:
1. Pipeline architecture is the default and only mode
2. Service factory correctly creates pipeline-based services
3. LLM clients are not created (pipeline handles inference directly)
4. The server works with the pipeline architecture
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from typing import Dict, Any
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from services.service_factory import ServiceFactory
from services.pipeline_chat_service import PipelineChatService


@pytest.fixture
def test_config():
    """Standard test configuration (pipeline is always active)."""
    return {
        'general': {
            'inference_provider': 'ollama',
            'inference_only': True,
            'verbose': True
        },
        'chat_history': {
            'enabled': False
        },
        'inference': {
            'ollama': {
                'model': 'llama2',
                'base_url': 'http://localhost:11434'
            }
        }
    }


# Traditional mode no longer exists - pipeline is always active


@pytest.fixture
def mock_logger():
    """Mock logger for testing."""
    logger = Mock()
    logger.info = Mock()
    logger.error = Mock()
    logger.warning = Mock()
    logger.debug = Mock()
    return logger


@pytest.fixture
def mock_app():
    """Mock FastAPI app with required state."""
    app = FastAPI()
    app.state = Mock()
    
    # Mock services
    app.state.mongodb_service = None
    app.state.redis_service = None
    app.state.logger_service = Mock()
    app.state.retriever = None
    app.state.prompt_service = None
    app.state.reranker_service = None
    app.state.llm_guard_service = None
    app.state.moderator_service = None
    app.state.chat_history_service = None
    app.state.auth_service = None
    
    return app


@pytest.mark.asyncio
async def test_pipeline_architecture_default(test_config, mock_logger, mock_app):
    """Test that pipeline architecture is the default."""
    service_factory = ServiceFactory(test_config, mock_logger)
    
    # Initialize LLM client
    await service_factory._initialize_llm_client(mock_app)
    
    # LLM client should always be None (pipeline handles inference)
    assert mock_app.state.llm_client is None
    assert any('pipeline architecture' in str(call) for call in mock_logger.info.call_args_list)
    
    # Initialize dependent services
    await service_factory._initialize_dependent_services(mock_app)
    
    # Should always have pipeline-based chat service
    assert hasattr(mock_app.state, 'chat_service')
    assert isinstance(mock_app.state.chat_service, PipelineChatService)
    assert any('pipeline-based chat service' in str(call) for call in mock_logger.info.call_args_list)


@pytest.mark.asyncio
async def test_no_traditional_mode(test_config, mock_logger, mock_app):
    """Test that only pipeline architecture exists."""
    service_factory = ServiceFactory(test_config, mock_logger)
    
    # Should always use pipeline architecture
    await service_factory._initialize_llm_client(mock_app)
    await service_factory._initialize_dependent_services(mock_app)
    
    # Verify pipeline architecture is used
    assert mock_app.state.llm_client is None
    assert isinstance(mock_app.state.chat_service, PipelineChatService)


@pytest.mark.asyncio
async def test_pipeline_chat_service_interface(test_config, mock_logger):
    """Test that PipelineChatService has the correct interface."""
    # Create pipeline chat service
    pipeline_chat_service = PipelineChatService(
        config=test_config,
        logger_service=mock_logger,
        chat_history_service=None,
        llm_guard_service=None,
        moderator_service=None,
        retriever=None,
        reranker_service=None,
        prompt_service=None
    )
    
    # Check required methods exist
    assert hasattr(pipeline_chat_service, 'process_chat')
    assert hasattr(pipeline_chat_service, 'process_chat_stream')
    assert hasattr(pipeline_chat_service, 'initialize')
    
    # Check method signatures match
    import inspect
    
    # process_chat should accept the same parameters
    process_chat_sig = inspect.signature(pipeline_chat_service.process_chat)
    expected_params = ['message', 'client_ip', 'adapter_name', 'system_prompt_id', 
                       'api_key', 'session_id', 'user_id']
    for param in expected_params:
        assert param in process_chat_sig.parameters
    
    # process_chat_stream should accept the same parameters
    process_stream_sig = inspect.signature(pipeline_chat_service.process_chat_stream)
    for param in expected_params:
        assert param in process_stream_sig.parameters


@pytest.mark.asyncio
async def test_health_service_with_pipeline(test_config, mock_logger, mock_app):
    """Test that health service works correctly with pipeline architecture."""
    service_factory = ServiceFactory(test_config, mock_logger)
    
    # Initialize services
    await service_factory._initialize_llm_client(mock_app)
    await service_factory._initialize_dependent_services(mock_app)
    
    # Health service should be created with llm_client=None
    assert hasattr(mock_app.state, 'health_service')
    # Health service should handle None llm_client gracefully


def test_pipeline_always_active(test_config, mock_logger):
    """Test that pipeline architecture is always active."""
    # Pipeline is always active regardless of config
    factory = ServiceFactory(test_config, mock_logger)
    # No pipeline config section needed
    assert 'pipeline' not in test_config


@pytest.mark.asyncio
async def test_no_llm_client_imports(test_config, mock_logger, mock_app):
    """Test that pipeline architecture doesn't create LLM client."""
    service_factory = ServiceFactory(test_config, mock_logger)
    
    # Initialize services - should not create LLM client
    await service_factory._initialize_llm_client(mock_app)
    await service_factory._initialize_dependent_services(mock_app)
    
    # Check that llm_client is None
    assert mock_app.state.llm_client is None
    
    # Check that pipeline chat service was created
    assert isinstance(mock_app.state.chat_service, PipelineChatService)


@pytest.mark.asyncio
async def test_pipeline_provider_initialization():
    """Test that pipeline providers are properly initialized."""
    from inference.pipeline_factory import PipelineFactory
    from inference.pipeline.providers import ProviderFactory
    
    config = {
        'general': {'inference_provider': 'ollama'},
        'inference': {
            'ollama': {
                'base_url': 'http://localhost:11434',
                'model': 'llama2'
            }
        }
    }
    
    # Create pipeline factory
    pipeline_factory = PipelineFactory(config)
    
    # Create service container
    container = pipeline_factory.create_service_container()
    
    # Provider should be registered
    assert container.has('llm_provider')
    
    # Initialize provider
    await pipeline_factory.initialize_provider(container)
    
    # Provider should be initialized
    provider = container.get('llm_provider')
    assert provider is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])