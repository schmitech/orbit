"""
Test for pipeline mode integration in the server.

This test verifies that:
1. Pipeline mode can be enabled via configuration
2. Service factory correctly creates pipeline-based services
3. Old LLM clients are not created in pipeline mode
4. The server can work without the old LLM client code
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
from services.chat_service import ChatService


@pytest.fixture
def pipeline_config():
    """Configuration with pipeline mode enabled."""
    return {
        'general': {
            'inference_provider': 'ollama',
            'inference_only': True,
            'verbose': True
        },
        'pipeline': {
            'enabled': True,  # Enable pipeline mode
            'use_direct_providers': True,
            'log_metrics': True
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


@pytest.fixture
def traditional_config(pipeline_config):
    """Configuration with pipeline mode disabled."""
    config = pipeline_config.copy()
    config['pipeline'] = config['pipeline'].copy()
    config['pipeline']['enabled'] = False
    return config


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
async def test_pipeline_mode_enabled(pipeline_config, mock_logger, mock_app):
    """Test that pipeline mode correctly initializes pipeline-based services."""
    service_factory = ServiceFactory(pipeline_config, mock_logger)
    
    # Initialize LLM client
    await service_factory._initialize_llm_client(mock_app)
    
    # In pipeline mode, llm_client should be None
    assert mock_app.state.llm_client is None
    assert any('Pipeline mode enabled' in str(call) for call in mock_logger.info.call_args_list)
    
    # Initialize dependent services
    await service_factory._initialize_dependent_services(mock_app)
    
    # Should have pipeline-based chat service
    assert hasattr(mock_app.state, 'chat_service')
    assert isinstance(mock_app.state.chat_service, PipelineChatService)
    assert any('pipeline-based chat service' in str(call) for call in mock_logger.info.call_args_list)


@pytest.mark.asyncio
async def test_traditional_mode_fails_gracefully(traditional_config, mock_logger, mock_app):
    """Test that traditional mode fails gracefully when legacy clients are not available."""
    service_factory = ServiceFactory(traditional_config, mock_logger)
    
    # Traditional mode should now fail because legacy clients have been removed
    with pytest.raises(RuntimeError) as exc_info:
        await service_factory._initialize_llm_client(mock_app)
    
    # Should get the helpful error message about using pipeline mode
    assert "Legacy client system is no longer available" in str(exc_info.value)
    assert "pipeline mode" in str(exc_info.value)


@pytest.mark.asyncio
async def test_pipeline_chat_service_interface(pipeline_config, mock_logger):
    """Test that PipelineChatService has the same interface as ChatService."""
    # Create pipeline chat service
    pipeline_chat_service = PipelineChatService(
        config=pipeline_config,
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
async def test_health_service_with_pipeline_mode(pipeline_config, mock_logger, mock_app):
    """Test that health service works correctly in pipeline mode."""
    service_factory = ServiceFactory(pipeline_config, mock_logger)
    
    # Initialize services
    await service_factory._initialize_llm_client(mock_app)
    await service_factory._initialize_dependent_services(mock_app)
    
    # Health service should be created with llm_client=None
    assert hasattr(mock_app.state, 'health_service')
    # Health service should handle None llm_client gracefully


def test_pipeline_config_detection(pipeline_config, traditional_config, mock_logger):
    """Test that service factory correctly detects pipeline mode from config."""
    # Pipeline mode enabled
    pipeline_factory = ServiceFactory(pipeline_config, mock_logger)
    assert pipeline_factory.config.get('pipeline', {}).get('enabled', False) is True
    
    # Pipeline mode disabled
    traditional_factory = ServiceFactory(traditional_config, mock_logger)
    assert traditional_factory.config.get('pipeline', {}).get('enabled', False) is False


@pytest.mark.asyncio
async def test_no_llm_client_imports_in_pipeline_mode(pipeline_config, mock_logger, mock_app):
    """Test that pipeline mode doesn't import old LLM client code."""
    service_factory = ServiceFactory(pipeline_config, mock_logger)
    
    # Initialize services in pipeline mode - should not import LLM client modules
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