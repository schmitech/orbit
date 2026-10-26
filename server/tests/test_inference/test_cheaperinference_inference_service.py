"""
Test Cheaper Inference inference service implementation.
"""

import os
import sys
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(server_dir)

from ai_services.implementations.inference.cheaperinference_inference_service import (
    CheaperInferenceInferenceService,
)


class TestCheaperInferenceInferenceService:
    """Test cases for Cheaper Inference inference service."""

    @pytest.fixture
    def mock_config(self) -> dict[str, Any]:
        return {
            "inference": {
                "cheaperinference": {
                    "api_key": "test-api-key",
                    "model": "deepseek-v4-flash",
                    "temperature": 0.1,
                    "top_p": 0.8,
                    "max_tokens": 2000,
                    "stream": True,
                }
            }
        }

    @pytest.fixture
    def mock_client(self):
        client = Mock()
        client.chat = Mock()
        client.chat.completions = Mock()

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "Test response from Cheaper Inference"
        mock_response.usage = None

        client.chat.completions.create = AsyncMock(return_value=mock_response)
        return client

    def test_configuration_extraction(self, mock_config, monkeypatch):
        monkeypatch.delenv("CHEAPERINFERENCE_API_KEY", raising=False)

        service = CheaperInferenceInferenceService(mock_config)

        assert service.provider_name == "cheaperinference"
        assert service.api_key == "test-api-key"
        assert service.base_url == "https://api.cheaperinference.com/v1"
        assert service.model == "deepseek-v4-flash"
        assert service.temperature == 0.1
        assert service.max_tokens == 2000
        assert service.top_p == 0.8

    @pytest.mark.asyncio
    async def test_generate(self, mock_config, mock_client):
        service = CheaperInferenceInferenceService(mock_config)
        service.initialized = True
        service.client = mock_client

        result = await service.generate("Hello")

        assert result == "Test response from Cheaper Inference"

        call_args = mock_client.chat.completions.create.call_args[1]
        assert call_args["model"] == "deepseek-v4-flash"
        assert call_args["messages"] == [{"role": "user", "content": "Hello"}]
        assert call_args["max_tokens"] == 2000
        assert call_args["temperature"] == 0.1
        assert call_args["top_p"] == 0.8

    @pytest.mark.asyncio
    async def test_generate_stream(self, mock_config):
        async def mock_stream():
            chunks = [
                Mock(choices=[Mock(delta=Mock(content="Hello"))]),
                Mock(choices=[Mock(delta=Mock(content=" from"))]),
                Mock(choices=[Mock(delta=Mock(content=" Cheaper Inference"))]),
            ]
            for chunk in chunks:
                yield chunk

        client = Mock()
        client.chat = Mock()
        client.chat.completions = Mock()
        client.chat.completions.create = AsyncMock(return_value=mock_stream())

        service = CheaperInferenceInferenceService(mock_config)
        service.initialized = True
        service.client = client

        chunks = []
        async for chunk in service.generate_stream("Hello"):
            chunks.append(chunk)

        assert chunks == ["Hello", " from", " Cheaper Inference"]
        call_args = client.chat.completions.create.call_args[1]
        assert call_args["stream"] is True
        assert call_args["stream_options"] == {"include_usage": True}
