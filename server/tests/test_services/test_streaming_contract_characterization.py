"""
Characterization tests for the streaming payload contract.

Step 1 ("Inventory") of docs/roadmap/pipeline-streaming-structured-events.md:
pin down today's actual yield-point behavior across StreamingHandler and
PipelineChatService before any structured-event refactor touches them. These
tests intentionally describe existing behavior, including the quirks the
roadmap doc calls out (e.g. cancellation truncating the stream with no done
chunk) — they are not a statement of desired behavior.
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))


def _build_service():
    """Minimal PipelineChatService with mocked collaborators, mirroring the
    pattern in test_pipeline_chat_service.py."""
    from services.pipeline_chat_service import PipelineChatService
    from services.chat_handlers.streaming_handler import StreamingState
    from inference.pipeline.base import ProcessingContext

    svc = PipelineChatService.__new__(PipelineChatService)
    svc._query_cache_enabled = False
    svc.config = {}
    svc.initialize = AsyncMock()

    svc.response_processor = MagicMock()
    svc.response_processor.log_request_details = AsyncMock()
    svc.response_processor.process_response = AsyncMock(return_value=("resp", "msg-1"))
    svc.response_processor._adapter_supports_threading = MagicMock(return_value=False)

    svc.conversation_handler = MagicMock()
    svc.conversation_handler.get_context = AsyncMock(return_value=[])
    svc.conversation_handler.check_limit_warning = AsyncMock(return_value=None)

    svc.streaming_handler = MagicMock()
    svc.streaming_handler.build_done_chunk = MagicMock(return_value='data: {"done": true}\n\n')

    svc.context_builder = MagicMock()
    svc.context_builder.resolve_runtime_model_override = MagicMock(return_value=(None, None, None))

    return svc, StreamingState, ProcessingContext


@pytest.mark.asyncio
async def test_consume_pipeline_stream_cancelled_mid_stream_emits_no_done_chunk():
    """Confirms the roadmap doc's claim: setting cancel_event mid-stream makes
    _consume_pipeline_stream_events return immediately with no done-shaped
    event at all — the stream is truncated, not terminated with a done
    marker."""
    from services.pipeline_chat_service import PipelineChatService
    from services.chat_handlers.streaming_handler import StreamingState
    from services.chat_handlers.streaming_events import DoneEvent, ResponseEvent

    svc = PipelineChatService.__new__(PipelineChatService)
    svc.pipeline = MagicMock()
    svc.pipeline.process_stream = MagicMock(return_value=MagicMock())

    async def fake_handler_process_stream_events(**kwargs):
        yield ResponseEvent(text="hello", extra={"done": False}), StreamingState()
        yield ResponseEvent(text=" world", extra={"done": False}), StreamingState()
        yield DoneEvent(), StreamingState()

    svc.streaming_handler = MagicMock()
    svc.streaming_handler.process_stream_events = fake_handler_process_stream_events

    cancel_event = asyncio.Event()
    seen = []
    async for event, _state in svc._consume_pipeline_stream_events(
        context=MagicMock(), adapter_name="a", tts_voice=None, language=None,
        return_audio=False, cancel_event=cancel_event,
    ):
        seen.append(event)
        cancel_event.set()  # simulate a client-triggered stop after the first item

    assert seen == [ResponseEvent(text="hello", extra={"done": False})]
    assert not any(isinstance(event, DoneEvent) for event in seen)


@pytest.mark.asyncio
async def test_safety_filter_refusal_yields_bare_done_chunk():
    """A safety-filter refusal emits {"response": refusal, "done": false} then
    a bare {"done": true} — no sources/metadata/threading, unlike the
    fully-featured done chunk built by build_done_chunk() for normal
    completions."""
    svc, StreamingState, ProcessingContext = _build_service()

    context = ProcessingContext(
        message="blocked message", adapter_name="test-adapter", session_id="sess1",
    )
    context.is_blocked = True
    context.error = "Message blocked by content moderator"

    svc.context_builder.build_context = MagicMock(return_value=context)

    async def fake_consume_pipeline_stream_events(*args, **kwargs):
        return
        yield  # pragma: no cover - makes this an async generator

    svc._consume_pipeline_stream_events = fake_consume_pipeline_stream_events

    chunks = [c async for c in svc.process_chat_stream(
        message=context.message, client_ip="127.0.0.1", adapter_name="test-adapter",
        session_id="sess1",
    )]

    assert chunks == [
        'data: {"response": "Message blocked by content moderator", "done": false}\n\n',
        'data: {"done": true}\n\n',
    ]
    svc.response_processor.process_response.assert_not_called()


@pytest.mark.asyncio
async def test_cache_hit_stream_done_chunk_includes_sources_and_metadata():
    """A cache-hit stream's done chunk shape differs from both the safety-filter
    bare done chunk and the build_done_chunk()-produced normal completion: it
    carries only "sources"/"metadata" straight from the cached entry."""
    svc, StreamingState, ProcessingContext = _build_service()
    svc._query_cache_enabled = True
    svc._build_query_cache_key = MagicMock(return_value="cache-key")
    svc._get_cached_response = AsyncMock(return_value={
        "response": "cached answer",
        "sources": [{"title": "doc1"}],
        "metadata": {"cached": True},
    })

    chunks = [c async for c in svc.process_chat_stream(
        message="hi", client_ip="127.0.0.1", adapter_name="test-adapter", session_id="sess1",
    )]

    assert chunks == [
        'data: {"response": "cached answer", "done": false}\n\n',
        'data: ' + json.dumps({
            "done": True,
            "sources": [{"title": "doc1"}],
            "metadata": {"cached": True},
        }) + '\n\n',
    ]


@pytest.mark.asyncio
async def test_empty_message_and_adapter_validation_errors():
    """Input-validation failures short-circuit before initialize()/pipeline
    work, each with their own {"error": ..., "done": true} chunk."""
    svc, _, _ = _build_service()

    chunks = [c async for c in svc.process_chat_stream(
        message="   ", client_ip="127.0.0.1", adapter_name="test-adapter", session_id="sess1",
    )]
    assert chunks == ['data: {"error": "message must not be empty", "done": true}\n\n']

    chunks = [c async for c in svc.process_chat_stream(
        message="hi", client_ip="127.0.0.1", adapter_name="", session_id="sess1",
    )]
    assert chunks == ['data: {"error": "adapter_name must not be empty", "done": true}\n\n']
