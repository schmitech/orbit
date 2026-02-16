"""
Test Z.AI inference service implementation.

This module tests the Z.AI inference service to ensure it works correctly
with the unified AI services architecture.
"""

import pytest
import os
import sys
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

# Get the absolute path to the server directory (parent of tests)
server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Add server directory to Python path
sys.path.append(server_dir)

from ai_services.implementations.inference.zai_inference_service import ZaiInferenceService


class TestZaiInferenceService:
    """Test cases for Z.AI inference service."""

    @pytest.fixture
    def mock_config(self) -> Dict[str, Any]:
        """Create a mock configuration for testing."""
        return {
            "inference": {
                "zai": {
                    "api_key": "test-api-key",
                    "model": "glm-4.6",
                    "temperature": 0.1,
                    "top_p": 0.8,
                    "max_tokens": 2000,
                    "stream": True,
                    "timeout": {
                        "connect": 10000,
                        "total": 120000
                    },
                    "retry": {
                        "enabled": True,
                        "max_retries": 3,
                        "initial_wait_ms": 1000,
                        "max_wait_ms": 30000,
                        "exponential_base": 2
                    }
                }
            }
        }

    @pytest.fixture
    def mock_zai_client(self):
        """Create a mock Z.AI client."""
        client = Mock()
        client.chat = Mock()
        client.chat.completions = Mock()
        
        # Mock non-streaming response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "Test response from Z.AI"
        
        client.chat.completions.create = AsyncMock(return_value=mock_response)
        
        return client

    @pytest.fixture
    def mock_stream_response(self):
        """Create a mock streaming response."""
        async def mock_stream():
            chunks = [
                Mock(choices=[Mock(delta=Mock(content="Hello"))]),
                Mock(choices=[Mock(delta=Mock(content=" world"))]),
                Mock(choices=[Mock(delta=Mock(content="!"))]),
            ]
            for chunk in chunks:
                yield chunk
        
        return mock_stream()

    @pytest.mark.asyncio
    async def test_initialization(self, mock_config):
        """Test service initialization."""
        with patch('ai_services.providers.zai_base.ZaiClient') as mock_zai_client_class:
            mock_client = Mock()
            mock_zai_client_class.return_value = mock_client
            
            service = ZaiInferenceService(mock_config)
            
            # Check that client was created
            assert service.client is not None
            assert service.model == "glm-4.6"
            assert service.temperature == 0.1
            assert service.max_tokens == 2000
            assert service.top_p == 0.8

    @pytest.mark.asyncio
    async def test_generate_simple_prompt(self, mock_config, mock_zai_client):
        """Test generating response with simple prompt."""
        with patch('ai_services.providers.zai_base.ZaiClient', return_value=mock_zai_client):
            service = ZaiInferenceService(mock_config)
            service.initialized = True  # Skip actual initialization
            
            result = await service.generate("Hello, how are you?")
            
            assert result == "Test response from Z.AI"
            
            # Verify the client was called with correct parameters
            mock_zai_client.chat.completions.create.assert_called_once()
            call_args = mock_zai_client.chat.completions.create.call_args
            assert call_args[1]["model"] == "glm-4.6"
            assert call_args[1]["messages"] == [{"role": "user", "content": "Hello, how are you?"}]
            assert call_args[1]["max_tokens"] == 2000
            assert call_args[1]["temperature"] == 0.1
            assert call_args[1]["top_p"] == 0.8

    @pytest.mark.asyncio
    async def test_generate_with_messages(self, mock_config, mock_zai_client):
        """Test generating response with messages format."""
        with patch('ai_services.providers.zai_base.ZaiClient', return_value=mock_zai_client):
            service = ZaiInferenceService(mock_config)
            service.initialized = True
            
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello, how are you?"}
            ]
            
            result = await service.generate("", messages=messages)
            
            assert result == "Test response from Z.AI"
            
            # Verify the client was called with messages
            call_args = mock_zai_client.chat.completions.create.call_args
            assert call_args[1]["messages"] == messages

    @pytest.mark.asyncio
    async def test_generate_stream(self, mock_config, mock_stream_response):
        """Test streaming response generation."""
        with patch('ai_services.providers.zai_base.ZaiClient') as mock_zai_client_class:
            mock_client = Mock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_stream_response)
            mock_zai_client_class.return_value = mock_client
            
            service = ZaiInferenceService(mock_config)
            service.initialized = True
            
            chunks = []
            async for chunk in service.generate_stream("Hello"):
                chunks.append(chunk)
            
            assert chunks == ["Hello", " world", "!"]
            
            # Verify streaming was enabled
            call_args = mock_client.chat.completions.create.call_args
            assert call_args[1]["stream"] is True

    @pytest.mark.asyncio
    async def test_verify_connection_success(self, mock_config):
        """Test successful connection verification."""
        with patch('ai_services.providers.zai_base.ZaiClient') as mock_zai_client_class:
            mock_client = Mock()
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message = Mock()
            mock_response.choices[0].message.content = "Hello"
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_zai_client_class.return_value = mock_client
            
            service = ZaiInferenceService(mock_config)
            result = await service.verify_connection()
            
            assert result is True

    @pytest.mark.asyncio
    async def test_verify_connection_failure(self, mock_config):
        """Test connection verification failure."""
        with patch('ai_services.providers.zai_base.ZaiClient') as mock_zai_client_class:
            mock_client = Mock()
            mock_client.chat.completions.create = AsyncMock(side_effect=Exception("Connection failed"))
            mock_zai_client_class.return_value = mock_client
            
            service = ZaiInferenceService(mock_config)
            result = await service.verify_connection()
            
            assert result is False

    @pytest.mark.asyncio
    async def test_error_handling(self, mock_config):
        """Test error handling during generation."""
        with patch('ai_services.providers.zai_base.ZaiClient') as mock_zai_client_class:
            mock_client = Mock()
            mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))
            mock_zai_client_class.return_value = mock_client
            
            service = ZaiInferenceService(mock_config)
            service.initialized = True
            
            with pytest.raises(Exception, match="API Error"):
                await service.generate("Hello")

    def test_configuration_extraction(self, mock_config):
        """Test that configuration is properly extracted."""
        with patch('ai_services.providers.zai_base.ZaiClient'):
            service = ZaiInferenceService(mock_config)
            
            # Test that the service extracts the correct configuration
            assert service.model == "glm-4.6"
            assert service.temperature == 0.1
            assert service.max_tokens == 2000
            assert service.top_p == 0.8

    @pytest.mark.asyncio
    async def test_parameter_override(self, mock_config, mock_zai_client):
        """Test that parameters can be overridden in generate calls."""
        with patch('ai_services.providers.zai_base.ZaiClient', return_value=mock_zai_client):
            service = ZaiInferenceService(mock_config)
            service.initialized = True
            
            await service.generate(
                "Hello",
                temperature=0.5,
                max_tokens=1000,
                top_p=0.9
            )
            
            # Verify overridden parameters were used
            call_args = mock_zai_client.chat.completions.create.call_args
            assert call_args[1]["temperature"] == 0.5
            assert call_args[1]["max_tokens"] == 1000
            assert call_args[1]["top_p"] == 0.9


if __name__ == "__main__":
    # Run tests if executed directly
    pytest.main([__file__, "-v"])
