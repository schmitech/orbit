"""
Tests for OpenAIRealtimeWebSocketHandler.
"""

import os
import sys
import importlib.util
import json
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


@pytest.mark.asyncio
async def test_grounding_waits_for_tool_response_done_before_creating_follow_up_response():
    websocket = MagicMock()
    adapter_manager = AsyncMock()
    retriever = AsyncMock()
    retriever.get_relevant_context.return_value = [{"answer": "Order A-100 has shipped."}]
    adapter_manager.get_adapter.return_value = retriever

    handler = OpenAIRealtimeWebSocketHandler(
        websocket=websocket,
        adapter_name="customer-orders-realtime-voice",
        adapter_config={
            "config": {
                "grounding_adapter": "intent-sql-postgres",
                "grounding_tool_name": "lookup_customer_orders",
            }
        },
        config={},
        adapter_manager=adapter_manager,
    )
    handler._openai_ws = AsyncMock()
    handler._send_client = AsyncMock()

    await handler._handle_function_call(
        {
            "call_id": "call-1",
            "name": "lookup_customer_orders",
            "arguments": '{"query": "Has order A-100 shipped?"}',
        }
    )

    sent = [json.loads(call.args[0]) for call in handler._openai_ws.send_str.await_args_list]
    assert [message["type"] for message in sent] == ["conversation.item.create"]

    await handler._map_openai_event(
        {
            "type": "response.done",
            "response": {"output": [{"type": "function_call"}]},
        }
    )

    sent = [json.loads(call.args[0]) for call in handler._openai_ws.send_str.await_args_list]
    assert [message["type"] for message in sent] == [
        "conversation.item.create",
        "response.create",
    ]
    handler._send_client.assert_not_awaited()


@pytest.mark.asyncio
async def test_completed_turn_is_persisted_to_chat_history():
    websocket = MagicMock()
    chat_history_service = AsyncMock()
    chat_history_service.add_conversation_turn.return_value = ("stored-user", "stored-assistant")

    handler = OpenAIRealtimeWebSocketHandler(
        websocket=websocket,
        adapter_name="open-ai-real-time-voice-chat",
        adapter_config={"config": {}},
        config={},
        session_id="session-1",
        user_id="user-1",
        api_key="test-key",
        chat_history_service=chat_history_service,
    )
    handler._send_client = AsyncMock()

    await handler._map_openai_event({
        "type": "conversation.item.input_audio_transcription.completed",
        "transcript": "How much is the birth certificate?",
    })
    await handler._map_openai_event({
        "type": "response.output_audio_transcript.delta", "delta": "It's twenty "
    })
    await handler._map_openai_event({
        "type": "response.output_audio_transcript.delta", "delta": "dollars."
    })
    await handler._map_openai_event({
        "type": "response.done",
        "response": {"output": [{"type": "message"}]},
    })

    chat_history_service.add_conversation_turn.assert_awaited_once_with(
        session_id="session-1",
        user_message="How much is the birth certificate?",
        assistant_response="It's twenty dollars.",
        user_id="user-1",
        api_key="test-key",
        adapter_name="open-ai-real-time-voice-chat",
    )
    assert _send_payloads(handler)[-1] == {
        "type": "done",
        "session_id": "session-1",
        "user_message_id": "stored-user",
        "assistant_message_id": "stored-assistant",
    }
    # Buffers reset after persisting, so a second empty done doesn't re-persist.
    await handler._map_openai_event({
        "type": "response.done",
        "response": {"output": [{"type": "message"}]},
    })
    chat_history_service.add_conversation_turn.assert_awaited_once()


@pytest.mark.asyncio
async def test_persist_turn_skips_when_no_chat_history_service():
    websocket = MagicMock()
    handler = OpenAIRealtimeWebSocketHandler(
        websocket=websocket,
        adapter_name="open-ai-real-time-voice-chat",
        adapter_config={"config": {}},
        config={},
    )
    handler._send_client = AsyncMock()
    handler._pending_user_message = "hello"

    # Should not raise even though chat_history_service is None.
    await handler._persist_turn()
    assert handler._pending_user_message == "hello"  # unchanged: persist was a no-op, not "cleared"


@pytest.mark.asyncio
async def test_persist_turn_skips_when_turn_is_empty():
    websocket = MagicMock()
    chat_history_service = AsyncMock()
    handler = OpenAIRealtimeWebSocketHandler(
        websocket=websocket,
        adapter_name="open-ai-real-time-voice-chat",
        adapter_config={"config": {}},
        config={},
        chat_history_service=chat_history_service,
    )

    await handler._persist_turn()

    chat_history_service.add_conversation_turn.assert_not_awaited()


def _send_payloads(handler):
    return [call.args[0] for call in handler._send_client.await_args_list]


@pytest.mark.asyncio
async def test_final_transcript_supplies_suffix_missing_from_streamed_deltas():
    handler = OpenAIRealtimeWebSocketHandler(
        websocket=MagicMock(),
        adapter_name="open-ai-real-time-voice-chat",
        adapter_config={"config": {}},
        config={},
    )
    handler._send_client = AsyncMock()

    await handler._map_openai_event({
        "type": "response.output_audio_transcript.delta",
        "response_id": "response-1",
        "item_id": "item-1",
        "output_index": 0,
        "content_index": 0,
        "delta": "The answer is",
    })
    await handler._map_openai_event({
        "type": "response.output_audio_transcript.done",
        "response_id": "response-1",
        "item_id": "item-1",
        "output_index": 0,
        "content_index": 0,
        "transcript": "The answer is forty-two.",
    })

    assert _send_payloads(handler) == [
        {"type": "assistant_transcript_delta", "delta": "The answer is"},
        {"type": "assistant_transcript_delta", "delta": " forty-two."},
    ]
    assert handler._pending_assistant_text == "The answer is forty-two."


def test_discard_pending_turn_clears_interrupted_turn_state():
    handler = OpenAIRealtimeWebSocketHandler(
        websocket=MagicMock(),
        adapter_name="open-ai-real-time-voice-chat",
        adapter_config={"config": {}},
        config={},
    )
    handler._pending_user_message = "Old question"
    handler._pending_assistant_text = "Old answer"
    handler._assistant_transcript_prefixes["response:item:0:0"] = "Old answer"

    handler._discard_pending_turn()

    assert handler._pending_user_message == ""
    assert handler._pending_assistant_text == ""
    assert handler._assistant_transcript_prefixes == {}
