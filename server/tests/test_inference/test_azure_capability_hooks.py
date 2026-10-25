"""
Tests for AzureBaseService's lifted token-parameter/temperature capability
hooks (_get_token_parameter_name, _resolve_token_value, _supports_temperature).

These moved from azure_vision_service.py onto AzureBaseService (see
docs/roadmap/temperature-token-parameter-capability-hooks.md). Per that plan,
azure_openai_inference_service.py deliberately does NOT adopt these hooks yet
(its generate/generate_stream still hardcode max_completion_tokens/temperature) —
that remains a separate, explicitly scoped decision.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest

from ai_services.implementations.vision.azure_vision_service import AzureVisionService


def _make_vision_service(deployment: str, **extra_config) -> AzureVisionService:
    config = {
        "vision": {
            "azure": {
                "endpoint": "https://example.openai.azure.com",
                "api_key": "test-key",
                "deployment_name": deployment,
                **extra_config,
            }
        }
    }
    return AzureVisionService(config)


@pytest.mark.parametrize("deployment", ["gpt-5", "gpt-4o", "gpt-4.1-deployment", "o1-preview"])
def test_modern_deployment_names_use_max_completion_tokens(deployment):
    service = _make_vision_service(deployment)
    assert service._get_token_parameter_name() == "max_completion_tokens"


@pytest.mark.parametrize("deployment", ["mistral-ocr-4-0", "my-custom-deployment", "gpt-35-turbo"])
def test_legacy_or_unrecognized_deployment_names_use_max_tokens(deployment):
    service = _make_vision_service(deployment)
    assert service._get_token_parameter_name() == "max_tokens"


def test_token_parameter_config_override_wins():
    service = _make_vision_service("gpt-5", token_parameter_name="max_tokens")
    assert service._get_token_parameter_name() == "max_tokens"


@pytest.mark.parametrize("deployment", ["gpt-5", "o1-preview", "o3-mini"])
def test_reasoning_style_deployment_names_reject_custom_temperature(deployment):
    service = _make_vision_service(deployment)
    assert service._supports_temperature() is False


@pytest.mark.parametrize("deployment", ["gpt-4o", "gpt-35-turbo", "mistral-ocr-4-0"])
def test_non_reasoning_deployment_names_support_temperature(deployment):
    service = _make_vision_service(deployment)
    assert service._supports_temperature() is True


def test_supports_temperature_config_override_wins_over_deployment_name():
    """A Foundry Catalog reasoning-style deployment can be force-enabled via config."""
    service = _make_vision_service("gpt-5-6-luna", supports_temperature=True)
    assert service._supports_temperature() is True

    service = _make_vision_service("gpt-4o", supports_temperature=False)
    assert service._supports_temperature() is False


def test_resolve_token_value_prefers_matching_param():
    service = _make_vision_service("gpt-4o")
    kwargs = {"max_tokens": 100, "max_completion_tokens": 200}
    assert service._resolve_token_value("max_completion_tokens", kwargs) == 200
    assert "max_tokens" not in kwargs
    assert "max_completion_tokens" not in kwargs


def test_resolve_token_value_defaults_to_configured_max_tokens():
    service = _make_vision_service("gpt-4o")
    service.max_tokens = 1500
    assert service._resolve_token_value("max_completion_tokens", {}) == 1500


class _FakeChoice:
    def __init__(self):
        self.message = type("M", (), {"content": "ok"})()


class _FakeResponse:
    def __init__(self):
        self.choices = [_FakeChoice()]
        self.usage = None


class _FakeCompletions:
    def __init__(self):
        self.last_params = None

    async def create(self, **params):
        self.last_params = params
        return _FakeResponse()


class _FakeChat:
    def __init__(self):
        self.completions = _FakeCompletions()


class _FakeClient:
    def __init__(self):
        self.chat = _FakeChat()


@pytest.mark.asyncio
async def test_verify_connection_omits_temperature_for_reasoning_deployment():
    """
    AzureVisionService.verify_connection overrides AzureBaseService's unconditional
    probe specifically so a temperature-restricted deployment doesn't fail its own
    health check (see azure_vision_service.py's verify_connection docstring).
    """
    service = _make_vision_service("gpt-5")
    service.client = _FakeClient()

    result = await service.verify_connection()

    assert result is True
    assert "temperature" not in service.client.chat.completions.last_params
    assert service.client.chat.completions.last_params["max_completion_tokens"] == 16


@pytest.mark.asyncio
async def test_verify_connection_includes_temperature_for_legacy_deployment():
    service = _make_vision_service("mistral-ocr-4-0")
    service.client = _FakeClient()

    result = await service.verify_connection()

    assert result is True
    params = service.client.chat.completions.last_params
    assert params["temperature"] == 0
    assert params["max_tokens"] == 16
