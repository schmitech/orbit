"""
Test NEAR AI Cloud inference service implementation.
"""

import os
import sys
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock

import pytest

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(server_dir)

from ai_services.implementations.inference.nearai_inference_service import NearAIInferenceService


class TestNearAIInferenceService:
    """Test cases for NEAR AI Cloud inference service."""

    @pytest.fixture
    def mock_config(self) -> Dict[str, Any]:
        return {
            "inference": {
                "nearai": {
                    "api_key": "test-api-key",
                    "model": "zai-org/GLM-5.1-FP8",
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
        mock_response.choices[0].message.content = "Test response from NEAR AI Cloud"

        client.chat.completions.create = AsyncMock(return_value=mock_response)
        return client

    def test_configuration_extraction(self, mock_config, monkeypatch):
        monkeypatch.delenv("NEARAI_API_KEY", raising=False)

        service = NearAIInferenceService(mock_config)

        assert service.provider_name == "nearai"
        assert service.api_key == "test-api-key"
        assert service.base_url == "https://cloud-api.near.ai/v1"
        assert service.model == "zai-org/GLM-5.1-FP8"
        assert service.temperature == 0.1
        assert service.max_tokens == 2000
        assert service.top_p == 0.8

    @pytest.mark.asyncio
    async def test_generate_maps_openai_compatibility_parameters(self, mock_config, mock_client):
        service = NearAIInferenceService(mock_config)
        service.initialized = True
        service.client = mock_client

        messages = [
            {"role": "developer", "content": "You are concise."},
            {"role": "user", "content": "Hello"},
        ]

        result = await service.generate(
            "",
            messages=messages,
            max_completion_tokens=123,
            store=True,
            reasoning_effort="low",
            strict=True,
        )

        assert result == "Test response from NEAR AI Cloud"

        call_args = mock_client.chat.completions.create.call_args[1]
        assert call_args["model"] == "zai-org/GLM-5.1-FP8"
        assert call_args["max_tokens"] == 123
        assert call_args["messages"][0]["role"] == "system"
        assert "max_completion_tokens" not in call_args
        assert "store" not in call_args
        assert "reasoning_effort" not in call_args
        assert "strict" not in call_args

    @pytest.mark.asyncio
    async def test_generate_stream(self, mock_config):
        async def mock_stream():
            chunks = [
                Mock(choices=[Mock(delta=Mock(content="Hello"))]),
                Mock(choices=[Mock(delta=Mock(content=" NEAR"))]),
                Mock(choices=[Mock(delta=Mock(content=" AI"))]),
            ]
            for chunk in chunks:
                yield chunk

        client = Mock()
        client.chat = Mock()
        client.chat.completions = Mock()
        client.chat.completions.create = AsyncMock(return_value=mock_stream())

        service = NearAIInferenceService(mock_config)
        service.initialized = True
        service.client = client

        chunks = []
        async for chunk in service.generate_stream("Hello"):
            chunks.append(chunk)

        assert chunks == ["Hello", " NEAR", " AI"]
        assert client.chat.completions.create.call_args[1]["stream"] is True
