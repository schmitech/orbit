#!/usr/bin/env python3

import os
import sys
from typing import Dict, Any
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(server_dir)

from ai_services.factory import AIServiceFactory
from ai_services.registry import register_image_generation_services
from ai_services.implementations.image.xai_image_service import XAIImageService


class TestXAIImageRegistration:
    @pytest.fixture(autouse=True)
    def reset_factory(self):
        AIServiceFactory._service_registry = {}
        AIServiceFactory._service_cache = {}
        import ai_services.registry as registry_module
        registry_module._services_registered = False
        yield
        AIServiceFactory._service_registry = {}
        AIServiceFactory._service_cache = {}
        registry_module._services_registered = False

    def test_register_xai_image_provider(self):
        config: Dict[str, Any] = {
            "image": {"enabled": True},
            "image_generation": {
                "xai": {"enabled": True, "model": "grok-imagine-image", "api_key": "test-key"},
                "openai": {"enabled": False},
                "gemini": {"enabled": False},
                "ollama": {"enabled": False},
            },
        }

        with patch("builtins.__import__") as mock_import:
            real_import = __import__
            mock_module = MagicMock()
            mock_module.XAIImageService = MagicMock()

            def side_effect(name, *args, **kwargs):
                if "ai_services.implementations.image" in name:
                    return mock_module
                return real_import(name, *args, **kwargs)

            mock_import.side_effect = side_effect

            register_image_generation_services(config)

        available_services = AIServiceFactory.list_available_services()
        assert "xai" in available_services.get("image_generation", [])


class TestXAIImageService:
    @pytest.mark.asyncio
    async def test_generate_image_uses_xai_sdk_base64(self):
        data_uri = "data:image/jpeg;base64,ZmFrZS1pbWFnZS1ieXRlcw=="

        class MockImageResponse:
            base64 = data_uri

        class MockImageClient:
            def __init__(self):
                self.calls = []

            async def sample(self, **kwargs):
                self.calls.append(kwargs)
                return MockImageResponse()

            async def sample_batch(self, **kwargs):
                self.calls.append(kwargs)
                return [MockImageResponse()]

        service = XAIImageService(
            {
                "image_generation": {
                    "xai": {
                        "api_key": "test-key",
                        "api_base": "https://api.x.ai/v1",
                        "model": "grok-imagine-image",
                        "aspect_ratio": "1:1",
                        "resolution": "1k",
                    }
                }
            }
        )
        service.client = MagicMock()
        service.client.image = MockImageClient()
        service.initialized = True

        result = await service.generate_image("A futuristic city")

        assert service.client.image.calls[0]["model"] == "grok-imagine-image"
        assert service.client.image.calls[0]["image_format"] == "base64"
        assert result["image_bytes"] == b"fake-image-bytes"
        assert result["format"] == "jpeg"
        assert result["revised_prompt"] is None

    @pytest.mark.asyncio
    async def test_verify_connection_lists_image_models(self):
        service = XAIImageService(
            {
                "image_generation": {
                    "xai": {
                        "api_key": "test-key",
                        "model": "grok-imagine-image",
                    }
                }
            }
        )
        service.client = MagicMock()
        service.client.models.list_image_generation_models = AsyncMock(return_value=[])
        service.initialized = True

        ok = await service.verify_connection()

        assert ok is True

    @pytest.mark.asyncio
    async def test_generate_image_rejects_language_model_config(self):
        service = XAIImageService(
            {
                "image_generation": {
                    "xai": {
                        "api_key": "test-key",
                        "model": "grok-4.3",
                    }
                }
            }
        )
        service.client = MagicMock()
        service.client.image = MagicMock()
        service.initialized = True

        with pytest.raises(ValueError, match="requires an image model"):
            await service.generate_image("A futuristic city")
