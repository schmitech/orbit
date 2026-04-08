"""
Tests for OpenAIRealtimeWebSocketHandler.
"""

import os
import sys
import importlib.util
from unittest.mock import AsyncMock, MagicMock

import pytest

_server_dir = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, _server_dir)

_module_path = os.path.join(_server_dir, 'services', 'chat_handlers', 'openai_realtime_websocket_handler.py')
_spec = importlib.util.spec_from_file_location('test_openai_realtime_websocket_handler_module', _module_path)
_module = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(_module)
OpenAIRealtimeWebSocketHandler = _module.OpenAIRealtimeWebSocketHandler


@pytest.mark.asyncio
async def test_session_update_uses_prompt_service_instructions():
    websocket = MagicMock()
    prompt_service = AsyncMock()
    prompt_service.get_prompt_by_id.return_value = {"prompt": "You are a calm travel concierge."}

    handler = OpenAIRealtimeWebSocketHandler(
        websocket=websocket,
        adapter_name="open-ai-real-time-voice-chat",
        adapter_config={
            "config": {
                "realtime_model": "gpt-realtime",
                "realtime_voice": "marin",
                "realtime_instructions": "SHOULD NOT BE USED",
            }
        },
        config={},
        prompt_service=prompt_service,
        system_prompt_id="prompt-456",
    )

    session_update = await handler._build_session_update()
    instructions = session_update["session"]["instructions"]

    assert "You are a calm travel concierge." in instructions
    assert "SHOULD NOT BE USED" not in instructions
    prompt_service.get_prompt_by_id.assert_awaited_once_with("prompt-456")


@pytest.mark.asyncio
async def test_session_update_falls_back_when_prompt_missing():
    websocket = MagicMock()
    prompt_service = AsyncMock()
    prompt_service.get_prompt_by_id.return_value = None

    handler = OpenAIRealtimeWebSocketHandler(
        websocket=websocket,
        adapter_name="open-ai-real-time-voice-chat",
        adapter_config={"config": {}},
        config={},
        prompt_service=prompt_service,
        system_prompt_id="missing-prompt",
    )

    session_update = await handler._build_session_update()

    assert "You are a helpful assistant." in session_update["session"]["instructions"]
