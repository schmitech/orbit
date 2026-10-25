"""
Tests for OpenAIBaseService's lifted token-parameter/temperature capability
hooks (_get_token_parameter_name, _resolve_token_value, _supports_temperature).

These moved from openai_inference_service.py / openai_vision_service.py onto
OpenAIBaseService (see docs/roadmap/temperature-token-parameter-capability-hooks.md).
This test exercises them through both subclasses to confirm the lift didn't
change behavior, plus the "modern"/"legacy" model coverage the plan calls for.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest

from ai_services.implementations.inference.openai_inference_service import OpenAIInferenceService
from ai_services.implementations.vision.openai_vision_service import OpenAIVisionService


def _make_inference_service(model: str, **extra_config) -> OpenAIInferenceService:
    config = {
        "inference": {
            "openai": {
                "api_key": "test-key",
                "model": model,
                **extra_config,
            }
        }
    }
    return OpenAIInferenceService(config)


def _make_vision_service(model: str, **extra_config) -> OpenAIVisionService:
    config = {
        "vision": {
            "openai": {
                "api_key": "test-key",
                "model": model,
                **extra_config,
            }
        }
    }
    return OpenAIVisionService(config)


@pytest.mark.parametrize("service_factory", [_make_inference_service, _make_vision_service])
class TestTokenParameterName:
    @pytest.mark.parametrize("model", ["gpt-5", "gpt-4o", "gpt-4.1", "o1-preview", "o3-mini"])
    def test_modern_models_use_max_completion_tokens(self, service_factory, model):
        service = service_factory(model)
        assert service._get_token_parameter_name() == "max_completion_tokens"

    @pytest.mark.parametrize("model", ["gpt-3.5-turbo", "gpt-4", "text-davinci-003"])
    def test_legacy_models_use_max_tokens(self, service_factory, model):
        service = service_factory(model)
        assert service._get_token_parameter_name() == "max_tokens"

    def test_config_override_wins(self, service_factory):
        service = service_factory("gpt-5", token_parameter_name="max_tokens")
        assert service._get_token_parameter_name() == "max_tokens"


@pytest.mark.parametrize("service_factory", [_make_inference_service, _make_vision_service])
class TestSupportsTemperature:
    @pytest.mark.parametrize("model", ["gpt-5", "gpt-5.1", "o1-preview", "o3-mini"])
    def test_reasoning_models_reject_custom_temperature(self, service_factory, model):
        service = service_factory(model)
        assert service._supports_temperature() is False

    @pytest.mark.parametrize("model", ["gpt-4o", "gpt-4.1", "gpt-3.5-turbo"])
    def test_non_reasoning_models_support_temperature(self, service_factory, model):
        service = service_factory(model)
        assert service._supports_temperature() is True


def test_resolve_token_value_prefers_matching_param():
    service = _make_inference_service("gpt-4o")
    kwargs = {"max_tokens": 100, "max_completion_tokens": 200}
    assert service._resolve_token_value("max_completion_tokens", kwargs) == 200
    assert "max_tokens" not in kwargs
    assert "max_completion_tokens" not in kwargs


def test_resolve_token_value_falls_back_to_any_override():
    service = _make_inference_service("gpt-4o")
    kwargs = {"max_output_tokens": 50}
    assert service._resolve_token_value("max_completion_tokens", kwargs) == 50


def test_resolve_token_value_defaults_to_configured_max_tokens():
    service = _make_inference_service("gpt-4o")
    service.max_tokens = 2000
    assert service._resolve_token_value("max_completion_tokens", {}) == 2000
