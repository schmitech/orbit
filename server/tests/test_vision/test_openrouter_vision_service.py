"""Focused tests for OpenRouter vision requests and registration."""

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ai_services.base import ServiceType
from ai_services.factory import AIServiceFactory
from ai_services.implementations.vision.openrouter_vision_service import OpenRouterVisionService
from ai_services.registry import register_vision_services


@pytest.mark.asyncio
async def test_openrouter_vision_sends_jpeg_and_reports_usage():
    service = OpenRouterVisionService({
        "visions": {"openrouter": {
            "api_key": "test-key", "model": "openai/gpt-4o",
            "retry": {"enabled": False},
        }}
    })
    service.client = MagicMock()
    service.client.chat.send_async = AsyncMock(return_value=SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="A cat"))],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=3),
    ))
    service.initialized = True

    usage = {}
    result = await service.multimodal_inference(b"\xff\xd8jpeg", "What is shown?", usage_sink=usage)

    assert result == "A cat"
    params = service.client.chat.send_async.call_args.kwargs
    assert params["messages"][0]["content"][1]["image_url"]["url"] == (
        "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8jpeg").decode()
    )
    assert usage["prompt_tokens"] == 12
    assert usage["completion_tokens"] == 3
    assert usage["provider"] == "openrouter"


def test_openrouter_vision_registration_respects_enabled_flag():
    with patch.object(AIServiceFactory, "register_service") as register:
        register_vision_services({"visions": {"openrouter": {"enabled": False}}})
        assert not any(call.args[:2] == (ServiceType.VISION, "openrouter") for call in register.call_args_list)

        register.reset_mock()
        register_vision_services({"visions": {"openrouter": {"enabled": True}}})
        assert any(call.args[:2] == (ServiceType.VISION, "openrouter") for call in register.call_args_list)
