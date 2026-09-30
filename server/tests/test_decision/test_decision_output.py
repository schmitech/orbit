"""
Tests that a decision model's typed result reaches every terminal output:
- InferencePipeline.process_stream non-streaming fallback payload
- StreamEvent parsing / serialization (DoneEvent.decision)
- StreamingHandler.build_done_event
- ResponseProcessor.build_result (non-streaming process_chat result)
- OpenAI-compatible completion response orbit extension
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

SERVER_DIR = Path(__file__).parent.parent.parent.absolute()
sys.path.insert(0, str(SERVER_DIR))

from inference.pipeline.base import ProcessingContext  # noqa: E402
from inference.pipeline.pipeline import InferencePipeline  # noqa: E402
from inference.pipeline.steps import DecisionModelStep, LLMInferenceStep  # noqa: E402
from services.chat_handlers.response_processor import ResponseProcessor  # noqa: E402
from services.chat_handlers.streaming_events import (  # noqa: E402
    DoneEvent,
    parse_stream_payload,
    stream_event_to_dict,
)
from services.chat_handlers.streaming_handler import StreamingHandler, StreamingState  # noqa: E402

DECISION = {
    "model": "nimble",
    "answers": {"refund": {"type": "noul", "noul": 0.99}},
    "usage": {"input_tokens": 10, "output_tokens": 1},
}


def _container():
    adapter_manager = MagicMock()
    adapter_manager.get_adapter_config.return_value = {
        "type": "decision_model",
        "decision_provider": "ollama",
        "config": {"questions": {"refund": {"type": "noul", "instructions": "Refund?"}}},
    }
    service = MagicMock(model="nimble")
    service.decide = AsyncMock(return_value=DECISION)
    adapter_manager.get_decision_service = AsyncMock(return_value=service)
    known = {"adapter_manager": adapter_manager, "config": {}}
    container = MagicMock()
    container.has.side_effect = lambda key: key in known
    container.get.side_effect = lambda key: known.get(key)
    container.get_or_none.side_effect = lambda key: known.get(key)
    return container


async def test_process_stream_fallback_includes_decision():
    container = _container()
    pipeline = InferencePipeline([DecisionModelStep(container), LLMInferenceStep(container)], container)

    chunks = [json.loads(c) async for c in pipeline.process_stream(
        ProcessingContext(adapter_name="ticket-triage", message="refund please"),
    )]

    assert chunks[-1]["done"] is True
    assert chunks[-1]["decision"] == DECISION
    assert json.loads(chunks[-1]["response"]) == DECISION["answers"]


async def test_non_streaming_process_sets_context_decision():
    container = _container()
    pipeline = InferencePipeline([DecisionModelStep(container), LLMInferenceStep(container)], container)

    ctx = await pipeline.process(ProcessingContext(adapter_name="ticket-triage", message="refund please"))

    assert ctx.decision == DECISION
    assert not ctx.has_error()


def test_done_event_round_trips_decision():
    event = parse_stream_payload({"done": True, "decision": DECISION})

    assert isinstance(event, DoneEvent)
    assert event.decision == DECISION
    assert stream_event_to_dict(event) == {"done": True, "decision": DECISION}


def test_done_event_without_decision_omits_key():
    assert "decision" not in stream_event_to_dict(DoneEvent())


def test_build_done_event_carries_decision():
    handler = StreamingHandler(config={}, audio_handler=MagicMock())

    event = handler.build_done_event(state=StreamingState(), decision=DECISION)

    assert event.decision == DECISION
    assert stream_event_to_dict(event)["decision"] == DECISION


def test_build_result_includes_decision():
    processor = ResponseProcessor(config={}, conversation_handler=MagicMock(), logger_service=MagicMock())

    result = processor.build_result(
        response=json.dumps(DECISION["answers"]), sources=[], metadata={}, processing_time=0.1,
        decision=DECISION,
    )

    assert result["decision"] == DECISION


def test_build_result_without_decision_omits_key():
    processor = ResponseProcessor(config={}, conversation_handler=MagicMock(), logger_service=MagicMock())

    result = processor.build_result(response="hi", sources=[], metadata={}, processing_time=0.1)

    assert "decision" not in result


def test_openai_completion_response_puts_decision_in_orbit_extension():
    from ai_services.services.inference_service import OpenAIResponseFormatter

    formatter = OpenAIResponseFormatter(model="nimble", provider="ollama")
    response = formatter.build_completion_response(content="{}", extra={"decision": DECISION})

    assert response["orbit"]["decision"] == DECISION
