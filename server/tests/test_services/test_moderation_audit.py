"""
Tests for moderation-block auditing in the safety pipeline steps
(server/inference/pipeline/steps/safety_filter.py,
server/inference/pipeline/steps/response_validation.py).

A blocked message/response should populate context.metadata["usage"] with
call_type="moderation" and the moderator's own provider/model, so blocked
conversations show up in the audit/cost UI instead of being silently dropped.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

SERVER_DIR = Path(__file__).parent.parent.parent.absolute()
sys.path.insert(0, str(SERVER_DIR))

from inference.pipeline.base import ProcessingContext  # noqa: E402
from inference.pipeline.steps.response_validation import ResponseValidationStep  # noqa: E402
from inference.pipeline.steps.safety_filter import SafetyFilterStep  # noqa: E402

pytestmark = pytest.mark.asyncio


def _make_container(moderator):
    known = {"moderator_service": moderator}
    container = MagicMock()
    container.has.side_effect = lambda key: key in known
    container.get.side_effect = lambda key: known.get(key)
    container.get_or_none.side_effect = lambda key: known.get(key)
    return container


def _moderator(is_safe, refusal_message=None, provider="openai", model="omni-moderation-latest"):
    moderator = MagicMock()
    moderator.check_safety = AsyncMock(return_value=(is_safe, refusal_message))
    moderator.get_moderator_identity.return_value = (provider, model)
    return moderator


class TestSafetyFilterStep:
    async def test_blocked_message_records_moderation_usage(self):
        moderator = _moderator(False, "I cannot assist with that type of request.")
        container = _make_container(moderator)
        ctx = ProcessingContext(adapter_name="chat", message="bad input")

        result = await SafetyFilterStep(container).process(ctx)

        assert result.is_blocked is True
        usage = result.metadata["usage"]
        assert usage["call_type"] == "moderation"
        assert usage["provider"] == "openai"
        assert usage["model"] == "omni-moderation-latest"

    async def test_safe_message_does_not_record_usage(self):
        moderator = _moderator(True)
        container = _make_container(moderator)
        ctx = ProcessingContext(adapter_name="chat", message="hello")

        result = await SafetyFilterStep(container).process(ctx)

        assert result.is_blocked is False
        assert "usage" not in result.metadata


class TestSafetyFilterStepPreservesEmbeddingUsage:
    async def test_blocked_message_keeps_moderation_record_alongside_prior_embedding_usage(self):
        """A skill-routing embedding call may have already run before the input
        is blocked (see _maybe_detect_skill). That embedding usage must still be
        auditable on its own, and must not swallow the moderation record (it
        previously did, via record_media_generation_usage's embedding fallback)."""
        moderator = _moderator(False, "I cannot assist with that type of request.")
        container = _make_container(moderator)
        ctx = ProcessingContext(adapter_name="chat", message="bad input")
        ctx.metadata["_usage_components"] = [{
            "reported": True, "source": "embedding",
            "provider": "openai", "model": "text-embedding-3-small",
            "prompt_tokens": 12,
        }]

        result = await SafetyFilterStep(container).process(ctx)

        assert result.is_blocked is True
        usage = result.metadata["usage"]
        assert usage["call_type"] == "moderation"
        assert usage["provider"] == "openai"
        assert usage["model"] == "omni-moderation-latest"
        # Detached into its own event, not lost.
        assert result.metadata["embedding_usage"]["call_type"] == "embedding"
        assert "_usage_components" not in result.metadata


class TestResponseValidationStep:
    async def test_blocked_response_records_moderation_usage(self):
        moderator = _moderator(False, "Response blocked by content moderator", provider="shieldstral", model="mistralai/Shieldstral-1.0-3B")
        container = _make_container(moderator)
        ctx = ProcessingContext(adapter_name="chat", message="hi", response="unsafe output")

        result = await ResponseValidationStep(container).process(ctx)

        assert result.is_blocked is True
        assert result.response == ""
        usage = result.metadata["usage"]
        assert usage["call_type"] == "moderation"
        assert usage["provider"] == "shieldstral"
        assert usage["model"] == "mistralai/Shieldstral-1.0-3B"

    async def test_safe_response_does_not_record_usage(self):
        moderator = _moderator(True)
        container = _make_container(moderator)
        ctx = ProcessingContext(adapter_name="chat", message="hi", response="safe output")

        result = await ResponseValidationStep(container).process(ctx)

        assert result.is_blocked is False
        assert "usage" not in result.metadata

    async def test_blocking_a_generated_response_preserves_its_usage_and_cost(self):
        """The LLM call that produced the response already ran and recorded
        real tokens/cost under call_type='chat' before validation blocks it.
        That must not be discarded/overwritten by the moderation record."""
        moderator = _moderator(False, "Response blocked by content moderator")
        container = _make_container(moderator)
        ctx = ProcessingContext(adapter_name="chat", message="hi", response="unsafe output")
        ctx.metadata["usage"] = {
            "call_type": "chat", "provider": "openai", "model": "gpt-5.4-mini",
            "prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70,
            "cost_usd": 0.000053, "reported": True,
        }

        result = await ResponseValidationStep(container).process(ctx)

        assert result.is_blocked is True
        usage = result.metadata["usage"]
        assert usage["call_type"] == "chat"
        assert usage["cost_usd"] == 0.000053
        assert usage["total_tokens"] == 70
