"""
`openai_stream_generator` (inside `_configure_chat_endpoint`'s
`/v1/chat/completions` handler) converts ORBIT's internal stream into
OpenAI-compatible SSE chunks. Step 5 of
docs/roadmap/pipeline-streaming-structured-events.md migrated it from
parsing `process_chat_stream`'s SSE strings (`json.loads` per chunk) to
consuming `process_chat_stream_events`'s StreamEvents directly. These tests
pin down that the resulting OpenAI-format SSE output is unchanged.
"""

import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from routes.routes_configurator import RouteConfigurator
from services.chat_handlers.streaming_events import (
    AudioChunkEvent,
    DoneEvent,
    ErrorEvent,
    RawEvent,
    ResponseEvent,
)


def _build_app(stream_events_fn):
    app = FastAPI()
    configurator = RouteConfigurator({}, logging.getLogger(__name__))
    configurator._create_dependencies()
    configurator._configure_chat_endpoint(app)

    chat_service = MagicMock()
    chat_service.authorize_session_access = AsyncMock()
    chat_service.process_chat_stream_events = stream_events_fn

    app.dependency_overrides[configurator.check_not_paused] = lambda: None
    app.dependency_overrides[configurator.get_chat_service] = lambda: chat_service
    app.dependency_overrides[configurator.get_api_key] = lambda: ("test-adapter", None)
    app.dependency_overrides[configurator.validate_session_id] = lambda: "sess1"
    app.dependency_overrides[configurator.get_user_id] = lambda: None

    return app


def _collect_sse_lines(client):
    lines = []
    body = {"messages": [{"role": "user", "content": "hi"}], "stream": True}
    with client.stream("POST", "/v1/chat/completions", json=body) as resp:
        for line in resp.iter_lines():
            if line.startswith("data:"):
                lines.append(line[len("data:"):].strip())
    return lines


def test_response_chunks_then_done_with_sources_and_audio():
    async def stream_events(**kwargs):
        yield ResponseEvent(text="Hello", extra={"done": False})
        yield ResponseEvent(text=" world", extra={"done": False})
        yield DoneEvent(sources=[{"title": "doc1"}], audio="YmFzZTY0", audio_format="mp3")

    client = TestClient(_build_app(stream_events))
    lines = _collect_sse_lines(client)

    assert lines[-1] == "[DONE]"
    payloads = [json.loads(line) for line in lines[:-1]]

    assert payloads[0]["choices"][0]["delta"] == {"role": "assistant", "content": "Hello"}
    assert payloads[1]["choices"][0]["delta"] == {"content": " world"}

    final = payloads[2]
    assert final["choices"][0]["finish_reason"] == "stop"
    assert "doc1" in json.dumps(final)
    assert "YmFzZTY0" in json.dumps(final)


def test_error_event_emits_error_finish_reason_and_stops():
    async def stream_events(**kwargs):
        yield ResponseEvent(text="partial", extra={"done": False})
        yield ErrorEvent(error="Pipeline failed", extra={"done": True})
        yield ResponseEvent(text="should not appear", extra={"done": False})

    client = TestClient(_build_app(stream_events))
    lines = _collect_sse_lines(client)

    assert lines[-1] == "[DONE]"
    payloads = [json.loads(line) for line in lines[:-1]]
    assert payloads[-1]["choices"][0]["finish_reason"] == "error"
    assert "Pipeline failed" in json.dumps(payloads[-1])
    # The event after the error must never have been processed.
    assert not any("should not appear" in json.dumps(p) for p in payloads)


def test_audio_chunk_event_is_relayed_as_orbit_extension_only():
    async def stream_events(**kwargs):
        yield AudioChunkEvent(audio_chunk="YmFzZTY0", audio_format="opus", chunk_index=0)
        yield DoneEvent()

    client = TestClient(_build_app(stream_events))
    lines = _collect_sse_lines(client)
    payloads = [json.loads(line) for line in lines[:-1]]

    assert "content" not in payloads[0]["choices"][0]["delta"]
    assert "YmFzZTY0" in json.dumps(payloads[0])


def test_raw_event_is_skipped():
    async def stream_events(**kwargs):
        yield RawEvent(raw="not valid json")
        yield ResponseEvent(text="hi", extra={"done": False})
        yield DoneEvent()

    client = TestClient(_build_app(stream_events))
    lines = _collect_sse_lines(client)
    payloads = [json.loads(line) for line in lines[:-1]]

    assert payloads[0]["choices"][0]["delta"] == {"role": "assistant", "content": "hi"}


def test_missing_done_event_still_terminates_stream():
    """If the upstream generator ends without a DoneEvent (e.g. cancellation
    — see the roadmap doc's cancellation-no-terminal-event finding), the SSE
    stream must still terminate with [DONE], not hang."""

    async def stream_events(**kwargs):
        yield ResponseEvent(text="hi", extra={"done": False})

    client = TestClient(_build_app(stream_events))
    lines = _collect_sse_lines(client)

    assert lines[-1] == "[DONE]"
