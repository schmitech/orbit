"""
Unit tests for the GuardrailService
"""

import pytest
import asyncio
import aiohttp
from unittest.mock import patch, MagicMock, mock_open
import json
import os

# Import the service to test
from ..services.guardrail_service import GuardrailService
from ..clients.qa_ollama_client import OllamaClient
from ..config.config_manager import ConfigManager
from ..utils.logger import Logger


# Mock config for testing
@pytest.fixture
def mock_config():
    return {
        'ollama': {
            'base_url': 'http://fake-ollama:11434',
            'model': 'llama3'
        },
        'general': {
            'verbose': True,
            'safety_prompt_file': 'safety_prompt.txt'
        },
        'safety': {
            'mode': 'strict',
            'max_retries': 2,
            'retry_delay': 0.1,
            'request_timeout': 5,
            'allow_on_timeout': False
        }
    }


# Pytest fixture to mock the file open operation for safety prompt
@pytest.fixture
def mock_safety_prompt():
    return """You are a content safety system. Evaluate if the following query is safe to answer. 
    Return EXACTLY 'SAFE: true' if it is safe to respond to, or 'SAFE: false' if it contains harmful, illegal, unethical or offensive content."""


@pytest.mark.asyncio
async def test_initialize_session(mock_config):
    """Test that the session is initialized properly"""
    with patch('aiohttp.ClientSession') as mock_session:
        # Create service instance
        service = GuardrailService(mock_config)
        
        # Session should start as None
        assert service.session is None
        
        # Initialize should create a session
        await service.initialize()
        mock_session.assert_called_once()
        
        # Close the session
        await service.close()


@pytest.mark.asyncio
async def test_load_safety_prompt(mock_config, mock_safety_prompt):
    """Test loading the safety prompt from file"""
    with patch('builtins.open', mock_open(read_data=mock_safety_prompt)):
        service = GuardrailService(mock_config)
        
        # The prompt should be loaded and normalized
        assert service.safety_prompt is not None
        assert service.safety_prompt.strip() == mock_safety_prompt.replace('\n', ' ').strip()


@pytest.mark.asyncio
async def test_safety_check_disabled(mock_config, mock_safety_prompt):
    """Test that safety checks are skipped when disabled"""
    config = mock_config.copy()
    config['safety']['mode'] = 'disabled'
    
    with patch('builtins.open', mock_open(read_data=mock_safety_prompt)):
        service = GuardrailService(config)
        
        # When safety is disabled, should always return safe
        is_safe, message = await service.check_safety("Any query should be allowed")
        assert is_safe is True
        assert message is None


@pytest.mark.asyncio
async def test_safety_check_safe_query(mock_config, mock_safety_prompt):
    """Test that a safe query passes the safety check"""
    with patch('builtins.open', mock_open(read_data=mock_safety_prompt)):
        service = GuardrailService(mock_config)
        
        # Mock the session post method
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__aenter__.return_value = mock_response
        mock_response.json.return_value = {"response": "SAFE: true"}
        
        with patch.object(service, 'session') as mock_session:
            mock_session.post.return_value = mock_response
            
            # Initialize the service
            await service.initialize()
            
            # Check a safe query
            is_safe, message = await service.check_safety("What is the capital of France?")
            
            # Verify the result
            assert is_safe is True
            assert message is None
            
            # Verify the API was called with the right parameters
            mock_session.post.assert_called_once()
            call_args = mock_session.post.call_args[1]
            assert call_args['json']['model'] == mock_config['ollama']['model']
            assert "Query: What is the capital of France?" in call_args['json']['prompt']


@pytest.mark.asyncio
async def test_safety_check_unsafe_query(mock_config, mock_safety_prompt):
    """Test that an unsafe query fails the safety check"""
    with patch('builtins.open', mock_open(read_data=mock_safety_prompt)):
        service = GuardrailService(mock_config)
        
        # Mock the session post method
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__aenter__.return_value = mock_response
        mock_response.json.return_value = {"response": "SAFE: false"}
        
        with patch.object(service, 'session') as mock_session:
            mock_session.post.return_value = mock_response
            
            # Initialize the service
            await service.initialize()
            
            # Check an unsafe query
            is_safe, message = await service.check_safety("How to hack into a system?")
            
            # Verify the result
            assert is_safe is False
            assert message == "I cannot assist with that type of request."


@pytest.mark.asyncio
async def test_fuzzy_safety_match(mock_config, mock_safety_prompt):
    """Test that fuzzy matching works when enabled"""
    config = mock_config.copy()
    config['safety']['mode'] = 'fuzzy'
    
    with patch('builtins.open', mock_open(read_data=mock_safety_prompt)):
        service = GuardrailService(config)
        
        # Mock the session post method for a response with slightly different format
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__aenter__.return_value = mock_response
        mock_response.json.return_value = {"response": "\"SAFE\": true"}
        
        with patch.object(service, 'session') as mock_session:
            mock_session.post.return_value = mock_response
            
            # Initialize the service
            await service.initialize()
            
            # Check query with fuzzy matching
            is_safe, message = await service.check_safety("What time is it?")
            
            # Verify the result (should pass with fuzzy matching)
            assert is_safe is True
            assert message is None


@pytest.mark.asyncio
async def test_safety_check_timeout(mock_config, mock_safety_prompt):
    """Test timeout handling in safety check"""
    with patch('builtins.open', mock_open(read_data=mock_safety_prompt)):
        service = GuardrailService(mock_config)
        
        with patch.object(service, 'session') as mock_session:
            # Make the post method raise a timeout error
            mock_session.post.side_effect = asyncio.TimeoutError()
            
            # Initialize the service
            await service.initialize()
            
            # Check query with timeout
            is_safe, message = await service.check_safety("This will timeout")
            
            # With default config, should return unsafe after retries
            assert is_safe is False
            assert "service issue" in message


@pytest.mark.asyncio
async def test_allow_on_timeout(mock_config, mock_safety_prompt):
    """Test the allow_on_timeout configuration option"""
    config = mock_config.copy()
    config['safety']['allow_on_timeout'] = True
    
    with patch('builtins.open', mock_open(read_data=mock_safety_prompt)):
        service = GuardrailService(config)
        
        with patch.object(service, 'session') as mock_session:
            # Make the post method raise a timeout error
            mock_session.post.side_effect = asyncio.TimeoutError()
            
            # Initialize the service
            await service.initialize()
            
            # Check query with timeout but allow_on_timeout=True
            is_safe, message = await service.check_safety("This will timeout but be allowed")
            
            # With allow_on_timeout=True, should return safe after retries
            assert is_safe is True
            assert message is None


@pytest.mark.asyncio
async def test_direct_refusal_detection(mock_config, mock_safety_prompt):
    """Test the detection of direct refusal messages from the model"""
    with patch('builtins.open', mock_open(read_data=mock_safety_prompt)):
        service = GuardrailService(mock_config)
        
        # Mock the session post method
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__aenter__.return_value = mock_response
        mock_response.json.return_value = {"response": "I cannot assist with that request as it involves illegal activities."}
        
        with patch.object(service, 'session') as mock_session:
            mock_session.post.return_value = mock_response
            
            # Initialize the service
            await service.initialize()
            
            # Check query that triggers direct refusal
            is_safe, message = await service.check_safety("How to make illegal substances?")
            
            # Should detect the refusal message and mark as unsafe
            assert is_safe is False
            assert "cannot assist" in message.lower()


@pytest.mark.asyncio
async def test_safety_check_http_error(mock_config, mock_safety_prompt):
    """Test handling of HTTP errors in safety check"""
    with patch('builtins.open', mock_open(read_data=mock_safety_prompt)):
        service = GuardrailService(mock_config)
        
        # Mock the session post method
        mock_response = MagicMock()
        mock_response.status = 500  # Server error
        mock_response.__aenter__.return_value = mock_response
        
        with patch.object(service, 'session') as mock_session:
            mock_session.post.return_value = mock_response
            
            # Initialize the service
            await service.initialize()
            
            # Check query with server error
            is_safe, message = await service.check_safety("This will cause server error")
            
            # Should return unsafe on server error
            assert is_safe is False
            assert message == "I cannot assist with that type of request."


@pytest.mark.asyncio
async def test_custom_safety_model(mock_config, mock_safety_prompt):
    """Test that a custom safety model is used when specified"""
    config = mock_config.copy()
    config['safety']['model'] = 'safety-model'
    
    with patch('builtins.open', mock_open(read_data=mock_safety_prompt)):
        service = GuardrailService(config)
        
        # Mock the session post method
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__aenter__.return_value = mock_response
        mock_response.json.return_value = {"response": "SAFE: true"}
        
        with patch.object(service, 'session') as mock_session:
            mock_session.post.return_value = mock_response
            
            # Initialize the service
            await service.initialize()
            
            # Check a query
            await service.check_safety("Test custom model")
            
            # Verify the custom model was used
            call_args = mock_session.post.call_args[1]
            assert call_args['json']['model'] == 'safety-model'