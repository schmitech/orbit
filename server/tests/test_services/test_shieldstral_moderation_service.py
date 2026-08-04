"""Unit tests for the Shieldstral OpenAI-compatible moderation service."""

import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ai_services.implementations.moderation.shieldstral_moderation_service import (
    DEFAULT_SHIELDSTRAL_POLICY,
    ShieldstralModerationService,
)


def _config(**shieldstral):
    return {"moderations": {"shieldstral": shieldstral}}


def _completion(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


class TestShieldstralModerationService:
    def test_defaults_to_vllm_and_bundled_policy(self):
        service = ShieldstralModerationService(_config())
        assert service.backend == "vllm"
        assert service.base_url == "http://localhost:8000/v1"
        assert service.model == "mistralai/Shieldstral-1.0-3B"
        assert service.policy == DEFAULT_SHIELDSTRAL_POLICY

    def test_llama_cpp_backend_uses_its_default_endpoint(self):
        service = ShieldstralModerationService(_config(backend="llama_cpp"))
        assert service.base_url == "http://localhost:8080/v1"

    def test_invalid_backend_is_rejected(self):
        with pytest.raises(ValueError, match="vllm.*llama_cpp"):
            ShieldstralModerationService(_config(backend="ollama"))

    def test_inline_policy_overrides_policy_file(self, tmp_path):
        policy_file = tmp_path / "policy.txt"
        policy_file.write_text("file policy", encoding="utf-8")
        service = ShieldstralModerationService(_config(policy="inline policy", policy_path=str(policy_file)))
        assert service.policy == "inline policy"

    def test_loads_policy_from_file_when_no_inline_policy(self, tmp_path):
        policy_file = tmp_path / "policy.txt"
        policy_file.write_text("file policy", encoding="utf-8")
        service = ShieldstralModerationService(_config(policy_path=str(policy_file)))
        assert service.policy == "file policy"

    @pytest.mark.parametrize(
        ("answer", "flagged", "categories"),
        [
            ("Yes", True, {"policy_violation": 1.0}),
            (" no. ", False, {}),
            ("maybe", False, {"ambiguous_response": 0.5}),
        ],
    )
    def test_parse_binary_response(self, answer, flagged, categories):
        assert ShieldstralModerationService._parse_response(answer) == (flagged, categories)

    @pytest.mark.asyncio
    async def test_vllm_request_flags_yes_response(self):
        service = ShieldstralModerationService(_config(backend="vllm", policy="test policy"))
        service.client.chat.completions.create = AsyncMock(return_value=_completion("Yes"))

        result = await service.moderate_content("unsafe request")

        assert result.is_flagged is True
        assert result.categories == {"policy_violation": 1.0}
        request = service.client.chat.completions.create.await_args.kwargs
        assert request["model"] == "mistralai/Shieldstral-1.0-3B"
        assert request["max_tokens"] == 8
        assert request["messages"][0]["role"] == "system"
        assert "test policy" in request["messages"][0]["content"]
        assert request["messages"][1]["content"] == "<content>\nunsafe request\n</content>"
        await service.close()

    @pytest.mark.asyncio
    async def test_llama_cpp_request_allows_no_response(self):
        service = ShieldstralModerationService(_config(backend="llama_cpp", base_url="http://llama.test/v1"))
        service.client.chat.completions.create = AsyncMock(return_value=_completion("No"))

        result = await service.moderate_content("benign request")

        assert result.is_flagged is False
        assert service.base_url == "http://llama.test/v1"
        await service.close()

    @pytest.mark.asyncio
    async def test_api_failure_fails_open(self):
        service = ShieldstralModerationService(_config())
        service.client.chat.completions.create = AsyncMock(side_effect=RuntimeError("offline"))

        result = await service.moderate_content("test")

        assert result.is_flagged is False
        assert result.categories == {"api_error": 0.5}
        assert "offline" in result.error
        await service.close()
