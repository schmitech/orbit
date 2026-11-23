"""Anthropic services must default to models Anthropic still serves.

claude-3-haiku-20240307 was retired on 2026-04-20 and claude-sonnet-4-20250514 on
2026-06-15: https://platform.claude.com/docs/en/about-claude/model-deprecations
"""

import pytest

from ai_services.implementations.inference.anthropic_inference_service import AnthropicInferenceService
from ai_services.implementations.moderation.anthropic_moderation_service import AnthropicModerationService

RETIRED = {"claude-3-haiku-20240307", "claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022"}


@pytest.fixture(autouse=True)
def anthropic_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


def test_inference_default_model_is_served():
    service = AnthropicInferenceService({"inference": {"anthropic": {}}})
    assert service.model not in RETIRED


def test_moderation_default_model_is_served():
    service = AnthropicModerationService({"moderations": {"anthropic": {}}})
    assert service.model not in RETIRED


def test_configured_moderation_model_is_kept():
    service = AnthropicModerationService({"moderations": {"anthropic": {"model": "claude-opus-5-5"}}})
    assert service.model == "claude-opus-5-5"
