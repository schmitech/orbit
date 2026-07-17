"""
Tests for OpenAIRealtimeTranslationWebSocketHandler.
"""

import os
import sys
import importlib.util
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocketDisconnect

_server_dir = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, _server_dir)

_module_path = os.path.join(
    _server_dir, 'services', 'chat_handlers', 'openai_realtime_translation_websocket_handler.py'
)
_spec = importlib.util.spec_from_file_location(
    'test_openai_realtime_translation_websocket_handler_module', _module_path
)
_module = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(_module)
OpenAIRealtimeTranslationWebSocketHandler = _module.OpenAIRealtimeTranslationWebSocketHandler


def _make_handler(config_target=None, query_target=None):
    cfg = {"realtime_model": "gpt-realtime-translate"}
    if config_target is not None:
        cfg["target_language"] = config_target
    return OpenAIRealtimeTranslationWebSocketHandler(
        websocket=MagicMock(),
        adapter_name="open-ai-real-time-translation",
        adapter_config={"config": cfg},
        config={},
        target_language=query_target,
    )


def test_query_language_overrides_config():
    handler = _make_handler(config_target="es", query_target="fr")
    session_update = handler._build_session_update()
    assert session_update["session"]["audio"]["output"]["language"] == "fr"


def test_config_language_used_when_no_query():
    handler = _make_handler(config_target="de")
    session_update = handler._build_session_update()
    assert session_update["session"]["audio"]["output"]["language"] == "de"


def test_default_language_when_unset():
    handler = _make_handler()
    session_update = handler._build_session_update()
    assert session_update["session"]["audio"]["output"]["language"] == "es"
    assert session_update["type"] == "session.update"


@pytest.mark.asyncio
async def test_audio_chunk_mapped_to_input_audio_buffer_append():
    handler = _make_handler(query_target="fr")
    handler.is_connected = True
    handler.websocket.receive_text = AsyncMock(
        side_effect=['{"type": "audio_chunk", "data": "QUJD"}', WebSocketDisconnect()]
    )
    handler._openai_ws = AsyncMock()
    handler._send_client = AsyncMock()

    await handler._client_loop()

    handler._openai_ws.send_str.assert_awaited_once()
    import json
    sent = json.loads(handler._openai_ws.send_str.await_args.args[0])
    assert sent == {"type": "session.input_audio_buffer.append", "audio": "QUJD"}


@pytest.mark.asyncio
async def test_set_target_language_pushes_session_update_live():
    import json
    handler = _make_handler(config_target="es")
    handler.is_connected = True
    handler.websocket.receive_text = AsyncMock(
        side_effect=['{"type": "set_target_language", "language": "fr"}', WebSocketDisconnect()]
    )
    handler._openai_ws = AsyncMock()
    handler._send_client = AsyncMock()

    await handler._client_loop()

    assert handler._target_language == "fr"
    sent = json.loads(handler._openai_ws.send_str.await_args.args[0])
    assert sent["type"] == "session.update"
    assert sent["session"]["audio"]["output"]["language"] == "fr"
    handler._send_client.assert_awaited_with(
        {"type": "target_language_updated", "target_language": "fr"}
    )


@pytest.mark.asyncio
async def test_map_openai_events_to_client_protocol():
    handler = _make_handler()
    sent = []
    handler._send_client = AsyncMock(side_effect=lambda m: sent.append(m))

    await handler._map_openai_event({"type": "session.output_audio.delta", "delta": "QUJD"})
    await handler._map_openai_event({"type": "session.output_transcript.delta", "delta": "hola"})
    await handler._map_openai_event({"type": "session.input_transcript.delta", "delta": "hello"})
    await handler._map_openai_event({"type": "session.closed"})

    assert sent[0]["type"] == "audio_chunk"
    assert sent[0]["data"] == "QUJD"
    assert sent[0]["sample_rate"] == 24000
    assert sent[1] == {"type": "assistant_transcript_delta", "delta": "hola"}
    assert sent[2] == {"type": "transcription", "text": "hello"}
    assert sent[3]["type"] == "done"
