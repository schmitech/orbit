"""
Tests for DecisionModelStep (server/inference/pipeline/steps/decision_model.py).

Covers:
- should_execute gating on adapter type
- plain-text message -> {state_key: message}; JSON {"state", "questions"} override (allowed / ignored)
- question validation rules
- provider/model resolution order
- context.decision / context.response / usage population, provider errors surfaced
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

SERVER_DIR = Path(__file__).parent.parent.parent.absolute()
sys.path.insert(0, str(SERVER_DIR))

from inference.pipeline.base import ProcessingContext  # noqa: E402
from inference.pipeline.steps.decision_model import DecisionModelStep, validate_questions  # noqa: E402

QUESTIONS = {
    "team": {"type": "choice", "instructions": "Which team?", "criteria": {"billing": "Payments", "other": "Other"}},
    "refund": {"type": "noul", "instructions": "Refund requested?"},
}

RESULT = {
    "model": "nimble",
    "answers": {
        "team": {"type": "choice", "choice": "billing", "probabilities": {"billing": 0.98, "other": 0.02}},
        "refund": {"type": "noul", "noul": 0.99},
    },
    "usage": {"input_tokens": 200, "output_tokens": 3},
}


def _adapter_config(**overrides):
    config = {
        "type": "decision_model",
        "decision_provider": "ollama",
        "model": "nimble",
        "config": {"state_key": "ticket", "questions": QUESTIONS},
    }
    config.update(overrides)
    return config


def _make_container(adapter_config=None, service=None, global_provider="typesafe"):
    adapter_manager = MagicMock()
    adapter_manager.get_adapter_config.return_value = adapter_config or _adapter_config()
    if service is None:
        service = MagicMock(model="nimble")
        service.decide = AsyncMock(return_value=RESULT)
    adapter_manager.get_decision_service = AsyncMock(return_value=service)

    known = {"adapter_manager": adapter_manager, "config": {"decision": {"provider": global_provider}}}
    container = MagicMock()
    container.has.side_effect = lambda key: key in known
    container.get.side_effect = lambda key: known.get(key)
    container.get_or_none.side_effect = lambda key: known.get(key)
    return container, adapter_manager, service


def _ctx(message="I was charged twice, please refund me", **kwargs):
    return ProcessingContext(adapter_name="ticket-triage", message=message, **kwargs)


class TestShouldExecute:
    def test_runs_for_decision_model_adapters(self):
        container, _, _ = _make_container()
        assert DecisionModelStep(container).should_execute(_ctx()) is True

    def test_skips_other_adapter_types(self):
        container, _, _ = _make_container(_adapter_config(type="passthrough"))
        assert DecisionModelStep(container).should_execute(_ctx()) is False

    def test_skips_blocked_context(self):
        container, _, _ = _make_container()
        ctx = _ctx()
        ctx.is_blocked = True
        assert DecisionModelStep(container).should_execute(ctx) is False

    def test_does_not_stream(self):
        container, _, _ = _make_container()
        assert DecisionModelStep(container).supports_streaming() is False


class TestProcess:
    async def test_plain_message_becomes_state_and_populates_outputs(self):
        container, adapter_manager, service = _make_container()

        ctx = await DecisionModelStep(container).process(_ctx())

        service.decide.assert_awaited_once_with(
            {"ticket": "I was charged twice, please refund me"}, QUESTIONS, model="nimble",
        )
        adapter_manager.get_decision_service.assert_awaited_once_with("ollama", "ticket-triage")
        assert ctx.decision == RESULT
        assert json.loads(ctx.response) == RESULT["answers"]
        assert ctx.runtime_provider == "ollama"
        assert ctx.runtime_model_name == "nimble"
        assert ctx.metadata["usage"]["prompt_tokens"] == 200
        assert ctx.metadata["usage"]["completion_tokens"] == 3
        assert ctx.metadata["usage"]["call_type"] == "decision"
        assert not ctx.has_error()

    async def test_default_state_key_is_input(self):
        container, _, service = _make_container(_adapter_config(config={"questions": QUESTIONS}))

        await DecisionModelStep(container).process(_ctx("hello"))

        assert service.decide.await_args.args[0] == {"input": "hello"}

    async def test_json_state_is_used(self):
        container, _, service = _make_container()
        message = json.dumps({"state": {"ticket": "t", "customer_tier": "gold"}})

        await DecisionModelStep(container).process(_ctx(message))

        assert service.decide.await_args.args[0] == {"ticket": "t", "customer_tier": "gold"}
        assert service.decide.await_args.args[1] == QUESTIONS

    async def test_json_question_override_when_allowed(self):
        custom = {"spam": {"type": "noul", "instructions": "Is this spam?"}}
        config = _adapter_config(config={"questions": QUESTIONS, "allow_question_override": True})
        container, _, service = _make_container(config)

        await DecisionModelStep(container).process(_ctx(json.dumps({"state": {"x": 1}, "questions": custom})))

        assert service.decide.await_args.args[1] == custom

    async def test_json_question_override_ignored_when_not_allowed(self):
        custom = {"spam": {"type": "noul", "instructions": "Is this spam?"}}
        container, _, service = _make_container()

        await DecisionModelStep(container).process(_ctx(json.dumps({"state": {"x": 1}, "questions": custom})))

        assert service.decide.await_args.args[1] == QUESTIONS

    async def test_json_without_state_object_is_treated_as_text(self):
        container, _, service = _make_container()
        message = '{"not_state": true}'

        await DecisionModelStep(container).process(_ctx(message))

        assert service.decide.await_args.args[0] == {"ticket": message}

    async def test_invalid_questions_set_error_without_calling_provider(self):
        container, adapter_manager, service = _make_container(_adapter_config(config={"questions": {}}))

        ctx = await DecisionModelStep(container).process(_ctx())

        assert ctx.has_error()
        assert "non-empty" in ctx.error
        adapter_manager.get_decision_service.assert_not_awaited()

    async def test_provider_resolution_order(self):
        # runtime_provider > adapter decision_provider > global decision.provider
        container, adapter_manager, _ = _make_container()
        await DecisionModelStep(container).process(_ctx(runtime_provider="typesafe"))
        assert adapter_manager.get_decision_service.await_args.args[0] == "typesafe"

        container, adapter_manager, _ = _make_container()
        await DecisionModelStep(container).process(_ctx())
        assert adapter_manager.get_decision_service.await_args.args[0] == "ollama"

        container, adapter_manager, _ = _make_container(_adapter_config(decision_provider=None))
        await DecisionModelStep(container).process(_ctx())
        assert adapter_manager.get_decision_service.await_args.args[0] == "typesafe"

    async def test_model_resolution_order(self):
        container, _, service = _make_container()
        await DecisionModelStep(container).process(_ctx(runtime_model_name="tev1"))
        assert service.decide.await_args.kwargs["model"] == "tev1"

        container, _, service = _make_container(_adapter_config(model=None))
        await DecisionModelStep(container).process(_ctx())
        assert service.decide.await_args.kwargs["model"] is None  # provider default

    async def test_resolved_model_reported_from_provider(self):
        service = MagicMock(model="jev-latest")
        service.decide = AsyncMock(return_value={**RESULT, "model": "jev-1.13.0"})
        container, _, _ = _make_container(_adapter_config(model="jev-latest"), service=service)

        ctx = await DecisionModelStep(container).process(_ctx())

        assert ctx.runtime_model_name == "jev-1.13.0"

    async def test_provider_error_is_surfaced_with_detail(self):
        service = MagicMock(model="nimble")
        service.decide = AsyncMock(side_effect=ValueError("Ollama decision error (HTTP 404): model 'nimble' not found"))
        container, _, _ = _make_container(service=service)

        ctx = await DecisionModelStep(container).process(_ctx())

        assert ctx.has_error()
        assert "model 'nimble' not found" in ctx.error
        assert ctx.decision is None

    async def test_unavailable_provider_is_surfaced(self):
        container, adapter_manager, _ = _make_container()
        adapter_manager.get_decision_service.side_effect = RuntimeError("Decision service initialization returned False")

        ctx = await DecisionModelStep(container).process(_ctx())

        assert ctx.has_error()
        assert "Decision provider 'ollama' is unavailable" in ctx.error


class TestValidateQuestions:
    @pytest.mark.parametrize("questions, expected", [
        ({}, "non-empty mapping"),
        ([], "non-empty mapping"),
        ({"": {"type": "noul", "instructions": "x"}}, "names must be non-empty"),
        ({"q": "not an object"}, "must be an object"),
        ({"q": {"type": "rank", "instructions": "x"}}, "invalid type"),
        ({"q": {"type": "noul"}}, "requires non-empty 'instructions'"),
        ({"q": {"type": "noul", "instructions": "  "}}, "requires non-empty 'instructions'"),
        ({"q": {"type": "choice", "instructions": "x"}}, "non-empty 'criteria' mapping"),
        ({"q": {"type": "choice", "instructions": "x", "criteria": {}}}, "non-empty 'criteria' mapping"),
        ({"q": {"type": "choice", "instructions": "x", "criteria": ["a", "b"]}}, "non-empty 'criteria' mapping"),
        ({"q": {"type": "score", "instructions": "x", "criteria": ["only"]}}, "at least 2 ordered levels"),
        ({"q": {"type": "score", "instructions": "x", "criteria": {"a": "b"}}}, "at least 2 ordered levels"),
    ])
    def test_invalid(self, questions, expected):
        assert expected in validate_questions(questions)

    def test_valid_including_optional_noul_criteria(self):
        questions = {
            **QUESTIONS,
            "urgency": {"type": "score", "instructions": "How urgent?", "criteria": ["Low", "High"]},
            "flag": {"type": "noul", "instructions": "Flag?", "criteria": {"yes": "flag it", "no": "fine"}},
        }
        assert validate_questions(questions) is None
