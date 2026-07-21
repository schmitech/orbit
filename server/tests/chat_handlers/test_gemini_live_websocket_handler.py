"""
Tests for GeminiLiveWebSocketHandler.
"""

import os
import sys
import importlib.util
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

_server_dir = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, _server_dir)

_module_path = os.path.join(_server_dir, 'services', 'chat_handlers', 'gemini_live_websocket_handler.py')
_spec = importlib.util.spec_from_file_location('test_gemini_live_websocket_handler_module', _module_path)
_module = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(_module)
GeminiLiveWebSocketHandler = _module.GeminiLiveWebSocketHandler
_resample_pcm16 = _module._resample_pcm16


@pytest.mark.asyncio
async def test_live_config_uses_prompt_service_instructions():
    websocket = MagicMock()
    prompt_service = AsyncMock()
    prompt_service.get_prompt_by_id.return_value = {"prompt": "You are a calm travel concierge."}

    handler = GeminiLiveWebSocketHandler(
        websocket=websocket,
        adapter_name="gemini-live-voice-chat",
        adapter_config={
            "config": {
                "realtime_model": "gemini-3.1-flash-live-preview",
                "realtime_voice": "Puck",
            }
        },
        config={},
        prompt_service=prompt_service,
        system_prompt_id="prompt-456",
    )

    live_config = await handler._build_live_config()
    instructions = live_config.system_instruction.parts[0].text

    assert "You are a calm travel concierge." in instructions
    prompt_service.get_prompt_by_id.assert_awaited_once_with("prompt-456")
    assert live_config.tools is None


@pytest.mark.asyncio
async def test_live_config_falls_back_when_prompt_missing():
    websocket = MagicMock()
    prompt_service = AsyncMock()
    prompt_service.get_prompt_by_id.return_value = None

    handler = GeminiLiveWebSocketHandler(
        websocket=websocket,
        adapter_name="gemini-live-voice-chat",
        adapter_config={"config": {}},
        config={},
        prompt_service=prompt_service,
        system_prompt_id="missing-prompt",
    )

    live_config = await handler._build_live_config()

    assert "You are a helpful assistant." in live_config.system_instruction.parts[0].text


@pytest.mark.asyncio
async def test_live_config_includes_tool_when_grounded():
    websocket = MagicMock()

    handler = GeminiLiveWebSocketHandler(
        websocket=websocket,
        adapter_name="qa-gemini-realtime-voice",
        adapter_config={
            "config": {
                "grounding_adapter": "qa-sql",
                "grounding_tool_name": "lookup_answer",
                "grounding_tool_description": "Look up an answer.",
            }
        },
        config={},
    )

    live_config = await handler._build_live_config()

    assert live_config.tools is not None
    declarations = live_config.tools[0].function_declarations
    assert len(declarations) == 1
    assert declarations[0].name == "lookup_answer"
    assert declarations[0].description == "Look up an answer."


def test_resample_pcm16_scales_length():
    samples = np.zeros(1600, dtype="<i2")
    data = samples.tobytes()

    resampled = _resample_pcm16(data, 24000, 16000)

    resampled_samples = np.frombuffer(resampled, dtype="<i2")
    expected_count = round(1600 * 16000 / 24000)
    assert resampled_samples.size == expected_count


def test_resample_pcm16_noop_when_rates_match():
    data = np.arange(100, dtype="<i2").tobytes()
    assert _resample_pcm16(data, 24000, 24000) == data


@pytest.mark.asyncio
async def test_handle_tool_call_invokes_grounding_and_sends_response():
    websocket = MagicMock()
    adapter_manager = AsyncMock()
    retriever = AsyncMock()
    retriever.get_relevant_context.return_value = [{"answer": "Twenty dollars."}]
    adapter_manager.get_adapter.return_value = retriever

    handler = GeminiLiveWebSocketHandler(
        websocket=websocket,
        adapter_name="qa-gemini-realtime-voice",
        adapter_config={
            "config": {
                "grounding_adapter": "qa-sql",
                "grounding_tool_name": "lookup_answer",
            }
        },
        config={},
        adapter_manager=adapter_manager,
        api_key="test-key",
    )

    session = AsyncMock()
    handler._session = session

    function_call = MagicMock()
    function_call.name = "lookup_answer"
    function_call.id = "call-1"
    function_call.args = {"query": "How much is the birth certificate?"}

    tool_call = MagicMock()
    tool_call.function_calls = [function_call]

    await handler._handle_tool_call(tool_call)

    adapter_manager.get_adapter.assert_awaited_once_with("qa-sql")
    retriever.get_relevant_context.assert_awaited_once()
    session.send_tool_response.assert_awaited_once()
    _, kwargs = session.send_tool_response.call_args
    responses = kwargs["function_responses"]
    assert len(responses) == 1
    assert responses[0].id == "call-1"
    assert responses[0].name == "lookup_answer"
    assert responses[0].response == {"result": "Twenty dollars."}


@pytest.mark.asyncio
async def test_handle_tool_call_ignores_unknown_tool_name():
    websocket = MagicMock()
    adapter_manager = AsyncMock()

    handler = GeminiLiveWebSocketHandler(
        websocket=websocket,
        adapter_name="qa-gemini-realtime-voice",
        adapter_config={
            "config": {
                "grounding_adapter": "qa-sql",
                "grounding_tool_name": "lookup_answer",
            }
        },
        config={},
        adapter_manager=adapter_manager,
    )

    session = AsyncMock()
    handler._session = session

    function_call = MagicMock()
    function_call.name = "some_other_tool"
    function_call.id = "call-2"
    function_call.args = {}

    tool_call = MagicMock()
    tool_call.function_calls = [function_call]

    await handler._handle_tool_call(tool_call)

    adapter_manager.get_adapter.assert_not_awaited()
    session.send_tool_response.assert_not_awaited()


@pytest.mark.asyncio
async def test_persist_turn_writes_accumulated_transcript_to_chat_history():
    websocket = MagicMock()
    chat_history_service = AsyncMock()

    handler = GeminiLiveWebSocketHandler(
        websocket=websocket,
        adapter_name="gemini-live-voice-chat",
        adapter_config={"config": {}},
        config={},
        session_id="session-1",
        user_id="user-1",
        api_key="test-key",
        chat_history_service=chat_history_service,
    )
    handler._pending_user_message = "How much is the birth certificate?"
    handler._pending_assistant_text = "It's twenty dollars."

    await handler._persist_turn()

    chat_history_service.add_conversation_turn.assert_awaited_once_with(
        session_id="session-1",
        user_message="How much is the birth certificate?",
        assistant_response="It's twenty dollars.",
        user_id="user-1",
        api_key="test-key",
        adapter_name="gemini-live-voice-chat",
    )
    assert handler._pending_user_message == ""
    assert handler._pending_assistant_text == ""


@pytest.mark.asyncio
async def test_persist_turn_skips_when_no_chat_history_service():
    websocket = MagicMock()
    handler = GeminiLiveWebSocketHandler(
        websocket=websocket,
        adapter_name="gemini-live-voice-chat",
        adapter_config={"config": {}},
        config={},
    )
    handler._pending_user_message = "hello"

    await handler._persist_turn()  # should not raise
    assert handler._pending_user_message == "hello"  # no-op, not "cleared"


@pytest.mark.asyncio
async def test_persist_turn_skips_when_turn_is_empty():
    websocket = MagicMock()
    chat_history_service = AsyncMock()
    handler = GeminiLiveWebSocketHandler(
        websocket=websocket,
        adapter_name="gemini-live-voice-chat",
        adapter_config={"config": {}},
        config={},
        chat_history_service=chat_history_service,
    )

    await handler._persist_turn()

    chat_history_service.add_conversation_turn.assert_not_awaited()
