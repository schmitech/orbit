#!/usr/bin/env python3

import os
import sys
import base64
from typing import Dict, Any
from unittest.mock import MagicMock, patch

import pytest

# Add server directory to Python path
server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(server_dir)

from ai_services.base import ServiceType
from ai_services.factory import AIServiceFactory
from ai_services.registry import register_image_generation_services
from ai_services.implementations.image.ollama_image_service import OllamaImageService
from ai_services.providers.ollama_base import OllamaBaseService
from utils.ollama_utils import OllamaConfig


class TestOllamaImageConfig:
    def test_image_generation_uses_direct_model_config(self):
        config = {
            "image_generation": {
                "ollama": {
                    "enabled": True,
                    "base_url": "http://localhost:11434",
                    "model": "x/z-image-turbo",
                }
            }
        }

        ollama_config = OllamaConfig(config, "image_generation")

        assert ollama_config.base_url == "http://localhost:11434"
        assert ollama_config.model == "x/z-image-turbo"

    def test_image_generation_without_model_falls_back_to_empty_default(self):
        config = {
            "image_generation": {
                "ollama": {
                    "enabled": True,
                }
            }
        }

        ollama_config = OllamaConfig(config, "image_generation")
        assert ollama_config.model == ""


class TestOllamaImageRegistration:
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

    def test_register_ollama_image_provider(self):
        config: Dict[str, Any] = {
            "image": {"enabled": True},
            "image_generation": {
                "ollama": {"enabled": True, "model": "x/z-image-turbo"},
                "openai": {"enabled": False},
                "gemini": {"enabled": False},
            },
        }

        with patch("builtins.__import__") as mock_import:
            real_import = __import__
            mock_module = MagicMock()
            mock_module.OllamaImageService = MagicMock()

            def side_effect(name, *args, **kwargs):
                if "ai_services.implementations.image" in name:
                    return mock_module
                return real_import(name, *args, **kwargs)

            mock_import.side_effect = side_effect

            register_image_generation_services(config)

        available_services = AIServiceFactory.list_available_services()
        assert "ollama" in available_services.get("image_generation", [])


class TestOllamaImageService:
    def test_image_generation_uses_image_warmup_endpoint(self):
        service = OllamaImageService(
            {
                "image_generation": {
                    "ollama": {
                        "model": "x/z-image-turbo",
                    }
                }
            }
        )

        assert service._get_warmup_endpoint() == "image_generation"

    @pytest.mark.asyncio
    async def test_generate_image_uses_v1_images_endpoint(self):
        image_bytes = b"fake-png-bytes"
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        captured = {}

        class MockResponse:
            status = 200

            async def json(self):
                return {
                    "data": [
                        {
                            "b64_json": encoded,
                            "mime_type": "image/png",
                        }
                    ]
                }

            async def text(self):
                return ""

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        class MockSession:
            def post(self, url, json):
                captured["url"] = url
                captured["json"] = json
                return MockResponse()

        class MockSessionManager:
            async def get_session(self):
                return MockSession()

        service = OllamaImageService(
            {
                "image_generation": {
                    "ollama": {
                        "model": "x/z-image-turbo",
                        "base_url": "http://localhost:11434/api",
                        "size": "1024x1024",
                    }
                }
            }
        )
        service.initialized = True
        service.session_manager = MockSessionManager()

        result = await service.generate_image("A test prompt")

        assert captured["url"] == "http://localhost:11434/v1/images/generations"
        assert captured["json"]["model"] == "x/z-image-turbo"
        assert captured["json"]["prompt"] == "A test prompt"
        assert captured["json"]["response_format"] == "b64_json"
        assert result["image_bytes"] == image_bytes
        assert result["format"] == "png"


class TestOllamaImageWarmup:
    @pytest.mark.asyncio
    async def test_warmup_uses_images_endpoint(self):
        captured = {}

        class MockResponse:
            status = 200

            async def json(self):
                return {"data": [{"b64_json": "ZmFrZQ=="}]}

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        class MockSession:
            def post(self, url, json, timeout):
                captured["url"] = url
                captured["json"] = json
                return MockResponse()

        class MockSessionManager:
            async def get_session(self):
                return MockSession()

        warmer = OllamaBaseService(
            config={"inference": {"ollama": {"model": "placeholder"}}},
            service_type=ServiceType.IMAGE_GENERATION,
            provider_name="ollama",
        ).model_warmer
        warmer.base_url = "http://localhost:11434/api"
        warmer.model = "x/z-image-turbo"
        warmer.session_manager = MockSessionManager()

        async def fake_is_model_loaded():
            return False

        warmer.is_model_loaded = fake_is_model_loaded

        ok = await warmer.warmup_model(endpoint="image_generation")

        assert ok is True
        assert captured["url"] == "http://localhost:11434/v1/images/generations"
        assert captured["json"]["model"] == "x/z-image-turbo"
        assert captured["json"]["response_format"] == "b64_json"
