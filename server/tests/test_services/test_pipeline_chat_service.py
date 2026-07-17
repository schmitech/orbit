"""
Unit tests for PipelineChatService.process_chat_stream

Focuses on the post-stream persistence gate: whether a completed stream's
response gets stored via conversation_handler.store_turn.

- test_cancelled_stream_skips_history_persistence: a stream that finishes
  naturally (stream_completed=True) after the client already requested
  cancellation must NOT be persisted. Otherwise the abandoned response leaks
  into the next request's context (fetched via get_context) and the model
  answers the stale, cancelled prompt instead of the new one.
- test_uncancelled_stream_still_persists_normally: guards the other direction
  — a normal, non-cancelled stream must still be persisted as before.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add server directory to path
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))


def _build_service(cancelled: bool):
    """Build a minimal PipelineChatService instance with a fake pipeline stream
    that always completes with a fixed response, plus mocked handlers.

    Uses a real ProcessingContext (not a bare mock/namespace) so the code under
    test fails loudly on a NameError/AttributeError rather than silently
    short-circuiting before reaching the persistence gate.
    """
    from services.pipeline_chat_service import PipelineChatService
    from services.chat_handlers.streaming_handler import StreamingState
    from inference.pipeline.base import ProcessingContext

    svc = PipelineChatService.__new__(PipelineChatService)
    svc._query_cache_enabled = False
    svc.config = {}
    svc.initialize = AsyncMock()

    svc.response_processor = MagicMock()
    svc.response_processor.log_request_details = AsyncMock()
    svc.response_processor.process_response = AsyncMock(return_value=("the full essay response", "msg-1"))
    # Sync method — short-circuits _build_threading_metadata to return None.
    svc.response_processor._adapter_supports_threading = MagicMock(return_value=False)

    svc.conversation_handler = MagicMock()
    svc.conversation_handler.get_context = AsyncMock(return_value=[])
    svc.conversation_handler.check_limit_warning = AsyncMock(return_value=None)

    svc.streaming_handler = MagicMock()
    svc.streaming_handler.build_done_chunk = MagicMock(return_value='data: {"done": true}\n\n')

    real_context = ProcessingContext(
        message="Write a 2000 word essay about distributed systems.",
        adapter_name="test-adapter",
        session_id="sess1",
        runtime_provider="test-provider",
    )
    svc.context_builder = MagicMock()
    svc.context_builder.build_context = MagicMock(return_value=real_context)
    svc.context_builder.resolve_runtime_model_override = MagicMock(return_value=(None, None, None))

    completed_state = StreamingState()
    completed_state.accumulated_text = "the full essay response"
    completed_state.stream_completed = True

    async def fake_consume_pipeline_stream(*args, **kwargs):
        yield 'data: {"response": "the full essay response", "done": false}\n\n', completed_state

    svc._consume_pipeline_stream = fake_consume_pipeline_stream

    cancel_event = asyncio.Event()
    if cancelled:
        cancel_event.set()

    return svc, real_context, cancel_event


@pytest.mark.asyncio
async def test_cancelled_stream_skips_history_persistence():
    """A stream that finishes naturally after the client already requested
    cancellation must not be stored via conversation_handler."""
    try:
        svc, real_context, cancel_event = _build_service(cancelled=True)
    except (ImportError, ModuleNotFoundError):
        pytest.skip("pipeline_chat_service dependencies not available in test env")

    chunks = [chunk async for chunk in svc.process_chat_stream(
        message=real_context.message,
        client_ip="127.0.0.1",
        adapter_name="test-adapter",
        session_id="sess1",
        cancel_event=cancel_event,
    )]

    # Sanity check: the fake pipeline chunk always reaches the client...
    assert any("full essay response" in c for c in chunks)
    # ...but persistence must be skipped once cancelled, and no error chunk emitted.
    assert not any('"error"' in c for c in chunks), chunks
    svc.response_processor.process_response.assert_not_called()


@pytest.mark.asyncio
async def test_uncancelled_stream_still_persists_normally():
    """A normal, non-cancelled stream must still be persisted as before —
    guards against an over-broad fix that skips persistence unconditionally."""
    try:
        svc, real_context, cancel_event = _build_service(cancelled=False)
    except (ImportError, ModuleNotFoundError):
        pytest.skip("pipeline_chat_service dependencies not available in test env")

    chunks = [chunk async for chunk in svc.process_chat_stream(
        message=real_context.message,
        client_ip="127.0.0.1",
        adapter_name="test-adapter",
        session_id="sess1",
        cancel_event=cancel_event,
    )]

    assert any("full essay response" in c for c in chunks)
    assert not any('"error"' in c for c in chunks), chunks
    svc.response_processor.process_response.assert_awaited_once()
