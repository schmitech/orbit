"""Model registry. No network — only the availability logic.

A provider without a key must be reported as unavailable so the gate skips it
rather than failing: a missing key is a missing prerequisite, not a regression.
"""

from __future__ import annotations

import pytest
from mcpeval.models import available, judge_spec, registry

pytestmark = pytest.mark.unit


def test_registry_covers_every_provider():
    assert {spec.provider for spec in registry()} == {"openai", "anthropic", "azure"}


def test_model_is_unavailable_without_its_key(monkeypatch):
    for spec in registry():
        monkeypatch.delenv(spec.env_key, raising=False)
        if spec.endpoint_key:
            monkeypatch.delenv(spec.endpoint_key, raising=False)
    assert available() == []
    assert judge_spec() is None


def test_azure_needs_both_its_key_and_its_endpoint(monkeypatch):
    """A deployment is bound to an endpoint, so a key alone cannot reach it."""
    azure = next(spec for spec in registry() if spec.provider == "azure")
    monkeypatch.setenv("AZURE_ACCESS_KEY", "test-key")
    monkeypatch.delenv("AZURE_INFERENCE_ENDPOINT", raising=False)
    assert not azure.available()
    assert azure.missing_env() == ["AZURE_INFERENCE_ENDPOINT"]

    monkeypatch.setenv("AZURE_INFERENCE_ENDPOINT", "https://r.services.ai.azure.com/openai/v1")
    assert azure.available()
    assert azure.missing_env() == []


def test_only_the_keyed_provider_is_available(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_ACCESS_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    specs = available()
    assert [spec.provider for spec in specs] == ["anthropic"]


def test_judge_prefers_a_different_provider_than_the_model_under_test(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    anthropic = next(spec for spec in registry() if spec.provider == "anthropic")
    assert judge_spec(anthropic).provider == "openai"


def test_azure_does_not_judge_an_openai_run(monkeypatch):
    """Azure serves OpenAI models, so it is not an independent judge for one."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AZURE_ACCESS_KEY", "test-key")
    monkeypatch.setenv("AZURE_INFERENCE_ENDPOINT", "https://r.services.ai.azure.com/openai/v1")
    openai = next(spec for spec in registry() if spec.provider == "openai")
    # Same family, so the only honest report is a self-judged one — not a
    # different provider masquerading as independence.
    assert judge_spec(openai).family == openai.family


def test_judge_falls_back_to_self_when_only_one_provider_has_a_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_ACCESS_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    anthropic = next(spec for spec in registry() if spec.provider == "anthropic")
    assert judge_spec(anthropic).provider == "anthropic"


def test_reasoning_models_omit_temperature(monkeypatch):
    """gpt-5.x reject an explicit temperature, so the registry must not send one."""
    monkeypatch.setenv("EVAL_OPENAI_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    spec = next(spec for spec in registry() if spec.provider == "openai")
    assert spec.build().temperature is None


def test_azure_targets_the_versionless_foundry_endpoint(monkeypatch):
    """ORBIT drives Foundry through /openai/v1 with the plain OpenAI SDK, and
    routes on the deployment name — so the harness must do the same."""
    monkeypatch.setenv("AZURE_ACCESS_KEY", "test-key")
    monkeypatch.setenv("AZURE_INFERENCE_ENDPOINT", "https://r.services.ai.azure.com/openai/v1")
    monkeypatch.setenv("EVAL_AZURE_DEPLOYMENT", "gpt-5-mini")
    spec = next(spec for spec in registry() if spec.provider == "azure")
    model = spec.build()
    assert model.model_name == "gpt-5-mini"
    assert str(model.openai_api_base) == "https://r.services.ai.azure.com/openai/v1"
    assert model.temperature is None
