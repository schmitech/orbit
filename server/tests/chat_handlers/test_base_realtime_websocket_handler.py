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


# ---------------------------------------------------------------------------
# Realtime usage accumulation + session-level audit flush
# ---------------------------------------------------------------------------

def test_accumulate_realtime_usage_sums_across_turns():
    handler = _make_handler()

    handler._accumulate_realtime_usage("openai", "gpt-realtime", 100, 20, audio_prompt_tokens=50, audio_completion_tokens=10)
    handler._accumulate_realtime_usage("openai", "gpt-realtime", 200, 40, audio_prompt_tokens=80, audio_completion_tokens=15)

    acc = handler._usage_accumulator
    assert acc["reported"] is True
    assert acc["prompt_tokens"] == 300
    assert acc["completion_tokens"] == 60
    assert acc["total_tokens"] == 360
    assert acc["audio_prompt_tokens"] == 130
    assert acc["audio_completion_tokens"] == 25
    assert acc["provider"] == "openai"
    assert acc["model"] == "gpt-realtime"


@pytest.mark.asyncio
async def test_flush_realtime_usage_writes_one_audit_record_with_audio_tier():
    audit_service = AsyncMock()
    audit_service.chat_events_enabled = True
    pricing_service = MagicMock()
    pricing_service.estimate.return_value = MagicMock(
        input_rate_per_1m=4.0, output_rate_per_1m=16.0, pricing_source="pattern", cost_usd=1.23,
    )

    handler = _make_handler(
        audit_service=audit_service, pricing_service=pricing_service,
        session_id="sess-1", user_id="user-1", api_key="key-1",
    )
    handler._accumulate_realtime_usage(
        "openai", "gpt-realtime", 100, 20, audio_prompt_tokens=50, audio_completion_tokens=10,
    )

    await handler._flush_realtime_usage()

    audit_service.log_conversation.assert_awaited_once()
    kwargs = audit_service.log_conversation.call_args.kwargs
    assert kwargs["provider"] == "openai"
    assert kwargs["model"] == "gpt-realtime"
    assert kwargs["session_id"] == "sess-1"
    assert kwargs["usage"]["usage_unit"] == "audio_tokens"
    assert kwargs["usage"]["usage_quantity"] == 60
    assert kwargs["usage"]["cost_usd"] == 1.23
    pricing_service.estimate.assert_called_once_with(
        "openai", "gpt-realtime", 100, 20, audio_prompt_tokens=50, audio_completion_tokens=10,
    )


@pytest.mark.asyncio
async def test_flush_realtime_usage_noop_when_nothing_accumulated():
    """A session that never received a usage event must never write a
    fabricated audit row (e.g. a session that disconnected before any turn)."""
    audit_service = AsyncMock()
    audit_service.chat_events_enabled = True
    handler = _make_handler(audit_service=audit_service)

    await handler._flush_realtime_usage()

    audit_service.log_conversation.assert_not_awaited()


@pytest.mark.asyncio
async def test_flush_realtime_usage_includes_grounding_embedding_cost():
    audit_service = AsyncMock()
    audit_service.chat_events_enabled = True
    pricing_service = MagicMock()
    pricing_service.estimate.return_value = MagicMock(
        input_rate_per_1m=0.02,
        output_rate_per_1m=0.0,
        pricing_source="exact",
        cost_usd=0.00001,
    )
    handler = _make_handler(
        audit_service=audit_service, pricing_service=pricing_service
    )
    handler._accumulate_embedding_usage({
        "prompt_tokens": 500,
        "completion_tokens": 0,
        "total_tokens": 500,
        "provider": "openai",
        "model": "text-embedding-3-small",
        "reported": True,
    })

    await handler._flush_realtime_usage()

    usage = audit_service.log_conversation.call_args.kwargs["usage"]
    assert usage["embedding_prompt_tokens"] == 500
    assert usage["embedding_cost_usd"] == pytest.approx(0.00001)
    assert usage["cost_usd"] == pytest.approx(0.00001)
    assert audit_service.log_conversation.call_args.kwargs["provider"] == "openai"


@pytest.mark.asyncio
async def test_flush_realtime_usage_noop_without_audit_service():
    handler = _make_handler(audit_service=None)
    handler._accumulate_realtime_usage("openai", "gpt-realtime", 100, 20)

    # Must not raise even with no audit_service configured.
    await handler._flush_realtime_usage()
