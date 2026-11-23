"""
Tests for the Laya decision service (server/ai_services/implementations/decision/laya_decision_service.py).

`laya` is an optional (profile: torch) dependency, so this whole module is skipped when it isn't
installed - kept in its own file (rather than test_decision_services.py) so that skip doesn't also
take down the always-available ollama/typesafe/openai service tests.

Covers:
- Config lookup under decision_models.laya (model, device)
- initialize() stays cheap (no checkpoint load) so adapter preload at startup doesn't block on it
- The checkpoint loads lazily, exactly once, on the first decide()/verify_connection() call
- Concurrent callers join the same in-flight load instead of starting a second one, and a
  cancelled caller doesn't kill the load for whoever awaits it next
- decide() runs agent.predict() and normalizes the result; per-call model override is ignored
  with a warning (Laya loads one fixed checkpoint per process)
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SERVER_DIR = Path(__file__).parent.parent.parent.absolute()
sys.path.insert(0, str(SERVER_DIR))

laya = pytest.importorskip("laya")

from ai_services.implementations.decision.laya_decision_service import LayaDecisionService  # noqa: E402

QUESTIONS = {
    "team": {
        "type": "choice",
        "instructions": "Which team should handle this ticket?",
        "criteria": {"billing": "Payments and refunds", "technical": "Bugs"},
    },
    "refund": {"type": "noul", "instructions": "Does the customer ask for a refund?"},
}

ANSWERS = {
    "team": {"type": "choice", "choice": "billing", "probabilities": {"billing": 0.98, "technical": 0.02},
             "confidence": 0.92},
    "refund": {"type": "noul", "noul": 0.997},
}


def _config(**overrides):
    provider_config = {"enabled": True, "model": "english"}
    provider_config.update(overrides)
    return {"decision": {"provider": "laya", "enabled": True}, "decision_models": {"laya": provider_config}}


class TestLayaDecisionService:
    def test_reads_decision_models_config(self):
        service = LayaDecisionService(_config(model="typed-decisions", device="cpu"))
        assert service.model == "typed-decisions"
        assert service.device == "cpu"

    async def test_initialize_does_not_load_the_checkpoint(self, monkeypatch):
        # Preloaded at startup for any adapter that sets `decision_provider` - must stay cheap.
        load = MagicMock(return_value=MagicMock())
        monkeypatch.setattr(laya, "load", load)
        service = LayaDecisionService(_config())

        assert await service.initialize() is True

        load.assert_not_called()
        assert service.agent is None
        assert service.initialized is True

    async def test_decide_loads_the_checkpoint_lazily_once(self, monkeypatch):
        fake_agent = MagicMock()
        fake_agent.predict.return_value = {"model": "laya-rl-agent", "answers": ANSWERS, "usage": {}}
        load = MagicMock(return_value=fake_agent)
        monkeypatch.setattr(laya, "load", load)
        service = LayaDecisionService(_config(model="typed-decisions", device="cpu"))
        await service.initialize()
        load.assert_not_called()

        await service.decide({"ticket": "charged twice"}, QUESTIONS)
        await service.decide({"ticket": "another one"}, QUESTIONS)

        load.assert_called_once_with("typed-decisions", device="cpu")
        assert service.agent is fake_agent

    async def test_decide_runs_agent_predict_and_normalizes_result(self, monkeypatch):
        service = LayaDecisionService(_config())
        fake_agent = MagicMock()
        fake_agent.predict.return_value = {
            "model": "laya-rl-agent",
            "answers": ANSWERS,
            "usage": {"input_tokens": 120, "output_tokens": 0},
        }
        monkeypatch.setattr(laya, "load", MagicMock(return_value=fake_agent))

        result = await service.decide({"ticket": "charged twice"}, QUESTIONS)

        fake_agent.predict.assert_called_once_with({"ticket": "charged twice"}, QUESTIONS)
        assert result == {"model": "english", "answers": ANSWERS, "usage": {"input_tokens": 120, "output_tokens": 0}}

    async def test_concurrent_callers_share_one_checkpoint_load(self, monkeypatch):
        fake_agent = MagicMock()
        fake_agent.predict.return_value = {"model": "laya-rl-agent", "answers": ANSWERS, "usage": {}}
        load_started = asyncio.Event()
        release_load = asyncio.Event()

        def _slow_load(model, device=None):
            # Signal from the event loop thread: setting an asyncio.Event directly from this
            # worker thread races with the loop's own wakeup machinery and can hang the waiter.
            loop.call_soon_threadsafe(load_started.set)
            # Block the worker thread until the test releases it, so both callers overlap.
            asyncio.run_coroutine_threadsafe(release_load.wait(), loop).result()
            return fake_agent

        loop = asyncio.get_event_loop()
        monkeypatch.setattr(laya, "load", MagicMock(side_effect=_slow_load))
        service = LayaDecisionService(_config())

        first = asyncio.ensure_future(service.decide({"q": "1"}, QUESTIONS))
        await load_started.wait()
        second = asyncio.ensure_future(service.decide({"q": "2"}, QUESTIONS))
        release_load.set()
        await asyncio.gather(first, second)

        laya.load.assert_called_once()

    async def test_cancelling_one_caller_does_not_abort_the_load_for_the_next(self, monkeypatch):
        fake_agent = MagicMock()
        release_load = asyncio.Event()

        def _slow_load(model, device=None):
            asyncio.run_coroutine_threadsafe(release_load.wait(), loop).result()
            return fake_agent

        loop = asyncio.get_event_loop()
        monkeypatch.setattr(laya, "load", MagicMock(side_effect=_slow_load))
        service = LayaDecisionService(_config())

        first = asyncio.ensure_future(service._ensure_agent())
        await asyncio.sleep(0.01)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first

        second = asyncio.ensure_future(service._ensure_agent())
        await asyncio.sleep(0.01)
        release_load.set()
        agent = await second

        assert agent is fake_agent
        laya.load.assert_called_once()

    async def test_per_call_model_override_is_ignored_with_warning(self, monkeypatch, caplog):
        service = LayaDecisionService(_config())
        fake_agent = MagicMock()
        fake_agent.predict.return_value = {"model": "laya-rl-agent", "answers": ANSWERS, "usage": {}}
        monkeypatch.setattr(laya, "load", MagicMock(return_value=fake_agent))

        result = await service.decide({"q": "x"}, QUESTIONS, model="multilingual")

        assert result["model"] == "english"
        assert "ignoring per-call override" in caplog.text

    async def test_missing_answers_raises(self, monkeypatch):
        service = LayaDecisionService(_config())
        fake_agent = MagicMock()
        fake_agent.predict.return_value = {"model": "laya-rl-agent"}
        monkeypatch.setattr(laya, "load", MagicMock(return_value=fake_agent))

        with pytest.raises(ValueError, match="did not include answers"):
            await service.decide({"q": "x"}, QUESTIONS)

    async def test_verify_connection_loads_when_needed(self, monkeypatch):
        service = LayaDecisionService(_config())
        monkeypatch.setattr(laya, "load", MagicMock(return_value=MagicMock()))

        assert await service.verify_connection() is True
        assert service.agent is not None

    async def test_verify_connection_false_on_load_failure(self, monkeypatch):
        service = LayaDecisionService(_config())
        monkeypatch.setattr(laya, "load", MagicMock(side_effect=RuntimeError("no GPU")))

        assert await service.verify_connection() is False

    async def test_close_clears_agent_and_in_flight_load(self):
        service = LayaDecisionService(_config())
        service.agent = MagicMock()
        service.initialized = True

        await service.close()

        assert service.agent is None
        assert service._load_future is None
        assert service.initialized is False
