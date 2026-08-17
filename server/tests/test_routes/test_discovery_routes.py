"""
Tests for GET /admin/adapters/{adapter_name}/models, especially the ?skill=
param: a skill with no LLM/media-provider of its own (e.g. Fetch) must report
the CALLING adapter's own model list, not a sanitized single-default-model
name for the skill's own (LLM-less) adapter — matching how build_context()
resolves the model override for such skills at request time.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.discovery_routes import discovery_router


class FakeAdapterManager:
    def __init__(self, configs, skill_map):
        self._configs = configs
        self._skill_map = skill_map

    def get_adapter_config(self, name):
        return self._configs.get(name)

    def get_skill_adapter(self, skill):
        return self._skill_map.get(skill)


def _make_app(adapter_manager, config=None):
    app = FastAPI()
    app.include_router(discovery_router)
    app.state.adapter_manager = adapter_manager
    app.state.config = config or {}
    return TestClient(app)


CALLER_CFG = {
    'type': 'multimodal',
    'inference_provider': 'ollama_cloud',
    'model': 'gpt-oss:120b',
    'capabilities': {'available_skills': ['Fetch', 'Image']},
    'allowed_models': [
        {'name': 'gpt-oss:120b', 'provider': 'ollama_cloud', 'model': 'gpt-oss:120b-cloud'},
        {'name': 'claude', 'provider': 'anthropic', 'model': 'claude-sonnet-4-5'},
    ],
}

FETCH_CFG = {
    'type': 'fetch',
    # No inference_provider/model — Fetch has no LLM of its own.
    'capabilities': {'available_skills': []},
}

IMAGE_CFG = {
    'type': 'image_generation',
    'image_provider': 'gemini',
    'allowed_image_models': [
        {'name': 'imagen', 'provider': 'gemini', 'model': 'imagen-4'},
    ],
    'capabilities': {'available_skills': []},
}


class TestSkillParamNoOwnLLM:
    def test_fetch_skill_reports_callers_allowed_models(self):
        """Fetch has no model of its own — must fall back to the caller's
        allowed_models, not a sanitized single-default-model name."""
        manager = FakeAdapterManager(
            {'simple-chat-with-files': CALLER_CFG, 'fetch': FETCH_CFG},
            {'Fetch': 'fetch'},
        )
        client = _make_app(manager)

        resp = client.get(
            "/admin/adapters/simple-chat-with-files/models",
            params={"skill": "Fetch"},
            headers={"X-API-Key": "irrelevant"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["has_restrictions"] is True
        names = [m["name"] for m in body["models"]]
        assert names == ["gpt-oss:120b", "claude"]
        # The critical regression check: no sanitized/mangled name variant present.
        assert "gpt-oss-120b" not in names


class TestSkillParamOwnLLMOrMedia:
    def test_image_skill_reports_its_own_allowed_image_models(self):
        """A skill with its own media provider (image_generation) reports ITS
        own list, not the caller's."""
        manager = FakeAdapterManager(
            {'simple-chat-with-files': CALLER_CFG, 'image-generator': IMAGE_CFG},
            {'Image': 'image-generator'},
        )
        client = _make_app(manager)

        resp = client.get(
            "/admin/adapters/simple-chat-with-files/models",
            params={"skill": "Image"},
            headers={"X-API-Key": "irrelevant"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["adapter_name"] == "image-generator"
        assert [m["name"] for m in body["models"]] == ["imagen"]

    def test_unknown_skill_returns_404(self):
        manager = FakeAdapterManager({'simple-chat-with-files': CALLER_CFG}, {})
        client = _make_app(manager)

        resp = client.get(
            "/admin/adapters/simple-chat-with-files/models",
            params={"skill": "NotARealSkill"},
            headers={"X-API-Key": "irrelevant"},
        )

        assert resp.status_code == 404
