"""
Unit tests for the Presidio (PII) moderation service.

Tests cover:
- Configuration parsing (base URL normalization, env override, defaults)
- Analyzer-response -> ModerationResult mapping
- moderate_content / moderate_batch against a fake HTTP session
- Error propagation (the service raises rather than failing open, so
  ModeratorService applies the configured allow_on_timeout policy)

No network access: the aiohttp session is replaced with a fake throughout.
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ai_services.implementations.moderation.presidio_moderation_service import (  # noqa: E402
    DEFAULT_ENTITIES,
    PresidioModerationService,
)


def _config(**presidio):
    return {"moderations": {"presidio": presidio}}


class _FakeResponse:
    """Minimal aiohttp response supporting `async with`."""

    def __init__(self, status=200, payload=None, text="", json_exc=None):
        self.status = status
        self._payload = payload
        self._text = text
        self._json_exc = json_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def json(self):
        if self._json_exc:
            raise self._json_exc
        return self._payload

    async def text(self):
        return self._text


def _service(response=None, **presidio):
    """Build a service whose HTTP session returns `response` for every call."""
    service = PresidioModerationService(_config(**presidio))
    service.initialized = True

    session = MagicMock()
    session.post = MagicMock(return_value=response)
    session.get = MagicMock(return_value=response)
    service.connection_manager.get_session = AsyncMock(return_value=session)
    service._session = session
    return service


def _entity(entity_type, score, start=0, end=1):
    return {"entity_type": entity_type, "start": start, "end": end, "score": score}


# =============================================================================
# Configuration
# =============================================================================

class TestConfiguration:
    def test_defaults(self):
        service = PresidioModerationService(_config())
        assert service.base_url == "http://localhost:5002"
        assert service.language == "en"
        assert service.score_threshold == 0.5
        assert service.entities == DEFAULT_ENTITIES
        assert service.model == "presidio-analyzer"

    def test_overrides(self):
        service = PresidioModerationService(_config(
            base_url="http://presidio:3000",
            language="es",
            score_threshold=0.8,
            entities=["person", "us_ssn"],
        ))
        assert service.base_url == "http://presidio:3000"
        assert service.language == "es"
        assert service.score_threshold == 0.8
        # Entities are normalized to Presidio's upper-case naming
        assert service.entities == ["PERSON", "US_SSN"]

    def test_api_base_key_is_accepted(self):
        service = PresidioModerationService(_config(api_base="http://elsewhere:5002"))
        assert service.base_url == "http://elsewhere:5002"

    @pytest.mark.parametrize("configured", [
        "http://presidio:5002",
        "http://presidio:5002/",
    ])
    def test_trailing_slash_produces_the_same_url(self, configured):
        service = PresidioModerationService(_config(base_url=configured))
        assert service._url("/analyze") == "http://presidio:5002/analyze"

    def test_path_prefix_is_preserved(self):
        service = PresidioModerationService(_config(base_url="http://gw/presidio/"))
        assert service._url("/analyze") == "http://gw/presidio/analyze"
        # The session is anchored at the origin, since aiohttp rejects a
        # base_url carrying a path
        assert service.connection_manager.base_url == "http://gw"

    @pytest.mark.parametrize("configured", [0, -1])
    def test_batch_size_is_clamped_to_at_least_one(self, configured):
        # A semaphore of 0 would block moderate_batch forever; a negative value
        # would raise on every call.
        service = PresidioModerationService(_config(batch_size=configured))
        assert service.batch_size == 1

    def test_batch_size_override_is_respected(self):
        assert PresidioModerationService(_config(batch_size=4)).batch_size == 4

    def test_env_var_takes_precedence_over_config(self, monkeypatch):
        monkeypatch.setenv("PRESIDIO_ANALYZER_API_BASE", "http://from-env:5002")
        service = PresidioModerationService(_config(base_url="http://from-yaml:5002"))
        assert service.base_url == "http://from-env:5002"


# =============================================================================
# Response mapping
# =============================================================================

class TestResultsToResult:
    def test_no_entities_is_safe(self):
        service = PresidioModerationService(_config())
        result = service._results_to_result([])
        assert result.is_flagged is False
        assert result.categories == {}
        assert result.provider == "presidio"

    def test_entity_above_threshold_flags(self):
        service = PresidioModerationService(_config())
        result = service._results_to_result([_entity("EMAIL_ADDRESS", 1.0)])
        assert result.is_flagged is True
        assert result.categories == {"pii.email_address": 1.0}

    def test_entity_below_threshold_is_scored_but_not_flagged(self):
        service = PresidioModerationService(_config(score_threshold=0.8))
        result = service._results_to_result([_entity("US_SSN", 0.4)])
        assert result.is_flagged is False
        assert result.categories == {"pii.us_ssn": 0.4}

    def test_entity_outside_configured_list_is_scored_but_not_flagged(self):
        service = PresidioModerationService(_config(entities=["US_SSN"]))
        result = service._results_to_result([_entity("DATE_TIME", 0.9)])
        assert result.is_flagged is False
        assert result.categories == {"pii.date_time": 0.9}

    def test_repeated_entity_type_keeps_max_score(self):
        service = PresidioModerationService(_config())
        result = service._results_to_result([
            _entity("PHONE_NUMBER", 0.6),
            _entity("PHONE_NUMBER", 0.95),
            _entity("PHONE_NUMBER", 0.75),
        ])
        assert result.categories == {"pii.phone_number": 0.95}

    def test_entry_without_entity_type_is_ignored(self):
        service = PresidioModerationService(_config())
        result = service._results_to_result([{"start": 0, "end": 4, "score": 0.9}])
        assert result.is_flagged is False
        assert result.categories == {}


# =============================================================================
# moderate_content
# =============================================================================

@pytest.mark.asyncio
class TestModerateContent:
    async def test_flags_pii_and_sends_expected_payload(self):
        service = _service(_FakeResponse(payload=[_entity("EMAIL_ADDRESS", 1.0)]))

        result = await service.moderate_content("mail me at a@b.com")

        assert result.is_flagged is True
        assert result.categories == {"pii.email_address": 1.0}

        url = service._session.post.call_args.args[0]
        payload = service._session.post.call_args.kwargs["json"]
        assert url == "http://localhost:5002/analyze"
        assert payload["text"] == "mail me at a@b.com"
        assert payload["language"] == "en"
        assert payload["score_threshold"] == 0.5
        assert payload["entities"] == DEFAULT_ENTITIES

    async def test_clean_content_passes(self):
        service = _service(_FakeResponse(payload=[]))
        result = await service.moderate_content("what is the capital of France?")
        assert result.is_flagged is False

    async def test_non_200_raises(self):
        service = _service(_FakeResponse(status=500, text="boom"))
        with pytest.raises(RuntimeError, match="HTTP 500"):
            await service.moderate_content("hello")

    async def test_non_list_payload_raises(self):
        service = _service(_FakeResponse(payload={"error": "bad request"}))
        with pytest.raises(RuntimeError, match="Unexpected Presidio analyze response"):
            await service.moderate_content("hello")

    async def test_malformed_json_raises(self):
        service = _service(_FakeResponse(json_exc=ValueError("not json")))
        with pytest.raises(ValueError):
            await service.moderate_content("hello")

    async def test_connection_error_propagates(self):
        service = _service(_FakeResponse(payload=[]))
        service.connection_manager.get_session = AsyncMock(
            side_effect=OSError("connection refused")
        )
        # The service must not swallow this: ModeratorService applies the
        # configured retry / allow_on_timeout policy instead.
        with pytest.raises(OSError):
            await service.moderate_content("hello")


# =============================================================================
# moderate_batch
# =============================================================================

@pytest.mark.asyncio
class TestModerateBatch:
    async def test_empty_batch(self):
        service = _service(_FakeResponse(payload=[]))
        assert await service.moderate_batch([]) == []

    async def test_preserves_input_order(self):
        service = PresidioModerationService(_config())
        service.initialized = True

        responses = {
            "clean": [],
            "email": [_entity("EMAIL_ADDRESS", 0.9)],
            "ssn": [_entity("US_SSN", 0.95)],
        }
        service._analyze = AsyncMock(side_effect=lambda text: responses[text])

        results = await service.moderate_batch(["clean", "email", "ssn"])

        assert [r.is_flagged for r in results] == [False, True, True]
        assert results[1].categories == {"pii.email_address": 0.9}
        assert results[2].categories == {"pii.us_ssn": 0.95}

    async def test_zero_batch_size_still_completes(self):
        # Regression: an unclamped batch_size of 0 made this hang forever.
        service = PresidioModerationService(_config(batch_size=0))
        service.initialized = True
        service._analyze = AsyncMock(return_value=[_entity("EMAIL_ADDRESS", 1.0)])

        results = await asyncio.wait_for(service.moderate_batch(["a@b.co", "c@d.co"]), timeout=5)

        assert [r.is_flagged for r in results] == [True, True]

    async def test_error_in_one_item_propagates(self):
        service = PresidioModerationService(_config())
        service.initialized = True
        service._analyze = AsyncMock(side_effect=RuntimeError("analyzer down"))
        with pytest.raises(RuntimeError, match="analyzer down"):
            await service.moderate_batch(["a", "b"])


# =============================================================================
# Lifecycle
# =============================================================================

@pytest.mark.asyncio
class TestLifecycle:
    async def test_initialize_warns_on_unsupported_entities(self, caplog):
        service = _service(
            _FakeResponse(payload=["EMAIL_ADDRESS", "PHONE_NUMBER"]),
            entities=["EMAIL_ADDRESS", "US_SSN"],
        )
        service.initialized = False

        assert await service.initialize() is True
        assert service.initialized is True
        assert "US_SSN" in caplog.text

    async def test_initialize_tolerates_non_list_supported_entities(self, caplog):
        # A 200 response carrying an error object must not be treated as the
        # entity list (which would report every entity as unsupported).
        service = _service(
            _FakeResponse(payload={"error": "No matching recognizers were found"}),
            entities=["EMAIL_ADDRESS"],
        )
        service.initialized = False

        assert await service.initialize() is True
        assert "Unexpected Presidio /supportedentities response" in caplog.text
        assert "does not support configured entities" not in caplog.text

    async def test_initialize_tolerates_non_200_supported_entities(self, caplog):
        service = _service(_FakeResponse(status=500, text="boom"))
        service.initialized = False

        assert await service.initialize() is True
        assert "returned HTTP 500" in caplog.text

    async def test_initialize_tolerates_unreachable_analyzer(self):
        service = _service(_FakeResponse(payload=[]))
        service.initialized = False
        service.connection_manager.get_session = AsyncMock(side_effect=OSError("down"))
        # Startup must not fail; moderate_content raises later instead
        assert await service.initialize() is True

    async def test_verify_connection(self):
        service = _service(_FakeResponse(status=200))
        assert await service.verify_connection() is True

        service = _service(_FakeResponse(status=503))
        assert await service.verify_connection() is False

    async def test_close_releases_session(self):
        service = _service(_FakeResponse(payload=[]))
        service.connection_manager.close = AsyncMock()
        await service.close()
        service.connection_manager.close.assert_awaited_once()
        assert service.initialized is False
