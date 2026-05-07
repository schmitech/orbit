#!/usr/bin/env python3

import base64
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(server_dir)

from ai_services.implementations.image.openai_image_service import OpenAIImageService


class TestOpenAIImageService:
    @pytest.mark.asyncio
    async def test_gpt_image_generation_omits_response_format(self):
        encoded = base64.b64encode(b"fake-png").decode("utf-8")
        service = OpenAIImageService(
            {
                "image_generation": {
                    "openai": {
                        "api_key": "test-key",
                        "model": "gpt-image-2",
                        "size": "1024x1024",
                        "quality": "auto",
                        "output_format": "png",
                    }
                }
            }
        )
        service.initialized = True
        service.client = MagicMock()
        service.client.images.generate = AsyncMock(
            return_value=SimpleNamespace(
                data=[SimpleNamespace(b64_json=encoded, revised_prompt=None)]
            )
        )

        result = await service.generate_image("A test image")
        call_kwargs = service.client.images.generate.call_args.kwargs

        assert call_kwargs["model"] == "gpt-image-2"
        assert call_kwargs["quality"] == "auto"
        assert call_kwargs["output_format"] == "png"
        assert "response_format" not in call_kwargs
        assert "style" not in call_kwargs
        assert result["image_bytes"] == b"fake-png"
        assert result["format"] == "png"

    @pytest.mark.asyncio
    async def test_dalle_generation_requests_b64_json(self):
        encoded = base64.b64encode(b"fake-png").decode("utf-8")
        service = OpenAIImageService(
            {
                "image_generation": {
                    "openai": {
                        "api_key": "test-key",
                        "model": "dall-e-3",
                        "size": "1024x1024",
                        "quality": "hd",
                        "style": "natural",
                    }
                }
            }
        )
        service.initialized = True
        service.client = MagicMock()
        service.client.images.generate = AsyncMock(
            return_value=SimpleNamespace(
                data=[SimpleNamespace(b64_json=encoded, revised_prompt="Revised prompt")]
            )
        )

        result = await service.generate_image("A test image")
        call_kwargs = service.client.images.generate.call_args.kwargs

        assert call_kwargs["model"] == "dall-e-3"
        assert call_kwargs["response_format"] == "b64_json"
        assert call_kwargs["quality"] == "hd"
        assert call_kwargs["style"] == "natural"
        assert "output_format" not in call_kwargs
        assert result["image_bytes"] == b"fake-png"
        assert result["revised_prompt"] == "Revised prompt"
