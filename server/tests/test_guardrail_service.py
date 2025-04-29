"""
Unit tests for the GuardrailService
"""

import pytest
import asyncio
import aiohttp
from unittest.mock import patch, MagicMock, mock_open
import json
import os
import sys
import logging

# Add the server directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the service to test
from services.guardrail_service import GuardrailService
from server.inference.clients.ollama import OllamaClient
from config.config_manager import load_config

# Configure logging
logging.basicConfig(level=logging.INFO)

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
            'enabled': True,
            'mode': 'strict',
            'provider_override': 'ollama',
            'model': 'shieldgemma:2b',
            'max_retries': 3,
            'retry_delay': 1.0,
            'request_timeout': 10,
            'allow_on_timeout': False,
            'temperature': 0.0,
            'top_p': 1.0,
            'top_k': 1,
            'num_predict': 20,
            'stream': False,
            'repeat_penalty': 1.1
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
    config['safety']['enabled'] = False
    
    with patch('builtins.open', mock_open(read_data=mock_safety_prompt)):
        service = GuardrailService(config)
        
        # When safety is disabled, should always return safe
        is_safe, message = await service.check_safety("Any query should be allowed")
        assert is_safe is True
        assert message is None


@pytest.mark.asyncio
async def test_safety_check_provider_override(mock_config, mock_safety_prompt):
    """Test that the provider override is used when specified"""
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
            await service.check_safety("What is the capital of France?")
            
            # Verify the API was called with the right parameters
            mock_session.post.assert_called_once()
            call_args = mock_session.post.call_args[1]
            assert call_args['json']['model'] == mock_config['safety']['model']
            assert call_args['json']['temperature'] == mock_config['safety']['temperature']
            assert call_args['json']['top_p'] == mock_config['safety']['top_p']
            assert call_args['json']['top_k'] == mock_config['safety']['top_k']
            assert call_args['json']['num_predict'] == mock_config['safety']['num_predict']
            assert call_args['json']['repeat_penalty'] == mock_config['safety']['repeat_penalty']


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
            assert call_args['json']['model'] == mock_config['safety']['model']
            assert call_args['json']['temperature'] == mock_config['safety']['temperature']
            assert call_args['json']['top_p'] == mock_config['safety']['top_p']
            assert call_args['json']['top_k'] == mock_config['safety']['top_k']
            assert call_args['json']['num_predict'] == mock_config['safety']['num_predict']
            assert call_args['json']['repeat_penalty'] == mock_config['safety']['repeat_penalty']
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
            
            # Verify the number of retries matches config
            assert mock_session.post.call_count == mock_config['safety']['max_retries'] + 1
            
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

if __name__ == '__main__':
    # Run the tests
    pytest.main([__file__, '-v'])