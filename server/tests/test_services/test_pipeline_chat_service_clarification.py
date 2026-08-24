"""
Regression test for PipelineChatService.process_chat's handling of a blocked-
but-answered pipeline context.

IntentClarificationStep (Phase 5, docs/roadmap/intent-template-retrieval.md)
short-circuits LLM inference the same way FetchStep/SafetyFilterStep do —
via ProcessingContext.set_error(..., block=True) — so the pipeline stops
before LLMInferenceStep and the clarifying question becomes the response.

Before this fix, process_chat() (the non-streaming path used by /v1/chat and
the OpenAI-compatible endpoint) treated ANY blocked context as a failure and
returned {"error": ...}, which routes_configurator.py turns into an HTTP 500 —
so a clarification question crashed the request instead of answering it.
Only process_chat_stream() had is_blocked-aware handling.

    venv/bin/python -m pytest server/tests/test_services/test_pipeline_chat_service_clarification.py
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))


def _build_service(*, blocked_response: str = None, intent_clarification: bool = False, error: str = None):
    from services.pipeline_chat_service import PipelineChatService
    from inference.pipeline.base import ProcessingContext

    svc = PipelineChatService.__new__(PipelineChatService)
    svc._query_cache_enabled = False
    svc.initialize = AsyncMock()
    svc.response_processor = MagicMock()
    svc.response_processor.log_request_details = AsyncMock()
    svc.response_processor.process_response = AsyncMock(return_value=("final response", "msg-1"))
    svc.response_processor.build_result = MagicMock(return_value={"response": "final response"})

    svc.context_builder = MagicMock()
    svc.context_builder.resolve_runtime_model_override = MagicMock(return_value=(None, None, None))

    svc.conversation_handler = MagicMock()
    svc.conversation_handler.get_context = AsyncMock(return_value=[])

    svc._maybe_detect_skill = AsyncMock(return_value=(None, False))
    svc._audit_usage_only_request = AsyncMock()
    svc._audit_embedding_usage = AsyncMock()
    svc._audit_reranking_usage = AsyncMock()
    svc._determine_inference_backend = MagicMock(return_value="test-backend")
    svc._determine_inference_model = MagicMock(return_value="test-model")
    svc._maybe_generate_full_audio = AsyncMock(return_value=(None, None))
    svc._persist_generated_image = AsyncMock()
    svc._persist_generated_video = AsyncMock()
    svc._persist_generated_document = AsyncMock()
    svc._persist_generated_audio = AsyncMock()

    context = ProcessingContext(
        message="what department is that in?",
        adapter_name="intent-sql-postgres",
        session_id="sess1",
    )
    context.retrieved_docs = [{
        "content": blocked_response or "",
        "metadata": {"source": "intent", "intent_action": "clarify"} if intent_clarification else {},
    }]
    if error is not None:
        context.set_error(error, block=True)
        context.response = blocked_response if blocked_response is not None else error
        if intent_clarification:
            context.metadata["intent_clarification"] = context.retrieved_docs[0]["metadata"]

    svc.context_builder.build_context = MagicMock(return_value=context)
    svc.pipeline = MagicMock()
    svc.pipeline.process = AsyncMock(return_value=context)

    return svc, context


@pytest.mark.asyncio
async def test_intent_clarification_block_returns_response_not_error():
    """A clarification question must reach the client as a normal chat response."""
    svc, context = _build_service(
        blocked_response="Which department did you mean: Engineering or Sales?",
        intent_clarification=True,
        error="Which department did you mean: Engineering or Sales?",
    )

    result = await svc.process_chat(
        message=context.message, client_ip="127.0.0.1", adapter_name=context.adapter_name,
        session_id=context.session_id,
    )

    assert "error" not in result
    svc.response_processor.process_response.assert_awaited_once()
    svc._audit_usage_only_request.assert_not_called()


@pytest.mark.asyncio
async def test_non_clarification_block_still_returns_error():
    """A genuinely blocked/failed context (e.g. safety filter refusal, no
    intent_clarification marker) must still surface as {"error": ...} —
    guards against an over-broad fix that swallows real failures."""
    svc, context = _build_service(
        blocked_response=None,
        intent_clarification=False,
        error="Message blocked by content moderator",
    )

    result = await svc.process_chat(
        message=context.message, client_ip="127.0.0.1", adapter_name=context.adapter_name,
        session_id=context.session_id,
    )

    assert result == {"error": "Message blocked by content moderator"}
    svc.response_processor.process_response.assert_not_awaited()
    svc._audit_usage_only_request.assert_awaited_once()


def _build_streaming_service(*, blocked_text: str, real_error: bool = False):
    """Mirrors _build_service but for process_chat_stream: mocks
    _consume_pipeline_stream as an empty async generator (exactly what
    streaming_handler.process_stream does for a single {"response": ..., "done":
    true} pipeline chunk — it accumulates the text internally and yields
    nothing), leaving final_state None. That's the situation the streaming
    is_blocked handling at pipeline_chat_service.py:~1153 exists for."""
    from services.pipeline_chat_service import PipelineChatService
    from inference.pipeline.base import ProcessingContext

    svc = PipelineChatService.__new__(PipelineChatService)
    svc._query_cache_enabled = False
    svc.initialize = AsyncMock()
    svc.response_processor = MagicMock()
    svc.response_processor.log_request_details = AsyncMock()

    svc.context_builder = MagicMock()
    svc.context_builder.resolve_runtime_model_override = MagicMock(return_value=(None, None, None))

    svc.conversation_handler = MagicMock()
    svc.conversation_handler.get_context = AsyncMock(return_value=[])

    svc._maybe_detect_skill = AsyncMock(return_value=(None, False))
    svc._audit_usage_only_request = AsyncMock()

    context = ProcessingContext(
        message="show me expensive orders",
        adapter_name="intent-sql-postgres",
        session_id="sess1",
    )
    if real_error:
        context.error = "Datasource unavailable"  # has_error() true, is_blocked False
    else:
        context.set_error(blocked_text, block=True)
        context.response = blocked_text

    svc.context_builder.build_context = MagicMock(return_value=context)

    async def _empty_stream(*args, **kwargs):
        return
        yield  # pragma: no cover - makes this an async generator

    svc._consume_pipeline_stream = _empty_stream

    return svc, context


@pytest.mark.asyncio
async def test_streaming_clarification_block_is_streamed_to_client():
    """Before the fix, context.has_error() (true for any is_blocked context)
    returned before the dedicated is_blocked handling ever ran, so the client
    received zero chunks for a clarification/refusal — reproducing the "No
    response received from the server" symptom OrbitChat showed."""
    svc, context = _build_streaming_service(blocked_text="Which one did you mean: Engineering or Sales?")

    chunks = [chunk async for chunk in svc.process_chat_stream(
        message=context.message, client_ip="127.0.0.1", adapter_name=context.adapter_name,
        session_id=context.session_id,
    )]

    assert any("Which one did you mean" in c for c in chunks), chunks
    assert any('"done": true' in c for c in chunks), chunks
    svc._audit_usage_only_request.assert_not_called()


@pytest.mark.asyncio
async def test_streaming_real_error_still_short_circuits():
    """A genuine error (has_error() true, is_blocked false) must still stop
    the stream via the audit-and-return path, not fall into the blocked
    handling below it."""
    svc, context = _build_streaming_service(blocked_text="", real_error=True)

    chunks = [chunk async for chunk in svc.process_chat_stream(
        message=context.message, client_ip="127.0.0.1", adapter_name=context.adapter_name,
        session_id=context.session_id,
    )]

    assert chunks == []
    svc._audit_usage_only_request.assert_awaited_once()
