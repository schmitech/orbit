import asyncio
import sys
import os

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class _FakeModels:
    def __init__(self):
        self.list_calls = 0

    async def list(self):
        self.list_calls += 1
        return []


class _FakeOpenAIClient:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.models = _FakeModels()
        _FakeOpenAIClient.instances.append(self)

    async def close(self):
        pass


class _FakeHTTPClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


@pytest.mark.asyncio
async def test_openai_initialize_rebuilds_missing_client(monkeypatch):
    """A previously closed cached OpenAI provider rebuilds and re-verifies."""
    from ai_services.providers import openai_compatible_base
    from ai_services.implementations.inference.openai_inference_service import (
        OpenAIInferenceService,
    )

    _FakeOpenAIClient.instances = []
    monkeypatch.setattr(openai_compatible_base, "AsyncOpenAI", _FakeOpenAIClient)
    monkeypatch.setattr(openai_compatible_base.httpx, "AsyncClient", _FakeHTTPClient)

    service = OpenAIInferenceService({
        "inference": {
            "openai": {
                "api_key": "test-key",
                "model": "gpt-test",
            }
        }
    })

    original_client = service.client
    service.client = None
    service.initialized = True
    service._verification_attempted = True
    service.connection_verified = True
    service._verification_inflight = False

    assert await service.initialize() is True
    await asyncio.sleep(0)

    assert service.client is not None
    assert service.client is not original_client
    assert len(_FakeOpenAIClient.instances) == 2
    assert service._verification_attempted is True
    assert service.connection_verified is True
    assert service._verification_inflight is False
    assert service.client.models.list_calls == 1
