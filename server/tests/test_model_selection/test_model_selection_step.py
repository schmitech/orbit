"""
Tests for ModelSelectionStep (server/inference/pipeline/steps/model_selection.py).

Covers:
- should_execute gating on context.auto_select_requested
- score -> routing_tier rounding (boundary cases)
- degrade paths: low confidence, refused, malformed answer, decision-service
  error, no matching routing_tier entry — all leave context unchanged, no error
- usage recorded via add_usage_component(source="model_routing")
- resolution follows context.model_routing_adapter_name, not context.adapter_name
  (the skill-with-no-own-LLM case)
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

SERVER_DIR = Path(__file__).parent.parent.parent.absolute()
sys.path.insert(0, str(SERVER_DIR))

from inference.pipeline.base import ProcessingContext  # noqa: E402
from inference.pipeline.steps.model_selection import ModelSelectionStep  # noqa: E402

ALLOWED_MODELS = [
    {"name": "low-m", "provider": "ollama", "model": "m-low", "routing_tier": "low"},
    {"name": "med-m", "provider": "ollama_cloud", "model": "m-med", "routing_tier": "medium"},
    {"name": "high-m", "provider": "anthropic", "model": "m-high", "routing_tier": "high"},
]


def _adapter_config(**overrides):
    config = {
        "capabilities": {"auto_model_selection": {"enabled": True, "decision_provider": "ollama"}},
        "allowed_models": list(ALLOWED_MODELS),
    }
    config.update(overrides)
    return config


def _decision_result(score, confidence=0.8, refused=False):
    return {
        "model": "tev1",
        "answers": {
            "capability": {
                "type": "score", "score": score, "confidence": confidence, "refused": refused,
                "legend": {"0": "low", "1": "medium", "2": "high"},
            }
        },
        "usage": {"input_tokens": 50, "output_tokens": 2},
    }


def _make_container(adapter_config=None, service=None, decide_side_effect=None):
    adapter_manager = MagicMock()
    adapter_manager.get_adapter_config.return_value = adapter_config if adapter_config is not None else _adapter_config()
    if service is None:
        service = MagicMock()
        if decide_side_effect is not None:
            service.decide = AsyncMock(side_effect=decide_side_effect)
        else:
            service.decide = AsyncMock(return_value=_decision_result(1.0))
    adapter_manager.get_decision_service = AsyncMock(return_value=service)

    known = {"adapter_manager": adapter_manager, "config": {"decision": {"provider": "ollama"}}}
    container = MagicMock()
    container.has.side_effect = lambda key: key in known
    container.get.side_effect = lambda key: known.get(key)
    container.get_or_none.side_effect = lambda key: known.get(key)
    return container, adapter_manager, service


def _ctx(**kwargs):
    defaults = dict(
        adapter_name="chat-adapter",
        model_routing_adapter_name="chat-adapter",
        auto_select_requested=True,
        message="hello",
    )
    defaults.update(kwargs)
    return ProcessingContext(**defaults)


class TestShouldExecute:
    def test_false_without_auto_select_requested(self):
        container, _, _ = _make_container()
        step = ModelSelectionStep(container)
        ctx = _ctx(auto_select_requested=False)
        assert step.should_execute(ctx) is False

    def test_false_when_blocked(self):
        container, _, _ = _make_container()
        step = ModelSelectionStep(container)
        ctx = _ctx(is_blocked=True)
        assert step.should_execute(ctx) is False

    def test_true_when_requested_and_not_blocked(self):
        container, _, _ = _make_container()
        step = ModelSelectionStep(container)
        ctx = _ctx()
        assert step.should_execute(ctx) is True


class TestScoreRounding:
    @pytest.mark.asyncio
    async def test_score_rounds_down_to_medium(self):
        container, _, service = _make_container()
        service.decide = AsyncMock(return_value=_decision_result(1.4))
        step = ModelSelectionStep(container)
        result = await step.process(_ctx())
        assert result.auto_selected_model == "med-m"
        assert result.runtime_provider == "ollama_cloud"
        assert result.runtime_model_name == "m-med"

    @pytest.mark.asyncio
    async def test_score_rounds_up_to_high(self):
        container, _, service = _make_container()
        service.decide = AsyncMock(return_value=_decision_result(1.6))
        step = ModelSelectionStep(container)
        result = await step.process(_ctx())
        assert result.auto_selected_model == "high-m"


class TestDegradePaths:
    @pytest.mark.asyncio
    async def test_low_confidence_leaves_context_unchanged(self):
        container, _, service = _make_container()
        service.decide = AsyncMock(return_value=_decision_result(1.0, confidence=0.1))
        step = ModelSelectionStep(container)
        ctx = _ctx()
        result = await step.process(ctx)
        assert result.auto_selected_model is None
        assert result.runtime_provider is None
        assert not result.has_error()

    @pytest.mark.asyncio
    async def test_refused_leaves_context_unchanged(self):
        container, _, service = _make_container()
        service.decide = AsyncMock(return_value=_decision_result(1.0, refused=True))
        step = ModelSelectionStep(container)
        result = await step.process(_ctx())
        assert result.auto_selected_model is None
        assert not result.has_error()

    @pytest.mark.asyncio
    async def test_malformed_answer_leaves_context_unchanged(self):
        container, _, service = _make_container()
        service.decide = AsyncMock(return_value={"model": "tev1", "answers": {}, "usage": {}})
        step = ModelSelectionStep(container)
        result = await step.process(_ctx())
        assert result.auto_selected_model is None
        assert not result.has_error()

    @pytest.mark.asyncio
    async def test_non_numeric_score_leaves_context_unchanged(self):
        """A malformed (non-numeric) score/confidence must degrade, not raise
        (round()/comparison on a non-numeric value would otherwise blow up the
        whole pipeline step instead of falling back to the default model)."""
        container, _, service = _make_container()
        service.decide = AsyncMock(return_value=_decision_result("not-a-number", confidence=0.8))
        step = ModelSelectionStep(container)
        result = await step.process(_ctx())
        assert result.auto_selected_model is None
        assert not result.has_error()

    @pytest.mark.asyncio
    async def test_non_numeric_confidence_leaves_context_unchanged(self):
        container, _, service = _make_container()
        service.decide = AsyncMock(return_value=_decision_result(1.0, confidence="high"))
        step = ModelSelectionStep(container)
        result = await step.process(_ctx())
        assert result.auto_selected_model is None
        assert not result.has_error()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("score", "confidence"),
        [(float("nan"), 0.8), (float("inf"), 0.8), (1.0, float("nan")), (1.0, float("inf"))],
    )
    async def test_non_finite_decision_values_leave_context_unchanged(self, score, confidence):
        container, _, service = _make_container()
        service.decide = AsyncMock(return_value=_decision_result(score, confidence=confidence))
        step = ModelSelectionStep(container)
        result = await step.process(_ctx())
        assert result.auto_selected_model is None
        assert not result.has_error()

    @pytest.mark.asyncio
    async def test_decision_service_exception_leaves_context_unchanged(self):
        container, _, _ = _make_container(decide_side_effect=RuntimeError("boom"))
        step = ModelSelectionStep(container)
        result = await step.process(_ctx())
        assert result.auto_selected_model is None
        assert not result.has_error()
        assert not result.is_blocked

    @pytest.mark.asyncio
    async def test_no_matching_tier_leaves_context_unchanged(self):
        config = _adapter_config(allowed_models=[
            {"name": "low-m", "provider": "ollama", "model": "m-low", "routing_tier": "low"},
            {"name": "high-m", "provider": "anthropic", "model": "m-high", "routing_tier": "high"},
        ])
        container, _, service = _make_container(adapter_config=config)
        service.decide = AsyncMock(return_value=_decision_result(1.0))  # resolves to "medium", not defined
        step = ModelSelectionStep(container)
        result = await step.process(_ctx())
        assert result.auto_selected_model is None
        assert not result.has_error()

    @pytest.mark.asyncio
    async def test_no_routing_tier_entries_leaves_context_unchanged(self):
        config = _adapter_config(allowed_models=[{"name": "auto"}])
        container, _, _ = _make_container(adapter_config=config)
        step = ModelSelectionStep(container)
        result = await step.process(_ctx())
        assert result.auto_selected_model is None
        assert not result.has_error()


class TestUsageTracking:
    @pytest.mark.asyncio
    async def test_successful_decision_adds_model_routing_usage_component(self):
        container, _, service = _make_container()
        service.decide = AsyncMock(return_value=_decision_result(1.0))
        step = ModelSelectionStep(container)
        result = await step.process(_ctx())
        components = result.metadata.get("_usage_components", [])
        assert any(c.get("source") == "model_routing" for c in components)
        routing_component = next(c for c in components if c.get("source") == "model_routing")
        assert routing_component["prompt_tokens"] == 50
        assert routing_component["completion_tokens"] == 2

    @pytest.mark.asyncio
    async def test_failed_matching_still_records_usage(self):
        """A routing call that succeeded but found no matching tier is still costed."""
        config = _adapter_config(allowed_models=[
            {"name": "low-m", "provider": "ollama", "model": "m-low", "routing_tier": "low"},
        ])
        container, _, service = _make_container(adapter_config=config)
        service.decide = AsyncMock(return_value=_decision_result(2.0))  # resolves to "high", undefined
        step = ModelSelectionStep(container)
        result = await step.process(_ctx())
        assert result.auto_selected_model is None
        components = result.metadata.get("_usage_components", [])
        assert any(c.get("source") == "model_routing" for c in components)


class TestRoutingAdapterResolution:
    @pytest.mark.asyncio
    async def test_resolves_via_model_routing_adapter_name_not_adapter_name(self):
        """A skill with no LLM of its own: context.adapter_name is the skill adapter,
        but allowed_models/auto_model_selection must come from the calling adapter."""
        calling_adapter_config = _adapter_config()
        skill_adapter_config = {"capabilities": {}, "allowed_models": []}

        def get_adapter_config(name):
            return {"chat-adapter": calling_adapter_config, "fetch-skill": skill_adapter_config}.get(name)

        adapter_manager = MagicMock()
        adapter_manager.get_adapter_config.side_effect = get_adapter_config
        service = MagicMock()
        service.decide = AsyncMock(return_value=_decision_result(1.0))
        adapter_manager.get_decision_service = AsyncMock(return_value=service)
        known = {"adapter_manager": adapter_manager, "config": {"decision": {"provider": "ollama"}}}
        container = MagicMock()
        container.has.side_effect = lambda key: key in known
        container.get.side_effect = lambda key: known.get(key)
        container.get_or_none.side_effect = lambda key: known.get(key)

        step = ModelSelectionStep(container)
        ctx = _ctx(adapter_name="fetch-skill", model_routing_adapter_name="chat-adapter")
        result = await step.process(ctx)
        assert result.auto_selected_model == "med-m"
