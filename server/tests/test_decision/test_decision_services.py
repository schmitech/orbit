"""
Tests for the decision model services (server/ai_services/implementations/decision/).

Covers:
- OllamaDecisionService: /v1/systemone request shape, model override, restricted retries
  (4xx fail once with detail; 429/5xx and connection errors retry), timeout plumbing, close()
- TypeSafeDecisionService: SDK question conversion, client construction, response
  normalization, error mapping, model override, aclose(), ms -> seconds timeout
- Config lookup under decision_models.<provider>
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

SERVER_DIR = Path(__file__).parent.parent.parent.absolute()
sys.path.insert(0, str(SERVER_DIR))

from ai_services.implementations.decision.ollama_decision_service import (  # noqa: E402
    DecisionRetryableError,
    OllamaDecisionService,
)

QUESTIONS = {
    "team": {
        "type": "choice",
        "instructions": "Which team should handle this ticket?",
        "criteria": {"billing": "Payments and refunds", "technical": "Bugs"},
    },
    "refund": {"type": "noul", "instructions": "Does the customer ask for a refund?"},
    "urgency": {"type": "score", "instructions": "How urgent?", "criteria": ["Routine", "Soon", "Urgent"]},
}

ANSWERS = {
    "team": {"type": "choice", "choice": "billing", "probabilities": {"billing": 0.98, "technical": 0.02},
             "confidence": 0.92},
    "refund": {"type": "noul", "noul": 0.997},
}


def _config(provider="ollama", **overrides):
    provider_config = {
        "enabled": True,
        "model": "nimble" if provider == "ollama" else "jev-latest",
        "timeout": {"connect": 1000, "total": 12000},
        "retry": {"enabled": True, "max_retries": 2, "initial_wait_ms": 1, "max_wait_ms": 1,
                  "exponential_base": 2},
    }
    provider_config.update(overrides)
    return {"decision": {"provider": provider, "enabled": True}, "decision_models": {provider: provider_config}}


class _FakeResponse:
    def __init__(self, status, json_data=None, text=""):
        self.status = status
        self._json = json_data
        self._text = text

    async def json(self):
        return self._json

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    """Returns the queued responses (or raises queued exceptions) in order."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def post(self, url, json=None):
        self.calls.append((url, json))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _ollama_service(session, **overrides):
    service = OllamaDecisionService(_config("ollama", **overrides))
    service.connection_manager.get_session = AsyncMock(return_value=session)
    return service


class TestOllamaDecisionService:
    def test_reads_decision_models_config(self):
        service = OllamaDecisionService(_config("ollama", base_url="http://gpu-box:11434/", model="tev1"))
        assert service.base_url == "http://gpu-box:11434"
        assert service.model == "tev1"
        assert service.connection_manager.base_url == "http://gpu-box:11434"

    def test_timeout_total_ms_reaches_connection_manager(self):
        service = OllamaDecisionService(_config("ollama"))
        assert service.connection_manager.timeout_ms == 12000

    async def test_posts_relative_systemone_path_with_payload(self):
        session = _FakeSession(_FakeResponse(200, {"model": "nimble", "answers": ANSWERS,
                                                   "usage": {"input_tokens": 841, "output_tokens": 4}}))
        service = _ollama_service(session)

        result = await service.decide({"ticket": "charged twice"}, QUESTIONS)

        url, payload = session.calls[0]
        assert url == "/v1/systemone"
        assert payload == {"model": "nimble", "state": {"ticket": "charged twice"}, "questions": QUESTIONS}
        assert result == {"model": "nimble", "answers": ANSWERS, "usage": {"input_tokens": 841, "output_tokens": 4}}

    async def test_per_call_model_override(self):
        session = _FakeSession(_FakeResponse(200, {"model": "tev1:0.8b", "answers": ANSWERS}))
        service = _ollama_service(session)

        result = await service.decide({"q": "x"}, QUESTIONS, model="tev1:0.8b")

        assert session.calls[0][1]["model"] == "tev1:0.8b"
        assert result["model"] == "tev1:0.8b"
        assert result["usage"] == {}

    async def test_client_error_fails_once_with_provider_detail(self):
        session = _FakeSession(_FakeResponse(422, text='{"error":"criteria must not be empty"}'))
        service = _ollama_service(session)

        with pytest.raises(ValueError, match="HTTP 422.*criteria must not be empty"):
            await service.decide({"q": "x"}, QUESTIONS)
        assert len(session.calls) == 1

    async def test_server_error_is_retried(self):
        session = _FakeSession(
            _FakeResponse(503, text="loading model"),
            _FakeResponse(200, {"model": "nimble", "answers": ANSWERS}),
        )
        service = _ollama_service(session)

        result = await service.decide({"q": "x"}, QUESTIONS)

        assert result["answers"] == ANSWERS
        assert len(session.calls) == 2

    async def test_connection_error_is_retried(self):
        session = _FakeSession(
            aiohttp.ClientConnectionError("refused"),
            _FakeResponse(200, {"model": "nimble", "answers": ANSWERS}),
        )
        service = _ollama_service(session)

        result = await service.decide({"q": "x"}, QUESTIONS)

        assert result["answers"] == ANSWERS
        assert len(session.calls) == 2

    async def test_exhausted_retries_keep_status_and_body(self):
        session = _FakeSession(*[_FakeResponse(503, text="model is loading") for _ in range(3)])
        service = _ollama_service(session)

        with pytest.raises(DecisionRetryableError) as exc_info:
            await service.decide({"q": "x"}, QUESTIONS)

        assert exc_info.value.status == 503
        assert exc_info.value.body == "model is loading"
        assert str(exc_info.value) == "HTTP 503: model is loading"
        assert len(session.calls) == 3

    async def test_missing_answers_raises(self):
        session = _FakeSession(_FakeResponse(200, {"model": "nimble"}))
        service = _ollama_service(session)

        with pytest.raises(ValueError, match="did not include answers"):
            await service.decide({"q": "x"}, QUESTIONS)

    async def test_close_closes_connection_manager(self):
        service = OllamaDecisionService(_config("ollama"))
        service.connection_manager.close = AsyncMock()

        await service.close()

        service.connection_manager.close.assert_awaited_once()


typesafe_sdk = pytest.importorskip("typesafe_sdk")


class TestTypeSafeDecisionService:
    @pytest.fixture
    def module(self):
        from ai_services.implementations.decision import typesafe_decision_service
        return typesafe_decision_service

    @pytest.fixture
    def fake_client(self, module, monkeypatch):
        client = MagicMock()
        client.system_one = AsyncMock(return_value=typesafe_sdk.SystemOneResponse.model_validate({
            "model": "jev-1.13.0",
            "usage": {"input_tokens": 120, "output_tokens": 3},
            "answers": ANSWERS,
        }))
        client.aclose = AsyncMock()
        client_cls = MagicMock(return_value=client)
        monkeypatch.setattr(module, "AsyncTypeSafeClient", client_cls)
        return client_cls, client

    def _service(self, module, monkeypatch, **overrides):
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        cfg = _config("typesafe", api_key="ts-test-key", base_url="https://api.typesafe.test", **overrides)
        return module.TypeSafeDecisionService(cfg)

    def test_question_conversion_to_sdk_objects(self, module):
        converted = module.to_sdk_questions(QUESTIONS)

        assert isinstance(converted["team"], typesafe_sdk.Choice)
        assert converted["team"].criteria == QUESTIONS["team"]["criteria"]
        assert isinstance(converted["refund"], typesafe_sdk.Noul)
        assert isinstance(converted["urgency"], typesafe_sdk.Score)
        assert list(converted["urgency"].criteria) == ["Routine", "Soon", "Urgent"]

    async def test_client_constructed_from_config_with_seconds_timeout(self, module, monkeypatch, fake_client):
        client_cls, _ = fake_client
        service = self._service(module, monkeypatch)

        assert await service.initialize() is True

        client_cls.assert_called_once_with(
            api_key="ts-test-key", base_url="https://api.typesafe.test", model="jev-latest", timeout=12.0,
        )

    async def test_initialize_fails_without_api_key(self, module, monkeypatch, fake_client):
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        service = module.TypeSafeDecisionService(_config("typesafe"))

        with pytest.raises(ValueError, match="TYPESAFE_API_KEY"):
            await service.initialize()

    async def test_decide_normalizes_response_and_applies_model_override(self, module, monkeypatch, fake_client):
        _, client = fake_client
        service = self._service(module, monkeypatch)

        result = await service.decide({"content": "hello"}, QUESTIONS, model="jev-1.13.0")

        kwargs = client.system_one.await_args.kwargs
        assert kwargs["state"] == {"content": "hello"}
        assert kwargs["model"] == "jev-1.13.0"
        assert isinstance(kwargs["questions"]["team"], typesafe_sdk.Choice)
        assert result["model"] == "jev-1.13.0"
        assert result["usage"] == {"input_tokens": 120, "output_tokens": 3}
        assert result["answers"]["team"]["choice"] == "billing"
        assert result["answers"]["refund"]["noul"] == 0.997

    async def test_sdk_errors_become_value_error_with_detail(self, module, monkeypatch, fake_client):
        _, client = fake_client
        client.system_one.side_effect = typesafe_sdk.TypeSafeError("400 questions.team.criteria is required")
        service = self._service(module, monkeypatch)

        with pytest.raises(ValueError, match="criteria is required"):
            await service.decide({"content": "x"}, QUESTIONS)

    async def test_close_awaits_aclose(self, module, monkeypatch, fake_client):
        _, client = fake_client
        service = self._service(module, monkeypatch)
        await service.initialize()

        await service.close()

        client.aclose.assert_awaited_once()
        assert service.client is None
