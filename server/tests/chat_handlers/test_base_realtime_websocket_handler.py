"""
Tests for BaseRealtimeWebSocketHandler — the shared scaffolding both
OpenAIRealtimeWebSocketHandler and GeminiLiveWebSocketHandler subclass.
"""

import os
import sys
import importlib.util
from unittest.mock import AsyncMock, MagicMock

import pytest

_server_dir = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, _server_dir)

_module_path = os.path.join(
    _server_dir, 'services', 'chat_handlers', 'base_realtime_websocket_handler.py'
)
_spec = importlib.util.spec_from_file_location('test_base_realtime_websocket_handler_module', _module_path)
_module = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(_module)
BaseRealtimeWebSocketHandler = _module.BaseRealtimeWebSocketHandler


def _make_handler(**overrides):
    websocket = overrides.pop("websocket", MagicMock())
    return BaseRealtimeWebSocketHandler(
        websocket=websocket,
        adapter_name=overrides.pop("adapter_name", "some-realtime-adapter"),
        adapter_config=overrides.pop("adapter_config", {"config": {}}),
        config=overrides.pop("config", {}),
        **overrides,
    )


@pytest.mark.asyncio
async def test_persist_turn_writes_and_clears_buffers():
    chat_history_service = AsyncMock()
    chat_history_service.add_conversation_turn.return_value = ("user-id", "assistant-id")

    handler = _make_handler(
        session_id="session-1",
        user_id="user-1",
        api_key="test-key",
        chat_history_service=chat_history_service,
    )
    handler._pending_user_message = "How much is the birth certificate?"
    handler._pending_assistant_text = "Twenty dollars."

    result = await handler._persist_turn()

    assert result == ("user-id", "assistant-id")
    chat_history_service.add_conversation_turn.assert_awaited_once_with(
        session_id="session-1",
        user_message="How much is the birth certificate?",
        assistant_response="Twenty dollars.",
        user_id="user-1",
        api_key="test-key",
        adapter_name="some-realtime-adapter",
    )
    assert handler._pending_user_message == ""
    assert handler._pending_assistant_text == ""


@pytest.mark.asyncio
async def test_persist_turn_skips_when_no_chat_history_service():
    handler = _make_handler()
    handler._pending_user_message = "hello"

    result = await handler._persist_turn()

    assert result == (None, None)
    assert handler._pending_user_message == "hello"  # no-op, not "cleared"


@pytest.mark.asyncio
async def test_persist_turn_skips_when_turn_is_empty():
    chat_history_service = AsyncMock()
    handler = _make_handler(chat_history_service=chat_history_service)

    result = await handler._persist_turn()

    assert result == (None, None)
    chat_history_service.add_conversation_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_persist_turn_swallows_errors_and_still_clears_buffers():
    chat_history_service = AsyncMock()
    chat_history_service.add_conversation_turn.side_effect = RuntimeError("db down")
    handler = _make_handler(chat_history_service=chat_history_service)
    handler._pending_user_message = "hello"
    handler._pending_assistant_text = "hi"

    result = await handler._persist_turn()

    assert result == (None, None)
    assert handler._pending_user_message == ""
    assert handler._pending_assistant_text == ""


def test_discard_pending_turn_clears_buffers():
    handler = _make_handler()
    handler._pending_user_message = "hello"
    handler._pending_assistant_text = "hi"

    handler._discard_pending_turn()

    assert handler._pending_user_message == ""
    assert handler._pending_assistant_text == ""


@pytest.mark.asyncio
async def test_resolve_realtime_instructions_uses_provider_label_in_logs(caplog):
    prompt_service = AsyncMock()
    prompt_service.get_prompt_by_id.return_value = None
    handler = _make_handler(prompt_service=prompt_service, system_prompt_id="missing-prompt")
    handler.provider_label = "Test Provider"

    with caplog.at_level("WARNING"):
        instructions = await handler._resolve_realtime_instructions()

    assert "You are a helpful assistant." in instructions
    assert any("Test Provider" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_run_until_either_cancels_pending_task_and_logs_exception(caplog):
    import asyncio

    async def fails():
        raise RuntimeError("boom")

    async def never_finishes():
        await asyncio.sleep(10)

    task_a = asyncio.create_task(fails())
    task_b = asyncio.create_task(never_finishes())

    with caplog.at_level("ERROR"):
        await BaseRealtimeWebSocketHandler._run_until_either(task_a, task_b)

    assert task_b.cancelled()
    assert any("boom" in record.message for record in caplog.records)
